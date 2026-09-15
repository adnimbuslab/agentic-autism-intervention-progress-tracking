"""Import a completed annotation spreadsheet into gold annotations.

Converts a returned CSV into ``gold_<annotator>.json``, the same shape
`annotate_gold` writes, so the rest of the chain -- agreement, adjudication,
scoring -- is unchanged regardless of which tool the annotator used.

Validation is strict and total, and nothing is guessed. A value that is not in
the field's vocabulary is reported with its row and cell rather than
normalized into the nearest match: a silent correction here would put a value
into the gold standard that the annotator did not choose, and every accuracy
figure downstream would inherit it.

The three cell states are kept distinct, because collapsing them is how a gold
standard acquires claims nobody made:

    a value        the annotator's judgement
    `none`         the transcript supports nothing here -- a finding
    empty          not yet annotated -- the row is incomplete and excluded

An incomplete row is excluded from the import rather than partially recorded.
Adjudication already excludes segments unresolved on any field; admitting a
half-filled row here would simply move the same hole further downstream.

Usage:
    uv run python -m tests.eval.extraction.import_gold_sheet annotator_a
    uv run python -m tests.eval.extraction.import_gold_sheet annotator_a --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from tests.eval.extraction.annotate_gold import (
    CATEGORICAL_VALUES,
    FIELDS,
    FREE_TEXT_FIELDS,
    annotations_path,
)
from tests.eval.extraction.export_gold_sheet import NULL_WORD, sheet_path

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"

# Words annotators reach for to mean "nothing here". Accepted as the null
# finding; anything else unrecognized is an error, not a guess.
NULL_SYNONYMS = frozenset({NULL_WORD, "n/a", "na", "null", "-", "--"})


class CellError(Exception):
    """A cell that cannot be read as any of the three valid states."""


def parse_cell(field: str, raw: str) -> tuple[str, Any]:
    """Return ``(state, value)`` where state is 'value', 'null' or 'empty'."""
    text = (raw or "").strip()
    if not text:
        return "empty", None
    if text.casefold() in NULL_SYNONYMS:
        return "null", None
    if field in FREE_TEXT_FIELDS:
        return "value", text
    normalized = text.casefold().replace(" ", "_").replace("-", "_")
    if normalized in CATEGORICAL_VALUES[field]:
        return "value", normalized
    raise CellError(
        f"{field}={text!r} is not an allowed value. Expected one of: "
        f"{', '.join(CATEGORICAL_VALUES[field])} (or '{NULL_WORD}')."
    )


def read_sheet(
    path: Path,
    annotator: str,
    valid_ids: set[str],
    round_number: int = 1,
) -> dict[str, Any]:
    """Parse a returned sheet into annotations plus a problem report."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    annotations: dict[str, Any] = {}
    incomplete: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    unknown_segments: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()

    for line_no, row in enumerate(rows, start=2):  # line 1 is the header
        segment_id = (row.get("segment_id") or "").strip()
        if not segment_id:
            errors.append({"row": str(line_no), "problem": "missing segment_id"})
            continue
        if segment_id not in valid_ids:
            unknown_segments.append(segment_id)
            continue
        if segment_id in seen:
            duplicates.append(segment_id)
            continue
        seen.add(segment_id)

        values: dict[str, Any] = {}
        blank_fields: list[str] = []
        row_errors: list[str] = []
        for field in FIELDS:
            try:
                state, value = parse_cell(field, row.get(field, ""))
            except CellError as exc:
                row_errors.append(str(exc))
                continue
            if state == "empty":
                blank_fields.append(field)
            else:
                values[field] = value

        if row_errors:
            errors.extend(
                {"row": str(line_no), "segment_id": segment_id, "problem": message}
                for message in row_errors
            )
            continue
        if blank_fields:
            incomplete.append(
                {"row": line_no, "segment_id": segment_id, "blank": blank_fields}
            )
            continue

        annotations[segment_id] = {
            "segment_id": segment_id,
            "child_id": (row.get("child_id") or "").strip(),
            "field_values": {f: values[f] for f in FIELDS},
            "notes": (row.get("notes") or "").strip(),
            "annotator": annotator,
            "source": "spreadsheet",
            "round": round_number,
        }

    return {
        "annotations": annotations,
        "n_rows": len(rows),
        "n_complete": len(annotations),
        "incomplete": incomplete,
        "errors": errors,
        "unknown_segments": unknown_segments,
        "duplicates": duplicates,
        "missing_segments": sorted(valid_ids - seen),
    }


