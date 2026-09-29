"""Facts answering the round-11 technical questions. No model is called.

    R11-5  every recorded Cohen's-kappa child-cluster bootstrap interval, re-run
           with its original inputs and seed: replicates requested / valid /
           dropped, the reason each dropped replicate was undefined, the number
           of child clusters. The re-run must reproduce the recorded interval.
    R11-6  version-control chronology of the reporting validator, the grounding
           scorer and the recorded 11-report artefact; the prohibited-content
           check exactly as it stood at the recorded run.
    R11-8  unaccounted target-frame episode-type mass in the 121-set episode-type
           re-weighting (round4_analysis poststrat), per child and overall.

    uv run python -m tests.eval.extraction.round11_analysis
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.extraction import reliability_stats as rel
from tests.eval.extraction import round4_analysis as r4
from tests.eval.extraction.agreement_report import CATEGORICAL_FIELDS, cohens_kappa, paired_values, shared_segments

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).parent / "results"
OUT = RESULTS / "round11_analysis.json"
REPORT_RUN = "9ecc330"


def load(name: str) -> Any:
    return json.loads((RESULTS / name).read_text())


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


# --------------------------------------------------------------------------
# R11-5
# --------------------------------------------------------------------------

def _draws(pairs_len: int, clusters: list[str], n_boot: int, seed: int):
    """The exact index sequence of reliability_stats' child-cluster bootstrap."""
    rng = random.Random(seed)
    grouped = rel.cluster_index(clusters)
    labels = sorted(grouped)
    for _ in range(n_boot):
        drawn = [labels[rng.randrange(len(labels))] for _ in labels]
        yield drawn, [p for lab in drawn for p in grouped[lab]]


def _why(sample: list[tuple]) -> str:
    cats = {v for pair in sample for v in pair}
    return f"single category in replicate ({'/'.join(sorted(str(c) for c in cats))}): expected agreement = 1"


def kappa_accounting(pairs: list[tuple], clusters: list[str], recorded: dict, n_boot: int, seed: int) -> dict[str, Any]:
    valid, dropped = 0, Counter()
    for drawn, idx in _draws(len(pairs), clusters, n_boot, seed):
        sample = [pairs[i] for i in idx]
        if cohens_kappa(sample) is None:
            dropped[_why(sample) + f"; {len(set(drawn))} distinct children drawn"] += 1
        else:
            valid += 1
    assert valid == recorded["n_valid"] and n_boot == recorded["n_requested"], (valid, recorded)
    assert recorded["unit"] == "child"
    return {"requested": n_boot, "valid": valid, "dropped": n_boot - valid,
            "pct_dropped": round(100 * (n_boot - valid) / n_boot, 3), "reasons": dict(dropped),
            "n_clusters": len(set(clusters)), "n_items": len(pairs),
            "interval": [recorded["lower"], recorded["upper"]]}


def delta_accounting(before, after, clusters, recorded, n_boot, seed) -> dict[str, Any]:
    valid, dropped = 0, Counter()
    for drawn, idx in _draws(len(before), clusters, n_boot, seed):
        b1, b2 = [before[i] for i in idx], [after[i] for i in idx]
        k1, k2 = cohens_kappa(b1), cohens_kappa(b2)
        if k1 is None or k2 is None:
            which = "round 1" if k1 is None else "round 2"
            dropped[f"{which} kappa undefined: " + _why(b1 if k1 is None else b2)] += 1
        else:
            valid += 1
    assert valid == recorded["n_valid"], (valid, recorded)
    return {"requested": n_boot, "valid": valid, "dropped": n_boot - valid,
            "pct_dropped": round(100 * (n_boot - valid) / n_boot, 3), "reasons": dict(dropped),
            "n_clusters": len(set(clusters)), "n_items": len(before),
            "interval": [recorded["lower"], recorded["upper"]]}


