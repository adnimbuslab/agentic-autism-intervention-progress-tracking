"""Build the response to the MDPI round-5 review comments.

Reads the three comments from ``Round5_Review_Feedback.docx`` in document order
(R5-1, R5-2, R5-3) and answers each underneath, verbatim comment first. Every
number is read from a recorded artefact, chiefly ``round5_analysis.json`` (added
this round, no model calls), and each table names its source. Statements about
the data are asserted before they are printed.

Author decisions for this round (2026-09-26):
    R5-1  episode-weighted estimand stays primary; equal-child weighting reported
          as a sensitivity analysis, including where it changes a conclusion
    R5-2  the capped-vs-shorter reference-null analysis moves into Methods/Results
    R5-3  the reviewer's suggested Conclusion phrase, used as written

    uv run python -m tests.eval.extraction.round5_analysis
    uv run python docs/paper/make_round5_response.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PAPER = Path(__file__).resolve().parent
sys.path.insert(0, str(PAPER))

import docx  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from docx.shared import RGBColor  # noqa: E402
from docx.table import Table  # noqa: E402
from docx.text.paragraph import Paragraph  # noqa: E402

from make_round2_response import AQUA, BLUE, COLOUR, GRID, MODELS, ORANGE, Doc, pct, short  # noqa: E402
from make_round4_response import render_comment  # noqa: E402

ROOT = PAPER.parents[1]
RESULTS = ROOT / "tests" / "eval" / "extraction" / "results"
QUESTIONS = PAPER / "Round5_Review_Feedback.docx"
FIG = PAPER / "figures" / "round5"
OUT = PAPER / "Round5_Review_Response.docx"
FIELDS = ["domain", "modality", "prompt_level", "outcome"]
METRIC_NAMES = {"merged_agreement": "Merged agreement", "unsupported_rate": "Unsupported assertion",
                "whole_record": "Whole-record agreement"}


def load(name: str) -> Any:
    return json.loads((RESULTS / name).read_text())


def pp(x: float) -> str:
    return f"{100 * x:+.1f}"


def ci_pp(v: float, lo: float, hi: float) -> str:
    return f"{pp(v)} [{pp(lo)}, {pp(hi)}]"


def v_ci(v: float, lo: float, hi: float) -> str:
    return f"{100 * v:.1f} [{100 * lo:.1f}, {100 * hi:.1f}]"


# ---------------------------------------------------------------------------
# Comments, verbatim and in order
# ---------------------------------------------------------------------------

def read_comments() -> list[dict[str, Any]]:
    src = docx.Document(str(QUESTIONS))
    comments: list[dict[str, Any]] = []
    for el in src.element.body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "tbl":
            text = Table(el, src).rows[0].cells[0].text.strip()
            parts = [p.strip() for p in text.split("|")]
            if len(parts) == 3 and parts[0].startswith("R5-"):
                comments.append({"id": parts[0], "severity": parts[1], "title": parts[2], "items": []})
        elif tag == "p" and comments:
            t = Paragraph(el, src).text.strip()
            if t and any(t.startswith(k) for k in ("Location:", "Reviewer concern:", "Required action:", "Status:")):
                comments[-1]["items"].append(t)
    return comments


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig_child_weighting(cw: dict) -> Path:
    pc = cw["per_child"]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(13, 4.4), gridspec_kw={"width_ratios": [1, 1.2, 1.2]})
    kids = sorted(pc, key=lambda c: (pc[c]["retained"], c))
    a1.barh(range(len(kids)), [pc[k]["retained"] for k in kids], color=BLUE, height=0.6, label="retained")
    a1.barh(range(len(kids)), [pc[k]["removed"] for k in kids], left=[pc[k]["retained"] for k in kids],
            color=ORANGE, height=0.6, label="removed (overlap)")
    for i, k in enumerate(kids):
        a1.text(12.3, i, f"{pc[k]['retained']}/12", va="center", fontsize=7.5)
    a1.set_yticks(range(len(kids)), kids, fontsize=7.6)
    a1.set_xlim(0, 14.5)
    a1.legend(frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    a1.set_title("A. Retained episodes per child (121)", loc="left", fontsize=9.5, weight="bold")
    for ax, key, t in ((a2, "merged_agreement", "B. Merged agreement"), (a3, "unsupported_rate", "C. Unsupported assertion")):
        for j, m in enumerate(MODELS):
            v = cw["per_model"][m][key]
            ep = cw["_episode_ci"][m][key]
            ax.plot([100 * ep["lower"], 100 * ep["upper"]], [j - 0.15] * 2, color=COLOUR[m], lw=2)
            ax.scatter([100 * v["episode_weighted"]], [j - 0.15], color=COLOUR[m], s=28, zorder=3)
            ax.plot([100 * v["ci95"]["lower"], 100 * v["ci95"]["upper"]], [j + 0.15] * 2, color=COLOUR[m], lw=2,
                    ls=(0, (2, 1.5)))
            ax.scatter([100 * v["child_weighted"]], [j + 0.15], facecolor="white", edgecolor=COLOUR[m], s=28,
                       zorder=3, lw=1.5)
        ax.set_yticks(range(len(MODELS)), [short(m) for m in MODELS], fontsize=8)
        ax.invert_yaxis()
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.set_xlabel("% (95% child-cluster CI)")
        ax.set_title(t, loc="left", fontsize=9.5, weight="bold")
    a2.scatter([], [], color="k", s=24, label="episode-weighted (primary)")
    a2.scatter([], [], facecolor="white", edgecolor="k", s=24, label="equal-child-weighted (sensitivity)")
    a2.legend(frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    fig.tight_layout()
    p = FIG / "r5_fig1_child_weighting.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def fig_reference_nulls(rn: dict) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.7), sharey=True)
    for ax, (side, nm) in zip(axes, (("main_batch_330", "Main batch (330)"), ("frozen_132", "Frozen evaluation set (132)"))):
        for i, (g, lab, col) in enumerate((("capped_8", "capped (8 turns)", BLUE), ("under_8", "shorter (< 8 turns)", AQUA))):
            v = rn[side][g]
            xs = [k + (i - 0.5) * 0.38 for k in range(len(FIELDS))]
            ax.bar(xs, [100 * v["gold_null_share"][f] for f in FIELDS], width=0.36, color=col, label=f"{lab}, n = {v['n']}")
            for x, f in zip(xs, FIELDS):
                ax.text(x, 100 * v["gold_null_share"][f] + 0.8, f"{100 * v['gold_null_share'][f]:.1f}", ha="center", fontsize=7)
        ax.set_xticks(range(len(FIELDS)), [f.replace("_", " ") for f in FIELDS])
        ax.set_title(nm, loc="left", fontsize=9.5, weight="bold")
        ax.legend(frameon=False, fontsize=7.5)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("% of episodes with a reference null")
    fig.tight_layout()
    p = FIG / "r5_fig2_reference_nulls.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------

def a_r51(b: Doc, ctx) -> None:
    cw = ctx["cw"]; pc = cw["per_child"]; pm = cw["per_model"]; pair = cw["paired_qwen3_14b_minus_qwen2_5_7b"]
    ep_pair = ctx["r3"]["holdout_sensitivity"]["excluding_all_pool_episodes"]["paired_qwen3_14b_minus_qwen2_5_7b"]
    n = sum(v["retained"] for v in pc.values())
    assert n == 121 and len(pc) == 11
    fewest = min(pc, key=lambda c: pc[c]["retained"])
    undefined = [c for c, v in pc.items() if v["reference_null_slots"] == 0]
    max_merged_shift = max(abs(pm[m]["merged_agreement"]["child_weighted_minus_episode_weighted"]) for m in MODELS)
    assert max_merged_shift < 0.015
    assert ep_pair["unsupported_rate"]["ci95"]["excludes_zero"] and not pair["unsupported_rate"]["excludes_zero"]
    assert not pair["merged_agreement"]["excludes_zero"]
    for m in MODELS:
        for k in METRIC_NAMES:
            assert abs(pm[m][k]["episode_weighted"] - ctx["r4_121"][m][k]["value"]) < 1e-4

    b.label("Short answer")
    b.answer_line(
        f"**Retained episodes per child range from {pc[fewest]['retained']} ({fewest}) to 12; six children keep all "
        "12.** We keep the episode-weighted estimand as primary, state it explicitly, and add an "
        "equal-child-weighted sensitivity estimate for the three central metrics. **Merged and whole-record "
        f"agreement are robust (every model moves by at most {100 * max_merged_shift:.1f} points). Unsupported "
        "assertion is not: under equal-child weighting the qwen3:14b − qwen2.5:7b paired difference on the 121-set "
        f"is {ci_pp(pair['unsupported_rate']['value'], pair['unsupported_rate']['lower'], pair['unsupported_rate']['upper'])} "
        "points and its interval includes zero,** because per-child reference-null denominators are small. This is "
        "reported as found.")

    b.table("Retained evaluation episodes per child after overlap exclusion, weights under each estimand, and "
            "reference-null slots (the unsupported-assertion denominator). Source: `round5_analysis.json` "
            "(child_weighting_121.per_child).",
            ["Child", "Frozen", "Removed", "Retained", "Episode weight", "Equal-child weight", "Reference-null slots"],
            [[c, str(v["frozen"]), str(v["removed"]), str(v["retained"]), pct(v["episode_weight"]),
              pct(v["equal_child_weight"]), str(v["reference_null_slots"])] for c, v in pc.items()]
            + [["Total", "132", str(132 - n), str(n), "100%", "100%", str(sum(v["reference_null_slots"] for v in pc.values()))]],
            [1.2, 0.6, 0.7, 0.7, 1.0, 1.1, 1.3])

    rows = []
    for m in MODELS:
        row = [short(m)]
        for k in METRIC_NAMES:
            v = pm[m][k]
            row += [f"{100 * v['episode_weighted']:.1f}",
                    v_ci(v["child_weighted"], v["ci95"]["lower"], v["ci95"]["upper"])]
        rows.append(row)
    b.table("Central 121-set metrics, episode-weighted (primary, as recorded in `round4_analysis.json`) and "
            "equal-child-weighted (sensitivity), %. Equal-child: metric within each child, then the unweighted mean "
            "of children; 95% child-cluster percentile bootstrap, 10,000 replicates. Unsupported assertion is "
            f"defined for {pm['qwen3:14b']['unsupported_rate']['n_children_defined']} of 11 children. "
            "Source: `round5_analysis.json` (child_weighting_121.per_model).",
            ["Model", "Merged: episode", "Merged: child [CI]", "Unsupp.: episode", "Unsupp.: child [CI]",
             "Whole: episode", "Whole: child [CI]"],
            rows, [0.9, 0.75, 1.15, 0.75, 1.15, 0.7, 1.1])

    b.table("Paired difference qwen3:14b − qwen2.5:7b on the 121-set, percentage points [95% child-cluster CI]. "
            "Episode-weighted: `round3_analysis.json` (holdout_sensitivity.excluding_all_pool_episodes). "
            "Equal-child: `round5_analysis.json`.",
            ["Metric", "Episode-weighted (primary)", "Equal-child-weighted (sensitivity)"],
            [[METRIC_NAMES[k],
              ci_pp(ep_pair[k]["value"], ep_pair[k]["ci95"]["lower"], ep_pair[k]["ci95"]["upper"])
              + (" *" if ep_pair[k]["ci95"]["excludes_zero"] else ""),
              ci_pp(pair[k]["value"], pair[k]["lower"], pair[k]["upper"]) + (" *" if pair[k]["excludes_zero"] else "")]
             for k in METRIC_NAMES],
            [1.8, 2.4, 2.5])
    b.p("* interval excludes zero.")

    b.figure(fig_child_weighting(cw), "A: retained versus removed evaluation episodes per child. B, C: "
             "episode-weighted (filled, solid) and equal-child-weighted (open, dashed) estimates with 95% "
             "child-cluster intervals on the 121-set.")

    b.label("Supporting argument")
    b.bullets([
        f"**Where the weight moves.** Under episode weighting {fewest} contributes {pct(pc[fewest]['episode_weight'])} "
        f"of the estimate; under equal-child weighting every child contributes {pct(1 / len(pc))}. Children who kept "
        f"all 12 episodes drop from {pct(12 / n)} to {pct(1 / len(pc))}.",
        "**Agreement metrics.** Merged and whole-record agreement change by about a point or less for every model, "
        "and the qwen3:14b − qwen2.5:7b merged-agreement difference stays small with an interval including zero "
        "under both weightings.",
        "**Unsupported assertion.** Its denominator is reference-null slots, not episodes, so the recorded value is "
        f"weighted by reference-null slot. On the 121-set those slots are few and uneven by child "
        f"({', '.join(undefined)}: none, so the rate is undefined and the child is left out; others 1–10). Equal-child "
        "weighting gives a child with one slot the same weight as a child with ten, which is why qwen2.5:7b moves "
        f"from {100 * pm['qwen2.5:7b']['unsupported_rate']['episode_weighted']:.1f}% to "
        f"{100 * pm['qwen2.5:7b']['unsupported_rate']['child_weighted']:.1f}% and the paired difference loses its "
        "interval. The main-batch paired difference (330 segments) is not affected by this comment.",
        "**Why episode weighting stays primary.** It is the estimand used for the main batch (330) and the "
        "original 132 in every earlier round, so the 121 remains directly comparable with them. No other "
        "rationale for the choice is documented; the authors may add one.",
    ])
    b.boxed("Suggested manuscript wording (Section 2.13 Methods; Section 3.3 Results; Section 4.9)", [
        "**Methods 2.13:** \"After overlap exclusion, 121 of the 132 frozen evaluation episodes remained, with "
        f"{pc[fewest]['retained']} to 12 episodes per child (Table X). The primary post-audit estimand is episode-weighted: "
        "metrics are pooled over retained episodes (for unsupported assertion, over reference-null field slots), as for "
        "the main batch and the original 132-episode set. As a sensitivity analysis we computed each metric within "
        "child and averaged children with equal weight, with 95% child-cluster bootstrap intervals; unsupported "
        "assertion is undefined for children with no reference-null slots, and such children were omitted from that "
        "average.\"",
        "**Results 3.3:** \"Equal-child weighting changed merged and whole-record agreement by at most "
        f"{100 * max_merged_shift:.1f} percentage points for any model (Table Y). For unsupported assertion, which "
        f"was defined for {pm['qwen3:14b']['unsupported_rate']['n_children_defined']} children on 1–10 reference-null "
        "slots each, the qwen3:14b − qwen2.5:7b difference was "
        f"{ci_pp(ep_pair['unsupported_rate']['value'], ep_pair['unsupported_rate']['ci95']['lower'], ep_pair['unsupported_rate']['ci95']['upper'])} "
        "percentage points under episode weighting and "
        f"{ci_pp(pair['unsupported_rate']['value'], pair['unsupported_rate']['lower'], pair['unsupported_rate']['upper'])} "
        "under equal-child weighting.\"",
        "**Limitations 4.9:** \"On the post-audit 121-episode set, the unsupported-assertion comparison between the "
        "two strongest generators was sensitive to how children were weighted, reflecting few reference-null "
        "opportunities per child.\"",
    ], fill="EAF7F1", edge="1BAF7A")


def a_r52(b: Doc, ctx) -> None:
    rn = ctx["rn"]
    for side in ("main_batch_330", "frozen_132"):
        c, u = rn[side]["capped_8"], rn[side]["under_8"]
        assert c["gold_null_mean"] < u["gold_null_mean"]
        assert c["reference_null_slots"]["domain"] == 0 and c["reference_null_slots"]["prompt_level"] == 0
        assert c["qwen2.5:7b_unsupported"] > u["qwen2.5:7b_unsupported"]

    b.label("Short answer")
    b.answer_line(
        "**The analysis is now reported in Methods and Results, by field, with the comparison defined; "
        "Limitations only refers back to it.** It was computed in Round 4 (`round4_analysis.json`, "
        "episode_cap.annotated_by_cap) but never reported outside the Limitations sentence. Capped episodes carry "
        f"fewer reference nulls in both annotated sets (field mean {pct(rn['main_batch_330']['capped_8']['gold_null_mean'])} vs "
        f"{pct(rn['main_batch_330']['under_8']['gold_null_mean'])} in the main batch; "
        f"{pct(rn['frozen_132']['capped_8']['gold_null_mean'])} vs {pct(rn['frozen_132']['under_8']['gold_null_mean'])} "
        "in the frozen 132). Domain and prompt level are never null in capped episodes. The comparison is descriptive, "
        "with no inferential test.")
    b.p(f"**Definition.** {rn['definition'][0].upper() + rn['definition'][1:]}. Turns are counted as speaker lines "
        "(lines beginning `*`) in the rendered episode text. A reference null is a field the adjudicated reference "
        "standard leaves empty; each is one opportunity for an unsupported assertion.")
    rows = []
    for side, nm in (("main_batch_330", "Main batch (330)"), ("frozen_132", "Frozen 132")):
        for g, lab in (("capped_8", "capped (8)"), ("under_8", "shorter (< 8)")):
            v = rn[side][g]
            rows.append([nm, lab, str(v["n"])]
                        + [f"{pct(v['gold_null_share'][f])} ({v['reference_null_slots'][f]})" for f in FIELDS]
                        + [pct(v["gold_null_mean"]), f"{v['reference_null_slots_total']} / {v['field_slots']}",
                           pct(v["qwen2.5:7b_unsupported"])])
    b.table("Reference-null share by field (count of null slots), pooled mean of the four fields, total null "
            "slots over all field slots, and qwen2.5:7b unsupported-assertion rate, for capped and shorter episodes. "
            "Descriptive; not adjusted for other differences between the groups. Source: `round5_analysis.json` "
            "(reference_nulls_by_cap), from `round4_analysis.json`.",
            ["Set", "Episodes", "n", "domain", "modality", "prompt level", "outcome", "Mean", "Null slots",
             "qwen2.5:7b unsupp."],
            rows, [0.85, 0.75, 0.35, 0.6, 0.7, 0.65, 0.7, 0.5, 0.7, 0.75])
    b.figure(fig_reference_nulls(rn), "Share of episodes whose reference value is null, by field, for capped "
             "(8-turn) and shorter episodes, in the main batch and the frozen 132.")
    b.label("Supporting argument")
    b.bullets([
        "**Why it matters for unsupported assertion.** The unsupported-assertion rate is computed over reference-null "
        "slots, so a group with fewer nulls offers fewer opportunities. The null-slot totals are similar in size "
        f"between groups ({rn['main_batch_330']['capped_8']['reference_null_slots_total']} vs "
        f"{rn['main_batch_330']['under_8']['reference_null_slots_total']} in the main batch; "
        f"{rn['frozen_132']['capped_8']['reference_null_slots_total']} vs "
        f"{rn['frozen_132']['under_8']['reference_null_slots_total']} in the frozen 132), but they sit almost "
        "entirely in modality and outcome.",
        "**Scope.** The analysis uses the main batch and the original 132, as recorded; it was not rerun on the "
        "121. Denominators are small, and capped episodes may differ from shorter ones in ways other than length; "
        "the design cannot separate the two.",
    ])
    b.boxed("Suggested manuscript wording (Methods 2.12; Results; Limitations 4.9)", [
        "**Methods 2.12 (add):** \"To describe whether the eight-turn maximum was associated with reference-standard "
        "completeness, we compared episodes that reached the maximum (exactly eight speaker turns; 'capped') with "
        "shorter episodes, reporting the share of episodes with a reference null for each categorical field and the "
        "qwen2.5:7b unsupported-assertion rate, in the main batch and the frozen evaluation set. This comparison is "
        "descriptive.\"",
        "**Results (add):** \"Capped episodes had fewer reference nulls than shorter episodes in both sets (mean "
        f"across fields {pct(rn['main_batch_330']['capped_8']['gold_null_mean'])} vs "
        f"{pct(rn['main_batch_330']['under_8']['gold_null_mean'])} in the main batch and "
        f"{pct(rn['frozen_132']['capped_8']['gold_null_mean'])} vs {pct(rn['frozen_132']['under_8']['gold_null_mean'])} "
        "in the evaluation set; Table Z). Domain and prompt level were never null in capped episodes; nulls were "
        "concentrated in modality and outcome. The qwen2.5:7b unsupported-assertion rate was higher in capped "
        f"episodes ({pct(rn['main_batch_330']['capped_8']['qwen2.5:7b_unsupported'])} vs "
        f"{pct(rn['main_batch_330']['under_8']['qwen2.5:7b_unsupported'])}; "
        f"{pct(rn['frozen_132']['capped_8']['qwen2.5:7b_unsupported'])} vs "
        f"{pct(rn['frozen_132']['under_8']['qwen2.5:7b_unsupported'])}), on "
        f"{rn['main_batch_330']['capped_8']['reference_null_slots_total']}–"
        f"{rn['frozen_132']['capped_8']['reference_null_slots_total']} null slots per group.\"",
        "**Limitations 4.9 (replace the empirical clause):** \"… context across those boundaries is lost. Capped "
        "episodes differed descriptively from shorter ones in reference-null frequency (Section 3.x), so extraction "
        "behaviour and the opportunities for unsupported assertion may differ under longer context windows.\"",
    ], fill="EAF7F1", edge="1BAF7A")


def a_r53(b: Doc, ctx) -> None:
    r3 = ctx["r3"]; r4g = ctx["r4g"]; cw = ctx["cw"]
    main = r3["model_performance"]["main_batch"]["paired_qwen3_14b_minus_qwen2_5_7b"]
    hold = r3["model_performance"]["holdout"]["paired_qwen3_14b_minus_qwen2_5_7b"]
    h121 = r3["holdout_sensitivity"]["excluding_all_pool_episodes"]["paired_qwen3_14b_minus_qwen2_5_7b"]
    cwp = cw["paired_qwen3_14b_minus_qwen2_5_7b"]
    ma = lambda g, m: r4g[g]["per_model"][m]["merged_agreement"]["value"]  # noqa: E731
    assert ma("main_batch_330", "qwen2.5:7b") > ma("main_batch_330", "qwen3:14b")
    assert ma("overlap_excluded_121", "qwen3:14b") > ma("overlap_excluded_121", "qwen2.5:7b")
    for d in (main, hold, h121):
        assert not d["merged_agreement"]["ci95"]["excludes_zero"]
        assert d["unsupported_rate"]["ci95"]["excludes_zero"]

    b.label("Short answer")
    b.answer_line(
        "**Agreed. The top two generators swap order on merged agreement between the main batch and the 121-set, "
        "and every paired interval includes zero.** The Conclusion now uses the reviewer's phrase and states that "
        "the top-two ordering was not stable.")
    rows = [
        ["Main batch (330)", f"{100 * ma('main_batch_330', 'qwen2.5:7b'):.1f}", f"{100 * ma('main_batch_330', 'qwen3:14b'):.1f}",
         ci_pp(main["merged_agreement"]["value"], main["merged_agreement"]["ci95"]["lower"], main["merged_agreement"]["ci95"]["upper"]),
         ci_pp(main["unsupported_rate"]["value"], main["unsupported_rate"]["ci95"]["lower"], main["unsupported_rate"]["ci95"]["upper"])],
        ["Frozen 132", f"{100 * ma('frozen_132', 'qwen2.5:7b'):.1f}", f"{100 * ma('frozen_132', 'qwen3:14b'):.1f}",
         ci_pp(hold["merged_agreement"]["value"], hold["merged_agreement"]["ci95"]["lower"], hold["merged_agreement"]["ci95"]["upper"]),
         ci_pp(hold["unsupported_rate"]["value"], hold["unsupported_rate"]["ci95"]["lower"], hold["unsupported_rate"]["ci95"]["upper"])],
        ["121, episode-weighted", f"{100 * ma('overlap_excluded_121', 'qwen2.5:7b'):.1f}", f"{100 * ma('overlap_excluded_121', 'qwen3:14b'):.1f}",
         ci_pp(h121["merged_agreement"]["value"], h121["merged_agreement"]["ci95"]["lower"], h121["merged_agreement"]["ci95"]["upper"]),
         ci_pp(h121["unsupported_rate"]["value"], h121["unsupported_rate"]["ci95"]["lower"], h121["unsupported_rate"]["ci95"]["upper"])],
        ["121, equal-child (sensitivity)", f"{100 * cw['per_model']['qwen2.5:7b']['merged_agreement']['child_weighted']:.1f}",
         f"{100 * cw['per_model']['qwen3:14b']['merged_agreement']['child_weighted']:.1f}",
         ci_pp(cwp["merged_agreement"]["value"], cwp["merged_agreement"]["lower"], cwp["merged_agreement"]["upper"]),
         ci_pp(cwp["unsupported_rate"]["value"], cwp["unsupported_rate"]["lower"], cwp["unsupported_rate"]["upper"])],
    ]
    b.table("The two strongest generators across evaluation sets: merged agreement (%) and paired differences "
            "qwen3:14b − qwen2.5:7b (percentage points, 95% child-cluster CI). Sources: `round4_analysis.json` "
            "(same_universe.groups), `round3_analysis.json` (paired), `round5_analysis.json` (equal-child).",
            ["Set", "qwen2.5:7b merged", "qwen3:14b merged", "Paired Δ merged", "Paired Δ unsupported"],
            rows, [1.6, 0.95, 0.95, 1.55, 1.65])
    b.label("Supporting argument")
    b.bullets([
        "**What is stable.** On every set qwen2.5:3b has the lowest merged agreement and the lowest "
        "unsupported-assertion rate, and llama3.2 and qwen3:14b have high unsupported-assertion rates. Under the "
        "primary (episode-weighted) estimand the qwen3:14b − qwen2.5:7b unsupported-assertion difference excludes "
        "zero on the main batch, the frozen 132 and the 121.",
        "**What is not.** The top-two order on merged agreement reverses, on differences of about one point.",
        "**Note on consistency with R5-1.** The phrase 'unsupported-assertion conclusions' refers to the primary "
        "estimand. Under the equal-child sensitivity analysis the 121-set unsupported-assertion difference between "
        "the two strongest generators includes zero; this is stated in Results and Limitations (R5-1).",
    ])
    b.boxed("Suggested manuscript wording (Section 5, Conclusions)", [
        "Replace \"preserved the broad model-ranking conclusions\" with: \"preserved the broad comparative pattern "
        "and unsupported-assertion conclusions, although the ordering of the two strongest generators on merged "
        "agreement was not stable.\"",
    ], fill="EAF7F1", edge="1BAF7A")


ANSWERS = {"R5-1": a_r51, "R5-2": a_r52, "R5-3": a_r53}


def build() -> Path:
    FIG.mkdir(parents=True, exist_ok=True)
    r5, r4, r3 = load("round5_analysis.json"), load("round4_analysis.json"), load("round3_analysis.json")
    cw = r5["child_weighting_121"]
    r4g = r4["same_universe"]["groups"]
    r4_121 = r4g["overlap_excluded_121"]["per_model"]
    cw["_episode_ci"] = {m: {k: r4_121[m][k]["ci95"] for k in METRIC_NAMES} for m in MODELS}
    ctx = {"cw": cw, "rn": r5["reference_nulls_by_cap"], "r3": r3, "r4g": r4g, "r4_121": r4_121}
    comments = read_comments()
    assert [c["id"] for c in comments] == list(ANSWERS), [c["id"] for c in comments]
    assert all(len(c["items"]) == 4 for c in comments)

    b = Doc()
    grey = RGBColor(0x52, 0x51, 0x4E)
    b.doc.add_heading("Response to MDPI Round-5 Review Comments", level=0)
    b.p("Answers the three open comments in 'Round5_Review_Feedback.docx', in their original order and wording. "
        "Branch model-finetuning, built 2026-09-26. Internal working document; not for submission.", colour=grey)
    b.p("Every number is read from a recorded artefact named in the table that shows it. This round adds "
        "`round5_analysis.json`, computed from preserved outputs and the deterministic CHAT pipeline with **no "
        "model call**. Claims about the data are checked by assertion when this document is built.", colour=grey)

    pair = cw["paired_qwen3_14b_minus_qwen2_5_7b"]["unsupported_rate"]
    b.h("Summary", 1)
    b.table("Each comment and the answer in one line.", ["ID", "Severity", "Answer"], [
        ["R5-1", "Moderate", "Per-child counts reported (6–12). Episode-weighted estimand kept as primary and stated; "
                             "equal-child sensitivity added. Agreement robust; 121-set unsupported-assertion gap not"],
        ["R5-2", "Moderate", "Capped-vs-shorter reference-null analysis moved into Methods/Results, by field; "
                             "Limitations refers back"],
        ["R5-3", "Minor", "Reviewer's Conclusion phrase adopted; top-two ordering stated as not stable"],
    ], [0.55, 0.85, 5.3])
    b.label("One result that changes what the manuscript says")
    b.bullets([
        "**R5-1:** under equal-child weighting, the qwen3:14b − qwen2.5:7b unsupported-assertion difference on the "
        f"121-set is {ci_pp(pair['value'], pair['lower'], pair['upper'])} points; its interval includes zero. "
        "Under the primary estimand it excludes zero. Both are reported.",
    ])

    for c in comments:
        b.page_break()
        b.h(f"{c['id']}  ·  {c['severity']}  ·  {c['title']}", 1)
        render_comment(b, c)
        b.h("Response", 2)
        ANSWERS[c["id"]](b, ctx)

    b.page_break()
    b.h("Suggested resolution order, with status", 1)
    b.table("The reviewer's order, unchanged, with what this round did.", ["#", "Comment", "Next action (reviewer)", "Status"], [
        ["1", "R5-1", "Check per-child counts and add an equal-child-weighted sensitivity estimate or justify the "
                      "episode-weighted estimand.", "Done; both"],
        ["2", "R5-2", "Report the capped-versus-shorter reference-null analysis properly or remove the statement.",
         "Done; reported in Methods/Results"],
        ["3", "R5-3", "Tighten the Conclusion wording around model-ranking stability.", "Done; wording supplied"],
    ], [0.3, 0.8, 3.9, 1.7])
    b.h("How this document was produced", 1)
    b.code(["uv run python -m tests.eval.extraction.round5_analysis   # no model calls; needs exp-data/ locally",
            "uv run python docs/paper/make_round5_response.py"])
    b.doc.save(str(OUT))
    return OUT


if __name__ == "__main__":
    print(build())
