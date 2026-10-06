"""Before/after report for the R10 downstream recomputation.

"Before" = the result artefacts at commit PRE (model-finetuning, pre-audit
reference); "after" = the same artefacts regenerated on this branch from the
post-audit reference (codebook_audit_r10/gold_labels_postaudit_r10.json) and the
preserved generator / MARS outputs. No model was run. Facts only.

    uv run python docs/paper/make_round10_recompute.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PAPER = Path(__file__).resolve().parent
sys.path.insert(0, str(PAPER))

from docx.shared import RGBColor  # noqa: E402

from make_round2_response import Doc  # noqa: E402

ROOT = PAPER.parents[1]
RES = "tests/eval/extraction/results"
PRE = "a475457"
OUT = PAPER / "Round10_Recompute_Report.docx"
FIELDS = ["domain", "modality", "prompt_level", "outcome"]
MODELS = ["llama3.2:latest", "qwen2.5:3b", "qwen2.5:7b", "qwen3:14b"]
GEN3 = MODELS[:3]
CHANGED_FIGURES = ["fig16_field_accuracy.png", "fig17_unsupported.png", "fig18_record_ceiling.png",
                   "fig20_mars_outcomes.png", "fig21_selection.png", "fig22_extended_roster.png"]


def pre(name: str) -> Any:
    return json.loads(subprocess.run(["git", "show", f"{PRE}:{RES}/{name}"], cwd=ROOT, capture_output=True,
                                     text=True, check=True).stdout)


def post(name: str) -> Any:
    return json.loads((ROOT / RES / name).read_text())


def p1(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}"


def ci(v: dict) -> str:
    c = v.get("ci95", v)
    return f"{p1(v['value'])} [{p1(c['lower'])}, {p1(c['upper'])}]"


def dci(v: dict) -> str:
    val = v.get("value", v.get("difference"))
    c = v.get("ci95", v)
    ex = c.get("excludes_zero", v.get("excludes_zero"))
    return f"{100 * val:+.1f} [{100 * c['lower']:+.1f}, {100 * c['upper']:+.1f}]" + (" *" if ex else "")


def pa(a: str, b: str) -> str:
    return f"{a} → {b}"


def build() -> Path:
    b = Doc()
    grey = RGBColor(0x52, 0x51, 0x4E)
    b.doc.add_heading("Round 10 — Downstream Recomputation After the Codebook Audit", level=0)
    b.p(f"Before = result artefacts at commit {PRE} (pre-audit reference). After = the same artefacts regenerated on "
        "branch r10-postaudit-recompute from `codebook_audit_r10/gold_labels_postaudit_r10.json` (98 human-audited "
        "changes) and the preserved generator and MARS outputs. No generator, MARS judge or reporter was run. Facts "
        "only; no manuscript wording. Built 2026-09-27.", colour=grey)

    # ---- strongest generator
    r4a, r4b = pre("round4_analysis.json"), post("round4_analysis.json")
    ga, gb = r4a["same_universe"]["groups"]["main_batch_330"]["per_model"], r4b["same_universe"]["groups"]["main_batch_330"]["per_model"]
    rank = lambda g, ms: sorted(ms, key=lambda m: -g[m]["merged_agreement"]["value"])  # noqa: E731
    assert rank(gb, GEN3)[0] == "qwen2.5:7b" and rank(gb, MODELS)[0] == "qwen2.5:7b"
    assert post("mars_selection_analysis.json")["best_generator"] == "qwen2.5:7b"
    b.h("Selected strongest generator", 1)
    b.bullets([
        "**Qwen 2.5 7B remains the strongest generator on merged agreement**, among the three original generators and "
        "among all four (asserted in this build and by round4_analysis.py's own strength-order check).",
        "Merged-agreement order before: " + " > ".join(f"{m} {p1(ga[m]['merged_agreement']['value'])}" for m in rank(ga, MODELS)),
        "Merged-agreement order after: " + " > ".join(f"{m} {p1(gb[m]['merged_agreement']['value'])}" for m in rank(gb, MODELS)),
    ])

    # ---- generator metrics
    b.h("1. Main-batch generator metrics (330)", 1)
    b.table("Per generator, % [95% child-cluster CI], before → after. Source: round4_analysis.json "
            "(same_universe.groups.main_batch_330).",
            ["Generator", "Merged agreement", "Unsupported assertion", "Whole record"],
            [[m, *[pa(ci(ga[m][k]), ci(gb[m][k])) for k in ("merged_agreement", "unsupported_rate", "whole_record")]] for m in MODELS],
            [1.1, 1.9, 1.9, 1.8])
    r3a, r3b = pre("round3_analysis.json"), post("round3_analysis.json")
    pa3, pb3 = (r["model_performance"]["main_batch"]["paired_qwen3_14b_minus_qwen2_5_7b"] for r in (r3a, r3b))
    b.table("Paired qwen3:14b − qwen2.5:7b, main batch, percentage points [95% CI]. Source: round3_analysis.json. * excludes zero.",
            ["Metric", "Before", "After"], [[k, dci(pa3[k]), dci(pb3[k])] for k in pa3], [1.8, 2.4, 2.4])
    hma, hmb = pre("holdout_metrics.json")["batch"]["per_model"], post("holdout_metrics.json")["batch"]["per_model"]
    b.table("Per-field agreement, main batch, % before → after. Source: holdout_metrics.json (batch).",
            ["Generator", *FIELDS],
            [[m, *[pa(p1(hma[m]["per_field_accuracy"][f]), p1(hmb[m]["per_field_accuracy"][f])) for f in FIELDS]] for m in MODELS],
            [1.1, 1.4, 1.4, 1.4, 1.4])

    # ---- unsupported by field
    fa, fb = pre("round9_analysis.json")["r9_5_field_unsupported"]["main_batch_330"], post("round9_analysis.json")["r9_5_field_unsupported"]["main_batch_330"]
    b.h("2. Unsupported assertion by field (330)", 1)
    b.table("Reference-null opportunities per field, before → after. Source: round9_analysis.json (r9_5).",
            ["", *FIELDS, "Total"],
            [["Opportunities", *[pa(str(fa["gold_null_by_field"][f]), str(fb["gold_null_by_field"][f])) for f in FIELDS],
              pa(str(sum(fa["gold_null_by_field"].values())), str(sum(fb["gold_null_by_field"].values())))]],
            [1.2, 1.1, 1.1, 1.1, 1.1, 1.1])
    b.table("Unsupported assertions / opportunities per field, before → after.", ["Generator", *FIELDS, "Pooled %"],
            [[m, *[pa(f"{fa['per_model'][m]['per_field'][f]['hallucinated']}/{fa['per_model'][m]['per_field'][f]['gold_null']}",
                      f"{fb['per_model'][m]['per_field'][f]['hallucinated']}/{fb['per_model'][m]['per_field'][f]['gold_null']}") for f in FIELDS],
              pa(p1(fa["per_model"][m]["pooled"]["rate"]), p1(fb["per_model"][m]["pooled"]["rate"]))] for m in MODELS],
            [1.1, 1.1, 1.2, 1.1, 1.2, 1.0])

    # ---- oracle
    oa, ob = pre("round9_analysis.json")["r9_8_oracle"], post("round9_analysis.json")["r9_8_oracle"]
    b.h("3. Oracle ceilings", 1)
    lab = {"three_generators_all_outputs_330": "3 generators, all outputs, 330 (the reported ceiling)",
           "three_generators_reviewable_only_330": "3 generators, MARS-reviewable outputs only",
           "three_generators_all_outputs_mars_returned": "3 generators, segments MARS returned",
           "three_generators_all_outputs_rerank_required": "3 generators, rerank-required segments",
           "four_generators_all_outputs_330": "4 generators, all outputs, 330"}
    b.table("Numerator/denominator (%), before → after. Source: round9_analysis.json (r9_8_oracle); mars_evaluation.json.",
            ["Definition", "Before", "After"],
            [[l, f"{oa[k]['numerator']}/{oa[k]['denominator']} ({p1(oa[k]['rate'])})", f"{ob[k]['numerator']}/{ob[k]['denominator']} ({p1(ob[k]['rate'])})"]
             for k, l in lab.items()], [3.4, 1.6, 1.6])

    # ---- MARS
    ma, mb = pre("mars_evaluation.json"), post("mars_evaluation.json")
    b.h("4. MARS", 1)
    b.table("Whole-record results, % before → after. Source: mars_evaluation.json.", ["Quantity", "Before → after"], [
        ["Coverage (265/330; selection does not use the reference)", pa(p1(ma["mars"]["coverage"]), p1(mb["mars"]["coverage"]))],
        ["MARS accuracy over returned", pa(p1(ma["mars"]["accuracy_over_returned"]), p1(mb["mars"]["accuracy_over_returned"]))],
        ["MARS accuracy over all 330", pa(p1(ma["mars"]["accuracy_over_all"]), p1(mb["mars"]["accuracy_over_all"]))],
        ["Best single generator (qwen2.5:7b)", pa(p1(ma["best_generator_accuracy"]), p1(mb["best_generator_accuracy"]))],
        ["Oracle ceiling (3 generators)", pa(p1(ma["oracle_ceiling"]), p1(mb["oracle_ceiling"]))],
        ["Oracle capture rate", pa(f"{ma['oracle_capture_rate']:.3f}", f"{mb['oracle_capture_rate']:.3f}")],
    ], [4.2, 2.5])
    sa, sb = pre("mars_selection_analysis.json"), post("mars_selection_analysis.json")
    assert sa["mars_selection_counts"] == sb["mars_selection_counts"]
    b.table("Selection quality on the 142 judged segments (published definitions), % before → after. Source: "
            "mars_selection_analysis.json. * child-clustered interval excludes zero.",
            ["Field", "MARS", "Best generator", "Random candidate", "MARS − best (clustered)", "MARS − random (clustered)"],
            [[f, pa(p1(sa["per_field"][f]["mars"]), p1(sb["per_field"][f]["mars"])),
              pa(p1(sa["per_field"][f]["best_generator"]), p1(sb["per_field"][f]["best_generator"])),
              pa(p1(sa["per_field"][f]["random_candidate"]), p1(sb["per_field"][f]["random_candidate"])),
              pa(dci(sa["per_field"][f]["vs_best_generator_clustered"]), dci(sb["per_field"][f]["vs_best_generator_clustered"])),
              pa(dci(sa["per_field"][f].get("vs_random_candidate_clustered", sa["per_field"][f]["vs_random_candidate"])),
                 dci(sb["per_field"][f].get("vs_random_candidate_clustered", sb["per_field"][f]["vs_random_candidate"])))]
             for f in FIELDS]
            + [["mean", *[pa(p1(sa["mean_accuracy"][k]), p1(sb["mean_accuracy"][k])) for k in ("mars", "best_generator", "random_candidate")], "", ""]],
            [0.8, 0.9, 0.9, 0.9, 1.6, 1.6])
    mca, mcb = r4a["mars_clustered"], r4b["mars_clustered"]
    b.table("Round-4 corrected comparators (random over reviewable candidates; strongest reviewable generator), "
            "percentage points [95% child-cluster CI], before → after. Source: round4_analysis.json (mars_clustered). * excludes zero.",
            ["Field", "MARS − random reviewable", "MARS − strongest reviewable"],
            [[f, pa(dci(mca["per_field"][f]["vs_random_reviewable"]), dci(mcb["per_field"][f]["vs_random_reviewable"])),
              pa(dci(mca["per_field"][f]["vs_best_reviewable_fallback"]), dci(mcb["per_field"][f]["vs_best_reviewable_fallback"]))] for f in FIELDS]
            + [["mean (MARS / random / strongest, %)", pa(f"{p1(mca['mean']['mars'])} / {p1(mca['mean']['random_expected_reviewable'])}",
                                                         f"{p1(mcb['mean']['mars'])} / {p1(mcb['mean']['random_expected_reviewable'])}"),
                pa(p1(mca["mean"]["best_reviewable_fallback"]), p1(mcb["mean"]["best_reviewable_fallback"]))]],
            [1.4, 2.7, 2.7])

    # ---- other round outputs
    b.h("5. Other main-batch analysis outputs", 1)
    ca_, cb_ = r4a["same_universe"]["contrasts"]["main_batch_330-minus-overlap_excluded_121"], r4b["same_universe"]["contrasts"]["main_batch_330-minus-overlap_excluded_121"]
    b.table("Round 4 — main batch minus post-audit 121, percentage points [95% CI], before → after. * excludes zero.",
            ["Generator", "Merged agreement", "Unsupported assertion"],
            [[m, pa(dci(ca_[m]["merged_agreement"]), dci(cb_[m]["merged_agreement"])),
              pa(dci(ca_[m]["unsupported_rate"]), dci(cb_[m]["unsupported_rate"]))] for m in MODELS], [1.1, 2.8, 2.8])
    aba, abb = r4a["abstention"]["main_batch_330"], r4b["abstention"]["main_batch_330"]
    b.table("Round 4 — null-output rates, main batch, % before → after.",
            ["Generator", "Missed-value rate", "Null on reference-populated", "Overall model-null"],
            [[m, *[pa(p1(aba[m][k]), p1(abb[m][k])) for k in ("reported_missing_over_all_slots", "null_on_gold_populated", "overall_model_null_rate")]]
             for m in MODELS], [1.1, 1.8, 1.9, 1.9])
    eca, ecb = pre("round5_analysis.json")["reference_nulls_by_cap"]["main_batch_330"], post("round5_analysis.json")["reference_nulls_by_cap"]["main_batch_330"]
    b.table("Round 5 (and Round 4 episode_cap) — reference-null share by field, capped vs shorter, main batch, % before → after.",
            ["Group", *FIELDS, "qwen2.5:7b unsupported"],
            [[g, *[pa(p1(eca[g]["gold_null_share"][f]), p1(ecb[g]["gold_null_share"][f])) for f in FIELDS],
              pa(p1(eca[g]["qwen2.5:7b_unsupported"]), p1(ecb[g]["qwen2.5:7b_unsupported"]))] for g in ("capped_8", "under_8")],
            [1.0, 1.1, 1.1, 1.1, 1.1, 1.3])
    pba = pre("round8_analysis.json")["session_coverage"]["performance_by_position"]["main_batch_330"]["midpoint_as_later"]["per_model"]
    pbb = post("round8_analysis.json")["session_coverage"]["performance_by_position"]["main_batch_330"]["midpoint_as_later"]["per_model"]
    b.table("Round 8 — early minus later session half, main batch, percentage points [95% CI], before → after. * excludes zero.",
            ["Generator", "Merged agreement", "Unsupported assertion"],
            [[m, *[pa(f"{100 * pba[m][k]['early_minus_later']:+.1f} [{100 * pba[m][k]['ci95']['lower']:+.1f}, {100 * pba[m][k]['ci95']['upper']:+.1f}]" + (" *" if pba[m][k]["excludes_zero"] else ""),
                      f"{100 * pbb[m][k]['early_minus_later']:+.1f} [{100 * pbb[m][k]['ci95']['lower']:+.1f}, {100 * pbb[m][k]['ci95']['upper']:+.1f}]" + (" *" if pbb[m][k]["excludes_zero"] else ""))
                   for k in ("merged_agreement", "unsupported_rate")]] for m in MODELS], [1.1, 2.8, 2.8])

    b.h("6. What was regenerated, and what was deliberately not", 1)
    b.table("Artefacts regenerated on this branch (in this order).", ["Artefact", "Script"], [
        ["gold_labels.json ← post-audit copy", "cp codebook_audit_r10/gold_labels_postaudit_r10.json"],
        ["scored_against_gold.json, scored_against_gold_augmented.json", "score_against_gold --behavior-match excluded (as recorded)"],
        ["mars_evaluation.json", "mars_evaluation"], ["mars_selection_analysis.json", "mars_selection_analysis"],
        ["holdout_metrics.json", "holdout_metrics"], ["paper_metrics.json", "paper_metrics"],
        ["round3/4/5/8/9_analysis.json", "round3/4/5/8/9_analysis"],
        ["Figures " + ", ".join(f.split("_")[0] for f in CHANGED_FIGURES), "docs/paper/make_figures.py (other figures pixel-identical)"],
    ], [3.3, 3.4])
    b.bullets([
        "**round9_analysis.json R9-2/3/4 (reporter packets) kept from the pre-audit build.** Those facts describe the "
        "recorded 11-report run, whose packets were built from the pre-audit reference; the reporter was not rerun. "
        "Rebuilt from the post-audit reference, the packets would differ (input 7,414–8,040 tokens instead of 7,416–8,009).",
        "Not rebuilt: the manuscript and earlier response documents (they contain wording). 22 tests that pin published "
        "numbers now fail on this branch because the artefacts changed and the text did not; 6 audit-tool tests error "
        "because their fixture expects the pre-audit reference in gold_labels.json.",
        "Unchanged by construction: held-out 132/121 results, inter-annotator kappa, generator outputs, MARS selections.",
    ])
    b.doc.save(str(OUT))
    return OUT


if __name__ == "__main__":
    print(build())
