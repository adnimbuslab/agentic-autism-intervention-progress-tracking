"""Multi-model extraction comparison harness.

Runs a fixed, deterministic set of observation texts through
OllamaExtractionProvider configured with several different locally-served
models, and compares their real extraction behavior side by side.

This is a development-evaluation tool, not a pytest test: it makes real
network calls to a locally running Ollama instance and is intentionally
excluded from the automated suite. Run it directly:

    uv run python -m tests.eval.extraction.compare_providers

Requires:
    - Ollama running locally (default http://127.0.0.1:11434/v1)
    - The compared models already pulled (`ollama pull <model>`)
    - matplotlib installed (`uv sync --extra dev`)

Output:
    - tests/eval/extraction/results/comparison_<timestamp>.json  (raw results)
    - tests/eval/extraction/results/comparison_<timestamp>.png   (chart)
"""

from __future__ import annotations

import asyncio
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider
from src.backend.ml.extraction.schemas import ExtractionRequest, ExtractionStatus, SourceType
from src.backend.schemas.observation_schema import ContributorRole, Setting

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_API_KEY = "ollama"

# Models to compare -- must already be pulled locally (`ollama list` to check).
MODELS = [
    "llama3.2:latest",
    "deepseek-r1:1.5b",
    "gemma3:1b",
]

RESULTS_DIR = Path(__file__).parent / "results"

# Fixed, deterministic test set covering the extraction status space:
# success, partial (ambiguous), abstained (irrelevant), and a contradiction.
TEST_CASES: list[dict[str, object]] = [
    {
        "id": "clean_success",
        "text": (
            "During snack time, Maya pointed at the cup on the shelf and said "
            "'want cup' without any prompting from the teacher. She then handed "
            "the cup back after drinking, completely independently."
        ),
        "setting": Setting.SCHOOL,
        "contributor_role": ContributorRole.TEACHER,
    },
    {
        "id": "irrelevant_abstention",
        "text": "It was raining a lot today so we stayed inside most of the afternoon.",
        "setting": Setting.HOME,
        "contributor_role": ContributorRole.PARENT,
    },
    {
        "id": "ambiguous_partial",
        "text": "He did something with the blocks and seemed to enjoy it.",
        "setting": Setting.HOME,
        "contributor_role": ContributorRole.PARENT,
    },
    {
        "id": "prompted_verbal",
        "text": (
            "After the therapist asked 'what do you want?', Sam said 'juice' "
            "and pointed at the fridge."
        ),
        "setting": Setting.CLINIC,
        "contributor_role": ContributorRole.INTERVENTIONIST,
    },
    {
        "id": "contradiction",
        "text": (
            "Child requested the toy completely unprompted, though it was after "
            "the teacher gave a full physical prompt to reach for it."
        ),
        "setting": Setting.SCHOOL,
        "contributor_role": ContributorRole.TEACHER,
    },
]


@dataclass
class CaseResult:
    case_id: str
    status: str
    confidence: float | None
    duration_ms: int | None
    used_proper_tool_call: bool | None  # None = FAILED, could not determine
    domain: str | None
    behavior: str | None


@dataclass
class ModelComparison:
    model: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in ExtractionStatus}
        for r in self.results:
            counts[r.status] += 1
        return counts

    @property
    def mean_duration_ms(self) -> float | None:
        durations = [r.duration_ms for r in self.results if r.duration_ms is not None]
        return statistics.mean(durations) if durations else None

    @property
    def proper_tool_call_rate(self) -> float:
        determined = [r for r in self.results if r.used_proper_tool_call is not None]
        if not determined:
            return 0.0
        return sum(1 for r in determined if r.used_proper_tool_call) / len(determined)


def _make_request(case: dict[str, object]) -> ExtractionRequest:
    return ExtractionRequest(
        source_type=SourceType.CONVERSATIONAL,
        text=str(case["text"]),
        child_id="compare_child",
        session_id="compare_session",
        contributor_role=case["contributor_role"],  # type: ignore[arg-type]
        observation_date=date(2026, 8, 28),
        setting=case["setting"],  # type: ignore[arg-type]
    )


