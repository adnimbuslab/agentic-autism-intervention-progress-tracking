"""Export the frozen batch as an annotation spreadsheet, one file per annotator.

A clinician should not have to use a terminal to do clinical work. This writes
a CSV per annotator: transcript on the left, empty value columns on the right,
opened directly by Excel, Numbers or Google Sheets.

The sheet carries the transcript and nothing else about the segment. No model
output appears in it, so blindness survives the trip out of the repository --
the same property `annotate_gold` guarantees structurally.

Two conventions the importer depends on, and which the reference sheet states
for the annotator:

  - **An empty cell means "not yet annotated".** It is not a null.
  - **The word `none` means "the transcript supports no value here".** That is
    a finding, and the study depends on it: it is what makes an unsupported
    model value measurable as a hallucination rather than scored as a miss.

Row order is shuffled per annotator under a fixed seed. Both annotators judge
the same 330 segments, but presenting them in the same sequence would let
fatigue and drift land on the same segments for both, correlating their errors
in exactly the place kappa is meant to detect them. Import is keyed by
segment_id, so order carries no meaning downstream.

Usage:
    uv run python -m tests.eval.extraction.export_gold_sheet annotator_a annotator_b
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from tests.eval.extraction.annotate_gold import (
    CATEGORICAL_VALUES,
    FIELD_HELP,
    FIELDS,
    FREE_TEXT_FIELDS,
)

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
SHEETS_DIR = RESULTS_DIR / "annotation_sheets"

NULL_WORD = "none"
DEFAULT_SEED = 42

CONTEXT_COLUMNS = ["segment_id", "child_id", "corpus", "session_id", "transcript"]
COLUMNS = [*CONTEXT_COLUMNS, *FIELDS, "notes"]


def sheet_path(annotator: str) -> Path:
    return SHEETS_DIR / f"gold_sheet_{annotator}.csv"


def reference_path() -> Path:
    return SHEETS_DIR / "VALUE_REFERENCE.csv"


def rows_for(batch: dict[str, Any], annotator: str, seed: int) -> list[dict[str, str]]:
    """One row per segment, transcript filled, value columns blank."""
    entries = [
        {
            "segment_id": e["segment_id"],
            "child_id": e["child_id"],
            "corpus": e["corpus"],
            "session_id": e["session_id"],
            "transcript": e["chat_text"],
            **{field: "" for field in FIELDS},
            "notes": "",
        }
        for e in batch["candidates"]
    ]
    # Seeded on the annotator so each order is stable across re-exports -- an
    # annotator who re-downloads the sheet must not get a reshuffled one.
    random.Random(f"{seed}:{annotator}").shuffle(entries)
    return entries


def write_sheet(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        # utf-8-sig: Excel on Windows misreads plain UTF-8 accents without the
        # BOM, and transcripts carry them.
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_reference(path: Path) -> None:
    """The allowed values, as a sheet the annotator can keep open beside theirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field", "what it records", "allowed values"])
        for field in FIELDS:
            allowed = (
                "free text -- describe what the child did, in your own words"
                if field in FREE_TEXT_FIELDS
                else " | ".join(CATEGORICAL_VALUES[field])
            )
            writer.writerow([field, FIELD_HELP[field], allowed])
        writer.writerow([])
        writer.writerow(["CONVENTION", "meaning", ""])
        writer.writerow([
            NULL_WORD,
            "the transcript supports no value for this field -- a finding, "
            "please use it rather than guessing",
            "",
        ])
        writer.writerow([
            "(empty cell)",
            "not yet annotated -- these rows are reported as incomplete, "
            "not treated as 'none'",
            "",
        ])


INSTRUCTIONS = f"""
Instructions for the annotator
==============================

Fill one row per transcript segment. Read the transcript in the `transcript`
column and record ONLY what that transcript supports.

  {", ".join(FIELDS)}

  - Type the value exactly as listed in VALUE_REFERENCE.csv (copy/paste is
    safest). Capitalisation and surrounding spaces do not matter.
  - `behavior` is free text: describe what the child did, in your own words.
  - Write `{NULL_WORD}` when the transcript does not support any value for a
    field. This is a real answer, not a gap -- please do not guess to fill a
    field. An uncertain value and a `{NULL_WORD}` are different claims, and the
    second is the honest one where the evidence is absent.
  - Leave a cell EMPTY only if you have not done that row yet.
  - `notes` is optional and free text. Notes on why a call was difficult are
    valuable; they inform the adjudication step.

Do not reorder, rename, add or delete columns, and do not change the
`segment_id` column -- it is how your work is matched back up.

Save as CSV (keep the same file name) and send it back.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs="+")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    if not BATCH_PATH.exists():
        raise SystemExit(
            f"{BATCH_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.build_annotation_batch` first."
        )
    batch = json.loads(BATCH_PATH.read_text())

    for annotator in args.annotators:
        rows = rows_for(batch, annotator, args.seed)
        path = sheet_path(annotator)
        write_sheet(rows, path)
        print(f"  {path}  ({len(rows)} segments)")

    write_reference(reference_path())
    print(f"  {reference_path()}")

    instructions = SHEETS_DIR / "INSTRUCTIONS.txt"
    instructions.write_text(INSTRUCTIONS.lstrip())
    print(f"  {instructions}")

    print(
        "\nSend each annotator their own sheet plus VALUE_REFERENCE.csv and "
        "INSTRUCTIONS.txt.\nOn return: "
        "`uv run python -m tests.eval.extraction.import_gold_sheet <annotator>`"
    )


if __name__ == "__main__":
    main()
