"""Interval estimates and marginal diagnostics for the reliability figures.

`agreement_report` answers "what is kappa". A manuscript has to answer three
further questions, and each is a separate computation:

  1. **How precisely is it estimated?** A point kappa over 330 segments without
     an interval invites a reader to compare 0.570 against 0.595 as though the
     difference were real.

  2. **Could it have been higher?** Kappa is bounded above by the annotators'
     marginal distributions. Where one annotator used a category the other
     never used at all -- round 1's `modality`, where annotator A recorded 75
     nulls and annotator B none -- kappa is held down by that mismatch and no
     amount of care on the individual segments could have lifted it. `kappa_max`
     separates the two, and the separation is the finding: a low kappa with a
     low `kappa_max` is a definitional problem, not a careless annotator.

  3. **Did the intervention move it?** Round 1 and round 2 are the same
     annotators over the same segments, so the rounds are paired and the
     interval belongs on the *difference*, computed by resampling segments
     rather than by comparing two independent intervals.

Two interval estimators are computed and reported together. The bootstrap is
the one reported: it is assumption-light and survives the sparse categories
these fields actually have. The Fleiss-Cohen-Everitt large-sample variance is
computed alongside as a check -- when an assumption-light and an asymptotic
estimator agree, neither is carrying an error, and when they diverge the
asymptotic one is the one to distrust at these category counts.

Nothing here is reported for a round that does not exist. `delta_kappa` returns
None rather than a number when round 2 has not been imported.

Usage:
    uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b
    uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b --round1
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

from tests.eval.extraction.agreement_report import (
    CATEGORICAL_FIELDS,
    annotations_path,
    cohens_kappa,
    expected_agreement,
    interpret,
    observed_agreement,
    paired_values,
    shared_segments,
)

RESULTS_DIR = Path(__file__).parent / "results"

N_BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 20260915
ALPHA = 0.05


def kappa_max(pairs: list[tuple[str, str]]) -> float | None:
    """The largest kappa attainable while holding both marginals fixed.

    Observed agreement cannot exceed the overlap of the two marginal
    distributions: if annotator A used `none` 75 times and annotator B never
    used it, 75 items are forced to disagree before any segment is read. That
    ceiling is sum_i min(p_i., p_.i), and feeding it through the kappa formula
    gives the best the pair could have done at those marginals.
    """
    if not pairs:
        return None
    n = len(pairs)
    first = Counter(a for a, _ in pairs)
    second = Counter(b for _, b in pairs)
    p_o_max = sum(
        min(first[c], second[c]) / n for c in set(first) | set(second)
    )
    p_e = expected_agreement(pairs)
    if p_e >= 1.0:
        return None
    return (p_o_max - p_e) / (1.0 - p_e)


def asymptotic_variance(pairs: list[tuple[str, str]]) -> float | None:
    """Large-sample variance of Cohen's kappa (Fleiss, Cohen & Everitt, 1969).

        var = 1 / (n (1 - p_e)^4) * [ A + B - C ]

        A = sum_i p_ii [ (1 - p_e) - (p_i. + p_.i)(1 - p_o) ]^2
        B = (1 - p_o)^2 * sum_i sum_{j != i} p_ij (p_.i + p_j.)^2
        C = ( p_o p_e - 2 p_e + p_o )^2

    Reported as a cross-check on the bootstrap, not as the headline interval:
    the asymptotic approximation degrades exactly where these fields live, with
    several categories carrying only a handful of observations.
    """
    if not pairs:
        return None
    n = len(pairs)
    p_e = expected_agreement(pairs)
    p_o = observed_agreement(pairs)
    if p_e >= 1.0:
        return None

    joint = Counter(pairs)
    row = Counter(a for a, _ in pairs)
    col = Counter(b for _, b in pairs)
    categories = sorted(set(row) | set(col))

    p_row = {c: row[c] / n for c in categories}
    p_col = {c: col[c] / n for c in categories}

    term_a = sum(
        (joint[(c, c)] / n) * ((1 - p_e) - (p_row[c] + p_col[c]) * (1 - p_o)) ** 2
        for c in categories
    )
    term_b = (1 - p_o) ** 2 * sum(
        (count / n) * (p_col[i] + p_row[j]) ** 2
        for (i, j), count in joint.items()
        if i != j
    )
    term_c = (p_o * p_e - 2 * p_e + p_o) ** 2

    return (term_a + term_b - term_c) / (n * (1 - p_e) ** 4)


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile; `statistics.quantiles` cannot take one."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def bootstrap_kappa(
    pairs: list[tuple[str, str]],
    n_boot: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = ALPHA,
) -> dict[str, Any]:
    """Percentile bootstrap interval, resampling segments with replacement.

    Resamples that collapse to a single category leave kappa undefined rather
    than zero; they are dropped and counted, so a field whose interval rests on
    fewer replicates than requested says so instead of quietly narrowing.
    """
    if not pairs:
        return {"lower": None, "upper": None, "n_valid": 0, "n_requested": n_boot}

    rng = random.Random(seed)
    n = len(pairs)
    replicates: list[float] = []
    for _ in range(n_boot):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        value = cohens_kappa(sample)
        if value is not None:
            replicates.append(value)

    if not replicates:
        return {"lower": None, "upper": None, "n_valid": 0, "n_requested": n_boot}
    return {
        "lower": round(_percentile(replicates, alpha / 2), 4),
        "upper": round(_percentile(replicates, 1 - alpha / 2), 4),
        "n_valid": len(replicates),
        "n_requested": n_boot,
    }


def field_statistics(
    pairs: list[tuple[str, str]],
    n_boot: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Every reliability quantity reported for one field."""
    kappa = cohens_kappa(pairs)
    ceiling = kappa_max(pairs)
    variance = asymptotic_variance(pairs)
    se = math.sqrt(variance) if variance is not None and variance > 0 else None

    asymptotic: dict[str, Any] = {"se": None, "lower": None, "upper": None}
    if se is not None and kappa is not None:
        z = 1.959963984540054  # two-sided 95%
        asymptotic = {
            "se": round(se, 4),
            "lower": round(kappa - z * se, 4),
            "upper": round(kappa + z * se, 4),
        }

    return {
        "n": len(pairs),
        "n_categories_used": len({v for pair in pairs for v in pair}),
        "observed_agreement": round(observed_agreement(pairs), 4) if pairs else None,
        "expected_agreement": round(expected_agreement(pairs), 4) if pairs else None,
        "kappa": round(kappa, 4) if kappa is not None else None,
        "kappa_max": round(ceiling, 4) if ceiling is not None else None,
        "kappa_over_kappa_max": (
            round(kappa / ceiling, 4)
            if kappa is not None and ceiling not in (None, 0)
            else None
        ),
        "interpretation": interpret(kappa),
        "bootstrap_ci": bootstrap_kappa(pairs, n_boot=n_boot, seed=seed),
        "asymptotic_ci": asymptotic,
    }


