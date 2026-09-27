"""Analyses answering the MDPI round-8 review comments. No model is called.

    R8-1  session coverage   for each set (all segmented episodes, the 2,442 and
                             3,371 universes, the 1,320 pool, the 330 main batch,
                             the frozen 132 and the post-audit 121): sessions
                             represented per child and the distribution of each
                             episode's relative session position within its
                             child's longitudinal record
    R8-2  validator timeline git history of the governance validator, the
                             grounding scorer and the recorded report run

Relative session position: a child's sessions are ordered by the child's age in
the CHAT @ID header (every one of the 85 sessions has one), and session k of n
has position k / (n - 1), so 0 is the child's first visit and 1 the last. The
reference distribution is all segmented episodes, i.e. what the universe
builder could have kept.

    uv run python -m tests.eval.extraction.round8_analysis
"""

from __future__ import annotations

import json
import statistics
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.extraction import round4_analysis as r4

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).parent / "results"
OUT = RESULTS / "round8_analysis.json"
BINS = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0)]


def session_positions(sessions) -> dict[str, dict[str, Any]]:
    """session_id -> child, rank, n_sessions and relative position, ordered by child age."""
    by_child = defaultdict(list)
    for s in sessions:
        age = r4._months(s.header.participant_ids.get("CHI", {}).get("age", ""))
        assert age is not None, f"no age for {s.source_file}"
        by_child[s.child_id].append((age, s.source_file, f"{s.corpus}_{s.child_id}_{s.source_file}"))
    out = {}
    for child, ss in by_child.items():
        ss.sort()
        n = len(ss)
        for k, (age, _f, sid) in enumerate(ss):
            out[sid] = {"child_id": child, "rank": k, "n_sessions": n, "age_months": round(age, 2),
                        "position": k / (n - 1) if n > 1 else 0.0}
    return out


def bin_of(p: float) -> int:
    return min(int(p * 4), 3)


def describe(name: str, items: list[tuple[str, str]], pos: dict, ref_mean: dict[str, float] | None) -> dict[str, Any]:
    """items: (child_id, session_id) per episode."""
    by_child = defaultdict(list)
    for child, sid in items:
        assert pos[sid]["child_id"] == child
        by_child[child].append(sid)
    per_child = {}
    for c, sids in sorted(by_child.items()):
        ps = [pos[s]["position"] for s in sids]
        n_sess = next(iter(pos[s]["n_sessions"] for s in sids))
        per_child[c] = {
            "n": len(sids), "sessions_represented": len(set(sids)), "sessions_total": n_sess,
            "mean_position": round(statistics.mean(ps), 4), "median_position": round(statistics.median(ps), 4),
            "latest_session_reached": round(max(ps), 4),
            "quartile_shares": [round(sum(bin_of(p) == i for p in ps) / len(ps), 4) for i in range(4)],
        }
        if ref_mean is not None:
            per_child[c]["shift_vs_all_episodes"] = round(per_child[c]["mean_position"] - ref_mean[c], 4)
    allp = [pos[s]["position"] for _, s in items]
    out = {
        "name": name, "n": len(items), "n_children": len(per_child),
        "sessions_represented": sum(v["sessions_represented"] for v in per_child.values()),
        "sessions_total": sum(v["sessions_total"] for v in per_child.values()),
        "children_with_all_sessions": sum(v["sessions_represented"] == v["sessions_total"] for v in per_child.values()),
        "pooled_mean_position": round(statistics.mean(allp), 4),
        "child_mean_position": round(statistics.mean(v["mean_position"] for v in per_child.values()), 4),
        "pooled_quartile_shares": [round(sum(bin_of(p) == i for p in allp) / len(allp), 4) for i in range(4)],
        "per_child": per_child,
    }
    if ref_mean is not None:
        shifts = [v["shift_vs_all_episodes"] for v in per_child.values()]
        out["mean_child_shift_vs_all_episodes"] = round(statistics.mean(shifts), 4)
        out["min_child_shift"] = round(min(shifts), 4)
        out["max_child_shift"] = round(max(shifts), 4)
    return out


