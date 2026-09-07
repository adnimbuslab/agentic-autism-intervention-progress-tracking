"""Source-level gold annotation: what the transcript actually supports.

The annotator reads a transcript segment and records the field values it
supports. Model output is never shown. This is the study's annotation design,
and it differs from candidate judging in three ways that matter:

  1. **Model-independent.** Gold is authored from the source, so all three
     generators are scored against one common reference and the oracle ceiling
     is computed over that same reference. Adding a fourth generator later
     costs no new annotation.

  2. **No anchoring.** An annotator shown a model's answer is measurably more
     likely to accept it. Judging candidates reference-free would have made
     every generator's accuracy partly a function of how persuasive its output
     looked.

  3. **One pass, not three.** 330 segments per annotator rather than 330 x 3
     candidate outputs -- the same three-model comparison and the same oracle
     ceiling, at a third of the human cost.

Blindness is structural, not a matter of discipline: this module reads
``chat_text`` and never touches ``candidates``. See
``test_annotate_gold.py::TestBlindness``.

The batch is frozen. This reads it; it never rewrites it.

Usage:
    uv run python -m tests.eval.extraction.annotate_gold annotator_a
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.backend.schemas.observation_schema import (
    Domain,
    Modality,
    Outcome,
    PromptLevel,
)

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]

# Free-text fields take prose; categorical fields take one of a fixed set.
FREE_TEXT_FIELDS = frozenset({"behavior"})
CATEGORICAL_VALUES: dict[str, list[str]] = {
    "domain": [d.value for d in Domain],
    "modality": [m.value for m in Modality],
    "prompt_level": [p.value for p in PromptLevel],
    "outcome": [o.value for o in Outcome],
}

NULL_TOKEN = "-"

FIELD_HELP = {
    "domain": "The developmental domain the observed behaviour belongs to.",
    "behavior": "What the child did, in your own words, grounded in the transcript.",
    "modality": "How the child communicated it.",
    "prompt_level": "The support the child needed, if the transcript shows it.",
    "outcome": "How the attempt resolved, if the transcript shows it.",
}

INSTRUCTIONS = f"""
Record only what THIS transcript supports.

  - Enter the number of a value, or type it out.
  - Enter '{NULL_TOKEN}' when the transcript does not support any value for the
    field. A null is a finding, not a gap: it is what makes an unsupported
    model value measurable as a hallucination rather than scored as a miss.
  - '?' repeats the options, 's' skips the segment and leaves it unannotated.

Do not guess to fill a field. An uncertain value and a null are different
claims, and the second is the honest one where the evidence is absent.
"""


def annotations_path(annotator: str) -> Path:
    return RESULTS_DIR / f"gold_{annotator}.json"


def load_batch() -> dict[str, Any]:
    if not BATCH_PATH.exists():
        raise SystemExit(
            f"{BATCH_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.build_annotation_batch` first."
        )
    return json.loads(BATCH_PATH.read_text())


def segments_for_annotation(batch: dict[str, Any]) -> list[dict[str, Any]]:
    """The transcript segments only -- deliberately dropping model candidates.

    Every annotator sees every segment: gold is a property of the source, so
    there is no per-annotator assignment and the whole batch is the overlap on
    which reliability is computed.
    """
    return [
        {
            "segment_id": entry["segment_id"],
            "child_id": entry["child_id"],
            "corpus": entry["corpus"],
            "session_id": entry["session_id"],
            "chat_text": entry["chat_text"],
        }
        for entry in batch["candidates"]
    ]


def render(segment: dict[str, Any], index: int, total: int) -> None:
    print("\n" + "=" * 72)
    print(f"[{index}/{total}]  child: {segment['child_id']}  corpus: {segment['corpus']}")
    print("-" * 72)
    print(segment["chat_text"])
    print("=" * 72)


def _options_block(field: str) -> str:
    values = CATEGORICAL_VALUES[field]
    lines = [f"    {i + 1:2d}. {value}" for i, value in enumerate(values)]
    lines.append(f"     {NULL_TOKEN}. (not supported by this transcript)")
    return "\n".join(lines)


def prompt_categorical(field: str) -> str | None | object:
    """Ask for one categorical value. Returns the value, None, or SKIP."""
    values = CATEGORICAL_VALUES[field]
    print(f"\n  {field} -- {FIELD_HELP[field]}")
    print(_options_block(field))
    while True:
        raw = input(f"  {field}: ").strip().lower()
        if raw == "?":
            print(_options_block(field))
            continue
        if raw == "s":
            return SKIP
        if raw == NULL_TOKEN:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(values):
            return values[int(raw) - 1]
        if raw in values:
            return raw
        print(f"    unrecognized {raw!r} -- enter 1-{len(values)}, a value, "
              f"'{NULL_TOKEN}' for none, or '?' for the list")


def prompt_free_text(field: str) -> str | None | object:
    print(f"\n  {field} -- {FIELD_HELP[field]}")
    raw = input(f"  {field} ('{NULL_TOKEN}' if unsupported, 's' to skip): ").strip()
    if raw.lower() == "s":
        return SKIP
    if raw == NULL_TOKEN or not raw:
        return None
    return raw


class _Skip:
    """Sentinel: leave this segment unannotated rather than record a guess."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "SKIP"


SKIP = _Skip()


def collect_field_values(segment: dict[str, Any]) -> dict[str, Any] | None:
    """Prompt for every field. Returns None if the annotator skipped."""
    values: dict[str, Any] = {}
    for field in FIELDS:
        answer = (
            prompt_free_text(field)
            if field in FREE_TEXT_FIELDS
            else prompt_categorical(field)
        )
        if answer is SKIP:
            return None
        values[field] = answer
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotator")
    args = parser.parse_args()

    batch = load_batch()
    segments = segments_for_annotation(batch)

    out_path = annotations_path(args.annotator)
    annotations: dict[str, Any] = (
        json.loads(out_path.read_text()) if out_path.exists() else {}
    )
    remaining = [s for s in segments if s["segment_id"] not in annotations]

    print(f"Annotator: {args.annotator}")
    print(
        f"Segments: {len(segments)}   done: {len(segments) - len(remaining)}   "
        f"remaining: {len(remaining)}"
    )
    if not remaining:
        print("Nothing left to annotate.")
        return
    print(INSTRUCTIONS)
    print("Ctrl-C to stop; progress is saved after every segment.")

    try:
        for offset, segment in enumerate(remaining, start=1):
            render(segment, offset, len(remaining))
            values = collect_field_values(segment)
            if values is None:
                print("  skipped -- left unannotated")
                continue
            notes = input("  notes (optional): ").strip()

            annotations[segment["segment_id"]] = {
                "segment_id": segment["segment_id"],
                "child_id": segment["child_id"],
                "field_values": values,
                "notes": notes,
                "annotator": args.annotator,
            }
            # Written per segment so an interrupted session loses nothing.
            out_path.write_text(json.dumps(annotations, indent=2, ensure_ascii=False))
    except KeyboardInterrupt:
        print("\nStopped.")

    print(f"\nWrote {len(annotations)} gold annotations to {out_path}")
    print(
        "Once both annotators finish, run "
        "`uv run python -m tests.eval.extraction.agreement_report <a> <b>`, then "
        "`uv run python -m tests.eval.extraction.adjudicate <a> <b>`."
    )


if __name__ == "__main__":
    main()
