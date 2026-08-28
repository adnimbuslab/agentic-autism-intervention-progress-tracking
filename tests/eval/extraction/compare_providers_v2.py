"""Rigorous multi-model extraction comparison (v2) -- addresses the
methodological gaps identified after the v1 pilot (compare_providers.py):

  1. Pinned decoding parameters (temperature=0.0, seed=42) for reproducibility.
  2. Real behavioral segments sampled from the Rollins + Flusberg CHAT
     corpora (via sample_real_segments.py), not hand-written sentences.
  3. Repeated trials per case to estimate test-retest reliability, since v1
     directly observed non-deterministic output shape across repeated calls
     to the same model on identical input.
  4. Per-model repeat-count allocation is asymmetric and DELIBERATE, not an
     oversight: llama3.2:latest gets the largest sample because it is the
     only model producing real extraction variance to characterize;
     deepseek-r1:1.5b and gemma3:1b get a smaller confirmatory sample
     because v1 already established a mechanistic (not statistical)
     explanation for their 0% success rate (API-level tool-support
     rejection for gemma3, prose-instead-of-tool-call for deepseek-r1) --
     more trials would consume significant wall-clock time (deepseek-r1
     averaged ~49s/call in v1) without new information.

Item 4 from the original request ("a real accuracy metric") is NOT
implemented here: it requires expert-annotated ground truth, which per this
project's own phase boundary does not exist yet (CLAUDE.md, handoff §11).
Fabricating labels to compute a number would misrepresent the result.
Instead, this script reports test-retest agreement rate (does the same
model give the same status across repeated identical-input trials) as the
best available reliability proxy that does not require ground truth --
this is NOT an accuracy measure and must not be reported as one.

Not a pytest test -- makes real network calls, run directly:
    uv run python -m tests.eval.extraction.compare_providers_v2
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import APIError, AsyncOpenAI

from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider, _normalize_null_strings
from src.backend.ml.extraction.prompts import (
    EXTRACTION_TOOL_SCHEMA_OPENAI,
    PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt_chat_segment,
)
from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from tests.eval.extraction.sample_real_segments import (
    load_real_segments,
    render_segment_to_chat_text,
    sample_segments,
)

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_API_KEY = "ollama"
SEED = 42

# (model, n_segments, n_repeats) -- see module docstring for the rationale
# behind the asymmetric allocation.
MODEL_PLAN: list[tuple[str, int, int]] = [
    ("llama3.2:latest", 15, 3),
    ("deepseek-r1:1.5b", 6, 2),
    ("gemma3:1b", 6, 2),
]

RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class TrialResult:
    segment_id: str
    repeat_index: int
    status: str
    confidence: float | None
    duration_ms: int


@dataclass
class ModelRun:
    model: str
    n_segments: int
    n_repeats: int
    trials: list[TrialResult] = field(default_factory=list)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in ExtractionStatus}
        for t in self.trials:
            counts[t.status] += 1
        return counts

    @property
    def status_proportions(self) -> dict[str, float]:
        n = len(self.trials)
        if n == 0:
            return {}
        return {k: v / n for k, v in self.status_counts.items()}

    @property
    def mean_duration_ms(self) -> float | None:
        durations = [t.duration_ms for t in self.trials]
        return statistics.mean(durations) if durations else None

    @property
    def stdev_duration_ms(self) -> float | None:
        durations = [t.duration_ms for t in self.trials]
        return statistics.stdev(durations) if len(durations) > 1 else None

    @property
    def repeat_agreement_rate(self) -> float | None:
        """Fraction of segments where ALL repeat trials produced the same
        status. NOT an accuracy metric -- a test-retest reliability proxy
        that requires no ground truth."""
        by_segment: dict[str, list[str]] = {}
        for t in self.trials:
            by_segment.setdefault(t.segment_id, []).append(t.status)
        agreeing = [1 for statuses in by_segment.values() if len(set(statuses)) == 1]
        if not by_segment:
            return None
        return len(agreeing) / len(by_segment)


async def _extract_once(
    client: AsyncOpenAI, model: str, chat_text: str,
) -> tuple[str, float | None, int]:
    """Replicates OllamaExtractionProvider.extract()'s logic with pinned
    decoding params added (temperature=0.0, seed=42), reusing the same
    parsing/normalization helpers so results are directly comparable to the
    production code path."""
    start = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": build_user_prompt_chat_segment(chat_text)},
            ],
            tools=[EXTRACTION_TOOL_SCHEMA_OPENAI],
            tool_choice={"type": "function", "function": {"name": "record_observation"}},
            temperature=0.0,
            seed=SEED,
        )
    except APIError:
        duration_ms = int((time.monotonic() - start) * 1000)
        return ExtractionStatus.FAILED.value, None, duration_ms
    except Exception:
        duration_ms = int((time.monotonic() - start) * 1000)
        return ExtractionStatus.FAILED.value, None, duration_ms

    duration_ms = int((time.monotonic() - start) * 1000)

    tool_input = OllamaExtractionProvider._parse_tool_response(response)
    if tool_input is None:
        return ExtractionStatus.FAILED.value, None, duration_ms

    # _parse_tool_response already applies _normalize_null_strings internally
    from src.backend.ml.extraction.schemas import ExtractionRequest, SourceType
    from src.backend.schemas.observation_schema import ContributorRole, Setting
    from datetime import date

    dummy_request = ExtractionRequest(
        source_type=SourceType.CHAT_SEGMENT,
        text=chat_text,
        child_id="eval_child",
        session_id="eval_session",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2026, 8, 28),
        setting=Setting.CLINIC,
    )
    try:
        obs = OllamaExtractionProvider._build_observation(dummy_request, tool_input)
        status = OllamaExtractionProvider._determine_status(tool_input, obs)
    except Exception:
        return ExtractionStatus.FAILED.value, None, duration_ms

    return status.value, obs.confidence, duration_ms


async def run_model(model: str, n_segments: int, n_repeats: int, segments) -> ModelRun:
    client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
    run = ModelRun(model=model, n_segments=n_segments, n_repeats=n_repeats)
    for seg in segments[:n_segments]:
        chat_text = render_segment_to_chat_text(seg)
        for r in range(n_repeats):
            status, confidence, duration_ms = await _extract_once(client, model, chat_text)
            run.trials.append(
                TrialResult(
                    segment_id=seg.segment_id, repeat_index=r,
                    status=status, confidence=confidence, duration_ms=duration_ms,
                )
            )
            print(f"  [{model}] {seg.segment_id} (repeat {r}): {status} ({duration_ms}ms)")
    return run


def write_json(runs: list[ModelRun], out_path: Path) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "decoding_params": {"temperature": 0.0, "seed": SEED},
        "prompt_version": PROMPT_VERSION,
        "models": [
            {
                "model": r.model,
                "n_segments": r.n_segments,
                "n_repeats": r.n_repeats,
                "n_trials": len(r.trials),
                "status_counts": r.status_counts,
                "status_proportions": r.status_proportions,
                "mean_duration_ms": r.mean_duration_ms,
                "stdev_duration_ms": r.stdev_duration_ms,
                "repeat_agreement_rate": r.repeat_agreement_rate,
                "trials": [asdict(t) for t in r.trials],
            }
            for r in runs
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {out_path}")


def write_chart(runs: list[ModelRun], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    statuses = [s.value for s in ExtractionStatus]
    colors = {"success": "#4caf50", "partial": "#ffb300", "abstained": "#42a5f5", "failed": "#e53935"}
    models = [r.model for r in runs]

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    ax1, ax2, ax3 = axes

    bottoms = [0.0] * len(models)
    for status in statuses:
        values = [r.status_proportions.get(status, 0) * 100 for r in runs]
        ax1.bar(models, values, bottom=bottoms, label=status, color=colors.get(status))
        bottoms = [b + v for b, v in zip(bottoms, values)]
    ax1.set_title("Status distribution (% of trials)")
    ax1.set_ylabel("% of trials")
    ax1.legend()
    ax1.tick_params(axis="x", rotation=20)
    for i, r in enumerate(runs):
        ax1.annotate(f"n={len(r.trials)}", (i, 102), ha="center", fontsize=9)

    means = [r.mean_duration_ms or 0 for r in runs]
    stdevs = [r.stdev_duration_ms or 0 for r in runs]
    ax2.bar(models, means, yerr=stdevs, capsize=6, color="#607d8b")
    ax2.set_title("Latency: mean ± 1 SD across trials")
    ax2.set_ylabel("Duration (ms)")
    ax2.tick_params(axis="x", rotation=20)

    agreement = [(r.repeat_agreement_rate or 0) * 100 for r in runs]
    ax3.bar(models, agreement, color="#8e24aa")
    ax3.set_title(f"Test-retest agreement rate\n(same status across repeats; NOT accuracy)")
    ax3.set_ylabel("% of segments with unanimous status across repeats")
    ax3.set_ylim(0, 105)
    ax3.tick_params(axis="x", rotation=20)

    fig.suptitle(
        "OllamaExtractionProvider -- rigorous comparison (real CHAT segments, "
        "temperature=0, seed=42)", fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


def print_summary(runs: list[ModelRun]) -> None:
    print("\n=== Summary ===")
    for r in runs:
        print(f"\n{r.model} (n_segments={r.n_segments}, n_repeats={r.n_repeats}, n_trials={len(r.trials)})")
        print(f"  status proportions: { {k: round(v, 2) for k, v in r.status_proportions.items()} }")
        if r.mean_duration_ms is not None:
            sd = f"{r.stdev_duration_ms:.0f}" if r.stdev_duration_ms is not None else "n/a"
            print(f"  latency: mean {r.mean_duration_ms:.0f}ms, sd {sd}ms")
        if r.repeat_agreement_rate is not None:
            print(f"  test-retest agreement rate: {r.repeat_agreement_rate * 100:.0f}% (NOT an accuracy metric)")


async def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading real behavioral segments from Rollins + Flusberg corpora...")
    all_segments = load_real_segments()
    sample = sample_segments(all_segments, n=max(n for _, n, _ in MODEL_PLAN), seed=SEED)
    print(f"Sampled {len(sample)} segments (seed={SEED}) from {len(all_segments)} available.\n")

    runs: list[ModelRun] = []
    for model, n_segments, n_repeats in MODEL_PLAN:
        print(f"Running {n_segments} segments x {n_repeats} repeats against {model}...")
        runs.append(await run_model(model, n_segments, n_repeats, sample))

    print_summary(runs)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    write_json(runs, RESULTS_DIR / f"comparison_v2_{timestamp}.json")
    write_chart(runs, RESULTS_DIR / f"comparison_v2_{timestamp}.png")


if __name__ == "__main__":
    asyncio.run(main())
