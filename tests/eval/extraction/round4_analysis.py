"""Analyses answering the MDPI round-4 review comments. No model is called.

Every quantity is computed from preserved artefacts (scored outputs, recorded
generator responses, MARS outcomes) or from the deterministic CHAT pipeline,
which is re-run here to recover stable episode identities.

    R2-2  frame audit      the intended pool-exclusion frame, rebuilt by episode
                           identity, against the ID-based frame actually used
    R2-1  same universe    evaluation-set segments that also belong to the
                           2,442-segment universe of the main batch, with and
                           without the batch's judgeability condition
    R2-3  MARS clustered   child-cluster paired bootstrap, all four fields,
          / R2-6           against an analytical random-candidate expectation
                           and a precisely defined strongest-generator policy
    R2-4  abstention       three null-output rates with explicit denominators
    R2-5  episode cap      model-free re-segmentation under larger caps, and
                           gold/model behaviour by capped vs uncapped episodes
    P-2   corpus table     per-child characteristics read from CHAT headers

Stable episode identity is (session_id, source start line). Segment IDs are
not stable: they are numbered in selection order and change with the cap. The
rendered text is not an identity either: two episodes of one session can render
identically (e.g. runs of unintelligible "xxx ." turns).

    uv run python -m tests.eval.extraction.round4_analysis
"""

from __future__ import annotations

import json
import random
import re
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from data.pipeline import segment_episodes as seg
from data.pipeline.build_dataset import FLUSBERG_CHILDREN, ROLLINS_CHILDREN
from data.pipeline.chat_parser import parse_corpus_directory
from data.pipeline.deidentify import deidentify_sessions
from data.pipeline.select_segments import select_segments
from tests.eval.extraction.mars_branch_replay import to_result
from tests.eval.extraction.round3_analysis import (
    ACCEPTABLE, METRICS, _percentile, cluster_ci, paired_diff_ci,
)
from tests.eval.extraction.segmentation_stats import _selected_episodes
from tests.eval.extraction.sample_real_segments import (
    ROLLINS_DIR, ensure_flusberg_extracted, render_segment_to_chat_text,
)
from src.backend.ml.extraction.mars.candidates import build_candidates

RESULTS = Path(__file__).parent / "results"
OUT = RESULTS / "round4_analysis.json"
N_BOOT = 10_000
SEED = 20261001
HOLDOUT_SEED = 20260916
FIELDS = ["domain", "modality", "prompt_level", "outcome"]
RECORDED = ["domain", "behavior", "modality", "prompt_level", "outcome"]
ORIGINAL_GENERATORS = ["llama3.2:latest", "qwen2.5:3b", "qwen2.5:7b"]


def load(name: str) -> Any:
    return json.loads((RESULTS / name).read_text())




def ci_of(by_child: dict[str, list], fn: Callable, rng: random.Random) -> dict[str, Any]:
    rows = [r for rs in by_child.values() for r in rs]
    return {"value": round(fn(rows), 4) if rows and fn(rows) is not None else None,
            "n": len(rows), "n_children": len(by_child), "ci95": cluster_ci(by_child, fn, rng)}


# --------------------------------------------------------------------------
# Pipeline, run once
# --------------------------------------------------------------------------

def run_pipeline():
    sessions = (parse_corpus_directory(ROLLINS_DIR, "rollins", ROLLINS_CHILDREN)
                + parse_corpus_directory(ensure_flusberg_extracted(), "flusberg", FLUSBERG_CHILDREN))
    deid = deidentify_sessions(sessions).sessions
    return sessions, deid, seg.segment_sessions(deid)


def universe(episodes, cap: int) -> list[dict[str, Any]]:
    """Selected segments, each tied to its source episode for a stable identity."""
    out = []
    segs = select_segments(episodes, max_segments=cap)
    eps = _selected_episodes(episodes, cap)
    for s, e in zip(segs, eps, strict=True):
        assert s.source.session_id == e.session_id and len(s.source.turns) == len(e.utterances)
        text = render_segment_to_chat_text(s)
        out.append({"segment_id": s.segment_id, "key": (e.session_id, e.start_line),
                    "episode_type": e.episode_type.value, "child_id": s.source.child_id,
                    "corpus": s.source.corpus, "session_id": s.source.session_id, "chat_text": text,
                    "n_turns": len(s.source.turns),
                    "n_chi": sum(t.speaker == "CHI" for t in s.source.turns),
                    "has_tier": any(t.spa or t.act or t.gpx for t in s.source.turns),
                    "usable": len(text) > 20 and bool(s.source.turns)})
    keys = [u["key"] for u in out]
    assert len(keys) == len(set(keys)), "episode identity is not unique"
    return out


