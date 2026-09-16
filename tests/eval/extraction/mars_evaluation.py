"""Evaluation metrics for MARS against adjudicated annotations.

Reports the four quantities the manuscript needs together, because any one of
them alone is misleading:

    single best generator      the honest comparator
    MARS                       what reranking achieved
    oracle candidate ceiling   at least one generator fully correct
    oracle capture rate        how much of the available headroom was captured

"75% -> 82%" hides whether reranking left six points on the table or almost
none. Separating the two also directs the next iteration: a low capture rate is
a *reranking* problem (better judges, better fusion), a low ceiling is a
*generation* problem (more or more diverse generators).

Every accuracy here is conditional on abstention, so coverage and the
reason-code breakdown are reported alongside. A system that abstains on
everything hard posts a flattering accuracy and delivers nothing.

Usage:
    uv run python -m tests.eval.extraction.mars_evaluation
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]

# A field is acceptable when the model got it right, including correctly
# declining to fill it. "missing" and "hallucinated" are both failures: one
# omits supported evidence, the other invents unsupported evidence.
ACCEPTABLE = {"correct", "correctly_null"}


def is_fully_correct(
    field_judgments: dict[str, str], fields: list[str] | None = None
) -> bool:
    """Whole-extraction correctness.

    Deliberately strict: every scored field must be acceptable. A partially
    correct record is not a usable record for an interventionist, and MARS
    selects whole candidates rather than fields, so whole-record correctness is
    the unit that matches what the system actually returns.

    ``fields`` is the scored set. It is a parameter because free-text
    `behavior` may be excluded by the scoring policy, and holding it fixed
    would then fail every record on a field the study had decided not to score.
    """
    if not field_judgments:
        return False
    return all(field_judgments.get(f) in ACCEPTABLE for f in (fields or FIELDS))


def per_model_accuracy(
    gold: dict[str, dict[str, dict[str, str]]],
    models: list[str],
    fields: list[str] | None = None,
) -> dict[str, float | None]:
    """Fraction of judged segments each generator got fully correct."""
    accuracy: dict[str, float | None] = {}
    for model in models:
        judged = [g[model] for g in gold.values() if model in g]
        accuracy[model] = (
            sum(1 for j in judged if is_fully_correct(j, fields)) / len(judged)
            if judged
            else None
        )
    return accuracy


def oracle_ceiling(
    gold: dict[str, dict[str, dict[str, str]]],
    models: list[str],
    fields: list[str] | None = None,
) -> float | None:
    """Fraction of segments where *at least one* generator was fully correct.

    MARS cannot select a correct answer none of its generators produced, so
    this is a hard upper bound on what any reranker could achieve.
    """
    if not gold:
        return None
    hits = sum(
        1
        for judgments in gold.values()
        if any(is_fully_correct(judgments[m], fields) for m in models if m in judgments)
    )
    return hits / len(gold)


def oracle_capture_rate(
    mars: float | None, best_generator: float | None, oracle: float | None
) -> float | None:
    """Share of the theoretically available improvement that MARS captured.

        (mars - best) / (oracle - best)

    ``None`` where the denominator vanishes: if the oracle equals the best
    single generator there was no headroom for reranking to capture, and the
    ratio would be undefined rather than zero or one. Reporting a number there
    would invent a result.
    """
    if mars is None or best_generator is None or oracle is None:
        return None
    headroom = oracle - best_generator
    if headroom <= 0:
        return None
    return (mars - best_generator) / headroom


def mars_accuracy(
    gold: dict[str, dict[str, dict[str, str]]],
    outcomes: dict[str, dict[str, Any]],
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Accuracy over returned records, plus the coverage it is conditional on.

    ``accuracy_over_returned`` is the figure a reader intuitively wants;
    ``accuracy_over_all`` counts every abstention as a miss. Both are reported
    because they answer different questions, and quoting only the first from a
    system that abstains heavily would overstate it.
    """
    returned, correct = 0, 0
    abstained = Counter()

    for segment_id, outcome in outcomes.items():
        if outcome.get("status") != "success":
            abstained[outcome.get("reason_code") or "unspecified"] += 1
            continue
        returned += 1
        generators = outcome.get("selected_generator_ids") or []
        judgments = gold.get(segment_id, {})
        # A deduplicated candidate has several generators that produced
        # identical fields, so any of them carries the same judgment.
        selected = next((judgments[m] for m in generators if m in judgments), None)
        if selected and is_fully_correct(selected, fields):
            correct += 1

    total = len(outcomes)
    # Full precision throughout: these values feed the capture-rate arithmetic,
    # and rounding a metric before it is used compounds the error into the
    # figure that depends on it. Rounding happens at display time only.
    return {
        "n_total": total,
        "n_returned": returned,
        "n_abstained": total - returned,
        "coverage": returned / total if total else None,
        "accuracy_over_returned": correct / returned if returned else None,
        "accuracy_over_all": correct / total if total else None,
        "abstention_reasons": dict(abstained),
    }


