"""Does reranking select better than not reranking?

`mars_evaluation` answers "how accurate is MARS" with whole-record accuracy
over every returned record. That is the right headline and the wrong instrument
for this question, for two reasons:

  1. **It includes segments where MARS made no choice.** 123 of the 265
     returned records are single-candidate short-circuits: one generator
     cleared admission, no judge was consulted, and MARS passed the candidate
     through. Selection quality cannot be measured where no selection occurred.

  2. **Whole-record accuracy is too coarse to resolve it.** All four fields must
     be right, which happens on 4.5% of segments. A selector that improves one
     field in three records moves that number by a point at most, and the
     comparison ends in an underpowered null.

This module measures selection on the segments where selection happened, field
by field, against two baselines that bracket what selection is worth:

    random candidate    a selector with no judgement at all
    best generator      always use the strongest model; the simplest policy
                        that beats no-policy, and the one MARS must beat to
                        justify its cost

Differences are paired bootstraps over segments: every selector is scored on
the same resampled segments, because they are all choosing from the same
candidate sets and their errors are correlated.

Nothing here supersedes `mars_evaluation`. Whole-record accuracy is what the
system returns to an interventionist; this is a diagnostic for why that number
lands where it does.

Usage:
    uv run python -m tests.eval.extraction.mars_selection_analysis
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path
from typing import Any, Callable

RESULTS_DIR = Path(__file__).parent / "results"
SCORED_PATH = RESULTS_DIR / "scored_against_gold.json"
OUTCOMES_PATH = RESULTS_DIR / "mars_outcomes.json"
OUT_PATH = RESULTS_DIR / "mars_selection_analysis.json"

ACCEPTABLE = frozenset({"correct", "correctly_null"})
N_BOOTSTRAP = 10_000
SEED = 20260916
RANDOM_BASELINE_TRIALS = 2_000


GOLD_LABELS_PATH = RESULTS_DIR / "gold_labels.json"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"


def load_child_map(segments: list[str]) -> dict[str, str]:
    """Segment -> child, from the artefacts that actually record it.

    `scored_against_gold.json` keys segments to per-model judgements and
    carries no child, so reading it from there silently yields one cluster for
    everything -- which resamples to the identical set every replicate and
    produces a zero-width interval that looks like enormous precision. The
    guard below refuses that rather than reporting it.
    """
    mapping: dict[str, str] = {}
    for path, key in ((GOLD_LABELS_PATH, "gold"), (BATCH_PATH, "candidates")):
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        entries = payload.get(key)
        if isinstance(entries, dict):
            for segment, record in entries.items():
                if record.get("child_id"):
                    mapping.setdefault(segment, record["child_id"])
        elif isinstance(entries, list):
            for entry in entries:
                if entry.get("child_id"):
                    mapping.setdefault(entry["segment_id"], entry["child_id"])

    resolved = {s: mapping.get(s, "unknown") for s in segments}
    distinct = {c for c in resolved.values() if c != "unknown"}
    if len(distinct) < 2:
        raise SystemExit(
            "Cannot cluster by child: resolved "
            f"{len(distinct)} distinct children across {len(segments)} segments. "
            "A single cluster resamples to the identical set every replicate "
            "and yields a zero-width interval."
        )
    return resolved


def judged_segments(outcomes: dict[str, Any], gold: dict[str, Any]) -> list[str]:
    """Returned segments where more than one candidate was available.

    `candidate_count > 1` is the condition for a judge to have been consulted;
    at one candidate MARS short-circuits and selects nothing.
    """
    return sorted(
        s
        for s, entry in outcomes.items()
        if entry.get("status") == "success"
        and s in gold
        and (entry.get("candidate_count") or 0) > 1
    )


def acceptable(gold: dict[str, Any], segment: str, model: str | None, field: str) -> bool:
    if model is None or model not in gold[segment]:
        return False
    return gold[segment][model].get(field) in ACCEPTABLE


def mars_selector(outcomes: dict[str, Any]) -> Callable[[str], str | None]:
    def pick(segment: str) -> str | None:
        chosen = outcomes[segment].get("selected_generator_ids") or [None]
        return chosen[0]

    return pick


def accuracy(
    gold: dict[str, Any],
    segments: list[str],
    pick: Callable[[str], str | None],
    field: str,
) -> float:
    if not segments:
        return 0.0
    return sum(acceptable(gold, s, pick(s), field) for s in segments) / len(segments)


def random_baseline(
    gold: dict[str, Any],
    segments: list[str],
    models: list[str],
    field: str,
    trials: int = RANDOM_BASELINE_TRIALS,
    seed: int = SEED,
) -> float:
    """Expected accuracy of choosing uniformly among the available candidates.

    Averaged over repeated draws rather than evaluated once: a single random
    assignment is itself a noisy quantity, and the baseline is meant to be the
    expectation, not one sample from it.
    """
    rng = random.Random(seed)
    total = 0.0
    for _ in range(trials):
        hits = 0
        for segment in segments:
            available = [m for m in models if m in gold[segment]]
            if available:
                hits += acceptable(gold, segment, rng.choice(available), field)
        total += hits / len(segments)
    return total / trials


def paired_difference(
    gold: dict[str, Any],
    segments: list[str],
    pick_a: Callable[[str], str | None],
    pick_b: Callable[[str], str | None],
    field: str,
    n_boot: int = N_BOOTSTRAP,
    seed: int = SEED,
    clusters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Bootstrap interval on (a - b), both scored on the same resampled draw.

    `clusters` maps each segment to its child. Supplied, children are resampled
    and each drawn child contributes all of its segments: segments from one
    child share that child's language and session context and are not
    independent draws. Omitted, the unit is the segment, which is retained as a
    sensitivity analysis.
    """
    rng = random.Random(seed)
    n = len(segments)
    grouped: dict[str, list[str]] = {}
    if clusters is not None:
        for segment in segments:
            grouped.setdefault(clusters.get(segment, "unknown"), []).append(segment)
    labels = sorted(grouped)

    replicates: list[float] = []
    for _ in range(n_boot):
        if clusters is None:
            draw = [segments[rng.randrange(n)] for _ in range(n)]
        else:
            draw = [
                segment
                for _ in labels
                for segment in grouped[labels[rng.randrange(len(labels))]]
            ]
        size = len(draw)
        a = sum(acceptable(gold, s, pick_a(s), field) for s in draw) / size
        b = sum(acceptable(gold, s, pick_b(s), field) for s in draw) / size
        replicates.append(a - b)
    replicates.sort()
    lower = replicates[int(0.025 * n_boot)]
    upper = replicates[int(0.975 * n_boot)]
    return {
        "difference": round(statistics.mean(replicates), 4),
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "excludes_zero": bool(lower > 0 or upper < 0),
        "unit": "child" if clusters is not None else "segment",
    }