def replicate_accounting(eval121: list[str]) -> dict[str, Any]:
    ann = lambda n: load(f"gold_{n}.json")  # noqa: E731
    sets = {
        "reliability_round1 (330, pre-codebook)": ("reliability_round1.json", ann("annotator_a_round1"), ann("annotator_b_round1"), None),
        "reliability_current (330, final annotator state)": ("reliability_current.json", ann("annotator_a"), ann("annotator_b"), None),
        "reliability_holdout (frozen 132)": ("reliability_holdout.json", ann("holdout_annotator_a"), ann("holdout_annotator_b"), None),
        "reliability 121 (post-audit evaluation set; round6_analysis)": ("round6_analysis.json", ann("holdout_annotator_a"), ann("holdout_annotator_b"), set(eval121)),
    }
    out: dict[str, Any] = {"n_bootstrap": rel.N_BOOTSTRAP, "seed": rel.BOOTSTRAP_SEED, "kappa": {}, "kappa_change": {}}
    for name, (art, a, b, keep) in sets.items():
        rec = load(art)
        rec = rec["reliability"]["set_121"] if keep else rec
        if keep:
            a, b = {k: v for k, v in a.items() if k in keep}, {k: v for k, v in b.items() if k in keep}
        segs = shared_segments(a, b)
        out["kappa"][name] = {}
        for f in CATEGORICAL_FIELDS:
            pairs = paired_values(a, b, f, segs)
            clusters = rel.paired_clusters(a, b, f, segs)
            out["kappa"][name][f] = kappa_accounting(pairs, clusters, rec["fields"][f]["cluster_bootstrap_ci"],
                                                      rec["n_bootstrap"], rec["bootstrap_seed"])
    # Round comparison: 178 re-issued segments, round 1 vs round 2, and the paired change.
    rc = load("round_comparison.json")
    segs = sorted(load("reissue_round2_selection.json")["selected"])
    a1, b1, a2, b2 = ann("annotator_a_round1"), ann("annotator_b_round1"), ann("annotator_a"), ann("annotator_b")
    for f in CATEGORICAL_FIELDS:
        before, after = paired_values(a1, b1, f, segs), paired_values(a2, b2, f, segs)
        clusters = rel.paired_clusters(a1, b1, f, segs)
        for rnd, pairs in (("round1", before), ("round2", after)):
            out["kappa"].setdefault(f"round_comparison {rnd} (178 re-issued)", {})[f] = kappa_accounting(
                pairs, clusters, rc["fields"][f][rnd]["cluster_bootstrap_ci"], rel.N_BOOTSTRAP, rel.BOOTSTRAP_SEED)
        out["kappa_change"][f] = delta_accounting(before, after, clusters, rc["fields"][f]["delta_clustered"],
                                                  rel.N_BOOTSTRAP, rel.BOOTSTRAP_SEED)
    return out


# --------------------------------------------------------------------------
# R11-6
# --------------------------------------------------------------------------

def _span(commit: str, path: str, start: str, end: str) -> str:
    s = git("show", f"{commit}:{path}")
    i = s.find(start)
    return s[i:s.find(end, i)]


def _code_only(text: str) -> str:
    return "".join(l for l in text.splitlines(keepends=True) if not l.lstrip().startswith("#"))


def validator_facts() -> dict[str, Any]:
    client, scorer = "src/backend/ml/reporting_client.py", "tests/eval/reporting/groundedness.py"
    result = "tests/eval/reporting/results/reporting_groundedness.json"
    log = lambda p: [dict(zip(("commit", "date", "subject"), l.split("|", 2)))  # noqa: E731
                     for l in reversed(git("log", "--format=%h|%ad|%s", "--date=iso-strict", "--", p).splitlines())]
    val_hist = []
    for c in log(client):
        body = _span(c["commit"], client, "PROHIBITED_PATTERNS", "class ReportingClient")
        val_hist.append({**c, "validator_code_sha": hashlib.sha256(_code_only(body).encode()).hexdigest()[:12],
                         "diff_vs_previous": None})
    for prev, cur in zip(val_hist, val_hist[1:]):
        same = prev["validator_code_sha"] == cur["validator_code_sha"]
        cur["diff_vs_previous"] = "validator code identical (comment lines ignored)" if same else "VALIDATOR CODE CHANGED"
    created = val_hist[0]
    at_run = next(v for v in val_hist if v["commit"] == REPORT_RUN)
    assert created["validator_code_sha"] == at_run["validator_code_sha"], "validator logic changed before the run"

    src = git("show", f"{REPORT_RUN}:{client}")
    tree = ast.parse(src)
    patterns = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                    if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "PROHIBITED_PATTERNS" for t in n.targets))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "validate_report")
    validate_src = ast.get_source_segment(src, fn)

    sc_hist = log(scorer)
    count_span = lambda c: _code_only(_span(c, scorer, '"prohibited_content_reports"', ")"))  # noqa: E731
    run_rec = json.loads(git("show", f"{REPORT_RUN}:{result}"))
    return {
        "validator": {"file": client, "function": "validate_report", "created": created, "at_run": at_run,
                      "history": val_hist, "code_at_run": validate_src, "prohibited_patterns_at_run": patterns,
                      "validation_passed_rule_present_at_every_commit": all(
                          "validation_passed=len(validation_errors) == 0" in git("show", f"{c['commit']}:{client}")
                          for c in val_hist[: val_hist.index(at_run) + 1])},
        "scorer": {"file": scorer, "history": sc_hist, "report_count_rule_at_run": count_span(REPORT_RUN).strip(),
                   "report_count_rule_at_creation": count_span(sc_hist[0]["commit"]).strip()},
        "result_artifact": {"file": result, "history": log(result),
                            "at_run": {"n_llm_reports": run_rec["n_llm_reports"],
                                       "prohibited_content_reports": run_rec["summary"]["prohibited_content_reports"],
                                       "reports_passing_validation": run_rec["summary"]["reports_passing_validation"],
                                       "report_text_preserved": any("sections" in p for p in run_rec["per_child"])}},
        "config_dependency": "none: patterns are a module-level constant in reporting_client.py; no settings are read by validate_report",
    }


