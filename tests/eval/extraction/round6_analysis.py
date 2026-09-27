"""Analyses answering the round-6 technical questions. No model is called.

    R6-1  source-turn audit  every episode in the post-audit 121-set against every
                             episode in the 330 main batch, by source-line
                             identity (session_id, CHAT line number) of each
                             utterance used to build the episode; if any
                             evaluation episode shares a turn, the central
                             metrics are recomputed without it (sensitivity only)
    R6-3  reliability 121    Cohen's kappa per field, pre-adjudication holdout
                             annotators A and B, on the 121, beside the 132

Why line identity and not the stable-identity key: episode boundaries start one
utterance before the opening child turn, so adjacent episodes of one session can
share a source utterance while having different (session_id, start_line) keys.
Rendered text is not used, because distinct episodes can render identically.

    uv run python -m tests.eval.extraction.round6_analysis
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.extraction import reliability_stats as rel
from tests.eval.extraction import round4_analysis as r4
from tests.eval.extraction.round3_analysis import METRICS, paired_diff_ci

RESULTS = Path(__file__).parent / "results"
OUT = RESULTS / "round6_analysis.json"
SEED = 20261003
FIELDS = r4.FIELDS
MODELS = r4.ORIGINAL_GENERATORS + ["qwen3:14b"]


def source_lines(episodes) -> dict[tuple[str, int], frozenset[int]]:
    """Stable episode key -> CHAT line numbers of the utterances it was built from."""
    out = {}
    for e in episodes:
        k = (e.session_id, e.start_line)
        assert k not in out, "episode identity is not unique"
        lines = frozenset(u.line_number for u in e.utterances)
        assert len(lines) == len(e.utterances), "two utterances share a line number"
        out[k] = lines
    return out


def position(lines: frozenset[int], ln: int) -> str:
    return "first" if ln == min(lines) else "last" if ln == max(lines) else "interior"


def turn_audit(episodes, u3000: list[dict], u5000: list[dict], pool: set, fkey: dict) -> dict[str, Any]:
    lines = source_lines(episodes)
    by_id3 = {u["segment_id"]: u for u in u3000}
    frozen = {s["segment_id"]: s for s in r4.load("holdout_set.json")["segments"]}
    main_ids = list(r4.load("scored_against_gold_augmented.json")["gold"])
    assert len(main_ids) == 330
    main = {m: by_id3[m] for m in main_ids}
    eval121 = [s for s in frozen if fkey[s] not in pool]
    assert len(eval121) == 121

    main_by_session = defaultdict(list)
    for m, u in main.items():
        main_by_session[u["key"][0]].append(m)
    main_keys = {u["key"] for u in main.values()}

    affected, shared_all = [], set()
    for s in eval121:
        k = fkey[s]
        assert k not in main_keys, "identity overlap survived the round-4 exclusion"
        ev = lines[k]
        matches = []
        for m in main_by_session[k[0]]:
            common = ev & lines[main[m]["key"]]
            if common:
                mv = lines[main[m]["key"]]
                matches.append({"main_segment_id": m, "main_start_line": main[m]["key"][1],
                                "eval_position": [position(ev, ln) for ln in sorted(common)],
                                "main_position": [position(mv, ln) for ln in sorted(common)],
                                "shared_lines": sorted(common), "n_shared": len(common),
                                "main_n_turns": len(lines[main[m]["key"]])})
        if matches:
            shared = set().union(*(set(x["shared_lines"]) for x in matches))
            shared_all |= {(k[0], ln) for ln in shared}
            affected.append({"segment_id": s, "child_id": frozen[s]["child_id"], "session_id": k[0],
                             "start_line": k[1], "n_turns": len(ev), "matches": matches,
                             "n_shared_turns": len(shared)})

    # Context: the same audit on the full 132 (identity overlaps included).
    ident_132 = sum(fkey[s] in main_keys for s in frozen)
    turn_132 = sum(any(lines[fkey[s]] & lines[main[m]["key"]] for m in main_by_session[fkey[s][0]])
                   for s in frozen)

    per_child = defaultdict(lambda: {"affected_eval_episodes": 0, "shared_turns": 0})
    for a in affected:
        per_child[a["child_id"]]["affected_eval_episodes"] += 1
    for sess, _ln in shared_all:
        child = next(a["child_id"] for a in affected if a["session_id"] == sess)
        per_child[child]["shared_turns"] += 1

    return {
        "matching_key": "(session_id, CHAT source line number) of every utterance in the episode",
        "n_eval": len(eval121), "n_main": len(main),
        "n_eval_affected": len(affected),
        "n_main_involved": len({m["main_segment_id"] for a in affected for m in a["matches"]}),
        "n_distinct_shared_turns": len(shared_all),
        "n_eval_remaining": len(eval121) - len(affected),
        "per_child": dict(sorted(per_child.items())),
        "per_session": {sess: sum(1 for x in shared_all if x[0] == sess) for sess in sorted({x[0] for x in shared_all})},
        "affected": affected,
        "context_frozen_132": {"identity_overlap_with_330": ident_132, "turn_overlap_with_330": turn_132},
        "_eval121": eval121, "_affected_ids": {a["segment_id"] for a in affected},
    }


def sensitivity(audit: dict) -> dict[str, Any] | None:
    if not audit["n_eval_affected"]:
        return None
    frozen = {s["segment_id"]: s for s in r4.load("holdout_set.json")["segments"]}
    scored = r4.load("scored_holdout.json")["gold"]
    sets = {"overlap_excluded_121": audit["_eval121"],
            "turn_overlap_excluded": [s for s in audit["_eval121"] if s not in audit["_affected_ids"]]}
    out: dict[str, Any] = {}
    for name, segs in sets.items():
        per_model = {}
        for m in MODELS:
            by_child = defaultdict(list)
            for s in segs:
                by_child[frozen[s]["child_id"]].append(scored[s][m])
            rng = random.Random(f"{SEED}:{name}:{m}")
            per_model[m] = {k: r4.ci_of(by_child, lambda rr, fn=fn: fn(rr, FIELDS), rng) for k, fn in METRICS.items()}
        by_mc = {m: defaultdict(list) for m in ("qwen3:14b", "qwen2.5:7b")}
        for m in by_mc:
            for s in segs:
                by_mc[m][frozen[s]["child_id"]].append(scored[s][m])
        paired = {}
        for k, fn in METRICS.items():
            rng = random.Random(f"{SEED}:{name}:paired:{k}")
            val = (fn([r for rs in by_mc["qwen3:14b"].values() for r in rs], FIELDS)
                   - fn([r for rs in by_mc["qwen2.5:7b"].values() for r in rs], FIELDS))
            paired[k] = {"value": round(val, 4),
                         "ci95": paired_diff_ci(by_mc["qwen3:14b"], by_mc["qwen2.5:7b"], lambda rr, fn=fn: fn(rr, FIELDS), rng)}
        out[name] = {"n": len(segs), "n_children": len({frozen[s]["child_id"] for s in segs}), "per_model": per_model,
                     "paired_qwen3_14b_minus_qwen2_5_7b": paired}
    return out


def reliability_121(eval121: list[str]) -> dict[str, Any]:
    a = json.loads(rel.annotations_path("holdout_annotator_a").read_text())
    b = json.loads(rel.annotations_path("holdout_annotator_b").read_text())
    recorded = r4.load("reliability_holdout.json")
    full = rel.build_report(a, b, "holdout_annotator_a vs holdout_annotator_b")
    # The recomputation over all 132 must reproduce the recorded 132 figures before the subset is trusted.
    assert full["n_segments"] == 132 and full["mean_kappa"] == recorded["mean_kappa"]
    for f in rel.CATEGORICAL_FIELDS:
        assert full["fields"][f]["kappa"] == recorded["fields"][f]["kappa"]
        assert full["fields"][f]["cluster_bootstrap_ci"] == recorded["fields"][f]["cluster_bootstrap_ci"]
    keep = set(eval121)
    sub = rel.build_report({k: v for k, v in a.items() if k in keep}, {k: v for k, v in b.items() if k in keep},
                           "holdout_annotator_a vs holdout_annotator_b, overlap-excluded 121")
    assert sub["n_segments"] == 121
    return {"source_labels": ["gold_holdout_annotator_a.json", "gold_holdout_annotator_b.json"],
            "recorded_132": "reliability_holdout.json", "set_132": full, "set_121": sub}


def build() -> dict[str, Any]:
    _sessions, _deid, episodes = r4.run_pipeline()
    u3000, u5000 = r4.universe(episodes, 3000), r4.universe(episodes, 5000)
    fa = r4.frame_audit(u5000, u3000)
    audit = turn_audit(episodes, u3000, u5000, fa["_keys"]["pool"], fa["_keys"]["frozen"])
    sens = sensitivity(audit)
    rel121 = reliability_121(audit["_eval121"])
    audit.pop("_eval121"); audit.pop("_affected_ids")
    return {"generated_at": datetime.now(UTC).isoformat(), "seed": SEED,
            "interval_method": "child-cluster percentile bootstrap, 10,000 replicates, as in round3/round4",
            "turn_audit": audit, "sensitivity": sens, "reliability": rel121}


def main() -> None:
    report = build()
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    t = report["turn_audit"]
    print({k: v for k, v in t.items() if k.startswith("n_")}, t["context_frozen_132"])
    r = report["reliability"]
    print("mean kappa 132 / 121:", r["set_132"]["mean_kappa"], r["set_121"]["mean_kappa"])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
