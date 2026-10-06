"""Export the held-out set as blind annotation sheets.

Identical in discipline to the round-1 sheets — transcript on the left, empty
value columns on the right, per-annotator shuffle, no model output anywhere —
with one difference that is the point of the exercise: the annotators work from
the final codebook from the first segment, rather than reaching it after a
round of disagreement.

That makes this round answer two questions at once. It supplies a test set
whose membership was never conditioned on model behaviour, and it measures
whether the codebook generalises beyond the segments and the disagreements it
was written from. A kappa obtained here is a first-pass kappa under the final
protocol, not a within-annotator repeat, which is the comparison the two-round
result cannot supply on its own.

Usage:
    uv run python -m tests.eval.extraction.export_holdout_sheets annotator_a annotator_b
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Any

from tests.eval.extraction.annotate_gold import FIELDS
from tests.eval.extraction.export_gold_sheet import (
    CONTEXT_COLUMNS,
    SHEETS_DIR,
    write_reference,
    write_sheet,
)

RESULTS_DIR = Path(__file__).parent / "results"
HOLDOUT_PATH = RESULTS_DIR / "holdout_set.json"
CODEBOOK = Path(__file__).parents[3] / "docs" / "annotation_codebook.md"
SEED = 8484

COLUMNS = [*CONTEXT_COLUMNS, *FIELDS, "notes"]

NOTE = """
Held-out round — please read before starting
============================================

These segments are new. None of them appeared in the earlier rounds, and they
were selected without reference to any model's behaviour.

The difference from last time is that you have the codebook from the start.
Please read `annotation_codebook.md` before the first segment and apply it
throughout, rather than forming your own reading and reconciling later.

Everything else is as before:

  - work independently, and do not confer on individual segments;
  - `none` means the transcript supports no value for that field, and is a real
    answer rather than a gap;
  - leave a cell empty only if you have not reached that row yet;
  - notes on why a call was difficult are valuable.

We are measuring two things with this round: how well the field definitions
work when they are available from the beginning, and how the extraction models
perform on segments that were not selected because they happened to handle them.
Neither depends on you agreeing with each other, so please do not try to.
"""


def sheet_path(annotator: str) -> Path:
    return SHEETS_DIR / f"holdout_sheet_{annotator}.csv"


def rows_for(segments: list[dict[str, Any]], annotator: str, seed: int) -> list[dict[str, str]]:
    entries = [
        {
            "segment_id": s["segment_id"],
            "child_id": s["child_id"],
            "corpus": s["corpus"],
            "session_id": s["session_id"],
            "transcript": s["chat_text"],
            **{field: "" for field in FIELDS},
            "notes": "",
        }
        for s in segments
    ]
    random.Random(f"{seed}:{annotator}").shuffle(entries)
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs="+")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    if not HOLDOUT_PATH.exists():
        raise SystemExit(
            f"{HOLDOUT_PATH} not found. Freeze the held-out set first with "
            "`uv run python -m tests.eval.extraction.build_holdout_set`."
        )
    payload = json.loads(HOLDOUT_PATH.read_text())
    segments = payload["segments"]

    for annotator in args.annotators:
        rows = rows_for(segments, annotator, args.seed)
        path = sheet_path(annotator)
        write_sheet(rows, path)
        print(f"  {path}  ({len(rows)} segments)")

    reference = SHEETS_DIR / "VALUE_REFERENCE.csv"
    write_reference(reference)
    print(f"  {reference}")

    note = SHEETS_DIR / "HOLDOUT_NOTE.txt"
    note.write_text(NOTE.lstrip())
    print(f"  {note}")

    if CODEBOOK.exists():
        copy = SHEETS_DIR / CODEBOOK.name
        shutil.copyfile(CODEBOOK, copy)
        print(f"  {copy}")

    print(
        f"\n{len(segments)} segments, {payload['per_child_target']} per child, "
        f"seed {payload['seed']} (set) / {args.seed} (sheet order)."
        "\nSend each annotator their sheet, the codebook, VALUE_REFERENCE.csv "
        "and HOLDOUT_NOTE.txt."
        "\nDo not run generators over these segments until the sheets are back."
    )


if __name__ == "__main__":
    main()