# --------------------------------------------------------------------------
# R11-8
# --------------------------------------------------------------------------

def unaccounted_mass(fa: dict) -> dict[str, Any]:
    pool, fkey, ftype = fa["_keys"]["pool"], fa["_keys"]["frozen"], fa["_type"]["frozen"]
    frozen = {s["segment_id"]: s for s in load("holdout_set.json")["segments"]}
    segs121 = [s for s in frozen if fkey[s] not in pool]
    assert len(segs121) == 121
    levels = {"episode_type_7": lambda t: t, "other_vs_typed": lambda t: "other" if t == "other" else "typed"}
    recorded = load("round4_analysis.json")["same_universe"]["poststratified_121"]
    out: dict[str, Any] = {}
    for lname, lv in levels.items():
        for frame, rkey in (("intended", "to_intended_frame"), ("analysed", "to_analysed_frame")):
            mix = fa["_type"][frame]
            per_child, tot, missing_tot = {}, 0, 0
            for c in sorted({frozen[s]["child_id"] for s in segs121}):
                target = Counter()
                for t, n in mix[c].items():
                    target[lv(t)] += n
                have = Counter(lv(ftype[s]) for s in segs121 if frozen[s]["child_id"] == c)
                miss = {k: n for k, n in target.items() if not have[k]}
                T = sum(target.values())
                share = sum(miss.values()) / T
                assert round(share, 4) == recorded[lname][rkey]["unaccounted_intended_share_by_child"][c], (lname, frame, c)
                per_child[c] = {"frame_episodes": T, "unaccounted_episodes": sum(miss.values()),
                                "unaccounted_pct": round(100 * share, 2),
                                "missing_types": {k: {"frame_episodes": n, "share_of_child_frame_pct": round(100 * n / T, 2)}
                                                  for k, n in sorted(miss.items(), key=lambda kv: -kv[1])},
                                "sampled_types": dict(have)}
                tot += T
                missing_tot += sum(miss.values())
            out[f"{lname}/{frame}"] = {"per_child": per_child, "total_frame_episodes": tot, "total_unaccounted": missing_tot,
                                       "overall_unaccounted_pct": round(100 * missing_tot / tot, 2),
                                       "mean_of_child_pct": round(sum(v["unaccounted_pct"] for v in per_child.values()) / len(per_child), 2)}
    out["handling"] = ("round4_analysis.same_universe.poststrat: covered = sum of target counts over types present in the "
                       "child's sample; weight = (target[k] / covered) / (sample[k] / n_child). Types absent from the "
                       "sample receive no weight and are not imputed, redistributed to another type, or merged; their "
                       "target mass is excluded from 'covered' and reported as unaccounted.")
    return out


def build() -> dict[str, Any]:
    _s, _d, episodes = r4.run_pipeline()
    u3000, u5000 = r4.universe(episodes, 3000), r4.universe(episodes, 5000)
    fa = r4.frame_audit(u5000, u3000)
    segs121 = [s["segment_id"] for s in load("holdout_set.json")["segments"] if fa["_keys"]["frozen"][s["segment_id"]] not in fa["_keys"]["pool"]]
    return {"generated_at": datetime.now(UTC).isoformat(),
            "r11_5_bootstrap_accounting": replicate_accounting(segs121),
            "r11_6_validator": validator_facts(),
            "r11_8_unaccounted_mass": unaccounted_mass(fa)}


def main() -> None:
    report = build()
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
    for name, fields in report["r11_5_bootstrap_accounting"]["kappa"].items():
        print(name, {f: (v["valid"], v["dropped"], v["n_clusters"]) for f, v in fields.items()})
    print("change", {f: (v["valid"], v["dropped"]) for f, v in report["r11_5_bootstrap_accounting"]["kappa_change"].items()})
    for k, v in report["r11_8_unaccounted_mass"].items():
        if isinstance(v, dict):
            print(k, v["overall_unaccounted_pct"], v["total_unaccounted"], "/", v["total_frame_episodes"])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
