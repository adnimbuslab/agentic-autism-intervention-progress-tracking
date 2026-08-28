"""Interactive human annotation tool for extraction candidates.

Run this yourself (or hand it to a real annotator) -- it cannot be run by
an AI on your behalf, per this project's hard constraint that structured
ground truth must come from a trained human annotator, not an LLM
(docs/lld/Foundation_Model_Fine_Tuning.md).

For each candidate in annotation_candidates.json (produced by
build_annotation_candidates.py), shows the source CHAT segment text and the
model's extracted fields, and asks you to judge each field against the text:

  - If the model extracted a value: correct / incorrect / hallucinated
    (hallucinated = the text does not actually support any value for this
    field -- the model should have said null)
  - If the model extracted null: correctly_null / missing
    (missing = the text does support a value here, but the model said null)

Resumable: progress is saved after every candidate, quit anytime with
Ctrl+C or by answering 'q' and resume later -- already-annotated
candidates are skipped.

Usage:
    uv run python -m tests.eval.extraction.annotate
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
CANDIDATES_PATH = RESULTS_DIR / "annotation_candidates.json"
ANNOTATIONS_PATH = RESULTS_DIR / "annotations.json"

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]

VALUE_PRESENT_CHOICES = {"c": "correct", "i": "incorrect", "h": "hallucinated"}
VALUE_NULL_CHOICES = {"n": "correctly_null", "m": "missing"}


def load_candidates() -> list[dict]:
    if not CANDIDATES_PATH.exists():
        raise SystemExit(
            f"{CANDIDATES_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.build_annotation_candidates` first."
        )
    return json.loads(CANDIDATES_PATH.read_text())["candidates"]


def load_annotations() -> dict[str, dict]:
    if ANNOTATIONS_PATH.exists():
        return json.loads(ANNOTATIONS_PATH.read_text())
    return {}


def save_annotations(annotations: dict[str, dict]) -> None:
    ANNOTATIONS_PATH.write_text(json.dumps(annotations, indent=2))


def prompt_field(field: str, value) -> str | None:
    if value is None:
        choices = VALUE_NULL_CHOICES
        prompt = f"    {field} = null -- (n)correctly_null / (m)issing / (q)uit: "
    else:
        choices = VALUE_PRESENT_CHOICES
        prompt = f"    {field} = {value!r} -- (c)orrect / (i)ncorrect / (h)allucinated / (q)uit: "

    while True:
        answer = input(prompt).strip().lower()
        if answer == "q":
            return None
        if answer in choices:
            return choices[answer]
        print("    invalid choice, try again")


def annotate_one(candidate: dict) -> dict | None:
    print("\n" + "=" * 70)
    print(f"segment_id: {candidate['segment_id']}  (corpus: {candidate['corpus']})")
    print("-" * 70)
    print(candidate["chat_text"])
    print("-" * 70)
    print(f"model status: {candidate['status']}  confidence: {candidate['confidence']}")
    print()

    judgments: dict[str, str] = {}
    for field in FIELDS:
        value = candidate["extracted_fields"].get(field)
        judgment = prompt_field(field, value)
        if judgment is None:
            return None
        judgments[field] = judgment

    notes = input("  notes (optional, press enter to skip): ").strip()
    return {"field_judgments": judgments, "notes": notes}


def main() -> None:
    candidates = load_candidates()
    annotations = load_annotations()

    remaining = [c for c in candidates if c["segment_id"] not in annotations]
    print(f"{len(annotations)} already annotated, {len(remaining)} remaining.\n")

    for candidate in remaining:
        result = annotate_one(candidate)
        if result is None:
            print("\nStopping -- progress saved, resume anytime with the same command.")
            break
        annotations[candidate["segment_id"]] = result
        save_annotations(annotations)

    print(f"\n{len(annotations)}/{len(candidates)} candidates annotated.")
    print("Next: uv run python -m tests.eval.extraction.score_annotations")


if __name__ == "__main__":
    main()