# --------------------------------------------------------------------------
# R2-2  sampling-frame audit
# --------------------------------------------------------------------------

def frame_audit(u5000: list[dict], u3000: list[dict]) -> dict[str, Any]:
    pool = load("annotation_pool.json")["pool"]
    frozen = load("holdout_set.json")
    pool_ids = {p["segment_id"] for p in pool}
    by_id3 = {u["segment_id"]: u for u in u3000}
    # Pool IDs were issued by the cap-3000 selection, so they resolve there.
    assert all(by_id3[p["segment_id"]]["chat_text"] == p["chat_text"] for p in pool)
    pool_idents = {by_id3[p["segment_id"]]["key"] for p in pool}
    u3000_idents = {u["key"] for u in u3000}
    u5000_idents = {u["key"] for u in u5000}
    assert pool_idents <= u3000_idents, "pool is not inside the 2,442 universe"
    assert u3000_idents <= u5000_idents, "2,442 universe is not inside the 3,371 universe"

    usable = [u for u in u5000 if u["usable"]]
    used = [u for u in usable if u["segment_id"] not in pool_ids]                        # ID rule
    intended = [u for u in usable if u["key"] not in pool_idents]
    key = lambda u: u["key"]  # noqa: E731
    used_k, int_k = {key(u) for u in used}, {key(u) for u in intended}
    wrongly_retained = [u for u in used if key(u) not in int_k]
    wrongly_excluded = [u for u in intended if key(u) not in used_k]
    both = [u for u in used if key(u) in int_k]

    # Reproduce the frozen draw from the reconstructed ID-based frame. If this
    # matches, the frame used in 2026-09-16 is the one audited here.
    by_child = defaultdict(list)
    for u in used:
        by_child[u["child_id"]].append(u["segment_id"])
    rng, redraw = random.Random(HOLDOUT_SEED), []
    for c in sorted(by_child):
        ids = list(by_child[c])
        rng.shuffle(ids)
        redraw.extend(ids[:frozen["per_child_target"]])
    frozen_ids = [s["segment_id"] for s in frozen["segments"]]
    assert redraw == frozen_ids, "could not reproduce the frozen draw"

    by_id5 = {u["segment_id"]: u for u in u5000}
    assert all(by_id5[s["segment_id"]]["chat_text"] == s["chat_text"] for s in frozen["segments"])
    frozen_keys = {by_id5[s["segment_id"]]["key"] for s in frozen["segments"]}
    per_child = {}
    for c in sorted({u["child_id"] for u in usable}):
        f = lambda xs: sum(u["child_id"] == c for u in xs)  # noqa: E731
        per_child[c] = {"used_frame": f(used), "intended_frame": f(intended), "in_both": f(both),
                        "wrongly_retained": f(wrongly_retained), "wrongly_excluded": f(wrongly_excluded),
                        "coverage_of_intended": round(f(both) / f(intended), 4),
                        "sampling_fraction_used": round(frozen["per_child_target"] / f(used), 4)}

    def profile(xs: list[dict]) -> dict[str, Any]:
        return {"n": len(xs),
                "mean_turns": round(statistics.mean(u["n_turns"] for u in xs), 3) if xs else None,
                "share_8_turns": round(sum(u["n_turns"] == 8 for u in xs) / len(xs), 4) if xs else None,
                "mean_child_turns": round(statistics.mean(u["n_chi"] for u in xs), 3) if xs else None,
                "share_with_behavioural_tier": round(sum(u["has_tier"] for u in xs) / len(xs), 4) if xs else None,
                "share_in_2442_universe": round(sum(key(u) in u3000_idents for u in xs) / len(xs), 4) if xs else None,
                "episode_types": dict(Counter(u["episode_type"] for u in xs).most_common())}

    return {
        "n_universe_3371": len(u5000), "n_usable": len(usable), "n_pool": len(pool),
        "n_used_frame_id_rule": len(used), "n_intended_frame_identity_rule": len(intended),
        "n_in_both": len(both), "n_wrongly_retained_pool": len(wrongly_retained),
        "n_wrongly_excluded_non_pool": len(wrongly_excluded),
        "share_of_intended_frame_excluded": round(len(wrongly_excluded) / len(intended), 4),
        "share_of_used_frame_that_is_pool": round(len(wrongly_retained) / len(used), 4),
        "frozen_draw_reproduced": True,
        "frozen_segments_in_pool": sum(k in pool_idents for k in frozen_keys),
        "per_child": per_child,
        "profile": {"analysed_frame_in_both": profile(both), "wrongly_excluded": profile(wrongly_excluded),
                    "wrongly_retained": profile(wrongly_retained), "intended_frame": profile(intended)},
        # Within-child episode-type mix of the intended frame, for post-stratification.
        "_type": {"intended": {c: Counter(u["episode_type"] for u in intended if u["child_id"] == c)
                               for c in per_child},
                  "analysed": {c: Counter(u["episode_type"] for u in both if u["child_id"] == c)
                               for c in per_child},
                  "frozen": {s["segment_id"]: by_id5[s["segment_id"]]["episode_type"] for s in frozen["segments"]}},
        "_keys": {"u3000": u3000_idents, "pool": pool_idents, "frozen": {s["segment_id"]: by_id5[s["segment_id"]]["key"] for s in frozen["segments"]}},
    }


