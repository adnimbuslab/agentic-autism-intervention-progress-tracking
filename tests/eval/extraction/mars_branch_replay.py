"""Replay the recorded batch through the real MARS candidate stage.

MARS has never been run against live judge models -- no ``JudgeProvider`` is
implemented outside the unit-test stub -- so no MARS *accuracy* exists and none
is computed here. What does exist is the candidate set MARS would receive, and
that determines the shape of every decision it could make.

This module reconstructs each generator response recorded in
``annotation_batch.json`` and passes it through the production
``build_candidates`` / ``classify_branch`` path, unmodified. The output is the
branch distribution:

    no_reviewable_candidate   MARS abstains before any judge is consulted
    single_candidate          generators agreed; MARS short-circuits, no judging
    rerank_required           a genuine ranking decision exists

Two properties make this a statement about MARS and not about the annotation
batch. First, admission here is MARS-029 (SUCCESS/PARTIAL), not the batch's
``judgeable`` policy -- the batch was widened for annotation, and replaying it
under the runtime gate is what the runtime would see. Second, deduplication is
the real fingerprint, so "generators agreed" means agreed after MARS's own
normalization rather than after an ad-hoc string compare.

One caveat is recorded in the output rather than left implicit: the batch stored
five of the eight ``LLM_EXTRACTED_FIELDS``. Replayed candidates therefore carry
``None`` for goal_context, prompt_context and duration_seconds, so two responses
that differed only on an unrecorded field fingerprint as one. Every
``single_candidate`` count is thus an upper bound and every
``rerank_required`` count a lower bound.

Usage:
    uv run python -m tests.eval.extraction.mars_branch_replay
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.backend.ml.extraction.mars.candidates import (
    CandidateBranch,
    build_candidates,
    classify_branch,
)
from src.backend.ml.extraction.mars.safety import eligible_judges
from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Setting,
    StructuredObservation,
)

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
OUT_PATH = RESULTS_DIR / "mars_branch_replay.json"

RECORDED_FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]

# Every model served by the local Ollama instance. Judge eligibility (MARS-027)
# disqualifies only exact identities that generated a candidate, so the panel
# available for a segment depends on which generators contributed to it.
LOCAL_ROSTER = ["llama3.2:latest", "qwen2.5:3b", "qwen2.5:7b", "mistral:latest"]

# Rosters compared in the eligibility analysis. Judge eligibility (MARS-027)
# removes every model that generated one of the segment's candidates, so panel
# size is roster size minus admitted generators -- which makes the *number of
# non-generator models* the quantity that matters, not roster size as such.
CANDIDATE_ROSTERS: dict[str, list[str]] = {
    "current": LOCAL_ROSTER,
    "plus_qwen3_14b": [*LOCAL_ROSTER, "qwen3:14b"],
    "non_generators_only": ["mistral:latest", "qwen3:14b"],
}
UNRECORDED_FIELDS = ["goal_context", "prompt_context", "duration_seconds"]


def to_result(entry: dict[str, Any], model: str, payload: dict[str, Any]) -> ExtractionResult:
    """Rebuild one generator response as the provider originally returned it."""
    fields = payload.get("extracted_fields") or {}
    observation = StructuredObservation(
        child_id=entry["child_id"],
        session_id=entry["session_id"],
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2026, 8, 28),
        setting=Setting.CLINIC,
        confidence=payload.get("confidence"),
        **{f: fields.get(f) for f in RECORDED_FIELDS},
    )
    return ExtractionResult(
        status=ExtractionStatus(payload["status"]),
        observations=[observation],
        provider="replay",
        model=model,
        # The batch did not record the prompt version. Replay is a statement
        # about candidate structure, and no MARS code path reads this field,
        # so a marker is recorded rather than a real version invented.
        prompt_version="replay-unrecorded",
    )


def replay(batch: dict[str, Any]) -> dict[str, Any]:
    models: list[str] = batch["models"]
    branches: Counter[str] = Counter()
    per_child: dict[str, Counter] = defaultdict(Counter)
    distinct_candidates: Counter[int] = Counter()
    admitted_per_segment: Counter[int] = Counter()
    # Which generators survive MARS-029 admission, and which are discarded.
    admitted_by_model: Counter[str] = Counter()
    rebuild_failures: list[dict[str, str]] = []
    multiplicity_of_agreeing: Counter[int] = Counter()
    eligible_panel_size: Counter[int] = Counter()
    rerank_candidate_sets: list[Any] = []

    for entry in batch["candidates"]:
        results = []
        for model in models:
            payload = entry["candidates"][model]
            try:
                results.append(to_result(entry, model, payload))
            except ValidationError as exc:
                # Recorded values came from validated observations, so a failure
                # here is a real schema drift and must not be silently dropped.
                rebuild_failures.append(
                    {"segment_id": entry["segment_id"], "model": model, "error": str(exc)}
                )
            if payload["status"] in ("success", "partial"):
                admitted_by_model[model] += 1

        candidates, _discarded = build_candidates(results, with_rejections=True)
        branch = classify_branch(candidates)

        branches[str(branch)] += 1
        per_child[entry["child_id"]][str(branch)] += 1
        distinct_candidates[len(candidates)] += 1
        admitted_per_segment[
            sum(1 for m in models if entry["candidates"][m]["status"] in ("success", "partial"))
        ] += 1
        if branch is CandidateBranch.SINGLE_CANDIDATE:
            multiplicity_of_agreeing[candidates[0].multiplicity] += 1
        if branch is CandidateBranch.RERANK_REQUIRED:
            eligible_panel_size[len(eligible_judges(LOCAL_ROSTER, candidates))] += 1
            rerank_candidate_sets.append(candidates)

    total = len(batch["candidates"])
    return {
        "source_batch": BATCH_PATH.name,
        "batch_generated_at": batch["generated_at"],
        "n_segments": total,
        "models": models,
        "admission": "MARS-029 (SUCCESS/PARTIAL)",
        "batch_admission": batch["yield"].get("admit"),
        "branches": dict(branches),
        "branch_share": {k: round(v / total, 4) for k, v in branches.items()},
        "distinct_candidates_per_segment": dict(sorted(distinct_candidates.items())),
        "admitted_generators_per_segment": dict(sorted(admitted_per_segment.items())),
        "admitted_by_model": dict(admitted_by_model),
        "single_candidate_multiplicity": dict(sorted(multiplicity_of_agreeing.items())),
        "judge_roster": LOCAL_ROSTER,
        "eligible_judges_on_rerank_segments": dict(sorted(eligible_panel_size.items())),
        "roster_comparison": {
            name: {
                "roster": roster,
                "panel_sizes": dict(sorted(Counter(
                    len(eligible_judges(roster, c)) for c in rerank_candidate_sets
                ).items())),
                "n_rerank_segments": len(rerank_candidate_sets),
                "share_at_least_2": (
                    sum(1 for c in rerank_candidate_sets
                        if len(eligible_judges(roster, c)) >= 2)
                    / len(rerank_candidate_sets)
                    if rerank_candidate_sets else None
                ),
                "share_at_least_3": (
                    sum(1 for c in rerank_candidate_sets
                        if len(eligible_judges(roster, c)) >= 3)
                    / len(rerank_candidate_sets)
                    if rerank_candidate_sets else None
                ),
            }
            for name, roster in CANDIDATE_ROSTERS.items()
        },
        "per_child_branches": {c: dict(v) for c, v in sorted(per_child.items())},
        "rebuild_failures": rebuild_failures,
        "caveat": (
            "Candidates carry only the 5 fields the batch recorded; "
            f"{', '.join(UNRECORDED_FIELDS)} replay as None. single_candidate is "
            "therefore an upper bound and rerank_required a lower bound."
        ),
        "not_measured": (
            "MARS accuracy, coverage and abstention reason codes are absent: no "
            "live JudgeProvider exists, and no adjudicated labels exist. This "
            "file reports only the candidate set MARS would be handed."
        ),
    }


def render(report: dict[str, Any]) -> None:
    total = report["n_segments"]
    print(f"MARS candidate-stage replay over {total} segments")
    print(f"  admission: {report['admission']} "
          f"(batch was built with admit={report['batch_admission']})\n")
    print(f"  {'branch':<26}{'n':>6}{'share':>9}")
    for branch in ("no_reviewable_candidate", "single_candidate", "rerank_required"):
        n = report["branches"].get(branch, 0)
        print(f"  {branch:<26}{n:>6}{n / total:>8.1%}")

    print(f"\n  {'admitted generators':<26}{'segments':>9}")
    for k, v in report["admitted_generators_per_segment"].items():
        print(f"  {k} of {len(report['models'])}{'':<19}{v:>9}")

    print(f"\n  {'generator':<26}{'admitted':>9}{'share':>9}")
    for model, n in report["admitted_by_model"].items():
        print(f"  {model:<26}{n:>9}{n / total:>8.1%}")

    print(f"\n  eligible judges on the {report['branches'].get('rerank_required', 0)} "
          f"rerank segments (roster of {len(report['judge_roster'])})")
    for size, count in report["eligible_judges_on_rerank_segments"].items():  # noqa: E501
        print(f"  {size} eligible{'':<17}{count:>9}")

    if report["rebuild_failures"]:
        print(f"\n  !! {len(report['rebuild_failures'])} responses failed to rebuild")


def render_roster_comparison(report: dict[str, Any]) -> None:
    comparison = report.get("roster_comparison")
    if not comparison:
        return
    n = next(iter(comparison.values()))["n_rerank_segments"]
    print(f"\n  eligible-judge panels by roster, over the {n} rerank segments")
    print(f"    {'roster':<22}{'size':>5}{'panel sizes':>22}{'>=2':>8}{'>=3':>8}")
    for name, entry in comparison.items():
        sizes = ", ".join(f"{k}:{v}" for k, v in entry["panel_sizes"].items())
        print(f"    {name:<22}{len(entry['roster']):>5}{sizes:>22}"
              f"{entry['share_at_least_2']:>7.0%}{entry['share_at_least_3']:>8.0%}")


def main() -> None:
    if not BATCH_PATH.exists():
        raise SystemExit(
            f"{BATCH_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.build_annotation_batch` first."
        )
    report = replay(json.loads(BATCH_PATH.read_text()))
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    render(report)
    render_roster_comparison(report)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
