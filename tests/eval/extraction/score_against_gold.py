"""Score every generator against the single adjudicated gold standard.

Gold holds field *values*; the evaluation stack consumes per-field
*judgements*. This derives the second from the first, which is what lets one
model-independent reference score all three generators and yield an oracle
ceiling over the same segments.

The derivation is total and mechanical -- there is no human step here:

    gold null,  model null            -> correctly_null
    gold null,  model has a value     -> hallucinated   (unsupported by source)
    gold value, model null            -> missing        (supported, not extracted)
    gold value, model value, equal    -> correct
    gold value, model value, differ   -> incorrect

Reading `hallucinated` off a null gold value is the point of asking annotators
to record nulls explicitly. Without them an unsupported extraction is
indistinguishable from one the annotator merely failed to reach, and the
manuscript's unsupported-extraction rate would be unmeasurable.

`behavior` is free text, so equality needs a stated rule; `--behavior-match`
chooses it and the choice is recorded in the output. Exact match on prose
understates agreement badly and would drag whole-record correctness toward
zero for reasons of wording rather than substance, so the default is token
overlap at a stated threshold. `excluded` drops behavior from whole-record
correctness entirely and is the conservative option when reviewers object to
any automatic prose matching.

Usage:
    uv run python -m tests.eval.extraction.score_against_gold
    uv run python -m tests.eval.extraction.score_against_gold --behavior-match excluded
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.extraction.agreement_report import (
    FIELDS,
    normalize,
    token_overlap,
)

RESULTS_DIR = Path(__file__).parent / "results"
GOLD_PATH = RESULTS_DIR / "gold_labels.json"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
OUT_PATH = RESULTS_DIR / "scored_against_gold.json"

BEHAVIOR_FIELD = "behavior"
DEFAULT_OVERLAP_THRESHOLD = 0.5


def values_match(
    field: str,
    gold_value: object,
    model_value: object,
    *,
    behavior_match: str,
    threshold: float,
) -> bool:
    """Whether a model value counts as the gold value for this field."""
    gold_key, model_key = normalize(gold_value), normalize(model_value)
    if field != BEHAVIOR_FIELD or behavior_match == "exact":
        return gold_key == model_key
    return token_overlap(gold_key, model_key) >= threshold


def judge_field(
    field: str,
    gold_value: object,
    model_value: object,
    *,
    behavior_match: str,
    threshold: float,
) -> str:
    """One field's judgement, derived from gold and model values alone."""
    gold_null = gold_value is None
    model_null = model_value is None
    if gold_null and model_null:
        return "correctly_null"
    if gold_null:
        return "hallucinated"
    if model_null:
        return "missing"
    matched = values_match(
        field, gold_value, model_value,
        behavior_match=behavior_match, threshold=threshold,
    )
    return "correct" if matched else "incorrect"