# --------------------------------------------------------------------------
# R2-1  same-universe, unconditioned sensitivity
# --------------------------------------------------------------------------

def judgeable(cand: dict | None) -> bool:
    """The batch's admission rule: at least one populated recorded field."""
    if not cand:
        return False
    fields = cand.get("extracted_fields") or {}
    return any(fields.get(f) is not None for f in RECORDED)


def same_universe(audit: dict) -> dict[str, Any]:
    scored_h, scored_b = load("scored_holdout.json"), load("scored_against_gold_augmented.json")
    frozen = {s["segment_id"]: s for s in load("holdout_set.json")["segments"]}
    hb = {c["segment_id"]: c for c in load("holdout_batch.json")["candidates"]}
    child_b = {s: v["child_id"] for s, v in load("gold_labels.json")["gold"].items()}
    u3000, pool, fkey = audit["_keys"]["u3000"], audit["_keys"]["pool"], audit["_keys"]["frozen"]

    tags = {}
    for sid, s in frozen.items():
        k = fkey[sid]
        tags[sid] = {"child_id": s["child_id"], "in_pool": k in pool, "in_2442": k in u3000,
                     "judgeable_all3": all(judgeable(hb[sid]["candidates"].get(m)) for m in ORIGINAL_GENERATORS)}

    groups = {
        "main_batch_330": ("batch", list(scored_b["gold"])),
        "frozen_132": ("hold", list(frozen)),
        "overlap_excluded_121": ("hold", [s for s in frozen if not tags[s]["in_pool"]]),
        "same_universe_unconditioned": ("hold", [s for s in frozen if not tags[s]["in_pool"] and tags[s]["in_2442"]]),
        "same_universe_judgeable": ("hold", [s for s in frozen if not tags[s]["in_pool"] and tags[s]["in_2442"]
                                              and tags[s]["judgeable_all3"]]),
        "higher_cap_only": ("hold", [s for s in frozen if not tags[s]["in_pool"] and not tags[s]["in_2442"]]),
        "121_judgeable": ("hold", [s for s in frozen if not tags[s]["in_pool"] and tags[s]["judgeable_all3"]]),
        "121_not_judgeable": ("hold", [s for s in frozen if not tags[s]["in_pool"] and not tags[s]["judgeable_all3"]]),
    }
    out: dict[str, Any] = {"groups": {}, "tags_summary": {}}
    for name, (side, segs) in groups.items():
        scored = scored_b if side == "batch" else scored_h
        cmap = child_b if side == "batch" else {s: tags[s]["child_id"] for s in segs}
        per_model = {}
        for m in ORIGINAL_GENERATORS + ["qwen3:14b"]:
            by_child = defaultdict(list)
            for s in segs:
                by_child[cmap[s]].append(scored["gold"][s][m])
            rng = random.Random(f"{SEED}:{name}:{m}")
            per_model[m] = {k: ci_of(by_child, lambda rr, fn=fn: fn(rr, FIELDS), rng) for k, fn in METRICS.items()}
        out["groups"][name] = {"n": len(segs), "n_children": len({cmap[s] for s in segs}), "per_model": per_model}

    # Paired contrast on identical children: same-universe unconditioned minus judgeable-only is not
    # paired (the sets differ), so the within-121 contrast judgeable vs not is reported per model
    # as a child-cluster difference of two independent subsets.
    for m in ORIGINAL_GENERATORS + ["qwen3:14b"]:
        a = defaultdict(list); b = defaultdict(list)
        for s in groups["121_judgeable"][1]:
            a[tags[s]["child_id"]].append(scored_h["gold"][s][m])
        for s in groups["121_not_judgeable"][1]:
            b[tags[s]["child_id"]].append(scored_h["gold"][s][m])
        kids = sorted(set(a) | set(b))
        rng = random.Random(f"{SEED}:jdiff:{m}")
        reps = []
        for _ in range(N_BOOT):
            draw = [kids[rng.randrange(len(kids))] for _ in kids]
            ra = [r for k in draw for r in a.get(k, [])]
            rb = [r for k in draw for r in b.get(k, [])]
            if ra and rb:
                reps.append(METRICS["merged_agreement"](ra, FIELDS) - METRICS["merged_agreement"](rb, FIELDS))
        va = METRICS["merged_agreement"]([r for rs in a.values() for r in rs], FIELDS)
        vb = METRICS["merged_agreement"]([r for rs in b.values() for r in rs], FIELDS)
        out.setdefault("judgeable_minus_not_merged", {})[m] = {
            "value": round(va - vb, 4), "lower": round(_percentile(reps, 0.025), 4),
            "upper": round(_percentile(reps, 0.975), 4), "n_valid": len(reps), "unit": "child"}
    # Differences between groups, children resampled jointly (unpaired sets, shared clusters).
    def gdiff(ga: str, gb: str, m: str, metric: str) -> dict[str, Any]:
        def rows_by_child(g):
            side, segs = groups[g]
            scored = scored_b if side == "batch" else scored_h
            cmap = child_b if side == "batch" else {x: tags[x]["child_id"] for x in segs}
            d = defaultdict(list)
            for x in segs:
                d[cmap[x]].append(scored["gold"][x][m])
            return d
        a, b = rows_by_child(ga), rows_by_child(gb)
        fn = METRICS[metric]
        kids = sorted(set(a) | set(b))
        rng = random.Random(f"{SEED}:gdiff:{ga}:{gb}:{m}:{metric}")
        reps = []
        for _ in range(N_BOOT):
            draw = [kids[rng.randrange(len(kids))] for _ in kids]
            ra = [r for k in draw for r in a.get(k, [])]
            rb = [r for k in draw for r in b.get(k, [])]
            va, vb = (fn(ra, FIELDS) if ra else None), (fn(rb, FIELDS) if rb else None)
            if va is not None and vb is not None:
                reps.append(va - vb)
        v = fn([r for rs in a.values() for r in rs], FIELDS) - fn([r for rs in b.values() for r in rs], FIELDS)
        lo, hi = _percentile(reps, 0.025), _percentile(reps, 0.975)
        return {"value": round(v, 4), "lower": round(lo, 4), "upper": round(hi, 4),
                "excludes_zero": lo > 0 or hi < 0, "n_valid": len(reps), "unit": "child"}

    contrasts = [("main_batch_330", "same_universe_judgeable"), ("main_batch_330", "same_universe_unconditioned"),
                 ("higher_cap_only", "same_universe_unconditioned"), ("main_batch_330", "overlap_excluded_121")]
    out["contrasts"] = {f"{a}-minus-{b}": {m: {k: gdiff(a, b, m, k) for k in ("merged_agreement", "unsupported_rate")}
                                           for m in ORIGINAL_GENERATORS + ["qwen3:14b"]} for a, b in contrasts}

    # R2-2 diagnostic: reweight the 121 to the intended frame's episode-type mix within child.
    # Behavioural tiers are not usable here: they exist only in Rollins transcripts, so tier
    # presence is constant within child and child-stratified sampling already fixes it.
    def poststrat(level: Callable[[str], str], frame: str) -> dict[str, Any]:
        mix, ftype = audit["_type"][frame], audit["_type"]["frozen"]
        segs121 = groups["overlap_excluded_121"][1]
        w, unaccounted = {}, {}
        for c in sorted({tags[x]["child_id"] for x in segs121}):
            cs = [x for x in segs121 if tags[x]["child_id"] == c]
            target = Counter()
            for t, n in mix[c].items():
                target[level(t)] += n
            tot = sum(target.values())
            have = Counter(level(ftype[x]) for x in cs)
            covered = sum(n for k, n in target.items() if have[k])
            unaccounted[c] = round(1 - covered / tot, 4)
            for x in cs:
                k = level(ftype[x])
                # weight = intended share of cell (renormalised over covered cells) / sample share
                w[x] = (target[k] / covered) / (have[k] / len(cs))
        per_model = {}
        for m in ORIGINAL_GENERATORS + ["qwen3:14b"]:
            g = lambda x: scored_h["gold"][x][m]  # noqa: E731
            W = sum(w.values())
            hall = sum(w[x] * sum(g(x)[f] == "hallucinated" for f in FIELDS) for x in segs121)
            opp = hall + sum(w[x] * sum(g(x)[f] == "correctly_null" for f in FIELDS) for x in segs121)
            per_model[m] = {
                "merged_agreement": round(sum(w[x] * sum(g(x)[f] in ACCEPTABLE for f in FIELDS) / len(FIELDS)
                                              for x in segs121) / W, 4),
                "unsupported_rate": round(hall / opp, 4),
                "whole_record": round(sum(w[x] * all(g(x)[f] in ACCEPTABLE for f in FIELDS) for x in segs121) / W, 4)}
        return {"weights_range": [round(min(w.values()), 3), round(max(w.values()), 3)],
                "unaccounted_intended_share_by_child": unaccounted, "per_model": per_model}

    # Reweighting the same sample to the analysed frame and to the intended frame; the
    # difference between the two isolates the frame distortion from sampling noise.
    levels = {"episode_type_7": lambda t: t, "other_vs_typed": lambda t: "other" if t == "other" else "typed"}
    out["poststratified_121"] = {}
    for lname, lv in levels.items():
        a, i = poststrat(lv, "analysed"), poststrat(lv, "intended")
        out["poststratified_121"][lname] = {
            "to_analysed_frame": a, "to_intended_frame": i,
            "frame_effect": {m: {k: round(i["per_model"][m][k] - a["per_model"][m][k], 4)
                                 for k in a["per_model"][m]} for m in a["per_model"]}}
    out["tags_summary"] = {
        "n_frozen": len(tags), "in_pool": sum(t["in_pool"] for t in tags.values()),
        "in_2442": sum(t["in_2442"] for t in tags.values()),
        "judgeable_all3": sum(t["judgeable_all3"] for t in tags.values()),
        "judgeable_all3_among_121": sum(t["judgeable_all3"] for t in tags.values() if not t["in_pool"]),
    }
    return out


