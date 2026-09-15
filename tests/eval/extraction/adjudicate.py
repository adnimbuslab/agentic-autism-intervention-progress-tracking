"""Resolve two annotators' gold field values into one adjudicated gold standard.

`agreement_report` measures whether the annotators agreed. This decides what
the gold value *is*, which is a different act.

Three states, kept distinct because collapsing them is how a gold standard
quietly acquires values nobody chose:

    agreed        both annotators recorded the same value -- adopted as-is
    adjudicated   they differed and a human resolved it -- adopted with a record
    unresolved    they differed and nobody has resolved it -- NOT in the gold

An unresolved disagreement is excluded rather than broken by a rule (first
annotator wins, alphabetical, etc). Every such rule invents a value, and a gold
standard with invented values produces an accuracy figure that measures the
rule instead of the models.

Gold is model-independent: one value set per segment, against which all three
generators are scored and from which the oracle ceiling is computed. Deriving
each model's per-field judgements is `score_against_gold`'s job, not this one.

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
    FIELDS,
    annotations_path,
    normalize,
    shared_segments,
)
from tests.eval.extraction.annotate_gold import (
    CATEGORICAL_VALUES,
    FREE_TEXT_FIELDS,
    NULL_TOKEN,
)

RESULTS_DIR = Path(__file__).parent / "results"
GOLD_PATH = RESULTS_DIR / "gold_labels.json"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"


def split_by_consensus(
    first: dict[str, Any], second: dict[str, Any], segments: list[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Per segment: the fields both annotators agreed on, and the fields they did not.

    Agreement is on the normalized value, so casing and whitespace do not
    manufacture a disagreement. The value carried forward is the one the first
    annotator wrote, preserving their surface form.
    """
    agreed: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, list[str]] = {}
    for segment_id in segments:
        a = first[segment_id].get("field_values", {})
        b = second[segment_id].get("field_values", {})
        same = {
            field: a[field]
            for field in FIELDS
            if field in a and field in b and normalize(a[field]) == normalize(b[field])
        }
        differing = [f for f in FIELDS if f not in same]
        agreed[segment_id] = same
        if differing:
            conflicts[segment_id] = differing
    return agreed, conflicts


def resolve_interactively(
    segment_id: str,
    fields: list[str],
    first: dict[str, Any],
    second: dict[str, Any],
    names: tuple[str, str],
    chat_text: str | None = None,
) -> dict[str, Any]:
    """Ask a human to settle each disputed field. Skipping leaves it unresolved."""
    a = first[segment_id].get("field_values", {})
    b = second[segment_id].get("field_values", {})
    print("\n" + "=" * 72)
    print(segment_id)
    if chat_text:
        print("-" * 72)
        print(chat_text)
    print("=" * 72)

    resolved: dict[str, Any] = {}
    for field in fields:
        left, right = a.get(field), b.get(field)
        print(f"\n  {field}")
        print(f"    a. {names[0]}: {left!r}")
        print(f"    b. {names[1]}: {right!r}")
        if field in FREE_TEXT_FIELDS:
            hint = f"[a/b, free text, '{NULL_TOKEN}' for none, Enter to leave unresolved]"
        else:
            values = CATEGORICAL_VALUES[field]
            print(f"    or one of: {', '.join(values)}")
            hint = f"[a/b, a value, '{NULL_TOKEN}' for none, Enter to leave unresolved]"
        raw = input(f"    adjudicated value {hint}: ").strip()

        if not raw:
            continue
        if raw.lower() == "a":
            resolved[field] = left
        elif raw.lower() == "b":
            resolved[field] = right
        elif raw == NULL_TOKEN:
            resolved[field] = None
        elif field in FREE_TEXT_FIELDS:
            resolved[field] = raw
        elif raw.lower() in CATEGORICAL_VALUES[field]:
            resolved[field] = raw.lower()
        else:
            print(f"    unrecognized {raw!r} -- left unresolved")
    return resolved


def build_gold(
    agreed: dict[str, dict[str, Any]],
    adjudicated: dict[str, dict[str, Any]],
    annotations: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], Counter]:
    """Assemble the gold mapping, admitting only segments complete on every field."""
    gold: dict[str, dict[str, Any]] = {}
    counts: Counter = Counter()
    for segment_id, fields in agreed.items():
        values = {**fields, **adjudicated.get(segment_id, {})}
        missing = [f for f in FIELDS if f not in values]
        if missing:
            # A partially resolved segment is not a gold record. Admitting one
            # would score every model against a reference that is itself
            # undecided on those fields.
            counts["unresolved"] += 1
            continue
        gold[segment_id] = {
            "field_values": {f: values[f] for f in FIELDS},
            "child_id": annotations[segment_id].get("child_id"),
            "source": "adjudicated" if segment_id in adjudicated else "agreed",
        }
        counts["adjudicated" if segment_id in adjudicated else "agreed"] += 1
    return gold, counts


