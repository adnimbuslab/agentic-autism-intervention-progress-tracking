"""Export the surviving disagreements as an adjudication spreadsheet.

`adjudicate.py` resolves conflicts through an interactive prompt. That is fine
for a handful and wrong for 503: it cannot be paused, reviewed, handed to a
colleague or checked afterwards, and a clinician should not have to hold a
terminal session open for an afternoon of clinical judgement.

This writes one row per conflicted field, with everything the decision needs in
the row: the transcript, both annotators' values, and -- where the pair sits on
a boundary the codebook already settles -- the rule that settles it.

**Two kinds of row, and the difference is the whole point of the layout.**

  - 78 of the categorical conflicts are pairs the codebook already resolves.
    One annotator applied the rule and the other did not. These are decided by
    reading the rule, not by re-judging the segment, and the `codebook_rule`
    column carries it so the adjudicator is not asked to remember it.
  - The remainder are genuine judgements the scheme does not settle. 66 of them
    are `domain`, which has no codebook. These are the real work.

`behavior` is free text and disagrees almost everywhere by exact match, which
is why it dominates the row count. Those rows are usually a glance -- both
descriptions say the same thing in different words and either will serve -- so
they are placed last within each segment, after the judgements that need
thought.

Rows are grouped by segment so the transcript is read once and all of that
segment's fields are settled together. Sorting the sheet by field instead would
make the adjudicator read the same transcript up to five times.

Usage:
    uv run python -m tests.eval.extraction.export_adjudication_sheet annotator_a annotator_b
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from tests.eval.extraction.agreement_report import (
    annotations_path,
    normalize,
    shared_segments,
)
from tests.eval.extraction.annotate_gold import CATEGORICAL_VALUES, FIELDS, FREE_TEXT_FIELDS
from tests.eval.extraction.reissue_gold_sheet import CODEBOOK_BOUNDARIES, RULES

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
SHEETS_DIR = RESULTS_DIR / "annotation_sheets"
SHEET_PATH = SHEETS_DIR / "adjudication_sheet.csv"

NULL_WORD = "none"

COLUMNS = [
    "segment_id",
    "child_id",
    "field",
    "transcript",
    "annotator_a",
    "annotator_b",
    "codebook_rule",
    "decision",
    "notes",
]

# Categorical fields first, free text last: the judgements that need the
# transcript come before the ones that usually need only a glance.
FIELD_ORDER = [f for f in FIELDS if f not in FREE_TEXT_FIELDS] + [
    f for f in FIELDS if f in FREE_TEXT_FIELDS
]


def rule_for(field: str, left: Any, right: Any) -> str:
    """The codebook rule settling this pair, or '' where none does."""
    key = frozenset({left or NULL_WORD, right or NULL_WORD})
    rule = CODEBOOK_BOUNDARIES.get(field, {}).get(key)
    return RULES[rule] if rule else ""


def conflict_rows(
    first: dict[str, Any],
    second: dict[str, Any],
    segments: list[str],
    chat_texts: dict[str, str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for segment_id in segments:
        a = first[segment_id].get("field_values", {})
        b = second[segment_id].get("field_values", {})
        for field in FIELD_ORDER:
            if normalize(a.get(field)) == normalize(b.get(field)):
                continue
            rows.append({
                "segment_id": segment_id,
                "child_id": first[segment_id].get("child_id", ""),
                "field": field,
                "transcript": chat_texts.get(segment_id, ""),
                "annotator_a": a.get(field) or NULL_WORD,
                "annotator_b": b.get(field) or NULL_WORD,
                "codebook_rule": rule_for(field, a.get(field), b.get(field)),
                "decision": "",
                "notes": "",
            })
    return rows


def write_sheet(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


INSTRUCTIONS = f"""
Instructions for the adjudicator
================================

Each row is one field two annotators recorded differently. Read the transcript
and decide what the field should be.

In the `decision` column write ONE of:

  a            adopt annotator A's value, exactly as shown
  b            adopt annotator B's value, exactly as shown
  <a value>    neither -- type the value you judge correct
  {NULL_WORD}         the transcript supports no value for this field
  (empty)      you have not decided this row yet

Leaving a row empty is not neutral. A segment left undecided on ANY field is
excluded from the gold standard entirely, rather than being half-recorded, so
an unfinished row removes that whole segment from the study.

For `behavior`, `a` or `b` is almost always right -- the two descriptions
usually say the same thing in different words. Type your own only where neither
is accurate. These rows come last within each segment.

`codebook_rule` is filled in where docs/annotation_codebook.md already settles
the pair. Where it is filled in, apply the rule rather than re-judging the
segment: one annotator simply did not apply it. Where it is empty, the codebook
is silent and the call is yours.

Rows are grouped by segment, so read each transcript once and settle all of
that segment's rows together.

`notes` is optional. A note on why a call was hard is worth recording.

Do not reorder, rename, add or delete columns, and do not edit `segment_id`,
`field`, or either annotator column -- they are how your decisions are matched
back up.

Save as CSV with the same file name and send it back.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs=2)
    parser.add_argument("--out", type=Path, default=SHEET_PATH)
    parser.add_argument(
        "--segments",
        type=Path,
        default=None,
        help="Where the transcripts come from. Defaults to the frozen "
             "annotation batch; pass holdout_set.json to adjudicate a round "
             "annotated over the held-out set.",
    )
    args = parser.parse_args()

    loaded = []
    for name in args.annotators:
        path = annotations_path(name)
        if not path.exists():
            raise SystemExit(f"{path} not found. Both annotators must finish first.")
        loaded.append(json.loads(path.read_text()))
    first, second = loaded

    # Two artefact shapes hold transcripts: the batch keys them under
    # "candidates", the held-out set under "segments".
    source = args.segments or BATCH_PATH
    chat_texts: dict[str, str] = {}
    if source.exists():
        payload = json.loads(source.read_text())
        entries = payload.get("candidates") or payload.get("segments") or []
        chat_texts = {e["segment_id"]: e["chat_text"] for e in entries}

    segments = shared_segments(first, second)
    rows = conflict_rows(first, second, segments, chat_texts)
    write_sheet(rows, args.out)

    by_field: dict[str, int] = {}
    with_rule = 0
    for row in rows:
        by_field[row["field"]] = by_field.get(row["field"], 0) + 1
        if row["codebook_rule"]:
            with_rule += 1
    touched = len({row["segment_id"] for row in rows})

    print(f"Conflicted fields: {len(rows)} on {touched} of {len(segments)} segments")
    for field in FIELD_ORDER:
        if field in by_field:
            print(f"    {field:<14} {by_field[field]:>4}")
    print(f"\n  settled by an existing codebook rule : {with_rule}")
    print(f"  needing a fresh judgement            : {len(rows) - with_rule}")
    print(f"  segments already clean on every field: {len(segments) - touched}")

    instructions = args.out.parent / "ADJUDICATION_INSTRUCTIONS.txt"
    instructions.write_text(INSTRUCTIONS.lstrip())
    print(f"\n  {args.out}")
    print(f"  {instructions}")
    print(
        "\nOn return:\n"
        "  uv run python -m tests.eval.extraction.import_adjudication_sheet "
        f"--path {args.out}\n"
        "  uv run python -m tests.eval.extraction.adjudicate "
        f"{args.annotators[0]} {args.annotators[1]} --decisions <adjudications.json>"
    )


if __name__ == "__main__":
    main()
