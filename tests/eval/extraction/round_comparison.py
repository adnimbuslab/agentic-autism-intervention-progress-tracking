"""Pre-registered comparison of reliability before and after the codebook.

The analysis this implements is fixed now, before round 2 exists, because a
comparison designed after seeing its own result is not a comparison. Running it
today reports that round 2 has not been imported; it invents nothing.

**The estimand.** Per-field change in Cohen's kappa over the 178 re-issued
segments, round 1 against round 2, with a 95% interval from a paired bootstrap
over segments. Restricting to the re-issued segments is what makes the two
rounds comparable: the other 152 carry round-1 values in both, so including
them would dilute any change by a constant and understate it.

**The control.** `domain` is re-annotated in round 2 along with every other
field -- re-annotating a segment's `modality` while leaving a `domain` someone
already committed to is not an independent judgement -- but no codebook rule
touches `domain`. It therefore carries the same practice, fatigue and
regression-to-the-mean effects as the treated fields and none of the
instruction. If `modality`, `prompt_level` and `outcome` improve while `domain`
does not, the improvement is attributable to the codebook. If `domain` moves as
much as the rest, it is not: the honest reading would then be that
re-annotation, not the rules, produced the change.

That inference is the reason `domain` conflicts were left out of the re-issue
selection rather than swept in for convenience.

**What this cannot establish.** Two annotators converging on a stated rule is
agreement, not correctness. A codebook that told both annotators to record
`gestural` everywhere would drive kappa to 1.0 and the gold standard to
nonsense. Reliability after the codebook is a necessary condition for a usable
gold standard and not a sufficient one; validity rests on the rules themselves
being defensible, which is an argument made in prose and adjudicated by a
human, not a number this module produces.

Usage:
    uv run python -m tests.eval.extraction.round_comparison annotator_a annotator_b
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tests.eval.extraction.agreement_report import (
    CATEGORICAL_FIELDS,
    annotations_path,
    paired_values,
)
from tests.eval.extraction.reliability_stats import (
    BOOTSTRAP_SEED,
    N_BOOTSTRAP,
    delta_kappa,
    field_statistics,
)

RESULTS_DIR = Path(__file__).parent / "results"
SELECTION_PATH = RESULTS_DIR / "reissue_round2_selection.json"

# Fields the codebook speaks to. `domain` is deliberately absent -- it is the
# control, and naming it here would make it look like a treated field.
TREATED_FIELDS = ["modality", "prompt_level", "outcome"]
CONTROL_FIELDS = [f for f in CATEGORICAL_FIELDS if f not in TREATED_FIELDS]


def round2_present(first: dict[str, Any], second: dict[str, Any], segments: list[str]) -> bool:
    """True once either annotator has a round-2 record among the re-issued set."""
    return any(
        source[s].get("round", 1) >= 2
        for source in (first, second)
        for s in segments
        if s in source
    )


def compare(
    before_a: dict[str, Any],
    before_b: dict[str, Any],
    after_a: dict[str, Any],
    after_b: dict[str, Any],
    segments: list[str],
    n_boot: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Per-field before/after statistics and the paired interval on the change."""
    fields: dict[str, Any] = {}
    for field in CATEGORICAL_FIELDS:
        before = paired_values(before_a, before_b, field, segments)
        after = paired_values(after_a, after_b, field, segments)
        fields[field] = {
            "arm": "treated" if field in TREATED_FIELDS else "control",
            "round1": field_statistics(before, n_boot=n_boot, seed=seed),
            "round2": field_statistics(after, n_boot=n_boot, seed=seed),
            "delta": delta_kappa(before, after, n_boot=n_boot, seed=seed),
        }
    return {"n_segments": len(segments), "fields": fields}


def render(report: dict[str, Any]) -> None:
    print(f"Round 1 vs round 2, over the {report['n_segments']} re-issued segments\n")
    print(f"  {'field':<14}{'arm':>9}{'k round1':>10}{'k round2':>10}"
          f"{'delta':>9}{'95% CI (paired)':>20}")
    for field, entry in report["fields"].items():
        delta = entry["delta"]
        if delta is None:
            print(f"  {field:<14}{entry['arm']:>9}"
                  f"{entry['round1']['kappa']:>10.3f}{'--':>10}{'--':>9}{'--':>20}")
            continue
        interval = f"[{delta['lower']:+.3f}, {delta['upper']:+.3f}]"
        mark = "  *" if delta["excludes_zero"] else ""
        print(f"  {field:<14}{entry['arm']:>9}"
              f"{delta['kappa_before']:>10.3f}{delta['kappa_after']:>10.3f}"
              f"{delta['delta']:>+9.3f}{interval:>20}{mark}")
    print("\n  * interval excludes zero")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotators", nargs=2)
    parser.add_argument("--n-boot", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    args = parser.parse_args()

    if not SELECTION_PATH.exists():
        raise SystemExit(
            f"{SELECTION_PATH} not found. Run reissue_gold_sheet first -- the "
            "comparison is defined over the segments it selected."
        )
    segments = sorted(json.loads(SELECTION_PATH.read_text())["selected"])

    first, second = args.annotators
    paths = {
        "before_a": annotations_path(f"{first}_round1"),
        "before_b": annotations_path(f"{second}_round1"),
        "after_a": annotations_path(first),
        "after_b": annotations_path(second),
    }
    for name, path in paths.items():
        if not path.exists():
            raise SystemExit(f"{path} not found ({name}).")
    loaded = {name: json.loads(path.read_text()) for name, path in paths.items()}

    if not round2_present(loaded["after_a"], loaded["after_b"], segments):
        print(
            f"Round 2 has not been imported: none of the {len(segments)} re-issued "
            "segments carries a round-2 record.\n"
            "The comparison is defined and tested; it reports numbers once the "
            "returned sheets are merged with\n"
            "  uv run python -m tests.eval.extraction.import_gold_sheet "
            "<annotator> --path <sheet> --merge"
        )
        raise SystemExit(0)

    report = compare(
        loaded["before_a"], loaded["before_b"],
        loaded["after_a"], loaded["after_b"],
        segments, n_boot=args.n_boot, seed=args.seed,
    )
    render(report)

    out = RESULTS_DIR / "round_comparison.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
