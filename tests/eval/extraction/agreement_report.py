"""Inter-annotator agreement over the double-annotated gold standard.

Both annotators author gold field values from the transcript, independently,
over all 330 segments. Agreement is therefore computed on the *values* -- is
this segment's domain `language` or `play`? -- rather than on judgements of a
model's output. That is the quantity the study reports, and it is a property of
the annotation protocol alone, unaffected by which generators happen to be in
the batch.

Cohen's kappa is computed per field. Kappa is *not* pooled across fields by
concatenating labels: the fields draw on different category sets, so a pooled
confusion matrix would treat `verbal`-the-modality and `verbal`-the-prompt-level
as one category and compute a chance correction for a distribution that no
annotator ever drew from. The reported overall figures are instead a mean of
the per-field kappas and a record-level exact-agreement rate, both of which
state plainly what they aggregate.

`behavior` is free text. Exact-match agreement on prose understates real
agreement badly, so it is reported descriptively (exact and token-overlap
rates) and excluded from the mean kappa. Whether two behaviour descriptions
say the same thing is settled by a human at adjudication, not by string
comparison here.

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
FREE_TEXT_FIELDS = frozenset({"behavior"})
CATEGORICAL_FIELDS = [f for f in FIELDS if f not in FREE_TEXT_FIELDS]

# A null gold value is a substantive judgement ("the transcript supports
# nothing here"), so it is a category like any other rather than missing data.
NULL_CATEGORY = "__null__"


def annotations_path(annotator: str) -> Path:
    return RESULTS_DIR / f"gold_{annotator}.json"


def observed_agreement(pairs: list[tuple[str, str]]) -> float:
    """Share of items the two annotators judged identically."""
    if not pairs:
        return 0.0
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def expected_agreement(pairs: list[tuple[str, str]]) -> float:
    """Agreement predicted by each annotator's own marginal distribution.

    This is what kappa corrects for: two annotators who both label almost
    everything the same way will agree often by construction, and a raw
    agreement rate would read that as reliability.
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


def normalize(value: object) -> str:
    """Map a recorded value to a comparison key, nulls included as a category."""
    if value is None:
        return NULL_CATEGORY
    text = " ".join(str(value).split()).casefold()
    return text or NULL_CATEGORY


