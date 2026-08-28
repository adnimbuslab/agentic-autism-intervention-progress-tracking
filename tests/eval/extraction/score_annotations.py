"""Compute field-level metrics from completed human annotations.

Only meaningful once annotate.py has been run by a real human annotator --
scoring an empty or partial annotations.json will just show small-n
warnings rather than fabricated confidence.

Reports, per field and overall:
  - correctness rate  = (correct + correctly_null) / total judged
  - hallucination rate = hallucinated / total judged
      (this is exactly the HLD's stated "Unsupported extraction rate"
      safety metric -- docs/High_Level_Design.md § Success Metrics)
  - missing rate      = missing / total judged

Usage:
    uv run python -m tests.eval.extraction.score_annotations
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
ANNOTATIONS_PATH = RESULTS_DIR / "annotations.json"
CANDIDATES_PATH = RESULTS_DIR / "annotation_candidates.json"

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]
CORRECT_LABELS = {"correct", "correctly_null"}


def main() -> None:
    if not ANNOTATIONS_PATH.exists():
        raise SystemExit(
            f"{ANNOTATIONS_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.annotate` first -- "
            "this requires a human annotator, it cannot be generated automatically."
        )
    annotations = json.loads(ANNOTATIONS_PATH.read_text())
    n_annotated = len(annotations)

    if n_annotated == 0:
        print("0 candidates annotated yet -- nothing to score.")
        return
    if n_annotated < 20:
        print(
            f"WARNING: only {n_annotated} candidates annotated. Any metric below "
            f"is a pilot-scale estimate, not a publishable accuracy figure -- "
            f"say so explicitly if you report it.\n"
        )

    per_field_counts: dict[str, Counter] = {f: Counter() for f in FIELDS}
    for record in annotations.values():
        for field, judgment in record["field_judgments"].items():
            per_field_counts[field][judgment] += 1

    print(f"n = {n_annotated} human-annotated candidates\n")
    print(f"{'field':<14}{'n':>5}{'correct_rate':>15}{'hallucination_rate':>21}{'missing_rate':>15}")
    overall_counts: Counter = Counter()
    for field in FIELDS:
        counts = per_field_counts[field]
        total = sum(counts.values())
        overall_counts.update(counts)
        if total == 0:
            print(f"{field:<14}{0:>5}{'n/a':>15}{'n/a':>21}{'n/a':>15}")
            continue
        correct_rate = sum(counts[k] for k in CORRECT_LABELS) / total
        hallucination_rate = counts["hallucinated"] / total
        missing_rate = counts["missing"] / total
        print(f"{field:<14}{total:>5}{correct_rate:>15.2%}{hallucination_rate:>21.2%}{missing_rate:>15.2%}")

    total_all = sum(overall_counts.values())
    if total_all:
        overall_correct = sum(overall_counts[k] for k in CORRECT_LABELS) / total_all
        overall_hallucination = overall_counts["hallucinated"] / total_all
        overall_missing = overall_counts["missing"] / total_all
        print(f"\n{'OVERALL':<14}{total_all:>5}{overall_correct:>15.2%}{overall_hallucination:>21.2%}{overall_missing:>15.2%}")

    print(
        "\nNote: 'hallucination_rate' here is exactly the HLD's stated "
        "'Unsupported extraction rate' safety metric (docs/High_Level_Design.md "
        "§ Success Metrics) -- fraction of extracted-and-non-null fields the "
        "annotator judged as unsupported by the source text."
    )


if __name__ == "__main__":
    main()