def analyse(
    scored: dict[str, Any], outcomes: dict[str, Any], n_boot: int = N_BOOTSTRAP
) -> dict[str, Any]:
    gold = scored["gold"]
    fields = scored["scoring_fields"]
    models = scored["models"]
    segments = judged_segments(outcomes, gold)
    mars = mars_selector(outcomes)

    best = max(
        models,
        key=lambda m: statistics.mean(accuracy(gold, segments, lambda s: m, f) for f in fields),
    )

    child_of = load_child_map(segments)

    per_field: dict[str, Any] = {}
    for field in fields:
        per_field[field] = {
            "mars": round(accuracy(gold, segments, mars, field), 4),
            "best_generator": round(accuracy(gold, segments, lambda s: best, field), 4),
            "random_candidate": round(
                random_baseline(gold, segments, models, field), 4
            ),
            "per_generator": {
                m: round(accuracy(gold, segments, lambda s, mm=m: mm, field), 4)
                for m in models
            },
            "vs_best_generator": paired_difference(
                gold, segments, mars, lambda s: best, field, n_boot=n_boot
            ),
            "vs_best_generator_clustered": paired_difference(
                gold, segments, mars, lambda s: best, field, n_boot=n_boot,
                clusters=child_of,
            ),
        }

    # The random baseline is an expectation, so its paired interval is taken
    # against one fixed random assignment per replicate rather than against the
    # averaged expectation, which has no per-segment realisation to pair with.
    rng = random.Random(SEED + 1)
    fixed_random = {
        s: (
            rng.choice([m for m in models if m in gold[s]])
            if any(m in gold[s] for m in models)
            else None
        )
        for s in segments
    }
    for field in fields:
        per_field[field]["vs_random_candidate"] = paired_difference(
            gold, segments, mars, lambda s: fixed_random[s], field, n_boot=n_boot
        )
        per_field[field]["vs_random_candidate_clustered"] = paired_difference(
            gold, segments, mars, lambda s: fixed_random[s], field,
            n_boot=n_boot, clusters=child_of,
        )

    selection_counts = {m: 0 for m in models}
    for segment in segments:
        chosen = mars(segment)
        if chosen in selection_counts:
            selection_counts[chosen] += 1

    return {
        "n_judged_segments": len(segments),
        "n_returned": sum(
            1 for e in outcomes.values() if e.get("status") == "success"
        ),
        "n_short_circuit": sum(
            1
            for s, e in outcomes.items()
            if e.get("status") == "success" and (e.get("candidate_count") or 0) <= 1
        ),
        "best_generator": best,
        "fields": fields,
        "n_bootstrap": n_boot,
        "seed": SEED,
        "per_field": per_field,
        "mars_selection_counts": selection_counts,
        "mars_share_of_best_generator": round(
            selection_counts[best] / len(segments), 4
        )
        if segments
        else None,
        "mean_accuracy": {
            "mars": round(
                statistics.mean(per_field[f]["mars"] for f in fields), 4
            ),
            "best_generator": round(
                statistics.mean(per_field[f]["best_generator"] for f in fields), 4
            ),
            "random_candidate": round(
                statistics.mean(per_field[f]["random_candidate"] for f in fields), 4
            ),
        },
    }