def delta_kappa(
    before: list[tuple[str, str]],
    after: list[tuple[str, str]] | None,
    n_boot: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = ALPHA,
) -> dict[str, Any] | None:
    """Paired bootstrap interval on the change in kappa between two rounds.

    The two rounds share segments and annotators, so the replicates must be
    drawn over a common segment index and both kappas recomputed on the same
    draw. Two independent intervals compared by eye would ignore that pairing
    and overstate the uncertainty on the difference.

    Returns None when the later round does not exist. A manuscript number for a
    round that has not been annotated is the one thing this module must not
    produce.
    """
    if after is None:
        return None
    if len(before) != len(after):
        raise ValueError(
            f"paired rounds must cover the same items: {len(before)} vs {len(after)}"
        )

    kappa_before = cohens_kappa(before)
    kappa_after = cohens_kappa(after)
    if kappa_before is None or kappa_after is None:
        return None

    rng = random.Random(seed)
    n = len(before)
    replicates: list[float] = []
    for _ in range(n_boot):
        index = [rng.randrange(n) for _ in range(n)]
        one = cohens_kappa([before[i] for i in index])
        two = cohens_kappa([after[i] for i in index])
        if one is not None and two is not None:
            replicates.append(two - one)

    if not replicates:
        return None
    lower = _percentile(replicates, alpha / 2)
    upper = _percentile(replicates, 1 - alpha / 2)
    return {
        "kappa_before": round(kappa_before, 4),
        "kappa_after": round(kappa_after, 4),
        "delta": round(kappa_after - kappa_before, 4),
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "excludes_zero": bool(lower > 0 or upper < 0),
        "n_valid": len(replicates),
    }