# --------------------------------------------------------------------------
# R2-3 / R2-6  MARS, clustered, with exact comparator definitions
# --------------------------------------------------------------------------

def mars_clustered() -> dict[str, Any]:
    scored = load("scored_against_gold.json")["gold"]
    outcomes = load("mars_outcomes.json")
    batch = {c["segment_id"]: c for c in load("annotation_batch.json")["candidates"]}
    child = {s: v["child_id"] for s, v in load("gold_labels.json")["gold"].items()}
    msa = load("mars_selection_analysis.json")
    strength = ["qwen2.5:7b", "llama3.2:latest", "qwen2.5:3b"]  # main-batch merged agreement order
    b330 = load("holdout_metrics.json")["batch"]["per_model"]
    assert sorted(strength, key=lambda m: -b330[m]["mean_field_accuracy"]) == strength

    judged = sorted(s for s, o in outcomes.items()
                    if o.get("status") == "success" and (o.get("candidate_count") or 0) > 1)
    assert len(judged) == msa["n_judged_segments"]

    ok = lambda s, m, f: scored[s][m][f] in ACCEPTABLE  # noqa: E731
    rows: dict[str, dict[str, dict[str, float]]] = {}
    n_best_not_reviewable = 0
    for s in judged:
        entry = batch[s]
        results = [to_result(entry, m, entry["candidates"][m]) for m in ORIGINAL_GENERATORS]
        cands, _ = build_candidates(results, with_rejections=True)
        assert len(cands) == outcomes[s]["candidate_count"], s
        cand_gens = [list(c.generator_ids) for c in cands]
        reviewable = [g for gs in cand_gens for g in gs]
        pick = outcomes[s]["selected_generator_ids"][0]
        best_rev = next(m for m in strength if m in reviewable)
        n_best_not_reviewable += "qwen2.5:7b" not in reviewable
        rows[s] = {}
        for f in FIELDS:
            rows[s][f] = {
                "mars": float(ok(s, pick, f)),
                # R2-6 definitions
                "random_expected_reviewable": statistics.mean(float(ok(s, gs[0], f)) for gs in cand_gens),
                "random_expected_all_generators": statistics.mean(float(ok(s, m, f)) for m in ORIGINAL_GENERATORS),
                "best_fixed": float(ok(s, "qwen2.5:7b", f)),
                "best_reviewable_fallback": float(ok(s, best_rev, f)),
            }

    by_child = defaultdict(list)
    for s in judged:
        by_child[child[s]].append(s)
    kids = sorted(by_child)

    def boot(fa: str, fb: str, f: str, tag: str) -> dict[str, Any]:
        rng = random.Random(f"{SEED}:{tag}:{f}")
        value = statistics.mean(rows[s][f][fa] - rows[s][f][fb] for s in judged)
        reps = []
        for _ in range(N_BOOT):
            draw = [s for _ in kids for s in by_child[kids[rng.randrange(len(kids))]]]
            reps.append(sum(rows[s][f][fa] - rows[s][f][fb] for s in draw) / len(draw))
        lo, hi = _percentile(reps, 0.025), _percentile(reps, 0.975)
        return {"value": round(value, 4), "lower": round(lo, 4), "upper": round(hi, 4),
                "excludes_zero": lo > 0 or hi < 0, "n_valid": len(reps), "unit": "child"}

    comps = {
        "vs_random_reviewable": "random_expected_reviewable",
        "vs_random_all_generators": "random_expected_all_generators",
        "vs_best_fixed": "best_fixed",
        "vs_best_reviewable_fallback": "best_reviewable_fallback",
    }
    per_field = {}
    for f in FIELDS:
        per_field[f] = {k: round(statistics.mean(rows[s][f][k] for s in judged), 4)
                        for k in ("mars", "random_expected_reviewable", "random_expected_all_generators",
                                  "best_fixed", "best_reviewable_fallback")}
        for name, comp in comps.items():
            per_field[f][name] = boot("mars", comp, f, name)
    mean_of = lambda k: round(statistics.mean(per_field[f][k] for f in FIELDS), 4)  # noqa: E731
    # Published random baseline (2,000 seeded draws over all three generators) must equal the
    # analytical expectation over all three generators, up to Monte Carlo error.
    published = msa["mean_accuracy"]["random_candidate"]
    assert abs(published - mean_of("random_expected_all_generators")) < 0.005
    return {"n_judged": len(judged), "n_children": len(kids),
            "segments_per_child": {k: len(v) for k, v in sorted(by_child.items())},
            "n_segments_best_generator_not_reviewable": n_best_not_reviewable,
            "strength_order": strength, "per_field": per_field,
            "mean": {k: mean_of(k) for k in ("mars", "random_expected_reviewable",
                                             "random_expected_all_generators", "best_fixed",
                                             "best_reviewable_fallback")},
            "published_random_baseline": published,
            "published_random_method": "mean of 2,000 seeded (20260916) uniform draws over all three "
                                       "generators' outputs per segment; paired CIs used one further draw "
                                       "(seed 20260917)"}


