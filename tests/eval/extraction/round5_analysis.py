"""Analyses answering the MDPI round-5 review comments. No model is called.

    R5-1  child weighting  retained evaluation episodes per child after overlap
                           exclusion (121 of 132), and equal-child-weighted
                           estimates of the three central metrics beside the
                           episode-weighted ones, with child-cluster intervals
    R5-2  reference nulls  capped (8-turn) vs shorter episodes: reference-null
                           share by field and reference-null slot counts, read
                           from round4_analysis.json (episode_cap.annotated_by_cap)

Equal-child weighting takes the metric within each child, then the unweighted
mean over children. For unsupported assertion the within-child denominator is
that child's reference-null slots, so the metric is undefined for a child with
none; such children are left out of the mean and counted.

    uv run python -m tests.eval.extraction.round5_analysis
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from tests.eval.extraction import round4_analysis as r4
from tests.eval.extraction.round3_analysis import METRICS, _percentile

RESULTS = Path(__file__).parent / "results"
OUT = RESULTS / "round5_analysis.json"
N_BOOT = 10_000
SEED = 20261002
FIELDS = r4.FIELDS
MODELS = r4.ORIGINAL_GENERATORS + ["qwen3:14b"]
FROZEN_PER_CHILD = 12


def child_mean(fn: Callable, rows_by_child: dict[str, list], kids: list[str]) -> tuple[float | None, int]:
    vals = [fn(rows_by_child[k], FIELDS) for k in kids]
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals) if vals else None), len(vals)


def child_weighting(pool: set, fkey: dict) -> dict[str, Any]:
    frozen = {s["segment_id"]: s for s in r4.load("holdout_set.json")["segments"]}
    scored = r4.load("scored_holdout.json")["gold"]
    kept = [s for s in frozen if fkey[s] not in pool]
    assert len(kept) == 121
    segs = defaultdict(list)
    for s in kept:
        segs[frozen[s]["child_id"]].append(s)
    kids = sorted(segs)
    rows = {m: {k: [scored[s][m] for s in segs[k]] for k in kids} for m in MODELS}

    out: dict[str, Any] = {
        "per_child": {k: {"frozen": FROZEN_PER_CHILD, "retained": len(segs[k]),
                          "removed": FROZEN_PER_CHILD - len(segs[k]),
                          "episode_weight": round(len(segs[k]) / len(kept), 4),
                          "equal_child_weight": round(1 / len(kids), 4),
                          "reference_null_slots": sum(r[f] in ("hallucinated", "correctly_null")
                                                      for r in rows["qwen3:14b"][k] for f in FIELDS)}
                      for k in kids},
        "per_model": {}, "paired_qwen3_14b_minus_qwen2_5_7b": {},
    }
    # Reference-null slots are a property of the reference standard, so identical for every model.
    for m in MODELS:
        assert all(sum(r[f] in ("hallucinated", "correctly_null") for r in rows[m][k] for f in FIELDS)
                   == out["per_child"][k]["reference_null_slots"] for k in kids)

    for m in MODELS:
        out["per_model"][m] = {}
        for name, fn in METRICS.items():
            ew = fn([r for k in kids for r in rows[m][k]], FIELDS)
            cw, n_def = child_mean(fn, rows[m], kids)
            rng = random.Random(f"{SEED}:{m}:{name}")
            reps = []
            for _ in range(N_BOOT):
                draw = [kids[rng.randrange(len(kids))] for _ in kids]
                v, _n = child_mean(fn, rows[m], draw)
                if v is not None:
                    reps.append(v)
            out["per_model"][m][name] = {
                "episode_weighted": round(ew, 4), "child_weighted": round(cw, 4),
                "child_weighted_minus_episode_weighted": round(cw - ew, 4),
                "n_children_defined": n_def,
                "ci95": {"lower": round(_percentile(reps, 0.025), 4), "upper": round(_percentile(reps, 0.975), 4),
                         "n_valid": len(reps), "unit": "child"}}

    for name, fn in METRICS.items():
        a, b = rows["qwen3:14b"], rows["qwen2.5:7b"]
        va, vb = child_mean(fn, a, kids)[0], child_mean(fn, b, kids)[0]
        rng = random.Random(f"{SEED}:paired:{name}")
        reps = []
        for _ in range(N_BOOT):
            draw = [kids[rng.randrange(len(kids))] for _ in kids]
            xa, xb = child_mean(fn, a, draw)[0], child_mean(fn, b, draw)[0]
            if xa is not None and xb is not None:
                reps.append(xa - xb)
        lo, hi = _percentile(reps, 0.025), _percentile(reps, 0.975)
        out["paired_qwen3_14b_minus_qwen2_5_7b"][name] = {
            "value": round(va - vb, 4), "lower": round(lo, 4), "upper": round(hi, 4),
            "excludes_zero": lo > 0 or hi < 0, "n_valid": len(reps), "unit": "child"}
    return out


def reference_nulls() -> dict[str, Any]:
    ab = r4.load("round4_analysis.json")["episode_cap"]["annotated_by_cap"]
    out: dict[str, Any] = {"definition": "capped = rendered CHAT text has exactly 8 speaker turns "
                                         "(the segmentation maximum); shorter = fewer than 8",
                           "source": "round4_analysis.json episode_cap.annotated_by_cap"}
    for side, groups in ab.items():
        out[side] = {}
        for g, v in groups.items():
            slots = {f: round(v["gold_null_share"][f] * v["n"]) for f in FIELDS}
            out[side][g] = {"n": v["n"], "gold_null_share": v["gold_null_share"],
                            "gold_null_mean": v["gold_null_mean"], "reference_null_slots": slots,
                            "reference_null_slots_total": sum(slots.values()), "field_slots": 4 * v["n"],
                            "qwen2.5:7b_unsupported": v["qwen2.5:7b_unsupported"]}
    return out


def build() -> dict[str, Any]:
    _sessions, _deid, episodes = r4.run_pipeline()
    u3000, u5000 = r4.universe(episodes, 3000), r4.universe(episodes, 5000)
    audit = r4.frame_audit(u5000, u3000)
    return {
        "generated_at": datetime.now(UTC).isoformat(), "n_bootstrap": N_BOOT, "seed": SEED,
        "interval_method": "child-cluster percentile bootstrap; equal-child statistic recomputed per replicate",
        "child_weighting_121": child_weighting(audit["_keys"]["pool"], audit["_keys"]["frozen"]),
        "reference_nulls_by_cap": reference_nulls(),
    }


def main() -> None:
    report = build()
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    cw = report["child_weighting_121"]
    print("retained:", {k: v["retained"] for k, v in cw["per_child"].items()})
    print("paired child-weighted:", cw["paired_qwen3_14b_minus_qwen2_5_7b"])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
