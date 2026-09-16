"""Consolidate every measured result into one paper-ready metrics artefact.

The numbers reported in the manuscript live across eight files produced by six
scripts. That is correct for provenance and poor for writing: preparing a table
means opening several artefacts and reconciling denominators by hand, which is
how a rounding error or a stale figure reaches a submission.

This reads those artefacts and emits one `paper_metrics.json` plus a rendered
summary, with every figure carrying its own denominator and the command that
produced it. It computes nothing new -- if a number here disagrees with its
source, this file is wrong, not the source.

Quantities that are *not* measured are listed explicitly rather than omitted,
because a metrics summary that silently drops what was never measured reads as
a complete account of the study.

Usage:
    uv run python -m tests.eval.extraction.paper_metrics
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
OUT_PATH = RESULTS_DIR / "paper_metrics.json"

SOURCES = {
    "reliability_round1": "reliability_round1.json",
    "reliability_merged": "reliability_current.json",
    "round_comparison": "round_comparison.json",
    "reissue_selection": "reissue_round2_selection.json",
    "gold": "gold_labels.json",
    "scored": "scored_against_gold.json",
    "mars_evaluation": "mars_evaluation.json",
    "mars_selection": "mars_selection_analysis.json",
    "mars_summary": "mars_run_summary.json",
    "branch_replay": "mars_branch_replay.json",
}

ACCEPTABLE = frozenset({"correct", "correctly_null"})

# Stated here rather than inferred: a reader must be able to see what the study
# did not measure without cross-referencing the manuscript.
NOT_MEASURED = [
    "Frontier-model comparison (claude-*): blocked on corpus terms for "
    "third-party API processing and on IRB determination.",
    "Reporting LLM groundedness: no recorded evaluation artefact.",
    "Deterministic analytics, adequacy/abstention routing, validation engine: "
    "unit-tested as software, not evaluated as research (no result artefacts).",
    "Clinical or usability evaluation: no interventionist used the system.",
    "Whether reranking would pay on a balanced generator roster.",
]


def load() -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    missing: list[str] = []
    for key, name in SOURCES.items():
        path = RESULTS_DIR / name
        if path.exists():
            loaded[key] = json.loads(path.read_text())
        else:
            missing.append(name)
    if missing:
        raise SystemExit(
            "Missing artefacts: " + ", ".join(missing) + "\n"
            "Run the pipeline in docs/paper/artifacts.md first."
        )
    return loaded


def build(data: dict[str, Any]) -> dict[str, Any]:
    r1, merged = data["reliability_round1"], data["reliability_merged"]
    comparison, selection_meta = data["round_comparison"], data["reissue_selection"]
    gold, scored = data["gold"], data["scored"]
    mars, mars_sel = data["mars_evaluation"], data["mars_selection"]

    fields = scored["scoring_fields"]
    models = scored["models"]

    def field_rate(model: str, field: str, judgements: frozenset[str]) -> dict[str, Any]:
        counts = scored["per_field_counts"][model]
        hits = sum(counts.get(f"{field}:{j}", 0) for j in judgements)
        total = sum(v for k, v in counts.items() if k.startswith(f"{field}:"))
        return {"n": hits, "denominator": total, "rate": round(hits / total, 4) if total else None}

    def unsupported(model: str, field: str) -> dict[str, Any]:
        counts = scored["per_field_counts"][model]
        hallucinated = counts.get(f"{field}:hallucinated", 0)
        opportunities = hallucinated + counts.get(f"{field}:correctly_null", 0)
        return {
            "n": hallucinated,
            "denominator": opportunities,
            "rate": round(hallucinated / opportunities, 4) if opportunities else None,
        }

    return {
        "generated_from": SOURCES,
        "note": (
            "Derived entirely from the artefacts named above; nothing is "
            "recomputed. Every rate carries its own denominator."
        ),
        "annotation": {
            "n_segments": r1["n_segments"],
            "n_annotators": 2,
            "rounds": 2,
            "reliability": {
                "round1": {
                    "mean_kappa": r1["mean_kappa"],
                    "per_field": {
                        f: {
                            "kappa": r1["fields"][f]["kappa"],
                            "ci": [
                                r1["fields"][f]["bootstrap_ci"]["lower"],
                                r1["fields"][f]["bootstrap_ci"]["upper"],
                            ],
                            "kappa_max": r1["fields"][f]["kappa_max"],
                            "kappa_over_kappa_max": r1["fields"][f][
                                "kappa_over_kappa_max"
                            ],
                        }
                        for f in r1["fields"]
                    },
                },
                "merged": {
                    "mean_kappa": merged["mean_kappa"],
                    "per_field": {
                        f: {
                            "kappa": merged["fields"][f]["kappa"],
                            "ci": [
                                merged["fields"][f]["bootstrap_ci"]["lower"],
                                merged["fields"][f]["bootstrap_ci"]["upper"],
                            ],
                            "kappa_max": merged["fields"][f]["kappa_max"],
                        }
                        for f in merged["fields"]
                    },
                },
            },
            "codebook_intervention": {
                "n_reissued_segments": selection_meta["n_selected"],
                "n_conflicts_on_boundary": selection_meta["n_on_boundary"],
                "n_conflicts_codebook_silent": selection_meta["n_off_boundary"],
                "estimand": "change in kappa over the re-issued segments",
                "per_field": {
                    f: {
                        "arm": comparison["fields"][f]["arm"],
                        "kappa_before": comparison["fields"][f]["delta"]["kappa_before"],
                        "kappa_after": comparison["fields"][f]["delta"]["kappa_after"],
                        "delta": comparison["fields"][f]["delta"]["delta"],
                        "ci": [
                            comparison["fields"][f]["delta"]["lower"],
                            comparison["fields"][f]["delta"]["upper"],
                        ],
                        "excludes_zero": comparison["fields"][f]["delta"]["excludes_zero"],
                    }
                    for f in comparison["fields"]
                },
            },
        },
        "gold_standard": {
            "n_segments": gold["n_segments_in_gold"],
            "n_excluded": gold["counts"].get("unresolved", 0),
            "composition": gold["counts"],
            "adjudicator": gold["adjudicator"],
            "nulls_per_field": {
                f: sum(1 for v in gold["gold"].values() if v["field_values"][f] is None)
                for f in fields
            },
        },
        "extraction": {
            "scoring_policy": {
                "behavior_match": scored["behavior_match"],
                "scored_fields": fields,
            },
            "per_field_accuracy": {
                m: {f: field_rate(m, f, ACCEPTABLE) for f in fields} for m in models
            },
            "unsupported_extractions": {
                m: {f: unsupported(m, f) for f in fields} for m in models
            },
            "whole_record": {
                "per_generator": mars["per_generator_accuracy"],
                "best_generator": mars["best_generator"],
                "best_accuracy": mars["best_generator_accuracy"],
                "oracle_ceiling": mars["oracle_ceiling"],
                "headroom": round(
                    mars["oracle_ceiling"] - mars["best_generator_accuracy"], 4
                ),
            },
        },
        "mars": {
            "config": {
                "judges": data["mars_summary"]["judges"],
                "agreement_threshold": data["mars_summary"]["agreement_threshold"],
                "min_eligible_judges": data["mars_summary"]["min_eligible_judges"],
                "single_judge_ablation": data["mars_summary"]["single_judge_ablation"],
                "max_judge_discard_rate": round(
                    max(
                        e["discard_rate"]
                        for e in data["mars_summary"]["judge_reliability"].values()
                    ),
                    4,
                ),
            },
            "outcomes": {
                "n_total": mars["mars"]["n_total"],
                "n_returned": mars["mars"]["n_returned"],
                "coverage": mars["mars"]["coverage"],
                "abstention_reasons": mars["mars"]["abstention_reasons"],
            },
            "whole_record_accuracy": {
                "over_returned": mars["mars"]["accuracy_over_returned"],
                "over_all": mars["mars"]["accuracy_over_all"],
            },
            "selection_quality": {
                "n_judged_segments": mars_sel["n_judged_segments"],
                "n_short_circuit_excluded": mars_sel["n_short_circuit"],
                "mean_accuracy": mars_sel["mean_accuracy"],
                "share_choosing_best_generator": mars_sel[
                    "mars_share_of_best_generator"
                ],
                "per_field": {
                    f: {
                        "mars": mars_sel["per_field"][f]["mars"],
                        "best_generator": mars_sel["per_field"][f]["best_generator"],
                        "random_candidate": mars_sel["per_field"][f]["random_candidate"],
                        "vs_best": mars_sel["per_field"][f]["vs_best_generator"],
                        "vs_random": mars_sel["per_field"][f]["vs_random_candidate"],
                    }
                    for f in mars_sel["fields"]
                },
            },
        },
        "not_measured": NOT_MEASURED,
    }


def render(m: dict[str, Any]) -> None:
    pct = lambda v: "n/a" if v is None else f"{100 * v:.1f}%"  # noqa: E731

    print("=" * 74)
    print("PAPER-READY METRICS")
    print("=" * 74)

    a = m["annotation"]
    print(f"\nANNOTATION  ({a['n_segments']} segments, {a['n_annotators']} annotators, "
          f"{a['rounds']} rounds)")
    print(f"  {'field':<14}{'k round1':>10}{'k merged':>10}{'k_max r1':>10}"
          f"{'delta':>9}{'arm':>10}")
    for f, entry in a["codebook_intervention"]["per_field"].items():
        r1 = a["reliability"]["round1"]["per_field"][f]
        mg = a["reliability"]["merged"]["per_field"][f]
        star = "*" if entry["excludes_zero"] else " "
        print(f"  {f:<14}{r1['kappa']:>10.3f}{mg['kappa']:>10.3f}"
              f"{r1['kappa_max']:>10.3f}{entry['delta']:>+8.3f}{star}{entry['arm']:>10}")
    print(f"  mean kappa {a['reliability']['round1']['mean_kappa']:.3f} -> "
          f"{a['reliability']['merged']['mean_kappa']:.3f}    "
          f"(* paired CI excludes zero)")

    g = m["gold_standard"]
    print(f"\nGOLD STANDARD  {g['n_segments']} segments, {g['n_excluded']} excluded")
    print(f"  composition: {g['composition']}")
    print(f"  adjudicator: {g['adjudicator'][:60]}")

    e = m["extraction"]
    fields = e["scoring_policy"]["scored_fields"]
    print(f"\nEXTRACTION ACCEPTABLE RATE  (behavior {e['scoring_policy']['behavior_match']})")
    print(f"  {'generator':<20}" + "".join(f"{f[:10]:>12}" for f in fields))
    for model, per in e["per_field_accuracy"].items():
        print(f"  {model:<20}" + "".join(pct(per[f]['rate']).rjust(12) for f in fields))

    print("\nUNSUPPORTED EXTRACTIONS  (gold null, value asserted)")
    print(f"  {'generator':<20}" + "".join(f"{f[:10]:>12}" for f in fields))
    for model, per in e["unsupported_extractions"].items():
        cells = [
            f"{per[f]['n']}/{per[f]['denominator']}" if per[f]["denominator"] else "-"
            for f in fields
        ]
        print(f"  {model:<20}" + "".join(c.rjust(12) for c in cells))

    w = e["whole_record"]
    print(f"\nWHOLE-RECORD  best {w['best_generator']} {pct(w['best_accuracy'])}  "
          f"ceiling {pct(w['oracle_ceiling'])}  headroom {pct(w['headroom'])}")

    mars = m["mars"]
    print(f"\nMARS  coverage {pct(mars['outcomes']['coverage'])} "
          f"({mars['outcomes']['n_returned']}/{mars['outcomes']['n_total']})")
    print(f"  abstentions: {mars['outcomes']['abstention_reasons']}")
    print(f"  max judge discard rate: {pct(mars['config']['max_judge_discard_rate'])}")
    s = mars["selection_quality"]
    print(f"\n  selection on {s['n_judged_segments']} judged segments "
          f"({s['n_short_circuit_excluded']} short-circuits excluded)")
    print(f"    mean: MARS {pct(s['mean_accuracy']['mars'])}  "
          f"best {pct(s['mean_accuracy']['best_generator'])}  "
          f"random {pct(s['mean_accuracy']['random_candidate'])}")
    for f, entry in s["per_field"].items():
        vb, vr = entry["vs_best"], entry["vs_random"]
        print(f"    {f:<14}vs best {100 * vb['difference']:+6.1f}"
              f"{'*' if vb['excludes_zero'] else ' '}   "
              f"vs random {100 * vr['difference']:+6.1f}"
              f"{'*' if vr['excludes_zero'] else ' '}")

    print("\nNOT MEASURED")
    for item in m["not_measured"]:
        print(f"  - {item}")


def main() -> None:
    metrics = build(load())
    render(metrics)
    OUT_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