# --------------------------------------------------------------------------
# R2-4  abstention metrics
# --------------------------------------------------------------------------

def abstention() -> dict[str, Any]:
    # How often a null is an omitted key rather than an explicit null in the recorded output.
    omitted = Counter()
    for fname in ("annotation_batch_augmented.json", "holdout_batch.json"):
        for c in load(fname)["candidates"]:
            for m, cand in c["candidates"].items():
                ef = (cand or {}).get("extracted_fields")
                if not cand:
                    omitted["whole_candidate_absent"] += 1
                    continue
                for f in FIELDS:
                    if ef is None or f not in ef:
                        omitted["field_key_absent"] += 1
                    elif ef[f] is None:
                        omitted["explicit_null"] += 1
    out: dict[str, Any] = {"null_provenance_in_recorded_outputs": dict(omitted)}
    for name, fname in (("main_batch_330", "scored_against_gold_augmented.json"), ("frozen_132", "scored_holdout.json")):
        sc = load(fname)
        out[name] = {}
        for m in sc["models"]:
            c = Counter(sc["gold"][s][m][f] for s in sc["gold"] for f in FIELDS)
            n = sum(c.values())
            populated = c["correct"] + c["incorrect"] + c["missing"]
            gnull = c["correctly_null"] + c["hallucinated"]
            out[name][m] = {
                "n_field_slots": n, "counts": dict(c),
                "reported_missing_over_all_slots": round(c["missing"] / n, 4),
                "null_on_gold_populated": round(c["missing"] / populated, 4) if populated else None,
                "overall_model_null_rate": round((c["missing"] + c["correctly_null"]) / n, 4),
                "null_on_gold_null": round(c["correctly_null"] / gnull, 4) if gnull else None,
                "gold_populated_share": round(populated / n, 4),
            }
    return out