def mean_kappa(per_field: dict[str, Any]) -> float | None:
    """Mean of the per-field kappas over the categorical fields.

    Not a pooled kappa. The fields draw on different category sets, so a pooled
    confusion matrix would chance-correct against a distribution no annotator
    ever drew from -- the same argument `agreement_report` makes.
    """
    values = [
        per_field[f]["kappa"]
        for f in CATEGORICAL_FIELDS
        if per_field.get(f, {}).get("kappa") is not None
    ]
    return round(sum(values) / len(values), 4) if values else None


def build_report(
    first: dict[str, Any],
    second: dict[str, Any],
    label: str,
    n_boot: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    segments = shared_segments(first, second)
    per_field = {
        field: field_statistics(
            paired_values(first, second, field, segments), n_boot=n_boot, seed=seed
        )
        for field in CATEGORICAL_FIELDS
    }
    return {
        "label": label,
        "n_segments": len(segments),
        "n_bootstrap": n_boot,
        "bootstrap_seed": seed,
        "fields": per_field,
        "mean_kappa": mean_kappa(per_field),
    }


def render(report: dict[str, Any]) -> None:
    print(f"Reliability: {report['label']}  (n = {report['n_segments']} segments)")
    print(f"  {report['n_bootstrap']} bootstrap replicates, seed {report['bootstrap_seed']}\n")
    header = (
        f"  {'field':<14}{'n':>5}{'p_o':>8}{'p_e':>8}{'kappa':>8}"
        f"{'95% CI (boot)':>18}{'SE':>8}{'k_max':>8}{'k/k_max':>9}"
    )
    print(header)
    for field, stats in report["fields"].items():
        boot = stats["bootstrap_ci"]
        interval = (
            f"[{boot['lower']:.3f}, {boot['upper']:.3f}]"
            if boot["lower"] is not None
            else "--"
        )
        se = stats["asymptotic_ci"]["se"]
        print(
            f"  {field:<14}{stats['n']:>5}"
            f"{stats['observed_agreement']:>8.3f}{stats['expected_agreement']:>8.3f}"
            f"{stats['kappa']:>8.3f}{interval:>18}"
            f"{(f'{se:.3f}' if se is not None else '--'):>8}"
            f"{stats['kappa_max']:>8.3f}{stats['kappa_over_kappa_max']:>9.3f}"
        )
    print(f"\n  mean kappa across {len(report['fields'])} categorical fields: "
          f"{report['mean_kappa']:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs=2)
    parser.add_argument(
        "--round1",
        action="store_true",
        help="Read the frozen gold_<annotator>_round1.json snapshots.",
    )
    parser.add_argument("--n-boot", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    suffix = "_round1" if args.round1 else ""
    paths = [annotations_path(f"{a}{suffix}") for a in args.annotators]
    for path in paths:
        if not path.exists():
            raise SystemExit(f"{path} not found.")

    first, second = (json.loads(p.read_text()) for p in paths)
    label = f"{args.annotators[0]} vs {args.annotators[1]}" + (
        " (round 1, pre-codebook)" if args.round1 else ""
    )
    report = build_report(first, second, label, n_boot=args.n_boot, seed=args.seed)
    render(report)

    out = args.out or RESULTS_DIR / f"reliability{suffix or '_current'}.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
