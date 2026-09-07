"""Turn two annotators' independent judgements into an adjudicated gold standard.

`agreement_report` measures whether the annotators agreed. This decides what
the label *is*, which is a different act and the one `mars_evaluation` consumes.

Three states, kept distinct because collapsing them is how a gold standard
quietly acquires labels nobody made:

    agreed        both annotators gave the same judgement -- adopted as-is
    adjudicated   they differed and a human resolved it -- adopted with a record
    unresolved    they differed and nobody has resolved it -- NOT in the gold

An unresolved disagreement is excluded rather than broken by a rule (first
annotator wins, majority of one, etc). Every such rule invents a label, and a
gold standard with invented labels produces an accuracy figure that measures
the rule instead of the model.

Output matches what `mars_evaluation` expects:

    {"models": [...], "gold": {segment_id: {model: {field: judgement}}}}

Usage:
    uv run python -m tests.eval.extraction.adjudicate annotator_a annotator_b
    uv run python -m tests.eval.extraction.adjudicate annotator_a annotator_b --report-only
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.extraction.agreement_report import (
    MismatchedAnnotationItemsError,
    annotations_path,
    shared_keys,
)

RESULTS_DIR = Path(__file__).parent / "results"
GOLD_PATH = RESULTS_DIR / "gold_labels.json"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]
JUDGMENTS = {
    "c": "correct",
    "i": "incorrect",
    "h": "hallucinated",
    "n": "correctly_null",
    "m": "missing",
}


def split_by_consensus(
    first: dict[str, Any], second: dict[str, Any], keys: list[str]
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    """Per item: the fields both annotators agreed on, and the fields they did not."""
    agreed: dict[str, dict[str, str]] = {}
    conflicts: dict[str, list[str]] = {}
    for key in keys:
        a = first[key].get("field_judgments", {})
        b = second[key].get("field_judgments", {})
        same = {f: a[f] for f in FIELDS if f in a and a.get(f) == b.get(f)}
        differing = [f for f in FIELDS if a.get(f) != b.get(f)]
        agreed[key] = same
        if differing:
            conflicts[key] = differing
    return agreed, conflicts


def resolve_interactively(
    key: str,
    fields: list[str],
    first: dict[str, Any],
    second: dict[str, Any],
    names: tuple[str, str],
) -> dict[str, str]:
    """Ask a human to settle each disputed field. Skipping leaves it unresolved."""
    a = first[key].get("field_judgments", {})
    b = second[key].get("field_judgments", {})
    print("\n" + "=" * 72)
    print(f"{key}")
    resolved: dict[str, str] = {}
    for field in fields:
        print(f"  {field}: {names[0]}={a.get(field)!r}  {names[1]}={b.get(field)!r}")
        options = "/".join(sorted(JUDGMENTS))
        raw = input(f"    adjudicated value [{options}, Enter to leave unresolved]: ")
        choice = raw.strip().lower()
        if choice in JUDGMENTS:
            resolved[field] = JUDGMENTS[choice]
        elif choice:
            print(f"    unrecognized {choice!r} -- left unresolved")
    return resolved


def build_gold(
    agreed: dict[str, dict[str, str]],
    adjudicated: dict[str, dict[str, str]],
    annotations: dict[str, Any],
) -> tuple[dict[str, dict[str, dict[str, str]]], Counter]:
    """Assemble the gold mapping, admitting only items complete on every field."""
    gold: dict[str, dict[str, dict[str, str]]] = {}
    counts: Counter = Counter()
    for key, fields in agreed.items():
        judgments = {**fields, **adjudicated.get(key, {})}
        if len(judgments) < len(FIELDS):
            # A partially resolved item is not a label. `is_fully_correct`
            # treats a missing field as a failure, so admitting one here would
            # score the model down for a judgement no human ever made.
            counts["unresolved"] += 1
            continue
        record = annotations[key]
        segment_id = record.get("segment_id") or key.split("::")[0]
        model = record.get("model") or "unspecified"
        gold.setdefault(segment_id, {})[model] = judgments
        counts["adjudicated" if key in adjudicated else "agreed"] += 1
    return gold, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs=2)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Count agreements and conflicts without prompting or writing gold.",
    )
    args = parser.parse_args()

    names = tuple(args.annotators)
    loaded = []
    for name in names:
        path = annotations_path(name)
        if not path.exists():
            raise SystemExit(
                f"{path} not found. Both annotators must finish before "
                "adjudication; this script resolves judgements, it does not "
                "create them."
            )
        loaded.append(json.loads(path.read_text()))
    first, second = loaded

    try:
        keys = shared_keys(first, second)
    except MismatchedAnnotationItemsError as exc:
        raise SystemExit(f"Refusing to adjudicate: {exc}") from exc

    if not keys:
        raise SystemExit(
            "The two annotators share no items. Gold requires a "
            "double-annotated overlap."
        )

    agreed, conflicts = split_by_consensus(first, second, keys)
    n_conflicted_fields = sum(len(v) for v in conflicts.values())
    print(f"Double-annotated items: {len(keys)}")
    print(f"  fully agreed:        {len(keys) - len(conflicts)}")
    print(f"  with any conflict:   {len(conflicts)} ({n_conflicted_fields} fields)")

    if args.report_only:
        for key, fields in sorted(conflicts.items()):
            print(f"  {key}: {', '.join(fields)}")
        return

    adjudicated: dict[str, dict[str, str]] = {}
    if conflicts:
        print("\nAdjudicating conflicts. Enter to leave one unresolved.")
        try:
            for key, fields in sorted(conflicts.items()):
                resolved = resolve_interactively(key, fields, first, second, names)
                if resolved:
                    adjudicated[key] = resolved
        except KeyboardInterrupt:
            print("\nStopped -- unresolved items stay out of the gold standard.")

    gold, counts = build_gold(agreed, adjudicated, first)
    models = sorted({m for per_model in gold.values() for m in per_model})
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "annotators": list(names),
        "source_batch": BATCH_PATH.name,
        "models": models,
        "n_items_double_annotated": len(keys),
        "n_items_in_gold": sum(counts.values()) - counts["unresolved"],
        "counts": dict(counts),
        "gold": gold,
        "note": (
            "Items unresolved on any field are excluded, not defaulted. Accuracy "
            "computed from this file is conditional on the adjudicated subset."
        ),
    }
    GOLD_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print(f"\n  agreed        {counts['agreed']}")
    print(f"  adjudicated   {counts['adjudicated']}")
    print(f"  unresolved    {counts['unresolved']} (excluded from gold)")
    print(f"  segments in gold: {len(gold)} across models {models}")
    print(f"\nWrote {GOLD_PATH}")


if __name__ == "__main__":
    main()