# --------------------------------------------------------------------------
# R2-5  episode cap
# --------------------------------------------------------------------------

def cap_sensitivity(deid) -> dict[str, Any]:
    orig = seg.MAX_EPISODE_TURNS
    res = {}
    try:
        for cap in (8, 12, 16, 24, 10_000):
            seg.MAX_EPISODE_TURNS = cap
            eps = seg.segment_sessions(deid)
            lens = [len(e.utterances) for e in eps]
            covered = len({(e.session_id, u.line_number) for e in eps for u in e.utterances})
            res[str(cap) if cap < 10_000 else "none"] = {
                "n_episodes": len(eps), "share_at_cap": round(sum(x >= cap for x in lens) / len(lens), 4),
                "mean_turns": round(statistics.mean(lens), 3), "median_turns": statistics.median(lens),
                "p90_turns": sorted(lens)[int(0.9 * len(lens))], "max_turns": max(lens),
                "utterances_covered": covered, "utterances_total": sum(len(x.utterances) for x in deid)}
    finally:
        seg.MAX_EPISODE_TURNS = orig
    return res


def by_cap(chat_turns: Callable[[str], int]) -> dict[str, Any]:
    out = {}
    for name, fname, gname, bname in (
            ("main_batch_330", "scored_against_gold_augmented.json", "gold_labels.json", "annotation_batch.json"),
            ("frozen_132", "scored_holdout.json", "gold_holdout_labels.json", "holdout_batch.json")):
        sc, gold = load(fname), load(gname)["gold"]
        text = {c["segment_id"]: c["chat_text"] for c in load(bname)["candidates"]}
        grp = {"capped_8": [s for s in sc["gold"] if chat_turns(text[s]) == 8],
               "under_8": [s for s in sc["gold"] if chat_turns(text[s]) < 8]}
        out[name] = {}
        for g, segs in grp.items():
            gnull = {f: round(sum(gold[s]["field_values"].get(f) is None for s in segs) / len(segs), 4)
                     for f in FIELDS}
            by_child = defaultdict(list)
            for s in segs:
                by_child[gold[s]["child_id"]].append(sc["gold"][s]["qwen2.5:7b"])
            rows = [r for rs in by_child.values() for r in rs]
            out[name][g] = {"n": len(segs), "gold_null_share": gnull,
                            "gold_null_mean": round(statistics.mean(gnull.values()), 4),
                            "qwen2.5:7b_merged": round(METRICS["merged_agreement"](rows, FIELDS), 4),
                            "qwen2.5:7b_unsupported": round(METRICS["unsupported_rate"](rows, FIELDS), 4)}
    return out


