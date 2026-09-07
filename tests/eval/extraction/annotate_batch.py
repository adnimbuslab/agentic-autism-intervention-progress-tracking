"""SUPERSEDED -- candidate-level judging, retained for provenance only.

The study annotates at the source/gold level instead: annotators author field
values from the transcript with no model output shown (`annotate_gold`), and
every generator is scored against that one reference by `score_against_gold`.
That design is model-independent, removes anchoring on model output, costs one
pass per annotator rather than one per generator, and lets a fourth generator
be added later without any new annotation.

Do not run this for the reported study. It is kept because the batch it reads
is frozen and its judgement vocabulary is still the vocabulary
`score_against_gold` derives.

---

Interactive annotation over a child-stratified batch, one annotator at a time.

Supersedes annotate.py, which read the flat pilot candidate file, had no
per-annotator assignment, and wrote every annotator's judgments to one file --
so two annotators would overwrite each other and no agreement could be computed.

Each annotator judges only their assigned segments and writes their own file, so
the double-annotated overlap stays genuinely independent. Blind by default: the
annotator is not told which model produced a candidate, nor what the other
annotator said.

One pass judges one model. A batch holding several generators needs one pass
per generator per annotator; passes are keyed independently, so they can be run
in any order and resumed at any point.

Usage:
    uv run python -m tests.eval.extraction.annotate_batch annotator_a --model qwen2.5:7b
    uv run python -m tests.eval.extraction.annotate_batch annotator_a --model llama3.2:latest
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]

JUDGMENTS = {
    "c": "correct",
    "i": "incorrect",
    "h": "hallucinated",
    "n": "correctly_null",
    "m": "missing",
}

JUDGMENT_HELP = """
  c  correct          the value is supported by the transcript
  i  incorrect        a value was extracted, but the wrong one
  h  hallucinated     the value is not supported by anything in the transcript
  n  correctly_null   no value, and none was warranted
  m  missing          no value, but the transcript supports one
"""


def annotations_path(annotator: str) -> Path:
    return RESULTS_DIR / f"annotations_{annotator}.json"


def annotation_key(segment_id: str, model: str) -> str:
    """Identity of one judgeable item: a segment *and* the model that produced it.

    Keying on segment_id alone silently broke multi-model annotation two ways.
    A second pass over the same batch with a different ``--model`` found every
    segment already present and reported nothing left to do, so only one
    generator could ever be judged. And two annotators who happened to pass
    different ``--model`` values produced files that paired segment-to-segment,
    which `agreement_report` would have read as inter-rater disagreement when
    it was really two models' outputs being compared.
    """
    return f"{segment_id}::{model}"


def load_batch() -> dict[str, Any]:
    if not BATCH_PATH.exists():
        raise SystemExit(
            f"{BATCH_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.build_annotation_batch` first."
        )
    return json.loads(BATCH_PATH.read_text())


def assigned_candidates(
    batch: dict[str, Any], annotator: str
) -> list[dict[str, Any]]:
    """This annotator's segments, in the batch's own order."""
    assignments = batch.get("assignments", {})
    if annotator not in assignments:
        raise SystemExit(
            f"'{annotator}' has no assignment in this batch. "
            f"Assigned annotators: {sorted(assignments)}"
        )
    assigned = set(assignments[annotator])
    return [c for c in batch["candidates"] if c["segment_id"] in assigned]


def choose_model(batch: dict[str, Any], requested: str | None) -> str:
    models = batch.get("models", [])
    if requested:
        if requested not in models:
            raise SystemExit(f"Model '{requested}' not in batch. Available: {models}")
        return requested
    if len(models) > 1:
        raise SystemExit(
            f"This batch holds candidates from {len(models)} models {models}. "
            "Pass --model to say which one is being judged; judging several at "
            "once in a single pass would make the resulting labels ambiguous."
        )
    return models[0]


def render(candidate: dict[str, Any], model: str, index: int, total: int) -> None:
    print("\n" + "=" * 72)
    print(f"[{index}/{total}]  child: {candidate['child_id']}  corpus: {candidate['corpus']}")
    print("-" * 72)
    print(candidate["chat_text"])
    print("-" * 72)
    fields = candidate["candidates"][model]["extracted_fields"]
    print("Model output to judge:")
    for field in FIELDS:
        print(f"  {field:14s} {fields.get(field)!r}")
    print("=" * 72)


def prompt_field(field: str, value: object) -> str:
    while True:
        raw = input(f"  {field} = {value!r}  [c/i/h/n/m, ? for help]: ").strip().lower()
        if raw == "?":
            print(JUDGMENT_HELP)
            continue
        if raw in JUDGMENTS:
            return JUDGMENTS[raw]
        print(f"    unrecognized '{raw}' — expected one of {sorted(JUDGMENTS)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotator")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    batch = load_batch()
    model = choose_model(batch, args.model)
    candidates = assigned_candidates(batch, args.annotator)

    out_path = annotations_path(args.annotator)
    annotations: dict[str, Any] = (
        json.loads(out_path.read_text()) if out_path.exists() else {}
    )

    remaining = [
        c for c in candidates
        if annotation_key(c["segment_id"], model) not in annotations
    ]
    print(f"Annotator: {args.annotator}   model under judgment: {model}")
    print(
        f"Assigned: {len(candidates)}   done: {len(candidates) - len(remaining)}   "
        f"remaining: {len(remaining)}"
    )
    unjudged = [
        m for m in batch.get("models", [])
        if any(annotation_key(c["segment_id"], m) not in annotations for c in candidates)
        and m != model
    ]
    if unjudged:
        print(f"Other models still unjudged by {args.annotator}: {', '.join(unjudged)}")
    if not remaining:
        print(f"Nothing left to annotate for {model}.")
        return
    print(JUDGMENT_HELP)
    print("Ctrl-C to stop; progress is saved after every segment.")

    try:
        for offset, candidate in enumerate(remaining, start=1):
            render(candidate, model, offset, len(remaining))
            fields = candidate["candidates"][model]["extracted_fields"]
            judgments = {f: prompt_field(f, fields.get(f)) for f in FIELDS}
            notes = input("  notes (optional): ").strip()

            annotations[annotation_key(candidate["segment_id"], model)] = {
                "segment_id": candidate["segment_id"],
                "field_judgments": judgments,
                "notes": notes,
                "child_id": candidate["child_id"],
                "model": model,
                "annotator": args.annotator,
            }
            # Written per segment so an interrupted session loses nothing.
            out_path.write_text(json.dumps(annotations, indent=2, ensure_ascii=False))
    except KeyboardInterrupt:
        print("\nStopped.")

    print(f"\nWrote {len(annotations)} annotations to {out_path}")
    print(
        "Once both annotators finish, run "
        "`uv run python -m tests.eval.extraction.agreement_report <a> <b>`."
    )


if __name__ == "__main__":
    main()
