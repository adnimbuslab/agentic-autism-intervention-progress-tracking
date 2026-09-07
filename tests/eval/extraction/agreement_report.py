"""Inter-annotator agreement over the double-annotated batch.

Single-annotator ground truth carries no reliability estimate. This computes
Cohen's kappa per field across the segments two annotators both judged, which
is what lets the annotation protocol be reported rather than asserted.

Kappa is also the empirical anchor for the MARS agreement threshold -- but only
as an anchor. Human annotators judge fields against raw source text while MARS
judges rank a supplied candidate set; the two measure different tasks and their
numbers are not interchangeable. See docs/lld/Mars_Reranking.md, "Agreement
threshold selection".

Usage:
    uv run python -m tests.eval.extraction.agreement_report annotator_a annotator_b
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]


def annotations_path(annotator: str) -> Path:
    return RESULTS_DIR / f"annotations_{annotator}.json"


def observed_agreement(pairs: list[tuple[str, str]]) -> float:
    """Share of items the two annotators judged identically."""
    if not pairs:
        return 0.0
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def expected_agreement(pairs: list[tuple[str, str]]) -> float:
    """Agreement predicted by each annotator's own marginal distribution.

    This is what kappa corrects for: two annotators who both label almost
    everything "correct" will agree often by construction, and a raw agreement
    rate would read that as reliability.
    """
    if not pairs:
        return 0.0
    n = len(pairs)
    first = Counter(a for a, _ in pairs)
    second = Counter(b for _, b in pairs)
    categories = set(first) | set(second)
    return sum((first[c] / n) * (second[c] / n) for c in categories)


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa, or None where it is undefined.

    Undefined when chance agreement is total -- every item in one category, so
    there is no room for agreement beyond chance to be measured. Reporting 0.0
    there would understate reliability; reporting 1.0 would overstate it.
    """
    if not pairs:
        return None
    p_o = observed_agreement(pairs)
    p_e = expected_agreement(pairs)
    if p_e >= 1.0:
        return None
    return (p_o - p_e) / (1.0 - p_e)


def interpret(kappa: float | None) -> str:
    """Landis & Koch bands, for orientation only.

    These are conventional labels, not thresholds anything depends on.
    """
    if kappa is None:
        return "undefined"
    for bound, label in (
        (0.0, "poor"),
        (0.20, "slight"),
        (0.40, "fair"),
        (0.60, "moderate"),
        (0.80, "substantial"),
    ):
        if kappa <= bound:
            return label
    return "almost perfect"


def paired_judgments(
    first: dict[str, Any], second: dict[str, Any], field: str
) -> list[tuple[str, str]]:
    """Judgments for one field on every segment both annotators covered."""
    shared = sorted(set(first) & set(second))
    pairs: list[tuple[str, str]] = []
    for segment_id in shared:
        a = first[segment_id].get("field_judgments", {}).get(field)
        b = second[segment_id].get("field_judgments", {}).get(field)
        if a is not None and b is not None:
            pairs.append((a, b))
    return pairs


def build_report(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    overlap = sorted(set(first) & set(second))
    per_field = {}
    for field in FIELDS:
        pairs = paired_judgments(first, second, field)
        per_field[field] = {
            "n": len(pairs),
            "observed_agreement": round(observed_agreement(pairs), 4) if pairs else None,
            "expected_agreement": round(expected_agreement(pairs), 4) if pairs else None,
            "kappa": (round(k, 4) if (k := cohens_kappa(pairs)) is not None else None),
            "interpretation": interpret(cohens_kappa(pairs)),
        }

    disputed = [
        segment_id
        for segment_id in overlap
        if any(
            first[segment_id].get("field_judgments", {}).get(f)
            != second[segment_id].get("field_judgments", {}).get(f)
            for f in FIELDS
        )
    ]

    return {
        "n_overlap_segments": len(overlap),
        "n_annotator_a_only": len(set(first) - set(second)),
        "n_annotator_b_only": len(set(second) - set(first)),
        "per_field": per_field,
        "n_disputed_segments": len(disputed),
        "disputed_segments": disputed,
        "note": (
            "Kappa is computed over the double-annotated overlap only. Disputed "
            "segments require adjudication before they enter the gold standard; "
            "an unadjudicated disagreement is not a label."
        ),
    }


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)

    names = sys.argv[1], sys.argv[2]
    loaded = []
    for name in names:
        path = annotations_path(name)
        if not path.exists():
            raise SystemExit(
                f"{path} not found. Each annotator writes their own file; run "
                f"`uv run python -m tests.eval.extraction.annotate_batch {name}` first."
            )
        loaded.append(json.loads(path.read_text()))

    report = build_report(*loaded)
    out = RESULTS_DIR / f"agreement_{names[0]}_{names[1]}.json"
    out.write_text(json.dumps(report, indent=2))

    print(f"Inter-annotator agreement: {names[0]} vs {names[1]}")
    print(f"  double-annotated segments: {report['n_overlap_segments']}")
    print(f"  segments with any disagreement: {report['n_disputed_segments']}")
    print()
    header = f"  {'field':14s} {'n':>5s} {'observed':>9s} {'kappa':>7s}  interpretation"
    print(header)
    for field, stats in report["per_field"].items():
        kappa = "n/a" if stats["kappa"] is None else f"{stats['kappa']:.3f}"
        observed = (
            "n/a" if stats["observed_agreement"] is None
            else f"{stats['observed_agreement']:.3f}"
        )
        print(
            f"  {field:14s} {stats['n']:5d} {observed:>9s} "
            f"{kappa:>7s}  {stats['interpretation']}"
        )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