def render(report: dict[str, Any]) -> None:
    print(
        f"Selection measured on {report['n_judged_segments']} judged segments "
        f"({report['n_short_circuit']} of {report['n_returned']} returned records "
        "were short-circuits and are excluded)\n"
    )
    fields = report["fields"]
    print(f"  {'selector':<20}" + "".join(f"{f[:10]:>12}" for f in fields) + f"{'mean':>9}")
    for label, key in (
        ("MARS", "mars"),
        (f"best ({report['best_generator'].replace(':latest', '')})", "best_generator"),
        ("random candidate", "random_candidate"),
    ):
        values = [100 * report["per_field"][f][key] for f in fields]
        print(
            f"  {label:<20}"
            + "".join(f"{v:>11.1f}%" for v in values)
            + f"{100 * report['mean_accuracy'][key]:>8.1f}%"
        )

    for title, key in (
        ("MARS vs the best single generator", "vs_best_generator"),
        ("MARS vs a random candidate", "vs_random_candidate"),
    ):
        print(f"\n  {title}")
        print(f"    {'field':<14}{'diff':>7}{'95% CI (child)':>20}"
              f"{'95% CI (segment)':>20}")
        for field in fields:
            entry = report["per_field"][field][key]
            clustered = report["per_field"][field].get(f"{key}_clustered")

            def fmt(e: dict | None) -> str:
                if not e:
                    return "--"
                return (
                    f"[{100 * e['lower']:+6.1f},{100 * e['upper']:+6.1f}]"
                    + ("*" if e["excludes_zero"] else " ")
                )

            print(
                f"    {field:<14}{100 * entry['difference']:>+7.1f}"
                f"{fmt(clustered):>20}{fmt(entry):>20}"
            )
    print("\n  * interval excludes zero"
          "\n  child-clustered is the reported interval; segment-level is the "
          "sensitivity analysis")

    print(f"\n  MARS chose {report['best_generator']} on "
          f"{report['mars_share_of_best_generator']:.0%} of judged segments: "
          f"{report['mars_selection_counts']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-boot", type=int, default=N_BOOTSTRAP)
    args = parser.parse_args()

    for path, hint in (
        (SCORED_PATH, "tests.eval.extraction.score_against_gold"),
        (OUTCOMES_PATH, "tests.eval.extraction.run_mars ..."),
    ):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run `uv run python -m {hint}` first.")

    report = analyse(
        json.loads(SCORED_PATH.read_text()),
        json.loads(OUTCOMES_PATH.read_text()),
        n_boot=args.n_boot,
    )
    render(report)
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
