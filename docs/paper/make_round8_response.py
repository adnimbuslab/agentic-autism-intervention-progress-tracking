"""Build the response to the MDPI round-8 review comments (R8-1, R8-2).

Reads ``R8_review comments.docx`` in document order and answers each comment
underneath, verbatim comment first. Every number is read from
``round8_analysis.json`` (added this round, no model calls), and each table
names its source. Statements about the data are asserted before they are
printed.

    uv run python -m tests.eval.extraction.round8_analysis
    uv run python docs/paper/make_round8_response.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
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

from make_round2_response import AQUA, BLUE, GRID, INK, ORANGE, YELLOW, Doc, pct  # noqa: E402
from make_round3_response import GREY  # noqa: E402
from make_round4_response import render_comment  # noqa: E402

ROOT = PAPER.parents[1]
RESULTS = ROOT / "tests" / "eval" / "extraction" / "results"
QUESTIONS = PAPER / "R8_review comments.docx"
FIG = PAPER / "figures" / "round8"
OUT = PAPER / "Round8_Review_Response.docx"
SETS = [("all_episodes_9018", "All segmented episodes (9,018)"), ("universe_2442", "2,442 universe (cap 273/child)"),
        ("universe_3371", "3,371 universe (cap 455/child)"), ("pool_1320", "Annotation pool (1,320)"),
        ("main_batch_330", "Main batch (330)"), ("frozen_132", "Frozen evaluation set (132)"),
        ("overlap_excluded_121", "Post-audit evaluation set (121)")]
QCOL = [BLUE, AQUA, YELLOW, ORANGE]
QLAB = ["0–0.25 (earliest)", "0.25–0.5", "0.5–0.75", "0.75–1 (latest)"]


def load(name: str) -> Any:
    return json.loads((RESULTS / name).read_text())


def day(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%-d %b %Y")


def read_comments() -> list[dict[str, Any]]:
    src = docx.Document(str(QUESTIONS))
    comments: list[dict[str, Any]] = []
    for el in src.element.body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "tbl":
            text = Table(el, src).rows[0].cells[0].text.strip()
            parts = [p.strip() for p in text.split("|")]
            if len(parts) == 3 and parts[0].startswith("R8-"):
                comments.append({"id": parts[0], "severity": parts[1], "title": parts[2], "items": []})
        elif tag == "p" and comments:
            t = Paragraph(el, src).text.strip()
            if t and any(t.startswith(k) for k in ("Location:", "Reviewer concern:", "Required action:", "Status:")):
                comments[-1]["items"].append(t)
    return comments


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig_quartiles(sc: dict) -> Path:
    fig, ax = plt.subplots(figsize=(10, 3.9))
    for i, (k, lab) in enumerate(SETS):
        q = sc["sets"][k]["pooled_quartile_shares"]
        left = 0.0
        for j, v in enumerate(q):
            ax.barh(i, 100 * v, left=left, color=QCOL[j], edgecolor="white", lw=1.5, height=0.62)
            if v >= 0.06:
                ax.text(left + 50 * v, i, f"{100 * v:.0f}%", ha="center", va="center", fontsize=7.4,
                        color="white" if j in (0, 3) else INK)
            left += 100 * v
        ax.text(101.5, i, f"mean {sc['sets'][k]['pooled_mean_position']:.2f}", va="center", fontsize=7.6)
    ax.axvline(25, color=GREY, lw=0.6, ls=":"); ax.axvline(50, color=GREY, lw=0.6, ls=":"); ax.axvline(75, color=GREY, lw=0.6, ls=":")
    ax.set_yticks(range(len(SETS)), [s[1] for s in SETS], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 114)
    ax.set_xlabel("% of episodes, by relative session position within the child's record")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for c in QCOL], labels=QLAB, frameon=False, fontsize=7.6,
              ncol=4, loc="upper center", bbox_to_anchor=(0.45, 1.16))
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    p = FIG / "r8_fig1_session_quartiles.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def fig_per_child(sc: dict) -> Path:
    show = [("all_episodes_9018", "all episodes", GREY, "o"), ("universe_2442", "2,442 universe", BLUE, "s"),
            ("universe_3371", "3,371 universe", AQUA, "D"), ("main_batch_330", "main batch 330", ORANGE, "^"),
            ("overlap_excluded_121", "evaluation 121", YELLOW, "v")]
    ref = sc["sets"]["all_episodes_9018"]["per_child"]
    kids = sorted(ref, key=lambda c: (-ref[c]["sessions_total"], c))
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for j, (k, lab, col, mk) in enumerate(show):
        pc = sc["sets"][k]["per_child"]
        ys = [i + (j - 2) * 0.12 for i in range(len(kids))]
        ax.scatter([pc[c]["mean_position"] for c in kids], ys, color=col, marker=mk, s=30, zorder=3, label=lab,
                   edgecolor="white", lw=0.5)
    ax.set_yticks(range(len(kids)), [f"{c}  ({ref[c]['sessions_total']} sessions)" for c in kids], fontsize=7.8)
    ax.invert_yaxis()
    ax.axvline(0.5, color=GREY, lw=0.7, ls=":")
    ax.set_xlim(0, 0.75)
    ax.set_xlabel("mean relative session position (0 = first visit, 1 = last)")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=7.6, ncol=5, loc="upper center", bbox_to_anchor=(0.45, 1.12))
    fig.tight_layout()
    p = FIG / "r8_fig2_per_child_position.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def fig_timeline(vt: dict) -> Path:
    events = []
    for r in vt["validate_report"]:
        if r["logic_changed"]:
            events.append((r["date"], f"validate_report logic\ncommitted ({r['commit']})", BLUE))
    for r in vt["grounding_scorer"]:
        if r["logic_changed"]:
            events.append((r["date"], f"grounding scorer committed\n({r['commit']}); recorded run:\n0 LLM / 11 fallback", AQUA))
    for r in vt["recorded_runs"]:
        if r["n_llm_reports"]:
            events.append((r["date"], f"11 LLM reports first\nrecorded ({r['commit']}),\n{r['reports_passing_validation']}/11 pass", ORANGE))
    events.sort()
    t0 = datetime.fromisoformat(events[0][0])
    xs = [(datetime.fromisoformat(d) - t0).total_seconds() / 86400 for d, _, _ in events]
    fig, ax = plt.subplots(figsize=(10, 2.6))
    ax.axhline(0, color=INK, lw=1)
    for x, (d, lab, col), up in zip(xs, events, [1, 1, -1]):
        ax.scatter([x], [0], s=70, color=col, zorder=3)
        ax.text(x, 0.35 * up, f"{day(d)}\n{lab}", ha="center", va="bottom" if up > 0 else "top", fontsize=7.6)
    ax.text(xs[-1] + 1.5, 0, "criteria unchanged\nsince", va="center", fontsize=7.2, color=GREY)
    ax.set_xlim(-3, xs[-1] + 6)
    ax.set_ylim(-1.3, 1.3)
    ax.axis("off")
    fig.tight_layout()
    p = FIG / "r8_fig3_validator_timeline.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------

def a_r81(b: Doc, ctx) -> None:
    sc = ctx["r8"]["session_coverage"]
    s = sc["sets"]
    ref, u2, u3, mb, ev = (s[k] for k in ("all_episodes_9018", "universe_2442", "universe_3371", "main_batch_330",
                                           "overlap_excluded_121"))
    assert abs(ref["pooled_mean_position"] - 0.5) < 0.02
    assert u2["pooled_mean_position"] < u3["pooled_mean_position"] < ref["pooled_mean_position"]
    assert all(s[k]["mean_child_shift_vs_all_episodes"] < 0 for k, _ in SETS[1:])
    assert mb["pooled_mean_position"] < ev["pooled_mean_position"]
    long_kids = [c for c, v in ref["per_child"].items() if v["sessions_total"] >= 8]

    b.label("Short answer")
    b.answer_line(
        "**Early-session enrichment is present and is substantial in the lower-cap universe.** Across all segmented "
        f"episodes the mean relative session position is {ref['pooled_mean_position']:.2f} (0 = a child's first visit, "
        f"1 = the last). The 2,442-segment universe has mean {u2['pooled_mean_position']:.2f}, with "
        f"{pct(u2['pooled_quartile_shares'][0])} of its segments in the earliest quarter of each child's record against "
        f"{pct(ref['pooled_quartile_shares'][0])} available, and it omits "
        f"{u2['sessions_total'] - u2['sessions_represented']} of the {u2['sessions_total']} sessions entirely. The "
        f"3,371-segment universe is less skewed (mean {u3['pooled_mean_position']:.2f}; "
        f"{u3['sessions_represented']}/{u3['sessions_total']} sessions). The two branches therefore also differ in "
        f"longitudinal reach: the main batch has mean {mb['pooled_mean_position']:.2f} and the post-audit 121 "
        f"{ev['pooled_mean_position']:.2f}. The largest shifts, and all whole-session omissions, are in the Flusberg "
        "children with 8–13 sessions; the Rollins children (4–5 sessions) keep every session in both universes but are "
        "still shifted earlier in the 2,442 universe. Nothing was redrawn.")

    b.p("**Definition.** Each child's sessions are ordered by the child's age in the CHAT @ID header (available for all "
        "85 sessions). Session k of n has relative position k / (n − 1). Each episode takes its session's position. "
        "The reference is all 9,018 segmented episodes: what the universe builder could have retained.")
    b.table("Longitudinal coverage by set. Shift = mean over children of (child's mean position in the set − child's "
            "mean position over all episodes); negative = earlier. Source: `round8_analysis.json` "
            "(session_coverage.sets).",
            ["Set", "n", "Sessions represented", "Children with all sessions", "Mean position",
             "Earliest quarter", "Latest quarter", "Shift vs all"],
            [[lab, f"{s[k]['n']:,}", f"{s[k]['sessions_represented']}/{s[k]['sessions_total']}",
              f"{s[k]['children_with_all_sessions']}/11", f"{s[k]['pooled_mean_position']:.3f}",
              pct(s[k]["pooled_quartile_shares"][0]), pct(s[k]["pooled_quartile_shares"][3]),
              f"{s[k]['mean_child_shift_vs_all_episodes']:+.3f}" if "mean_child_shift_vs_all_episodes" in s[k] else "ref."]
             for k, lab in SETS],
            [1.9, 0.5, 0.8, 0.8, 0.7, 0.7, 0.7, 0.65])
    b.figure(fig_quartiles(sc), "Share of each set's episodes by relative session position quarter. All segmented "
             "episodes are spread evenly; the 2,442 universe, the pool and the main batch concentrate in each child's "
             "earliest quarter.")

    rows = []
    for c in sorted(ref["per_child"], key=lambda c: (-ref["per_child"][c]["sessions_total"], c)):
        row = [c]
        for k in ("all_episodes_9018", "universe_2442", "universe_3371", "main_batch_330", "overlap_excluded_121"):
            v = s[k]["per_child"][c]
            row.append(f"{v['sessions_represented']}/{v['sessions_total']} · {v['mean_position']:.2f}")
        rows.append(row)
    b.table("Per child: sessions represented / total · mean relative position. Source: `round8_analysis.json` "
            "(session_coverage.sets.*.per_child).",
            ["Child", "All episodes", "2,442 universe", "3,371 universe", "Main batch 330", "Evaluation 121"],
            rows, [1.3, 1.05, 1.05, 1.05, 1.05, 1.05])
    b.figure(fig_per_child(sc), "Mean relative session position per child. Grey circles are all segmented episodes; "
             "the universes and samples sit to the left, most strongly for the Flusberg children with long records.")

    b.label("Supporting argument")
    b.bullets([
        "**Mechanism, as the reviewer describes.** Within each child × episode-type stratum the builder keeps episodes "
        "in transcript order until the per-type allocation is reached (`data/pipeline/select_segments.py`, "
        "`_select_for_child`). Where a type has more episodes than its allocation, later sessions are cut. "
        f"Children with long records ({', '.join(sorted(long_kids))}) lose the most, including whole sessions.",
        f"**Why the 121 is later than its universe ({ev['pooled_mean_position']:.2f} vs "
        f"{u3['pooled_mean_position']:.2f}).** The frozen set was drawn at random from the 3,371 universe after pool "
        "episodes were removed, and the pool is itself early-heavy "
        f"(mean {s['pool_1320']['pooled_mean_position']:.2f}), so removing it leaves a later frame.",
        "**What this does and does not imply.** It characterises which part of each child's record the estimates "
        "describe. It does not by itself show that extraction agreement differs by session position; that was not "
        "tested, and no model was run. It adds a further documented difference between the main and evaluation "
        "branches, consistent with the manuscript's existing refusal to attribute the between-branch difference to "
        "any single cause.",
    ])
    b.boxed("Suggested manuscript wording (Sections 2.12–2.13, Results, and 4.9)", [
        "**Methods 2.12 (add):** \"Because the universe builder retains episodes in transcript order within each "
        "child × episode-type stratum, we characterised longitudinal coverage: each child's sessions were ordered by "
        "age, and each episode was assigned its session's relative position (0 = first visit, 1 = last).\"",
        f"**Results (add):** \"All segmented episodes had mean relative session position "
        f"{ref['pooled_mean_position']:.2f}. The 2,442-segment universe was enriched for early sessions (mean "
        f"{u2['pooled_mean_position']:.2f}; {pct(u2['pooled_quartile_shares'][0])} of segments in the earliest quarter "
        f"of each child's record; {u2['sessions_represented']} of {u2['sessions_total']} sessions represented), and the "
        f"3,371-segment universe less so (mean {u3['pooled_mean_position']:.2f}; {u3['sessions_represented']} of "
        f"{u3['sessions_total']} sessions). The main batch (mean {mb['pooled_mean_position']:.2f}) and the post-audit "
        f"evaluation set (mean {ev['pooled_mean_position']:.2f}) therefore differ in longitudinal reach as well as in "
        "universe (Table X). The enrichment was largest in children with eight or more sessions.\"",
        "**Limitations 4.9 (add):** \"Both universes over-represent each child's earlier sessions, the lower-cap "
        "universe markedly so, because episodes were retained in transcript order within strata. Estimates therefore "
        "describe earlier visits more than later ones, and the main and evaluation branches differ in longitudinal "
        "coverage. Whether extraction agreement varies with session position was not tested.\"",
    ], fill="EAF7F1", edge="1BAF7A")
    b.boxed("Decision for the authors", [
        "The reviewer asks for a new model experiment only if the diagnostic shows a substantial imbalance. The skew "
        "in the 2,442 universe is large. Options, none taken here: (a) acknowledge in Limitations only, as drafted "
        "above; (b) additionally stratify the existing scored outputs (330 and 121) by session position — no model "
        "run, no redraw — to show whether agreement differs between earlier and later sessions.",
    ])


def a_r82(b: Doc, ctx) -> None:
    vt = ctx["r8"]["validator_timeline"]
    vr = [r for r in vt["validate_report"] if r["logic_changed"]]
    gs = [r for r in vt["grounding_scorer"] if r["logic_changed"]]
    llm_runs = [r for r in vt["recorded_runs"] if r["n_llm_reports"]]
    pre = [r for r in vt["recorded_runs"] if not r["n_llm_reports"]]
    assert len(vr) == 1 and len(gs) == 1 and len(llm_runs) == 1 and len(pre) == 1
    assert vr[0]["date"] < gs[0]["date"] < llm_runs[0]["date"]
    assert gs[0]["commit"] == pre[0]["commit"] and pre[0]["n_fallback_reports"] == 11
    assert llm_runs[0]["reports_passing_validation"] == 0 and llm_runs[0]["n_llm_reports"] == 11

    b.label("Short answer")
    b.answer_line(
        "**The criteria were fixed in version-controlled code before any of the 11 model-generated reports was "
        "recorded, and were not changed afterwards.** The governance validator `validate_report` "
        f"(`src/backend/ml/reporting_client.py`) was committed on {day(vr[0]['date'])} ({vr[0]['commit']}) and its "
        "logic is unchanged in every later commit. The grounding scorer (`tests/eval/reporting/groundedness.py`) was "
        f"committed on {day(gs[0]['date'])} ({gs[0]['commit']}); the report file recorded in that same commit contains "
        "0 model-generated reports (all 11 were deterministic fallbacks), so no model prose had been scored when the "
        f"scorer was fixed. The 11 model-generated reports were first recorded on {day(llm_runs[0]['date'])} "
        f"({llm_runs[0]['commit']}), {llm_runs[0]['reports_passing_validation']}/11 passing; that commit changed only "
        "how totals are summed and printed.")
    b.table("What each criterion is, where it is implemented, and when its logic entered version control. Source: "
            "`round8_analysis.json` (validator_timeline).",
            ["Criterion", "Pass/fail rule", "Implemented in", "Logic fixed"],
            [["Prohibited content", "no diagnostic, treatment, causal or prognostic pattern in the prose",
              "validate_report", f"{day(vr[0]['date'])} ({vr[0]['commit']})"],
             ["Abstention / governance preservation", "every withheld metric (and insufficient evidence) acknowledged",
              "validate_report", f"{day(vr[0]['date'])} ({vr[0]['commit']})"],
             ["Numeric grounding", "every number in the prose appears in the evidence packet at printed precision",
              "groundedness.py", f"{day(gs[0]['date'])} ({gs[0]['commit']})"],
             ["Evidence-reference validity", "every cited record ID exists in the packet",
              "groundedness.py", f"{day(gs[0]['date'])} ({gs[0]['commit']})"]],
            [1.6, 2.6, 1.1, 1.4])
    b.table("Every commit touching the validator, the scorer or the recorded result. 'Logic changed' ignores comment "
            "lines.",
            ["Artefact", "Commit", "Date", "Logic changed / content"],
            [["validate_report", r["commit"], day(r["date"]), "yes" if r["logic_changed"] else "no"] for r in vt["validate_report"]]
            + [["grounding scorer", r["commit"], day(r["date"]), "yes" if r["logic_changed"] else "no"] for r in vt["grounding_scorer"]]
            + [["recorded report run", r["commit"], day(r["date"]),
                f"{r['n_llm_reports']} LLM / {r['n_fallback_reports']} fallback; {r['reports_passing_validation']} pass"]
               for r in vt["recorded_runs"]],
            [1.6, 0.9, 1.3, 2.9])
    b.figure(fig_timeline(vt), "Order of events from git history: validator, then scorer (recorded with 0 "
             "model-generated reports), then the 11 model-generated reports.")
    b.label("Supporting argument and limits")
    b.bullets([
        "**The 0/11 result comes from `validate_report`,** the oldest of the artefacts: every report failed on "
        "unacknowledged withheld metrics (cross-setting and cross-contributor comparison).",
        "**Earlier attempts.** Before the recorded run the reporting call failed structurally (prompt-only formatting "
        "on the `/v1` endpoint); schema-constrained decoding was adopted to fix structure, before any governance result "
        "existed (`docs/paper/clarification_answers_round2.md`, Q7). Those attempts fell back to the template and were "
        "not scored.",
        "**The one calibration that was made** (matching numbers at printed precision) was calibrated on the "
        "deterministic template, whose prose is grounded by construction, not on model output; it is documented in the "
        "scorer and precedes the model-generated run.",
        f"**Limit.** {vt['note']} The ordering of commits is therefore the evidence offered; the exact time of the run "
        "within 16–17 September is not recorded.",
    ])
    b.boxed("Suggested manuscript wording (Section 2.19)", [
        f"\"The four pass/fail criteria were fixed in version-controlled code before the 11 reports were generated and "
        f"were not modified afterwards: the governance validator (prohibited content; acknowledgement of insufficient "
        f"evidence and of each withheld metric) was committed on {day(vr[0]['date'])}, and the numeric-grounding and "
        f"evidence-reference scorer on {day(gs[0]['date'])}, when no model-generated report had yet been recorded "
        f"(commits {vr[0]['commit']}, {gs[0]['commit']}; reports recorded in {llm_runs[0]['commit']}).\"",
    ], fill="EAF7F1", edge="1BAF7A")


ANSWERS = {"R8-1": a_r81, "R8-2": a_r82}


def build() -> Path:
    FIG.mkdir(parents=True, exist_ok=True)
    ctx = {"r8": load("round8_analysis.json")}
    comments = read_comments()
    assert [c["id"] for c in comments] == list(ANSWERS), [c["id"] for c in comments]
    assert all(len(c["items"]) == 4 for c in comments)
    s = ctx["r8"]["session_coverage"]["sets"]

    b = Doc()
    grey = RGBColor(0x52, 0x51, 0x4E)
    b.doc.add_heading("Response to MDPI Round-8 Review Comments", level=0)
    b.p("Answers the two open comments in 'R8_review comments.docx', in their original order and wording. Branch "
        "model-finetuning, built 2026-09-27. Internal working document; not for submission.", colour=grey)
    b.p("Every number is read from `round8_analysis.json`, computed from the deterministic CHAT pipeline, recorded "
        "sample files and git history, with **no model call** and no redraw. Claims about the data are checked by "
        "assertion when this document is built.", colour=grey)
    b.h("Summary", 1)
    b.table("Each comment and the answer in one line.", ["ID", "Severity", "Answer"], [
        ["R8-1", "Moderate", f"Early-session enrichment present: mean position {s['universe_2442']['pooled_mean_position']:.2f} "
                             f"(2,442) and {s['universe_3371']['pooled_mean_position']:.2f} (3,371) vs "
                             f"{s['all_episodes_9018']['pooled_mean_position']:.2f} available; main batch "
                             f"{s['main_batch_330']['pooled_mean_position']:.2f}, evaluation 121 "
                             f"{s['overlap_excluded_121']['pooled_mean_position']:.2f}. Limitation wording supplied"],
        ["R8-2", "Minor / Moderate", "Criteria fixed in committed code before the 11 reports were recorded; unchanged "
                                     "since. Sentence and commit IDs supplied"],
    ], [0.55, 1.0, 5.15])

    for c in comments:
        b.page_break()
        b.h(f"{c['id']}  ·  {c['severity']}  ·  {c['title']}", 1)
        render_comment(b, c)
        b.h("Response", 2)
        ANSWERS[c["id"]](b, ctx)

    b.h("How this document was produced", 1)
    b.code(["uv run python -m tests.eval.extraction.round8_analysis   # no model calls; needs exp-data/ locally",
            "uv run python docs/paper/make_round8_response.py"])
    b.doc.save(str(OUT))
    return OUT


if __name__ == "__main__":
    print(build())