def score(
    gold_payload: dict[str, Any],
    batch: dict[str, Any],
    *,
    behavior_match: str,
    threshold: float,
) -> dict[str, Any]:
    models: list[str] = batch["models"]
    gold = gold_payload["gold"]
    by_segment = {e["segment_id"]: e for e in batch["candidates"]}

    scoring_fields = [
        f for f in FIELDS
        if not (f == BEHAVIOR_FIELD and behavior_match == "excluded")
    ]

    scored: dict[str, dict[str, dict[str, str]]] = {}
    per_field_counts: dict[str, Counter] = {m: Counter() for m in models}
    missing_from_batch: list[str] = []

    for segment_id, record in gold.items():
        entry = by_segment.get(segment_id)
        if entry is None:
            # Gold for a segment the batch does not contain cannot be scored.
            # Recorded rather than dropped: a silent omission here would shrink
            # every denominator without saying so.
            missing_from_batch.append(segment_id)
            continue
        gold_values = record["field_values"]
        per_model: dict[str, dict[str, str]] = {}
        for model in models:
            candidate = entry["candidates"].get(model) or {}
            extracted = candidate.get("extracted_fields") or {}
            judgments = {
                field: judge_field(
                    field, gold_values.get(field), extracted.get(field),
                    behavior_match=behavior_match, threshold=threshold,
                )
                for field in FIELDS
            }
            per_model[model] = judgments
            for field in scoring_fields:
                per_field_counts[model][f"{field}:{judgments[field]}"] += 1
        scored[segment_id] = per_model

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_gold": GOLD_PATH.name,
        "source_batch": BATCH_PATH.name,
        "models": models,
        "fields": FIELDS,
        # Consumed by mars_evaluation: whole-record correctness is judged over
        # exactly these, so an excluded free-text field cannot silently fail
        # every record.
        "scoring_fields": scoring_fields,
        "behavior_match": behavior_match,
        "behavior_overlap_threshold": threshold if behavior_match == "overlap" else None,
        "n_segments_scored": len(scored),
        "n_gold_segments_absent_from_batch": len(missing_from_batch),
        "gold_segments_absent_from_batch": missing_from_batch,
        "per_field_counts": {m: dict(c) for m, c in per_field_counts.items()},
        "gold": scored,
        "note": (
            "Judgements are derived from adjudicated gold values, not authored "
            "by annotators per candidate. Every generator is scored against the "
            "same reference, so the oracle ceiling is computed over a common set."
        ),
    }


def render(report: dict[str, Any]) -> None:
    fields = report["scoring_fields"]
    print(f"Scored {report['n_segments_scored']} segments against gold")
    print(f"  behavior matching: {report['behavior_match']}")
    if report["n_gold_segments_absent_from_batch"]:
        print(
            f"  !! {report['n_gold_segments_absent_from_batch']} gold segments "
            "are not in the batch and were not scored"
        )
    print()
    header = f"  {'generator':<20}" + "".join(f"{f[:9]:>11}" for f in fields)
    print(header)
    for model, counts in report["per_field_counts"].items():
        cells = []
        for field in fields:
            total = sum(v for k, v in counts.items() if k.startswith(f"{field}:"))
            ok = counts.get(f"{field}:correct", 0) + counts.get(f"{field}:correctly_null", 0)
            cells.append(f"{100 * ok / total:>10.1f}%" if total else f"{'n/a':>11}")
        print(f"  {model:<20}" + "".join(cells))
    print("\n  (acceptable = correct + correctly_null, per field)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--behavior-match",
        choices=["overlap", "exact", "excluded"],
        default="overlap",
        help="How a free-text behavior value is compared to gold (default: overlap).",
    )
    parser.add_argument(
        "--overlap-threshold", type=float, default=DEFAULT_OVERLAP_THRESHOLD
    )
    parser.add_argument(
        "--batch",
        type=Path,
        default=None,
        help="Batch to score. Defaults to the frozen annotation batch; pass "
             "annotation_batch_augmented.json to include a generator added "
             "after annotation. Gold is model-independent, so a later "
             "generator is scored against the same reference.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write. Defaults next to the batch that was scored, so "
             "an augmented run does not overwrite the primary result.",
    )
    args = parser.parse_args()

    batch_path = args.batch or BATCH_PATH
    out_path = args.out or (
        OUT_PATH
        if batch_path == BATCH_PATH
        else RESULTS_DIR / "scored_against_gold_augmented.json"
    )

    for path, hint in (
        (GOLD_PATH, "tests.eval.extraction.adjudicate <a> <b>"),
        (batch_path, "tests.eval.extraction.build_annotation_batch"),
    ):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run `uv run python -m {hint}` first.")

    report = score(
        json.loads(GOLD_PATH.read_text()),
        json.loads(batch_path.read_text()),
        behavior_match=args.behavior_match,
        threshold=args.overlap_threshold,
    )
    report["source_batch"] = batch_path.name
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    OUT_PATH_USED = out_path
    render(report)
    print(f"\nWrote {OUT_PATH_USED}")


if __name__ == "__main__":
    main()
