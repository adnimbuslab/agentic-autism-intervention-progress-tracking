"""Run MARS over the annotation batch and record what it decided.

Produces ``results/mars_outcomes.json``, the second input `mars_evaluation`
needs (the first is the adjudicated gold standard). Until this existed MARS
had never been executed against live models at all.

Generators are **replayed, not re-run**. The batch already holds each
generator's recorded response, and those exact responses are what the human
annotators judge. Re-generating here would let MARS select from candidates
nobody labelled, and the accuracy comparison would silently stop being
like-for-like. Judging is live: judges are the part that has never run.

Every calibration value is a required argument, mirroring the provider's own
refusal to default them. The agreement threshold in particular is an open
question -- a default here would settle it invisibly, in the layer least
visible to whoever should be deciding.

**A single-judge run is an ablation, not the system.** With one judge, top-choice
support is 1.0 by construction: there is no second opinion for the agreement
gate to disagree with, so the gate cannot reject anything and its threshold is
inert whatever it is set to. Such a run measures generation plus a one-model
ranking, and no claim about agreement gating can rest on it. The runner records
the panel size in the summary so a reader cannot mistake one for the other;
`--judges` should name about three eligible models before the gate is reported
on.

Usage:
    uv run python -m tests.eval.extraction.run_mars --judges mistral:latest \\
        --agreement-threshold 0.5 --min-eligible-judges 1 --min-valid-responses 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.extraction.mars.confidence import GeneratorConfidencePolicy
from src.backend.ml.extraction.mars.ollama_judge import OllamaRankingJudge
from src.backend.ml.extraction.mars.provider import (
    MarsExtractionProvider,
    MarsGenerator,
    MarsJudge,
)
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    ModelDescriptor,
    ModelRole,
    SourceType,
)
from src.backend.schemas.observation_schema import ContributorRole, Setting
from tests.eval.extraction.mars_branch_replay import to_result

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
OUTCOMES_PATH = RESULTS_DIR / "mars_outcomes.json"

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_API_KEY = "ollama"


class ReplayGenerator:
    """Returns the response this generator already produced for this segment.

    Satisfies the `ExtractionProvider` contract MARS consumes. The result is
    swapped in per segment by the runner rather than fetched from a model, so
    MARS sees byte-identical candidates to the ones under annotation.
    """

    def __init__(self, model: str) -> None:
        self._model = model
        self._next: ExtractionResult | None = None

    def load(self, result: ExtractionResult | None) -> None:
        self._next = result

    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        if self._next is None:
            # A generator with nothing recorded for this segment did not
            # produce a candidate. FAILED is the honest encoding: MARS's
            # admission predicate discards it, exactly as an empty response
            # from a live call would be discarded.
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                observations=[],
                provider="replay",
                model=self._model,
                prompt_version="replay-unrecorded",
            )
        return self._next


def selected_generator_ids(
    result: ExtractionResult, entry: dict[str, Any], models: list[str]
) -> list[str]:
    """Which generators produced the candidate MARS returned.

    Read back through MARS's own fingerprint rather than by re-comparing
    fields, so "the same candidate" means here exactly what it meant inside
    deduplication.
    """
    provenance = result.provenance
    if provenance is None or provenance.selected_internal_id is None:
        return []
    results = [
        to_result(entry, model, entry["candidates"][model])
        for model in models
        if model in entry["candidates"]
    ]
    for candidate in build_candidates(results):
        if candidate.internal_id == provenance.selected_internal_id:
            return list(candidate.generator_ids)
    return []


async def run(
    batch: dict[str, Any],
    judge_models: list[str],
    *,
    agreement_threshold: float,
    min_eligible_judges: int,
    min_valid_responses: int,
    policy: GeneratorConfidencePolicy,
    run_seed: str,
    base_url: str,
    limit: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    models: list[str] = batch["models"]
    replays = {m: ReplayGenerator(m) for m in models}

    provider = MarsExtractionProvider(
        generators=[
            MarsGenerator(
                provider=replays[m],
                descriptor=ModelDescriptor(identifier=m, role=ModelRole.GENERATOR),
            )
            for m in models
        ],
        judges=[
            MarsJudge(
                judge=OllamaRankingJudge(
                    base_url=base_url, api_key=OLLAMA_API_KEY, model=j
                ),
                descriptor=ModelDescriptor(identifier=j, role=ModelRole.JUDGE),
            )
            for j in judge_models
        ],
        agreement_threshold=agreement_threshold,
        generator_confidence_policy=policy,
        min_eligible_judges=min_eligible_judges,
        min_valid_judge_responses=min_valid_responses,
        run_seed=run_seed,
    )

    entries = batch["candidates"][:limit] if limit else batch["candidates"]
    outcomes: dict[str, Any] = {}
    statuses: Counter = Counter()
    reasons: Counter = Counter()

    for index, entry in enumerate(entries, start=1):
        for model in models:
            payload = entry["candidates"].get(model)
            replays[model].load(to_result(entry, model, payload) if payload else None)

        request = ExtractionRequest(
            source_type=SourceType.CHAT_SEGMENT,
            text=entry["chat_text"],
            child_id=entry["child_id"],
            session_id=entry["session_id"],
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2026, 8, 28),
            setting=Setting.CLINIC,
        )
        result = await provider.extract(request)

        provenance = result.provenance
        outcomes[entry["segment_id"]] = {
            "status": result.status.value,
            "reason_code": result.reason_code,
            "child_id": entry["child_id"],
            "selected_generator_ids": selected_generator_ids(result, entry, models),
            "control_confidence": result.control_confidence,
            "control_confidence_state": (
                result.control_confidence_state.value
                if result.control_confidence_state
                else None
            ),
            "candidate_count": provenance.candidate_count if provenance else 0,
            "top_choice_support": provenance.top_choice_support if provenance else None,
            "judges_used": provenance.judge_ids if provenance else [],
            "discarded_judges": provenance.discarded_judges if provenance else [],
        }
        statuses[result.status.value] += 1
        if result.reason_code:
            reasons[result.reason_code] += 1
        print(
            f"  [{index}/{len(entries)}] {entry['segment_id']}: "
            f"{result.status.value}{' / ' + result.reason_code if result.reason_code else ''}"
        )

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_batch": BATCH_PATH.name,
        "generators": models,
        "generator_source": "replayed from annotation_batch.json",
        "judges": judge_models,
        "agreement_threshold": agreement_threshold,
        "min_eligible_judges": min_eligible_judges,
        "min_valid_judge_responses": min_valid_responses,
        "generator_confidence_policy": policy.value,
        "run_seed": run_seed,
        "n_segments": len(entries),
        "n_judges_configured": len(judge_models),
        # Eligibility is per segment (MARS-027), so a configured judge is not
        # always a usable one; this flag reflects the roster, which is what
        # determines whether the agreement gate could ever bind.
        "single_judge_ablation": len(judge_models) < 2,
        "statuses": dict(statuses),
        "abstention_reasons": dict(reasons),
    }
    return outcomes, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judges", nargs="+", required=True)
    parser.add_argument("--agreement-threshold", type=float, required=True)
    parser.add_argument("--min-eligible-judges", type=int, required=True)
    parser.add_argument("--min-valid-responses", type=int, required=True)
    parser.add_argument(
        "--policy",
        choices=[p.value for p in GeneratorConfidencePolicy],
        default=GeneratorConfidencePolicy.MINIMUM.value,
    )
    parser.add_argument("--run-seed", default="mars-eval-1")
    parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    parser.add_argument("--limit", type=int, default=None, help="Smoke-test a prefix.")
    args = parser.parse_args()

    if not BATCH_PATH.exists():
        raise SystemExit(
            f"{BATCH_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.build_annotation_batch` first."
        )
    batch = json.loads(BATCH_PATH.read_text())

    outcomes, summary = asyncio.run(
        run(
            batch,
            args.judges,
            agreement_threshold=args.agreement_threshold,
            min_eligible_judges=args.min_eligible_judges,
            min_valid_responses=args.min_valid_responses,
            policy=GeneratorConfidencePolicy(args.policy),
            run_seed=args.run_seed,
            base_url=args.base_url,
            limit=args.limit,
        )
    )

    OUTCOMES_PATH.write_text(json.dumps(outcomes, indent=2) + "\n")
    (RESULTS_DIR / "mars_run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    if summary["single_judge_ablation"]:
        print(
            "\n  NOTE: single-judge run -- top-choice support is 1.0 by "
            "construction and the agreement gate cannot bind. This is an "
            "ablation; report no gating claim from it."
        )
    print(f"\nSegments: {summary['n_segments']}")
    print(f"  statuses:  {summary['statuses']}")
    print(f"  abstained: {summary['abstention_reasons'] or 'none'}")
    print(f"\nWrote {OUTCOMES_PATH}")


if __name__ == "__main__":
    main()