def build_evaluation(
    gold: dict[str, dict[str, dict[str, str]]],
    models: list[str],
    outcomes: dict[str, dict[str, Any]],
    fields: list[str] | None = None,
) -> dict[str, Any]:
    generators = per_model_accuracy(gold, models, fields)
    scored = {m: a for m, a in generators.items() if a is not None}
    best_model = max(scored, key=lambda m: scored[m]) if scored else None
    best = scored.get(best_model) if best_model else None
    ceiling = oracle_ceiling(gold, models, fields)
    mars = mars_accuracy(gold, outcomes, fields)

    return {
        "n_gold_segments": len(gold),
        "models": models,
        "scoring_fields": fields or FIELDS,
        "per_generator_accuracy": generators,
        "best_generator": best_model,
        "best_generator_accuracy": best,
        "oracle_ceiling": ceiling,
        "mars": mars,
        "oracle_capture_rate": oracle_capture_rate(
            mars["accuracy_over_returned"], best, ceiling
        ),
        "note": (
            "Accuracy is conditional on abstention; read it with `coverage` and "
            "`abstention_reasons`. Capture rate is undefined where the oracle "
            "ceiling equals the best single generator, because no headroom "
            "existed for reranking to capture."
        ),
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _render(report: dict[str, Any]) -> None:
    print(f"Gold segments: {report['n_gold_segments']}\n")
    print(f"  {'generator':24s} {'accuracy':>9s}")
    for model, accuracy in report["per_generator_accuracy"].items():
        marker = "  <- best" if model == report["best_generator"] else ""
        print(f"  {model:24s} {_fmt(accuracy):>9s}{marker}")

    mars = report["mars"]
    print()
    print(f"  {'single best generator':24s} {_fmt(report['best_generator_accuracy'])}")
    print(f"  {'MARS (over returned)':24s} {_fmt(mars['accuracy_over_returned'])}")
    print(f"  {'MARS (over all)':24s} {_fmt(mars['accuracy_over_all'])}")
    print(f"  {'oracle ceiling':24s} {_fmt(report['oracle_ceiling'])}")
    print(f"  {'oracle capture rate':24s} {_fmt(report['oracle_capture_rate'])}")
    print()
    print(
        f"  coverage {_fmt(mars['coverage'])}  "
        f"({mars['n_returned']}/{mars['n_total']} returned)"
    )
    print(f"  abstentions: {mars['abstention_reasons'] or 'none'}")


# Below this share of the gold set, MARS metrics are refused rather than
# reported. Not a tuning knob: the point is that a partial run is a different
# experiment, not a noisier version of the full one.
MIN_OUTCOME_COVERAGE = 0.95


def main() -> None:
    # The derived judgements, not gold_labels.json: gold holds field *values*,
    # and score_against_gold turns those into the per-model judgements these
    # metrics are defined over.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Compute MARS metrics even where the outcomes cover only part of "
             "the gold set. The coverage is recorded in the output.",
    )
    args = parser.parse_args()

    scored_path = RESULTS_DIR / "scored_against_gold.json"
    outcomes_path = RESULTS_DIR / "mars_outcomes.json"
    for path, hint in (
        (scored_path, "tests.eval.extraction.score_against_gold"),
        (outcomes_path, "tests.eval.extraction.run_mars ..."),
    ):
        if not path.exists():
            raise SystemExit(
                f"{path} not found. Run `uv run python -m {hint}` first; this "
                "script computes metrics, it does not create labels."
            )

    scored = json.loads(scored_path.read_text())
    outcomes = json.loads(outcomes_path.read_text())

    # A MARS metric computed over a fraction of the gold set is not a small
    # version of the real number, it is a different number wearing its name.
    # The 3-segment single-judge ablation that produced the first outcomes file
    # yielded an accuracy of 0.000 and a capture rate of -3.0 against a best
    # generator of 0.045 -- figures that look like findings and are noise.
    coverage = len(outcomes) / len(scored["gold"]) if scored["gold"] else 0.0
    if coverage < MIN_OUTCOME_COVERAGE and not args.allow_partial:
        raise SystemExit(
            f"mars_outcomes.json covers {len(outcomes)} of "
            f"{len(scored['gold'])} gold segments ({coverage:.1%}).\n"
            "Refusing to report MARS metrics over a partial run: accuracy, "
            "the oracle capture rate and the abstention profile are all\n"
            "defined over the whole batch and are meaningless on a subset.\n"
            "Re-run MARS over the full batch:\n"
            "  uv run python -m tests.eval.extraction.run_mars ...\n"
            "or pass --allow-partial to compute them anyway, which records "
            "the coverage in the output."
        )

    report = build_evaluation(
        scored["gold"], scored["models"],
        outcomes,
        scored.get("scoring_fields"),
    )
    report["outcome_coverage"] = coverage
    report["n_outcome_segments"] = len(outcomes)
    if coverage < MIN_OUTCOME_COVERAGE:
        report["partial_run_warning"] = (
            f"MARS outcomes cover {len(outcomes)} of {len(scored['gold'])} gold "
            f"segments ({coverage:.1%}). These metrics are not comparable to "
            "the per-generator accuracies, which are computed over the full set."
        )
    out = RESULTS_DIR / "mars_evaluation.json"
    out.write_text(json.dumps(report, indent=2))
    _render(report)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
