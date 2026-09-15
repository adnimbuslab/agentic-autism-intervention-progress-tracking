"""Re-issue the segments whose round-1 conflicts the codebook now settles.

Round 1 measured agreement under an incomplete protocol. Three boundaries were
left to the annotators' reading -- what counts as a gestural modality, when
accuracy applies at all, and whether an adult turn before a child response is a
prompt -- and the two annotators read them differently. `docs/annotation_codebook.md`
settles all three.

The tempting shortcut is to apply the codebook retroactively with a script:
rewrite every `gestural` that should have been `none` and recompute kappa. That
would produce a gold standard containing values no annotator ever chose, and a
reliability figure describing the rewrite rule rather than the annotators. The
same objection `adjudicate` exists to enforce applies here.

So the affected segments go back out, blind, and are annotated again under the
stated protocol. What that buys is two honest numbers -- kappa before the
codebook and kappa after it -- on the same segments and the same annotators.
The codebook becomes a measured result rather than an appendix.

Selection is by *boundary*, not by disagreement. A segment is re-issued when at
least one of its conflicting fields is a value pair the codebook now speaks to;
CODEBOOK_BOUNDARIES below is that table, and every pair in it cites the rule
that resolves it. Conflicts the codebook is silent on -- `domain` category
judgements, degree-of-completion calls like correct-vs-partial -- are NOT
re-issued. Nothing in the codebook would change those annotators' minds, and
re-running them would buy a kappa improvement the protocol did not earn. They
go to adjudication as they stand.

Two properties the sheets preserve:

  - **Blind.** Value columns go out empty. Neither annotator's round-1 values
    appear, nor the other's, nor which field was in conflict -- knowing that
    this segment's `modality` was disputed is itself an anchor.
  - **Whole-segment.** All five fields are re-annotated, not just the
    conflicting ones. Re-judging `outcome` while looking at a `prompt_level`
    someone already committed to is not an independent judgement.

Round 1 is frozen to `gold_<annotator>_round1.json` at issue time, before any
round-2 import can merge over it. Without that snapshot the "before" number is
gone.

Usage:
    uv run python -m tests.eval.extraction.reissue_gold_sheet annotator_a annotator_b
    uv run python -m tests.eval.extraction.reissue_gold_sheet annotator_a annotator_b --report-only
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from tests.eval.extraction.annotate_gold import (
    FIELDS,
    FREE_TEXT_FIELDS,
    annotations_path,
)
from tests.eval.extraction.export_gold_sheet import (
    COLUMNS,
    SHEETS_DIR,
    write_sheet,
)

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
# The sheets directory is the package that actually gets sent out, so the
# codebook is copied into it at issue time rather than referenced from docs/ --
# an annotator working from an emailed folder cannot follow a repo path, and a
# copy made once by hand would drift the next time the codebook is edited.
CODEBOOK_SOURCE = Path(__file__).parents[3] / "docs" / "annotation_codebook.md"

# A seed distinct from the round-1 export. Re-presenting these segments in
# their round-1 order would let an annotator recognise the sequence and recall
# what they answered last time, which is the anchoring the blind re-pass is for.
ROUND2_SEED = 4242
ROUND = 2

# The rules, as stated in docs/annotation_codebook.md.
RULES: dict[str, str] = {
    "modality_gestural": (
        "Codebook 1 -- gestural is a communicative gesture, not physical "
        "handling; multimodal needs two message-bearing channels; unknown vs none"
    ),
    "outcome_target": (
        "Codebook 2 -- correct/incorrect/partial/no_response need an "
        "identifiable target; absent acknowledgement is unknown, not incorrect"
    ),
    "prompt_antecedent": (
        "Codebook 3 -- the turn creating the opportunity is an antecedent, not "
        "a prompt; child-initiated is independent; most-supportive level wins"
    ),
}

# Unordered value pairs the codebook resolves, per field. A conflict on a pair
# that is NOT listed here is a judgement the codebook does not speak to.
CODEBOOK_BOUNDARIES: dict[str, dict[frozenset[str], str]] = {
    "modality": {
        frozenset({"gestural", "none"}): "modality_gestural",
        frozenset({"multimodal", "none"}): "modality_gestural",
        frozenset({"multimodal", "verbal"}): "modality_gestural",
        frozenset({"gestural", "multimodal"}): "modality_gestural",
        frozenset({"multimodal", "unknown"}): "modality_gestural",
        frozenset({"none", "unknown"}): "modality_gestural",
    },
    "outcome": {
        frozenset({"correct", "none"}): "outcome_target",
        frozenset({"correct", "unknown"}): "outcome_target",
        frozenset({"none", "partial"}): "outcome_target",
        frozenset({"incorrect", "none"}): "outcome_target",
        frozenset({"partial", "unknown"}): "outcome_target",
        frozenset({"incorrect", "unknown"}): "outcome_target",
        frozenset({"no_response", "none"}): "outcome_target",
        frozenset({"none", "unknown"}): "outcome_target",
        frozenset({"no_response", "unknown"}): "outcome_target",
    },
    # Every observed prompt_level pair is on a codebook boundary, because the
    # codebook states both the antecedent/prompt distinction and a total
    # ordering over the levels. That is a fact about this field, not a wildcard:
    # pairs are still listed one by one so the table stays auditable.
    "prompt_level": {
        frozenset({"independent", "verbal"}): "prompt_antecedent",
        frozenset({"model", "verbal"}): "prompt_antecedent",
        frozenset({"gestural", "verbal"}): "prompt_antecedent",
        frozenset({"partial_physical", "verbal"}): "prompt_antecedent",
        frozenset({"gestural", "model"}): "prompt_antecedent",
        frozenset({"independent", "model"}): "prompt_antecedent",
        frozenset({"independent", "partial_physical"}): "prompt_antecedent",
        frozenset({"gestural", "independent"}): "prompt_antecedent",
        frozenset({"full_physical", "independent"}): "prompt_antecedent",
    },
    # `domain` is absent deliberately. Its conflicts are category judgements
    # (cognitive vs language, play vs cognitive) that no codebook rule touches.
}

# The sheet writes `none` where the annotation records a null, so the two
# representations have to be reconciled before pairs are looked up.
NULL_WORD = "none"


def value_of(annotation: dict[str, Any], field: str) -> str:
    """The annotated value as a comparable string, nulls rendered as `none`."""
    return annotation["field_values"].get(field) or NULL_WORD


def conflicts_for(
    segment_id: str,
    first: dict[str, Any],
    second: dict[str, Any],
) -> list[dict[str, str]]:
    """Conflicting categorical fields for one segment, tagged by codebook rule.

    Free-text `behavior` is excluded: it disagrees almost everywhere by exact
    match, and whether two descriptions say the same thing is a question for
    adjudication, not a trigger for re-annotation.
    """
    found: list[dict[str, str]] = []
    for field in FIELDS:
        if field in FREE_TEXT_FIELDS:
            continue
        left, right = value_of(first, field), value_of(second, field)
        if left == right:
            continue
        rule = CODEBOOK_BOUNDARIES.get(field, {}).get(frozenset({left, right}))
        found.append({
            "segment_id": segment_id,
            "field": field,
            "values": f"{left} / {right}",
            "rule": rule or "",
        })
    return found


def select(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Segments to re-issue, plus the accounting behind the selection."""
    shared = sorted(set(first) & set(second))
    selected: dict[str, list[dict[str, str]]] = {}
    on_boundary: list[dict[str, str]] = []
    off_boundary: list[dict[str, str]] = []

    for segment_id in shared:
        conflicts = conflicts_for(segment_id, first[segment_id], second[segment_id])
        matched = [c for c in conflicts if c["rule"]]
        on_boundary.extend(matched)
        off_boundary.extend(c for c in conflicts if not c["rule"])
        if matched:
            selected[segment_id] = matched

    return {
        "shared": shared,
        "selected": selected,
        "on_boundary": on_boundary,
        "off_boundary": off_boundary,
    }