def session_coverage() -> dict[str, Any]:
    sessions, _deid, episodes = r4.run_pipeline()
    pos = session_positions(sessions)
    assert len(pos) == 85
    u3000, u5000 = r4.universe(episodes, 3000), r4.universe(episodes, 5000)
    fa = r4.frame_audit(u5000, u3000)
    by3 = {u["segment_id"]: u for u in u3000}
    by5 = {u["segment_id"]: u for u in u5000}
    pool_ids = [p["segment_id"] for p in r4.load("annotation_pool.json")["pool"]]
    main_ids = list(r4.load("scored_against_gold_augmented.json")["gold"])
    frozen_ids = [s["segment_id"] for s in r4.load("holdout_set.json")["segments"]]
    pool_keys, fkey = fa["_keys"]["pool"], fa["_keys"]["frozen"]

    sets = {
        "all_episodes_9018": [(e.child_id, e.session_id) for e in episodes],
        "universe_2442": [(u["child_id"], u["session_id"]) for u in u3000],
        "universe_3371": [(u["child_id"], u["session_id"]) for u in u5000],
        "pool_1320": [(by3[i]["child_id"], by3[i]["session_id"]) for i in pool_ids],
        "main_batch_330": [(by3[i]["child_id"], by3[i]["session_id"]) for i in main_ids],
        "frozen_132": [(by5[i]["child_id"], by5[i]["session_id"]) for i in frozen_ids],
        "overlap_excluded_121": [(by5[i]["child_id"], by5[i]["session_id"]) for i in frozen_ids if fkey[i] not in pool_keys],
    }
    assert [len(v) for v in sets.values()] == [9018, 2442, 3371, 1320, 330, 132, 121]
    ref = describe("all_episodes_9018", sets["all_episodes_9018"], pos, None)
    ref_mean = {c: v["mean_position"] for c, v in ref["per_child"].items()}
    out = {"position_definition": "session rank by child age (CHAT @ID) / (n_sessions - 1); 0 = first visit, 1 = last",
           "quartile_bins": [list(b) for b in BINS],
           "sessions": {sid: v for sid, v in sorted(pos.items())},
           "sets": {"all_episodes_9018": ref}}
    for name, items in sets.items():
        if name != "all_episodes_9018":
            out["sets"][name] = describe(name, items, pos, ref_mean)
    return out


# --------------------------------------------------------------------------
# R8-2  chronology
# --------------------------------------------------------------------------

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def span_at(commit: str, path: str, start: str, end: str) -> str | None:
    try:
        s = git("show", f"{commit}:{path}")
    except subprocess.CalledProcessError:
        return None
    i = s.find(start)
    j = s.find(end, i)
    return s[i:j] if i >= 0 and j >= 0 else None


def commits(path: str) -> list[dict[str, str]]:
    rows = git("log", "--format=%h|%ad", "--date=iso-strict", "--follow", "--", path).strip().splitlines()
    return [dict(zip(("commit", "date"), r.split("|"))) for r in reversed(rows)]


def validator_timeline() -> dict[str, Any]:
    client = "src/backend/ml/reporting_client.py"
    scorer = "tests/eval/reporting/groundedness.py"
    result = "tests/eval/reporting/results/reporting_groundedness.json"

    def history(path: str, start: str, end: str) -> list[dict[str, Any]]:
        rows, prev = [], None
        for c in commits(path):
            body = span_at(c["commit"], path, start, end)
            code = "".join(l for l in (body or "").splitlines(keepends=True) if not l.lstrip().startswith("#"))
            rows.append({**c, "present": body is not None, "logic_changed": body is not None and code != prev})
            prev = code if body is not None else prev
        return rows

    runs = []
    for c in commits(result):
        rec = json.loads(git("show", f"{c['commit']}:{result}"))
        runs.append({**c, "n_llm_reports": rec["n_llm_reports"], "n_fallback_reports": rec["n_fallback_reports"],
                     "reports_passing_validation": rec["summary"]["reports_passing_validation"]})
    return {
        "note": "Commit dates bound when code and results entered version control, not when a run executed; "
                "the result file carries no run timestamp.",
        "validate_report": history(client, "PROHIBITED_PATTERNS", "class ReportingClient"),
        "grounding_scorer": history(scorer, "STRUCTURAL_NUMBERS =", "\"child_id\": packet.child_id"),
        "recorded_runs": runs,
    }


def build() -> dict[str, Any]:
    return {"generated_at": datetime.now(UTC).isoformat(),
            "session_coverage": session_coverage(), "validator_timeline": validator_timeline()}


def main() -> None:
    report = build()
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    for k, v in report["session_coverage"]["sets"].items():
        print(f"{k:24s} n={v['n']:5d} sessions {v['sessions_represented']}/{v['sessions_total']} "
              f"mean pos {v['pooled_mean_position']:.3f} child-mean {v['child_mean_position']:.3f} "
              f"shift {v.get('mean_child_shift_vs_all_episodes')} q={v['pooled_quartile_shares']}")
    for k in ("validate_report", "grounding_scorer", "recorded_runs"):
        print(k, report["validator_timeline"][k])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