def load_chat_texts() -> dict[str, str]:
    """Transcripts for the adjudicator to read. Absent batch is not fatal."""
    if not BATCH_PATH.exists():
        return {}
    batch = json.loads(BATCH_PATH.read_text())
    return {e["segment_id"]: e["chat_text"] for e in batch["candidates"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs=2)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Count agreements and conflicts without prompting or writing gold.",
    )
    parser.add_argument(
        "--decisions",
        type=Path,
        default=None,
        help="Adjudications imported from a returned sheet "
             "(import_adjudication_sheet). Skips the interactive prompt; gold "
             "is assembled from these decisions instead.",
    )
    args = parser.parse_args()

    names = tuple(args.annotators)
    loaded = []
    for name in names:
        path = annotations_path(name)
        if not path.exists():
            raise SystemExit(
                f"{path} not found. Both annotators must finish before "
                "adjudication; this script resolves values, it does not "
                "create them."
            )
        loaded.append(json.loads(path.read_text()))
    first, second = loaded

    segments = shared_segments(first, second)
    if not segments:
        raise SystemExit(
            "The two annotators share no segments. Gold requires a "
            "double-annotated overlap."
        )

    agreed, conflicts = split_by_consensus(first, second, segments)
    n_conflicted_fields = sum(len(v) for v in conflicts.values())
    print(f"Double-annotated segments: {len(segments)}")
    print(f"  fully agreed:        {len(segments) - len(conflicts)}")
    print(f"  with any conflict:   {len(conflicts)} ({n_conflicted_fields} fields)")

    if args.report_only:
        for segment_id, fields in sorted(conflicts.items()):
            print(f"  {segment_id}: {', '.join(fields)}")
        return

    if args.decisions is not None:
        if not args.decisions.exists():
            raise SystemExit(f"{args.decisions} not found.")
        payload = json.loads(args.decisions.read_text())
        # Only conflicted fields are adjudicable. A decision on a field the
        # annotators already agreed on would silently overrule both of them.
        adjudicated = {
            segment_id: {
                field: value
                for field, value in fields.items()
                if field in conflicts.get(segment_id, [])
            }
            for segment_id, fields in payload["decisions"].items()
        }
        adjudicated = {k: v for k, v in adjudicated.items() if v}
        ignored = sum(
            len(fields) for fields in payload["decisions"].values()
        ) - sum(len(v) for v in adjudicated.values())
        print(f"\nDecisions loaded from {args.decisions.name}: "
              f"{sum(len(v) for v in adjudicated.values())} applied"
              + (f", {ignored} ignored (field not in conflict)" if ignored else ""))
        gold, counts = build_gold(agreed, adjudicated, first)
        _write_gold(gold, counts, names, segments)
        return

    chat_texts = load_chat_texts()
    adjudicated: dict[str, dict[str, Any]] = {}
    if conflicts:
        print("\nAdjudicating conflicts. Enter to leave one unresolved.")
        try:
            for segment_id, fields in sorted(conflicts.items()):
                resolved = resolve_interactively(
                    segment_id, fields, first, second, names,
                    chat_texts.get(segment_id),
                )
                if resolved:
                    adjudicated[segment_id] = resolved
        except KeyboardInterrupt:
            print("\nStopped -- unresolved segments stay out of the gold standard.")

    gold, counts = build_gold(agreed, adjudicated, first)
    _write_gold(gold, counts, names, segments)


def _write_gold(
    gold: dict[str, Any],
    counts: Counter,
    names: tuple[str, ...],
    segments: list[str],
) -> None:
    """Write gold_labels.json. One path, whether decisions came from a sheet
    or from the interactive prompt."""
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "annotators": list(names),
        "source_batch": BATCH_PATH.name,
        "level": "source_gold",
        "fields": FIELDS,
        "n_segments_double_annotated": len(segments),
        "n_segments_in_gold": len(gold),
        "counts": dict(counts),
        "gold": gold,
        "note": (
            "Gold field values authored from the transcript, model-independent. "
            "Segments unresolved on any field are excluded, not defaulted. "
            "Accuracy computed against this file is conditional on the "
            "adjudicated subset."
        ),
    }
    GOLD_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print(f"\n  agreed        {counts['agreed']}")
    print(f"  adjudicated   {counts['adjudicated']}")
    print(f"  unresolved    {counts['unresolved']} (excluded from gold)")
    print(f"  segments in gold: {len(gold)}")
    print(f"\nWrote {GOLD_PATH}")
    print(
        "\nNext: `uv run python -m tests.eval.extraction.score_against_gold` to "
        "score the generators against it."
    )


if __name__ == "__main__":
    main()
