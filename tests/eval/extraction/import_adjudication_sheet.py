"""Import a completed adjudication sheet into a decisions file.

Produces `adjudications.json`, the mapping `adjudicate.py --decisions` consumes
to build the gold standard. It never writes gold itself: assembling gold is one
job in one place, and duplicating it here would let the two paths drift.

Validation is strict and nothing is guessed. `a` and `b` are resolved against
the values recorded in the row rather than re-read from the annotation files,
so a decision always means what the adjudicator saw when they made it. A value
that is not in the field's vocabulary is reported with its row rather than
normalized into the nearest match.

An undecided row is not an error -- adjudication is expected to be done in
sittings -- but it is reported, because a segment left undecided on any field
is excluded from gold entirely and the adjudicator should know how many
segments their unfinished rows are costing.

Usage:
    uv run python -m tests.eval.extraction.import_adjudication_sheet
    uv run python -m tests.eval.extraction.import_adjudication_sheet --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from tests.eval.extraction.annotate_gold import CATEGORICAL_VALUES, FREE_TEXT_FIELDS
from tests.eval.extraction.export_adjudication_sheet import NULL_WORD, SHEET_PATH

RESULTS_DIR = Path(__file__).parent / "results"
DECISIONS_PATH = RESULTS_DIR / "adjudications.json"

NULL_SYNONYMS = frozenset({NULL_WORD, "n/a", "na", "null", "-", "--"})


class DecisionError(Exception):
    """A decision cell that cannot be read."""


def parse_decision(field: str, raw: str, left: str, right: str) -> tuple[str, Any]:
    """Return ``(state, value)`` where state is 'decided' or 'blank'.

    `a` and `b` resolve to the values shown in the row, which is what the
    adjudicator was looking at. Reading them back out of the annotation files
    instead would silently change the meaning of every `a` if those files were
    ever re-imported.
    """
    text = (raw or "").strip()
    if not text:
        return "blank", None

    lowered = text.casefold()
    if lowered == "a":
        return "decided", None if left.casefold() in NULL_SYNONYMS else left
    if lowered == "b":
        return "decided", None if right.casefold() in NULL_SYNONYMS else right
    if lowered in NULL_SYNONYMS:
        return "decided", None
    if field in FREE_TEXT_FIELDS:
        return "decided", text

    normalized = lowered.replace(" ", "_").replace("-", "_")
    if normalized in CATEGORICAL_VALUES[field]:
        return "decided", normalized
    raise DecisionError(
        f"{field}={text!r} is not 'a', 'b', '{NULL_WORD}', or an allowed value. "
        f"Expected one of: {', '.join(CATEGORICAL_VALUES[field])}."
    )


def read_sheet(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    decisions: dict[str, dict[str, Any]] = {}
    notes: dict[str, dict[str, str]] = {}
    blank: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    duplicates: list[str] = []

    for line_no, row in enumerate(rows, start=2):
        segment_id = (row.get("segment_id") or "").strip()
        field = (row.get("field") or "").strip()
        if not segment_id or not field:
            errors.append({"row": str(line_no), "problem": "missing segment_id or field"})
            continue
        if (segment_id, field) in seen:
            duplicates.append(f"{segment_id}/{field}")
            continue
        seen.add((segment_id, field))

        try:
            state, value = parse_decision(
                field,
                row.get("decision", ""),
                (row.get("annotator_a") or "").strip(),
                (row.get("annotator_b") or "").strip(),
            )
        except DecisionError as exc:
            errors.append(
                {"row": str(line_no), "segment_id": segment_id, "problem": str(exc)}
            )
            continue

        if state == "blank":
            blank.append({"row": str(line_no), "segment_id": segment_id, "field": field})
            continue

        decisions.setdefault(segment_id, {})[field] = value
        note = (row.get("notes") or "").strip()
        if note:
            notes.setdefault(segment_id, {})[field] = note

    # A segment is only rescued if every one of its conflicted rows is decided.
    conflicted: dict[str, set[str]] = {}
    for segment_id, field in seen:
        conflicted.setdefault(segment_id, set()).add(field)
    incomplete = sorted(
        segment_id
        for segment_id, fields in conflicted.items()
        if fields - set(decisions.get(segment_id, {}))
    )

    return {
        "decisions": decisions,
        "notes": notes,
        "n_rows": len(rows),
        "n_decided": sum(len(v) for v in decisions.values()),
        "blank": blank,
        "errors": errors,
        "duplicates": duplicates,
        "n_segments_touched": len(conflicted),
        "incomplete_segments": incomplete,
    }


def render(report: dict[str, Any]) -> None:
    print(f"Adjudication sheet: {report['n_rows']} rows")
    print(f"  decided               : {report['n_decided']}")
    print(f"  not yet decided       : {len(report['blank'])}")
    print(f"  cell errors           : {len(report['errors'])}")
    if report["duplicates"]:
        print(f"  duplicate rows        : {len(report['duplicates'])}")
    complete = report["n_segments_touched"] - len(report["incomplete_segments"])
    print(f"  segments fully settled: {complete} of {report['n_segments_touched']}")
    if report["incomplete_segments"]:
        print(
            f"  -> {len(report['incomplete_segments'])} segments still have an "
            "undecided field and would be EXCLUDED from gold"
        )

    for error in report["errors"][:20]:
        location = f"row {error['row']}"
        if "segment_id" in error:
            location += f" ({error['segment_id']})"
        print(f"    ! {location}: {error['problem']}")
    if len(report["errors"]) > 20:
        print(f"    ... and {len(report['errors']) - 20} more")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=SHEET_PATH)
    parser.add_argument("--out", type=Path, default=DECISIONS_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.path.exists():
        raise SystemExit(
            f"{args.path} not found. Export it with "
            "`uv run python -m tests.eval.extraction.export_adjudication_sheet "
            "<annotators>`, or pass --path to the returned file."
        )

    report = read_sheet(args.path)
    render(report)

    if args.dry_run:
        print("\nDry run -- nothing written.")
        return
    if report["errors"]:
        raise SystemExit(
            "\nRefusing to import: fix the cells above and re-run. Nothing was "
            "written -- a guessed decision would enter the gold standard as "
            "though the adjudicator had made it."
        )

    args.out.write_text(
        json.dumps(
            {
                "decisions": report["decisions"],
                "notes": report["notes"],
                "n_decided": report["n_decided"],
                "incomplete_segments": report["incomplete_segments"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"\nWrote {report['n_decided']} decisions to {args.out}")
    print(
        "\nNext: `uv run python -m tests.eval.extraction.adjudicate "
        f"annotator_a annotator_b --decisions {args.out}`"
    )


if __name__ == "__main__":
    main()
