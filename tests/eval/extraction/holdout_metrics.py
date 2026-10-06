"""Extraction metrics on the model-independent held-out set, beside the batch.

The 330-segment annotation batch was built by retaining only segments where
every generator produced an admissible response. That is a defensible way to
get a batch worth annotating, and it conditions the batch on model behaviour:
segments all three models found tractable are over-represented, so accuracy
measured there is an optimistic estimate of accuracy on segments drawn without
reference to any model.

The held-out set was drawn without that filter. Scoring the same generators
against both, over the same fields with the same rules, is what turns "the
batch may be easy" from an objection into a measured quantity. This script
reports the two side by side and the difference between them.

It computes nothing new: both sides come from `summarise_scored`, the same
function the extended-roster block uses. What is new is the pairing.

Usage:
    uv run python -m tests.eval.extraction.holdout_metrics
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.extraction.paper_metrics import summarise_scored

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_SCORED = RESULTS_DIR / "scored_against_gold_augmented.json"
HOLDOUT_SCORED = RESULTS_DIR / "scored_holdout.json"
HOLDOUT_GOLD = RESULTS_DIR / "gold_holdout_labels.json"
OUT_PATH = RESULTS_DIR / "holdout_metrics.json"


class PolicyMismatchError(Exception):
    """The two sides were scored under rules that do not compare."""


def check_same_policy(batch: dict[str, Any], holdout: dict[str, Any]) -> None:
    """Refuse to compare accuracies computed under different scoring rules.

    Mean field accuracy over four categorical fields and over those four plus
    free-text behavior are different quantities. Subtracting one from the other
    yields a plausible-looking number with no meaning, and nothing downstream
    would reveal it -- the published policy excludes behavior, so a held-out
    file scored with the default overlap rule would have silently understated
    the held-out side and inflated the reported selection effect.
    """
    for key in ("scoring_fields", "behavior_match", "behavior_overlap_threshold"):
        left, right = batch.get(key), holdout.get(key)
        if left != right:
            raise PolicyMismatchError(
                f"batch and held-out disagree on {key}: {left!r} vs {right!r}. "
                "Re-score one side with the other's policy; accuracies "
                "computed under different rules are not comparable."
            )


def build(batch: dict[str, Any], holdout: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    check_same_policy(batch, holdout)
    batch_summary = summarise_scored(batch)
    holdout_summary = summarise_scored(holdout)

    # Only generators present on both sides can be compared. The rosters do
    # match today; pairing on the intersection means they need not, and a
    # missing model is recorded rather than crashing the comparison.
    shared = [m for m in holdout["models"] if m in batch["models"]]

    delta: dict[str, Any] = {}
    for model in shared:
        b = batch_summary["per_model"][model]
        h = holdout_summary["per_model"][model]
        delta[model] = {
            "mean_field_accuracy": {
                "batch": b["mean_field_accuracy"],
                "holdout": h["mean_field_accuracy"],
                "delta": round(
                    h["mean_field_accuracy"] - b["mean_field_accuracy"], 4
                ),
            },
            "per_field_delta": {
                field: round(
                    (h["per_field_accuracy"][field] or 0.0)
                    - (b["per_field_accuracy"][field] or 0.0),
                    4,
                )
                for field in holdout["scoring_fields"]
            },
            "unsupported_rate": {
                "batch": b["unsupported_rate"],
                "holdout": h["unsupported_rate"],
                "delta": (
                    round(h["unsupported_rate"] - b["unsupported_rate"], 4)
                    if b["unsupported_rate"] is not None
                    and h["unsupported_rate"] is not None
                    else None
                ),
            },
            "mean_abstention_rate": {
                "batch": b["mean_abstention_rate"],
                "holdout": h["mean_abstention_rate"],
                "delta": round(
                    h["mean_abstention_rate"] - b["mean_abstention_rate"], 4
                ),
            },
        }

    bw, hw = batch_summary["whole_record"], holdout_summary["whole_record"]
    best_batch = max(bw["per_generator"].values()) if bw["per_generator"] else 0.0
    best_holdout = max(hw["per_generator"].values()) if hw["per_generator"] else 0.0

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "batch": {
            "source": batch.get("source_batch"),
            "n_segments": batch["n_segments_scored"],
            **batch_summary,
        },
        "holdout": {
            "source": holdout.get("source_batch"),
            "source_gold": holdout.get("source_gold"),
            "n_segments": holdout["n_segments_scored"],
            "n_segments_double_annotated": gold["n_segments_double_annotated"],
            "adjudicator": gold.get("adjudicator"),
            **holdout_summary,
        },
        "models_compared": shared,
        "fields": holdout["scoring_fields"],
        "scoring_policy": {
            "behavior_match": holdout["behavior_match"],
            "scored_fields": holdout["scoring_fields"],
        },
        "delta": delta,
        "whole_record": {
            "batch": {
                "best_generator": best_batch,
                "oracle_ceiling": bw["oracle_ceiling"],
                "headroom": round(bw["oracle_ceiling"] - best_batch, 4),
            },
            "holdout": {
                "best_generator": best_holdout,
                "oracle_ceiling": hw["oracle_ceiling"],
                "headroom": round(hw["oracle_ceiling"] - best_holdout, 4),
            },
        },
        "note": (
            "Both sides are scored by score_against_gold against their own "
            "model-independent adjudicated gold, over the same fields with the "
            "same behavior-matching rule. A negative delta means the generator "
            "did worse on segments that were not selected for model "
            "tractability, which is the quantity the held-out set exists to "
            "measure. The two golds were adjudicated by the same pair, so the "
            "comparison controls for the segment selection and not for the "
            "adjudicators."
        ),
    }


def render(report: dict[str, Any]) -> None:
    pct = lambda v: "n/a" if v is None else f"{100 * v:.1f}%"  # noqa: E731
    signed = lambda v: "n/a" if v is None else f"{100 * v:+.1f}"  # noqa: E731

    print("=" * 78)
    print("HELD-OUT SET vs ANNOTATION BATCH")
    print("=" * 78)
    print(
        f"batch   {report['batch']['n_segments']:>4} segments  "
        f"({report['batch']['source']})"
    )
    print(
        f"holdout {report['holdout']['n_segments']:>4} segments  "
        f"({report['holdout']['source']}, gold "
        f"{report['holdout']['source_gold']})"
    )

    print("\nMean field accuracy")
    print(f"  {'generator':<20}{'batch':>10}{'holdout':>10}{'delta':>10}")
    for model, d in report["delta"].items():
        m = d["mean_field_accuracy"]
        print(
            f"  {model:<20}{pct(m['batch']):>10}{pct(m['holdout']):>10}"
            f"{signed(m['delta']):>10}"
        )

    print("\nUnsupported assertion rate (lower is safer)")
    print(f"  {'generator':<20}{'batch':>10}{'holdout':>10}{'delta':>10}")
    for model, d in report["delta"].items():
        u = d["unsupported_rate"]
        print(
            f"  {model:<20}{pct(u['batch']):>10}{pct(u['holdout']):>10}"
            f"{signed(u['delta']):>10}"
        )

    print("\nWhole-record accuracy")
    for side in ("batch", "holdout"):
        w = report["whole_record"][side]
        print(
            f"  {side:<10} best {pct(w['best_generator']):>7}   "
            f"ceiling {pct(w['oracle_ceiling']):>7}   "
            f"headroom {pct(w['headroom']):>7}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-scored", type=Path, default=BATCH_SCORED)
    parser.add_argument("--holdout-scored", type=Path, default=HOLDOUT_SCORED)
    parser.add_argument("--holdout-gold", type=Path, default=HOLDOUT_GOLD)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    for path, hint in (
        (args.batch_scored, "tests.eval.extraction.score_against_gold --batch ..."),
        (args.holdout_scored, "tests.eval.extraction.score_against_gold --gold ... --batch ..."),
        (args.holdout_gold, "tests.eval.extraction.adjudicate ... --out ..."),
    ):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run `uv run python -m {hint}` first.")

    report = build(
        json.loads(args.batch_scored.read_text()),
        json.loads(args.holdout_scored.read_text()),
        json.loads(args.holdout_gold.read_text()),
    )
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    render(report)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