def shared_segments(first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    """Segments both annotators completed."""
    return sorted(set(first) & set(second))


def paired_values(
    first: dict[str, Any],
    second: dict[str, Any],
    field: str,
    segments: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Both annotators' values for one field, over the segments they share.

    A segment is paired only where both recorded the field at all. A field one
    annotator never reached is missing data, distinct from one they recorded as
    null -- which is a value and pairs normally.
    """
    if segments is None:
        segments = shared_segments(first, second)
    pairs: list[tuple[str, str]] = []
    for segment_id in segments:
        a = first[segment_id].get("field_values", {})
        b = second[segment_id].get("field_values", {})
        if field in a and field in b:
            pairs.append((normalize(a[field]), normalize(b[field])))
    return pairs


def token_overlap(first: str, second: str) -> float:
    """Jaccard overlap of word sets -- a floor on free-text agreement.

    Reported for `behavior` because exact match on prose is close to
    meaningless, and because a bare "annotators rarely matched" would be read
    as disagreement about the child's behaviour when it is usually a difference
    in wording.
    """
    a = {t for t in first.split() if t not in {NULL_CATEGORY}}
    b = {t for t in second.split() if t not in {NULL_CATEGORY}}
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def free_text_report(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    both_null = sum(1 for a, b in pairs if a == NULL_CATEGORY and b == NULL_CATEGORY)
    return {
        "n": len(pairs),
        "exact_agreement": round(observed_agreement(pairs), 4) if pairs else None,
        "mean_token_overlap": (
            round(sum(token_overlap(a, b) for a, b in pairs) / len(pairs), 4)
            if pairs
            else None
        ),
        "both_null": both_null,
        "kappa": None,
        "interpretation": "not applicable (free text)",
    }


def categorical_report(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    kappa = cohens_kappa(pairs)
    return {
        "n": len(pairs),
        "observed_agreement": round(observed_agreement(pairs), 4) if pairs else None,
        "expected_agreement": round(expected_agreement(pairs), 4) if pairs else None,
        "kappa": round(kappa, 4) if kappa is not None else None,
        "interpretation": interpret(kappa),
        "n_categories_used": len({v for pair in pairs for v in pair}),
    }


def per_field_report(
    first: dict[str, Any], second: dict[str, Any], segments: list[str]
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for field in FIELDS:
        pairs = paired_values(first, second, field, segments)
        report[field] = (
            free_text_report(pairs)
            if field in FREE_TEXT_FIELDS
            else categorical_report(pairs)
        )
    return report


def record_exact_agreement(
    first: dict[str, Any], second: dict[str, Any], segments: list[str]
) -> float | None:
    """Share of segments where both annotators matched on every field.

    Descriptive, not chance-corrected, and strict: it includes free-text
    `behavior`, so it is a lower bound on how often the two produced the same
    record rather than an estimate of reliability.
    """
    if not segments:
        return None
    matched = 0
    for segment_id in segments:
        a = first[segment_id].get("field_values", {})
        b = second[segment_id].get("field_values", {})
        if all(normalize(a.get(f)) == normalize(b.get(f)) for f in FIELDS):
            matched += 1
    return matched / len(segments)


def build_report(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    segments = shared_segments(first, second)
    per_field = per_field_report(first, second, segments)

    kappas = [
        per_field[f]["kappa"] for f in CATEGORICAL_FIELDS if per_field[f]["kappa"] is not None
    ]
    disputed = [
        segment_id
        for segment_id in segments
        if any(
            normalize(first[segment_id].get("field_values", {}).get(f))
            != normalize(second[segment_id].get("field_values", {}).get(f))
            for f in FIELDS
        )
    ]

    return {
        "n_overlap_segments": len(segments),
        "n_annotator_a_only": len(set(first) - set(second)),
        "n_annotator_b_only": len(set(second) - set(first)),
        "per_field": per_field,
        "overall": {
            "mean_kappa_categorical": round(sum(kappas) / len(kappas), 4) if kappas else None,
            "n_fields_in_mean": len(kappas),
            "fields_in_mean": CATEGORICAL_FIELDS,
            "record_exact_agreement": (
                round(r, 4)
                if (r := record_exact_agreement(first, second, segments)) is not None
                else None
            ),
            "basis": (
                "Mean of the per-field kappas over categorical fields. Kappa is "
                "not pooled across fields by concatenating labels: the fields "
                "use different category sets, so a pooled chance correction "
                "would be computed over a distribution no annotator drew from. "
                "behavior is free text and is excluded from the mean."
            ),
        },
        "n_disputed_segments": len(disputed),
        "disputed_segments": disputed,
        "note": (
            "Agreement is on gold field values authored from the transcript, "
            "not on judgements of model output. Disputed segments require "
            "adjudication before they enter the gold standard; an unadjudicated "
            "disagreement is not a label."
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
                f"`uv run python -m tests.eval.extraction.annotate_gold {name}` first."
            )
        loaded.append(json.loads(path.read_text()))

    report = build_report(*loaded)
    out = RESULTS_DIR / f"agreement_{names[0]}_{names[1]}.json"
    out.write_text(json.dumps(report, indent=2))

    print(f"Inter-annotator agreement: {names[0]} vs {names[1]}")
    print(f"  double-annotated segments: {report['n_overlap_segments']}")
    print(f"  segments with any disagreement: {report['n_disputed_segments']}")
    print()
    print(f"  {'field':14s} {'n':>5s} {'observed':>9s} {'kappa':>7s}  interpretation")
    for field, stats in report["per_field"].items():
        kappa = "n/a" if stats["kappa"] is None else f"{stats['kappa']:.3f}"
        observed = stats.get("observed_agreement") or stats.get("exact_agreement")
        observed_text = "n/a" if observed is None else f"{observed:.3f}"
        print(
            f"  {field:14s} {stats['n']:5d} {observed_text:>9s} "
            f"{kappa:>7s}  {stats['interpretation']}"
        )

    behavior = report["per_field"]["behavior"]
    if behavior["mean_token_overlap"] is not None:
        print(f"\n  behavior mean token overlap: {behavior['mean_token_overlap']:.3f}")

    overall = report["overall"]
    mean_kappa = overall["mean_kappa_categorical"]
    print(
        f"\n  mean kappa ({overall['n_fields_in_mean']} categorical fields): "
        + ("n/a" if mean_kappa is None else f"{mean_kappa:.3f}")
    )
    exact = overall["record_exact_agreement"]
    print(
        "  whole-record exact agreement: "
        + ("n/a" if exact is None else f"{exact:.3f}")
    )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