# --------------------------------------------------------------------------
# P-2  corpus characteristics
# --------------------------------------------------------------------------

def _months(age: str) -> float | None:
    m = re.match(r"(\d+);(\d*)\.?(\d*)", age or "")
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
    return y * 12 + mo + d / 30.4


def _fmt(months: float) -> str:
    return f"{int(months // 12)};{int(months % 12):02d}"


def corpus_table(sessions) -> list[dict[str, Any]]:
    by_child = defaultdict(list)
    for s in sessions:
        by_child[(s.corpus, s.child_id)].append(s)
    rows = []
    for (corpus, child), ss in sorted(by_child.items()):
        ages = [a for a in (_months(s.header.participant_ids.get("CHI", {}).get("age", "")) for s in ss) if a is not None]
        sexes = {s.header.participant_ids.get("CHI", {}).get("sex") for s in ss} - {None}
        partners = Counter(u.speaker for s in ss for u in s.utterances if u.speaker != "CHI")
        types = {s.header.raw_headers.get("Types") for s in ss} - {None}
        rows.append({
            "corpus": corpus, "child_id": child, "sessions": len(ss),
            "age_first": _fmt(min(ages)) if ages else None, "age_last": _fmt(max(ages)) if ages else None,
            "n_sessions_with_age": len(ages), "sex": "/".join(sorted(sexes)) or None,
            "types_header": "; ".join(sorted(types)) or None,
            "utterances": sum(len(s.utterances) for s in ss),
            "child_utterances": sum(u.speaker == "CHI" for s in ss for u in s.utterances),
            "main_partner": partners.most_common(1)[0][0] if partners else None,
        })
    return rows


