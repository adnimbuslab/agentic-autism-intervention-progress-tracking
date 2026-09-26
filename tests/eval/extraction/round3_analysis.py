"""Round-3 analyses over recorded artefacts. No model is called.

Three questions a reviewer asked that the existing artefacts can answer
without new data:

  1. **Composition of the post-codebook kappa.** The reported mean kappa over
     the 330 main-batch segments mixes two annotation states: round-2 values
     for the 178 segments re-issued under the codebook, round-1 values for the
     152 that were not. Kappa is recomputed on each part so the figure cannot
     be read as a clean before/after effect.

  2. **Child-cluster bootstrap intervals for model performance** -- merged
     categorical agreement, unsupported-assertion rate and whole-record
     agreement -- on the main batch and the held-out set, by the same
     procedure as the annotation kappa intervals (`reliability_stats`):
     10,000 replicates, children drawn with replacement, every segment of a
     drawn child retained, percentile interval.

  3. **Held-out leakage sensitivity.** `build_holdout_set` excluded the
     original pool by segment id, but segment ids are assigned in selection
     order and are not stable across the two selection caps it spanned. Pool
     episodes that re-appear under a new id are found here by transcript
     identity, and the held-out metrics are recomputed without them.

Every point estimate is checked against the artefact that first recorded it;
a mismatch raises rather than reporting a number that disagrees with the paper.

    uv run python -m tests.eval.extraction.round3_analysis
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from tests.eval.extraction.agreement_report import cohens_kappa, paired_values
from tests.eval.extraction.mars_evaluation import ACCEPTABLE
from tests.eval.extraction.reliability_stats import CATEGORICAL_FIELDS, _percentile

RESULTS = Path(__file__).parent / "results"
OUT = RESULTS / "round3_analysis.json"
N_BOOT = 10_000
SEED = 20260926


def load(name: str) -> Any:
    return json.loads((RESULTS / name).read_text())


# --------------------------------------------------------------------------
# 1. kappa composition
# --------------------------------------------------------------------------

def kappa_composition() -> dict[str, Any]:
    r1a, r1b = load("gold_annotator_a_round1.json"), load("gold_annotator_b_round1.json")
    fa, fb = load("gold_annotator_a.json"), load("gold_annotator_b.json")
    reissued = set(load("reissue_round2_selection.json")["selected"])
    all_ids = sorted(set(fa) & set(fb))
    retained = [s for s in all_ids if s not in reissued]
    re_ids = [s for s in all_ids if s in reissued]

    def mean_k(a, b, ids):
        per = {f: cohens_kappa(paired_values(a, b, f, ids)) for f in CATEGORICAL_FIELDS}
        return {"per_field": {f: round(v, 4) for f, v in per.items()},
                "mean": round(sum(per.values()) / len(per), 4), "n": len(ids)}

    out = {
        "final_state_all_330": mean_k(fa, fb, all_ids),
        "round1_all_330": mean_k(r1a, r1b, all_ids),
        "retained_152_round1_values": mean_k(fa, fb, retained),
        "reissued_178_round1_values": mean_k(r1a, r1b, re_ids),
        "reissued_178_round2_values": mean_k(fa, fb, re_ids),
    }
    # The retained segments must carry identical values in both states.
    for s in retained:
        assert fa[s]["field_values"] == r1a[s]["field_values"], s
        assert fb[s]["field_values"] == r1b[s]["field_values"], s
    assert out["final_state_all_330"]["mean"] == load("reliability_current.json")["mean_kappa"]
    assert out["round1_all_330"]["mean"] == load("reliability_round1.json")["mean_kappa"]
    return out


# --------------------------------------------------------------------------
# 2. model-performance metrics and their child-cluster intervals
# --------------------------------------------------------------------------

def merged(rows: list[dict[str, str]], fields: list[str]) -> float | None:
    if not rows:
        return None
    return sum(sum(r[f] in ACCEPTABLE for r in rows) / len(rows) for f in fields) / len(fields)


def unsupported(rows: list[dict[str, str]], fields: list[str]) -> float | None:
    hall = sum(r[f] == "hallucinated" for r in rows for f in fields)
    opp = hall + sum(r[f] == "correctly_null" for r in rows for f in fields)
    return hall / opp if opp else None


def whole(rows: list[dict[str, str]], fields: list[str]) -> float | None:
    return sum(all(r[f] in ACCEPTABLE for f in fields) for r in rows) / len(rows) if rows else None


METRICS: dict[str, Callable] = {"merged_agreement": merged, "unsupported_rate": unsupported,
                                "whole_record": whole}


def cluster_ci(by_child: dict[str, list], fn: Callable, rng: random.Random) -> dict[str, Any]:
    kids = sorted(by_child)
    reps = []
    for _ in range(N_BOOT):
        rows = [r for _ in kids for r in by_child[kids[rng.randrange(len(kids))]]]
        v = fn(rows)
        if v is not None:
            reps.append(v)
    return {"lower": round(_percentile(reps, 0.025), 4), "upper": round(_percentile(reps, 0.975), 4),
            "n_valid": len(reps), "n_requested": N_BOOT, "unit": "child"}


def paired_diff_ci(by_child_a, by_child_b, fn, rng) -> dict[str, Any]:
    kids = sorted(by_child_a)
    reps = []
    for _ in range(N_BOOT):
        draw = [kids[rng.randrange(len(kids))] for _ in kids]
        a = fn([r for k in draw for r in by_child_a[k]])
        b = fn([r for k in draw for r in by_child_b[k]])
        if a is not None and b is not None:
            reps.append(a - b)
    lo, hi = _percentile(reps, 0.025), _percentile(reps, 0.975)
    return {"lower": round(lo, 4), "upper": round(hi, 4), "excludes_zero": lo > 0 or hi < 0,
            "n_valid": len(reps), "unit": "child"}


def performance(scored: dict, child_of: dict[str, str], exclude: set[str] = frozenset(),
                seed: int = SEED) -> dict[str, Any]:
    fields = scored["scoring_fields"]
    segs = [s for s in scored["gold"] if s not in exclude]
    out: dict[str, Any] = {"n_segments": len(segs), "n_children": len({child_of[s] for s in segs}),
                           "per_model": {}}
    by_model_child: dict[str, dict[str, list]] = {}
    for m in scored["models"]:
        by_child = defaultdict(list)
        for s in segs:
            by_child[child_of[s]].append(scored["gold"][s][m])
        by_model_child[m] = by_child
        rows = [r for rs in by_child.values() for r in rs]
        rng = random.Random(f"{seed}:{m}")
        out["per_model"][m] = {
            name: {"value": round(fn(rows, fields), 4),
                   "ci95": cluster_ci(by_child, lambda rr, fn=fn: fn(rr, fields), rng)}
            for name, fn in METRICS.items()
        }
    if "qwen3:14b" in by_model_child and "qwen2.5:7b" in by_model_child:
        rng = random.Random(f"{seed}:paired")
        out["paired_qwen3_14b_minus_qwen2_5_7b"] = {
            name: {
                "value": round(fn([r for rs in by_model_child["qwen3:14b"].values() for r in rs], fields)
                               - fn([r for rs in by_model_child["qwen2.5:7b"].values() for r in rs], fields), 4),
                "ci95": paired_diff_ci(by_model_child["qwen3:14b"], by_model_child["qwen2.5:7b"],
                                       lambda rr, fn=fn: fn(rr, fields), rng),
            }
            for name, fn in METRICS.items()
        }
    return out


def check_against_recorded(perf: dict, side: str) -> None:
    # Tolerance 1e-4: the recorder rounds each field to 4 places before
    # averaging, this module averages first. Any substantive disagreement is
    # orders of magnitude larger.
    hm = load("holdout_metrics.json")[side]
    for m, v in perf["per_model"].items():
        rec = hm["per_model"][m]
        assert abs(v["merged_agreement"]["value"] - rec["mean_field_accuracy"]) <= 1e-4, (side, m)
        assert abs(v["unsupported_rate"]["value"] - rec["unsupported_rate"]) <= 1e-4, (side, m)
        assert abs(v["whole_record"]["value"] - hm["whole_record"]["per_generator"][m]) <= 1e-4, (side, m)


# --------------------------------------------------------------------------
# 3. held-out leakage
# --------------------------------------------------------------------------

def leakage() -> dict[str, Any]:
    pool = load("annotation_pool.json")["pool"]
    batch = load("annotation_batch.json")
    hold = load("holdout_set.json")["segments"]
    pool_by_text = {p["chat_text"]: p["segment_id"] for p in pool}
    kept = {c["segment_id"] for c in batch["candidates"]}

    # Reconstruct the 506 pool segments stage 2 examined: it walks the pool in
    # order and stops per child at the 30th kept segment.
    by_child = defaultdict(list)
    for p in pool:
        by_child[p["child_id"]].append(p["segment_id"])
    examined = set()
    for ids in by_child.values():
        last = max(i for i, s in enumerate(ids) if s in kept)
        examined.update(ids[: last + 1])
    assert len(examined) == batch["yield"]["segments_attempted"]

    rows = []
    for h in hold:
        pid = pool_by_text.get(h["chat_text"])
        if pid is None:
            continue
        rows.append({"holdout_id": h["segment_id"], "pool_id": pid, "child_id": h["child_id"],
                     "model_output_examined": pid in examined, "annotated_in_main_batch": pid in kept})
    return {
        "n_holdout": len(hold),
        "n_in_pool": len(rows),
        "n_model_output_examined": sum(r["model_output_examined"] for r in rows),
        "n_annotated_in_main_batch": sum(r["annotated_in_main_batch"] for r in rows),
        "segments": rows,
        "cause": "Segment ids are assigned in selection order per session, so the same id names "
                 "different episodes under the 3,000 and 5,000 selection caps; build_holdout_set "
                 "excluded the pool by id.",
    }


def build() -> dict[str, Any]:
    batch_scored = load("scored_against_gold_augmented.json")
    hold_scored = load("scored_holdout.json")
    child_batch = {s: v["child_id"] for s, v in load("gold_labels.json")["gold"].items()}
    child_hold = {s: v["child_id"] for s, v in load("gold_holdout_labels.json")["gold"].items()}

    perf_batch = performance(batch_scored, child_batch)
    perf_hold = performance(hold_scored, child_hold)
    check_against_recorded(perf_batch, "batch")
    check_against_recorded(perf_hold, "holdout")

    leak = leakage()
    all_leaked = {r["holdout_id"] for r in leak["segments"]}
    examined = {r["holdout_id"] for r in leak["segments"] if r["model_output_examined"]}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_bootstrap": N_BOOT,
        "seed": SEED,
        "interval_method": "Child-cluster percentile bootstrap: children drawn with replacement "
                           "(as many draws as children), all segments of each drawn child retained, "
                           "2.5th and 97.5th percentiles of the replicate statistic. Same procedure "
                           "as reliability_stats.bootstrap_kappa with clusters.",
        "kappa_composition": kappa_composition(),
        "model_performance": {"main_batch": perf_batch, "holdout": perf_hold},
        "holdout_leakage": leak,
        "holdout_sensitivity": {
            "excluding_all_pool_episodes": performance(hold_scored, child_hold, all_leaked),
            "excluding_model_examined_only": performance(hold_scored, child_hold, examined),
        },
    }


def main() -> None:
    report = build()
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    kc = report["kappa_composition"]
    print("kappa:", {k: v["mean"] for k, v in kc.items()})
    for side, perf in report["model_performance"].items():
        print(side, perf["n_segments"])
        for m, v in perf["per_model"].items():
            print(f"  {m:18s}", {k: (x["value"], x["ci95"]["lower"], x["ci95"]["upper"]) for k, x in v.items()})
    lk = report["holdout_leakage"]
    print("leak:", lk["n_in_pool"], "in pool;", lk["n_model_output_examined"], "examined;",
          lk["n_annotated_in_main_batch"], "annotated")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