def _used_proper_tool_call(raw_llm_response: str | None) -> bool | None:
    """Introspect the stored raw response to determine whether the model
    populated the OpenAI tool_calls field, or fell back to writing the tool
    call as text in message.content (see OllamaExtractionProvider's
    documented fallback for small local models)."""
    if not raw_llm_response:
        return None
    try:
        parsed = json.loads(raw_llm_response)
        message = parsed["choices"][0]["message"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None
    return bool(message.get("tool_calls"))


async def run_model(model: str) -> ModelComparison:
    provider = OllamaExtractionProvider(
        base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY, model=model,
    )
    comparison = ModelComparison(model=model)
    for case in TEST_CASES:
        request = _make_request(case)
        result = await provider.extract(request)
        obs = result.observations[0] if result.observations else None
        comparison.results.append(
            CaseResult(
                case_id=str(case["id"]),
                status=result.status.value,
                confidence=obs.confidence if obs else None,
                duration_ms=result.extraction_duration_ms,
                used_proper_tool_call=_used_proper_tool_call(result.raw_llm_response),
                domain=obs.domain.value if obs and obs.domain else None,
                behavior=obs.behavior if obs else None,
            )
        )
        print(f"  [{model}] {case['id']}: {result.status.value}")
    return comparison


async def run_all() -> list[ModelComparison]:
    comparisons = []
    for model in MODELS:
        print(f"Running {len(TEST_CASES)} cases against {model}...")
        comparisons.append(await run_model(model))
    return comparisons


def write_json(comparisons: list[ModelComparison], out_path: Path) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "models": [
            {
                "model": c.model,
                "status_counts": c.status_counts,
                "mean_duration_ms": c.mean_duration_ms,
                "proper_tool_call_rate": c.proper_tool_call_rate,
                "results": [asdict(r) for r in c.results],
            }
            for c in comparisons
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {out_path}")


def write_chart(comparisons: list[ModelComparison], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")  # headless -- no display available in this environment
    import matplotlib.pyplot as plt

    statuses = [s.value for s in ExtractionStatus]
    colors = {
        "success": "#4caf50",
        "partial": "#ffb300",
        "abstained": "#42a5f5",
        "failed": "#e53935",
    }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # --- Left: stacked bar of status distribution per model ---
    models = [c.model for c in comparisons]
    bottoms = [0.0] * len(models)
    for status in statuses:
        values = [c.status_counts.get(status, 0) for c in comparisons]
        ax1.bar(models, values, bottom=bottoms, label=status, color=colors.get(status))
        bottoms = [b + v for b, v in zip(bottoms, values)]
    ax1.set_title(f"Extraction status per model (n={len(TEST_CASES)} cases each)")
    ax1.set_ylabel("Case count")
    ax1.legend()
    ax1.tick_params(axis="x", rotation=20)

    # --- Right: mean latency + proper-tool-call rate per model ---
    durations = [c.mean_duration_ms or 0 for c in comparisons]
    tool_rates = [c.proper_tool_call_rate * 100 for c in comparisons]

    ax2b = ax2.twinx()
    bar_positions = range(len(models))
    ax2.bar([p - 0.2 for p in bar_positions], durations, width=0.4, color="#607d8b", label="Mean latency (ms)")
    ax2b.bar([p + 0.2 for p in bar_positions], tool_rates, width=0.4, color="#8e24aa", label="Proper tool_calls used (%)")
    ax2.set_xticks(list(bar_positions))
    ax2.set_xticklabels(models, rotation=20)
    ax2.set_ylabel("Mean latency (ms)", color="#607d8b")
    ax2b.set_ylabel("Proper tool_calls used (%)", color="#8e24aa")
    ax2b.set_ylim(0, 100)
    ax2.set_title("Latency and forced-tool-call reliability")

    fig.suptitle("OllamaExtractionProvider -- multi-model comparison", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


def print_summary(comparisons: list[ModelComparison]) -> None:
    print("\n=== Summary ===")
    for c in comparisons:
        print(f"\n{c.model}")
        print(f"  status counts: {c.status_counts}")
        print(f"  mean latency: {c.mean_duration_ms:.0f} ms" if c.mean_duration_ms else "  mean latency: n/a")
        print(f"  proper tool_calls used: {c.proper_tool_call_rate * 100:.0f}%")


async def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    comparisons = await run_all()
    print_summary(comparisons)
    write_json(comparisons, RESULTS_DIR / f"comparison_{timestamp}.json")
    write_chart(comparisons, RESULTS_DIR / f"comparison_{timestamp}.png")


if __name__ == "__main__":
    asyncio.run(main())