# --------------------------------------------------------------------------
# P-3  annotator confusion matrices (final pre-adjudication state, 330)
# --------------------------------------------------------------------------

def confusion() -> dict[str, Any]:
    fa, fb = load("gold_annotator_a.json"), load("gold_annotator_b.json")
    ids = sorted(set(fa) & set(fb))
    assert len(ids) == 330
    out = {}
    for f in FIELDS:
        pairs = [(str(fa[s]["field_values"].get(f)), str(fb[s]["field_values"].get(f))) for s in ids]
        cats = sorted({x for p in pairs for x in p})
        c = Counter(pairs)
        out[f] = {"categories": cats, "matrix_a_rows_b_cols": [[c[(r, k)] for k in cats] for r in cats],
                  "observed_agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4)}
    rel = load("reliability_current.json")["fields"]
    for f in FIELDS:
        assert abs(out[f]["observed_agreement"] - rel[f]["observed_agreement"]) < 1e-3, f
    return out


# --------------------------------------------------------------------------

def build() -> dict[str, Any]:
    sessions, deid, episodes = run_pipeline()
    u3000, u5000 = universe(episodes, 3000), universe(episodes, 5000)
    assert (len(u3000), len(u5000)) == (2442, 3371)
    audit = frame_audit(u5000, u3000)
    su = same_universe(audit)
    audit.pop("_keys"); audit.pop("_type")
    turns = lambda t: sum(line.startswith("*") for line in t.split("\n"))  # noqa: E731
    return {
        "generated_at": datetime.now(UTC).isoformat(), "n_bootstrap": N_BOOT, "seed": SEED,
        "interval_method": "child-cluster percentile bootstrap, as in round3_analysis",
        "frame_audit": audit, "same_universe": su, "mars_clustered": mars_clustered(),
        "abstention": abstention(),
        "episode_cap": {"resegmentation": cap_sensitivity(deid), "annotated_by_cap": by_cap(turns)},
        "corpus_characteristics": corpus_table(sessions),
        "annotator_confusion": confusion(),
    }


def main() -> None:
    report = build()
    OUT.write_text(json.dumps(report, indent=2, default=list) + "\n")
    fa = report["frame_audit"]
    print("frame:", {k: v for k, v in fa.items() if k.startswith("n_") or k.startswith("share")})
    print("same-universe tags:", report["same_universe"]["tags_summary"])
    print("mars mean:", report["mars_clustered"]["mean"])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