def rows_for(
    batch: dict[str, Any],
    segment_ids: set[str],
    annotator: str,
    seed: int,
) -> list[dict[str, str]]:
    """Blind round-2 rows: transcript filled, every value column empty."""
    entries = [
        {
            "segment_id": entry["segment_id"],
            "child_id": entry["child_id"],
            "corpus": entry["corpus"],
            "session_id": entry["session_id"],
            "transcript": entry["chat_text"],
            **{field: "" for field in FIELDS},
            "notes": "",
        }
        for entry in batch["candidates"]
        if entry["segment_id"] in segment_ids
    ]
    random.Random(f"{seed}:{annotator}").shuffle(entries)
    return entries


def sheet_path(annotator: str) -> Path:
    return SHEETS_DIR / f"gold_sheet_{annotator}_round{ROUND}.csv"


def round1_path(annotator: str) -> Path:
    return RESULTS_DIR / f"gold_{annotator}_round1.json"


def freeze_round1(annotator: str) -> tuple[Path, bool]:
    """Snapshot the round-1 gold file. Never overwrites an existing snapshot."""
    destination = round1_path(annotator)
    if destination.exists():
        return destination, False
    shutil.copyfile(annotations_path(annotator), destination)
    return destination, True


def render(report: dict[str, Any]) -> None:
    selected, on, off = report["selected"], report["on_boundary"], report["off_boundary"]
    total = len(on) + len(off)
    print(f"Round-1 double-annotated segments: {len(report['shared'])}")
    print(f"  categorical conflicts          : {total}")
    print(f"  on a codebook boundary         : {len(on)}")
    print(f"  codebook is silent             : {len(off)}")
    print(f"\nSegments to re-issue: {len(selected)}")

    by_rule = Counter(c["rule"] for c in on)
    print("\n  by rule")
    for rule, count in by_rule.most_common():
        print(f"    {count:>4}  {RULES[rule]}")

    by_field = Counter(c["field"] for c in on)
    print("\n  by field (conflicts on a boundary / total conflicts in field)")
    field_totals = Counter(c["field"] for c in on + off)
    for field in FIELDS:
        if field in field_totals:
            print(f"    {field:<14} {by_field[field]:>4} / {field_totals[field]:>4}")

    if off:
        by_silent_field = Counter(c["field"] for c in off)
        summary = ", ".join(f"{f} {n}" for f, n in by_silent_field.most_common())
        print(f"\n  left for adjudication (codebook silent): {summary}")
        for (field, values), count in Counter(
            (c["field"], c["values"]) for c in off
        ).most_common(8):
            print(f"    {count:>4}  {field}: {values}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs=2)
    parser.add_argument("--seed", type=int, default=ROUND2_SEED)
    parser.add_argument(
        "--report-only", action="store_true", help="Show the selection, write nothing."
    )
    args = parser.parse_args()

    for annotator in args.annotators:
        if not annotations_path(annotator).exists():
            raise SystemExit(
                f"{annotations_path(annotator)} not found. Import round 1 first."
            )
    if not BATCH_PATH.exists():
        raise SystemExit(f"{BATCH_PATH} not found; transcripts cannot be re-issued.")

    first_name, second_name = args.annotators
    first = json.loads(annotations_path(first_name).read_text())
    second = json.loads(annotations_path(second_name).read_text())

    report = select(first, second)
    render(report)

    if args.report_only:
        print("\nReport only -- nothing written.")
        return
    if not report["selected"]:
        print("\nNo segment sits on a codebook boundary; nothing to re-issue.")
        return

    print()
    for annotator in args.annotators:
        snapshot, fresh = freeze_round1(annotator)
        print(f"  {snapshot}  ({'frozen' if fresh else 'already frozen, kept'})")

    batch = json.loads(BATCH_PATH.read_text())
    segment_ids = set(report["selected"])
    for annotator in args.annotators:
        rows = rows_for(batch, segment_ids, annotator, args.seed)
        path = sheet_path(annotator)
        write_sheet(rows, path)
        print(f"  {path}  ({len(rows)} segments)")

    if CODEBOOK_SOURCE.exists():
        codebook_copy = SHEETS_DIR / CODEBOOK_SOURCE.name
        shutil.copyfile(CODEBOOK_SOURCE, codebook_copy)
        print(f"  {codebook_copy}")
    else:
        print(f"  ! {CODEBOOK_SOURCE} not found -- send the codebook by hand.")

    selection_path = RESULTS_DIR / f"reissue_round{ROUND}_selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "round": ROUND,
                "annotators": list(args.annotators),
                "codebook": "docs/annotation_codebook.md",
                "rules": RULES,
                "n_shared": len(report["shared"]),
                "n_selected": len(report["selected"]),
                "n_on_boundary": len(report["on_boundary"]),
                "n_off_boundary": len(report["off_boundary"]),
                "selected": report["selected"],
                "off_boundary": report["off_boundary"],
            },
            indent=2,
        )
    )
    print(f"  {selection_path}")

    print(
        "\nSend each annotator their round-2 sheet, VALUE_REFERENCE.csv, "
        "INSTRUCTIONS.txt\nand docs/annotation_codebook.md. On return:\n"
        "  uv run python -m tests.eval.extraction.import_gold_sheet <annotator> "
        "--path <sheet> --merge"
    )


if __name__ == "__main__":
    main()