def merge(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Later-round values replace earlier ones for the segments re-annotated.

    Only segments present in the incoming sheet are touched. A round-2 sheet
    carries the re-issued segments alone, so a plain overwrite of the gold file
    would silently discard every round-1 segment that was never in conflict.
    """
    merged = dict(existing)
    merged.update(incoming)
    return merged


def render(report: dict[str, Any], annotator: str, partial: bool = False) -> None:
    """Print the import report. `partial` suppresses the not-in-sheet count,
    which for a re-issued round is every segment that was never in conflict --
    expected, and not a gap worth flagging."""
    print(f"Sheet for {annotator}: {report['n_rows']} rows")
    print(f"  complete and imported : {report['n_complete']}")
    print(f"  incomplete (excluded) : {len(report['incomplete'])}")
    print(f"  cell errors           : {len(report['errors'])}")
    if report["unknown_segments"]:
        print(f"  unknown segment_ids   : {len(report['unknown_segments'])}")
    if report["duplicates"]:
        print(f"  duplicate segment_ids : {len(report['duplicates'])}")
    if report["missing_segments"] and not partial:
        print(f"  segments not in sheet : {len(report['missing_segments'])}")

    for error in report["errors"][:20]:
        location = f"row {error['row']}"
        if "segment_id" in error:
            location += f" ({error['segment_id']})"
        print(f"    ! {location}: {error['problem']}")
    if len(report["errors"]) > 20:
        print(f"    ... and {len(report['errors']) - 20} more")

    for row in report["incomplete"][:10]:
        print(f"    - row {row['row']} ({row['segment_id']}): blank {', '.join(row['blank'])}")
    if len(report["incomplete"]) > 10:
        print(f"    ... and {len(report['incomplete']) - 10} more incomplete rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotator")
    parser.add_argument("--path", type=Path, default=None, help="Override sheet path.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate without writing."
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Update the existing gold file in place rather than replacing it. "
             "Use for a re-issued round, whose sheet holds only some segments.",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=None,
        help="Round number recorded on each annotation. Defaults to 2 with "
             "--merge, 1 otherwise.",
    )
    args = parser.parse_args()

    path = args.path or sheet_path(args.annotator)
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Export sheets with "
            "`uv run python -m tests.eval.extraction.export_gold_sheet <annotators>`, "
            "or pass --path to the returned file."
        )
    if not BATCH_PATH.exists():
        raise SystemExit(f"{BATCH_PATH} not found; segment ids cannot be validated.")

    batch = json.loads(BATCH_PATH.read_text())
    valid_ids = {e["segment_id"] for e in batch["candidates"]}

    round_number = args.round if args.round is not None else (2 if args.merge else 1)
    report = read_sheet(path, args.annotator, valid_ids, round_number)
    render(report, args.annotator, partial=args.merge)

    if args.dry_run:
        print("\nDry run -- nothing written.")
        return
    if report["errors"]:
        raise SystemExit(
            "\nRefusing to import: fix the cell errors above and re-run. "
            "Nothing was written -- a guessed value would enter the gold "
            "standard as though the annotator had chosen it."
        )

    out = annotations_path(args.annotator)
    annotations = report["annotations"]
    if args.merge:
        if not out.exists():
            raise SystemExit(
                f"--merge given but {out} does not exist. There is nothing to "
                "merge into; import the first round without --merge."
            )
        existing = json.loads(out.read_text())
        annotations = merge(existing, annotations)
        print(
            f"\nMerged {report['n_complete']} round-{round_number} annotations "
            f"over {len(existing)} existing; {len(annotations)} total."
        )
    out.write_text(json.dumps(annotations, indent=2, ensure_ascii=False))
    print(f"Wrote {len(annotations)} gold annotations to {out}")
    if not args.merge and (report["incomplete"] or report["missing_segments"]):
        print(
            "Some segments are not yet annotated; re-import after they are "
            "filled in. Import is idempotent -- it rewrites the file from the "
            "sheet each time."
        )


if __name__ == "__main__":
    main()
