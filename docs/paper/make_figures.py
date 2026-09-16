"""Generate manuscript figures from measured data only.

Every number plotted here was produced by a run recorded in this repository.
Nothing is simulated, extrapolated, or filled in.

Figures 6-8 read ``annotation_batch.json`` directly rather than restating
constants, so they cannot drift from the artefact they describe.

The batch now exists (330 candidates, 11 children, 3 generators) but is *not
yet annotated*. Figures that require human labels -- field accuracy, inter-rater
kappa, the oracle selection ceiling, MARS capture rate -- remain absent. An
empty axis is preferable to a plausible-looking placeholder that could survive
into a submission. Figure 8 reports coverage headroom, which is what an oracle
selector could add in *populated fields*; it is not an accuracy ceiling and is
labelled as such.

    uv run python docs/paper/make_figures.py
"""

from __future__ import annotations

import itertools
import json
import textwrap
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1f2933"
MUTED = "#7b8794"
GRID = "#e4e7eb"
BLUE = "#3b6ea5"
TEAL = "#2a9d8f"
AMBER = "#e0a458"
RED = "#c1666b"

plt.rcParams.update({
    "font.size": 9,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 160,
})


def _finish(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", pad=14 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=8, color=MUTED)
    ax.grid(axis="both", color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)


# --- Figure 1: corpus composition -------------------------------------------
# Source: load_real_segments() over exp-data, 2026-09-07.
CHILDREN = [
    ("carl", "Rollins", 220), ("josh", "Rollins", 182), ("mars", "Rollins", 223),
    ("roger_rollins", "Rollins", 162), ("sid", "Rollins", 206),
    ("brett", "Flusberg", 273), ("jack", "Flusberg", 183), ("mark", "Flusberg", 273),
    ("rick", "Flusberg", 224), ("roger_flusberg", "Flusberg", 273),
    ("stuart", "Flusberg", 223),
]


def figure_corpus() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    names = [c[0] for c in CHILDREN]
    counts = [c[2] for c in CHILDREN]
    colors = [BLUE if c[1] == "Rollins" else TEAL for c in CHILDREN]
    ax.bar(names, counts, color=colors, zorder=3, width=0.68)
    ax.axhline(120, color=AMBER, linestyle="--", linewidth=1.2, zorder=4)
    ax.text(10.4, 132, "120 sampled per child", color=AMBER, fontsize=8, ha="right")
    ax.set_ylabel("behavioural segments")
    ax.tick_params(axis="x", rotation=45)
    for label in ax.get_xticklabels():
        label.set_ha("right")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=BLUE),
        plt.Rectangle((0, 0), 1, 1, color=TEAL),
    ]
    ax.legend(handles, ["Rollins", "Flusberg"], frameon=False, fontsize=8, loc="upper left")
    _finish(ax, "Figure 1 — Segment yield per child after deidentification",
            "2,442 segments, 11 children, 85 sessions. Child attribution corrected 2026-09-07.")
    fig.tight_layout()
    fig.savefig(OUT / "fig1_corpus.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 2: admission policy ---------------------------------------------
# Source: stratified 11-child probe (llama3.2, qwen2.5:3b, qwen2.5:7b) and
# 60-segment pilot (mistral), 2026-09-07.
ADMISSION = [
    ("qwen2.5:7b", 81.8, 100.0, 11),
    ("qwen2.5:3b", 31.8, 81.8, 22),
    ("llama3.2", 31.8, 72.7, 22),
    ("mistral", 1.7, 8.3, 60),
]


def figure_admission() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    names = [a[0] for a in ADMISSION]
    y = range(len(names))
    reviewable = [a[1] for a in ADMISSION]
    judgeable = [a[2] for a in ADMISSION]
    ax.barh([i + 0.19 for i in y], judgeable, height=0.36, color=TEAL,
            label="judgeable (≥1 populated field)", zorder=3)
    ax.barh([i - 0.19 for i in y], reviewable, height=0.36, color=BLUE,
            label="reviewable (SUCCESS/PARTIAL)", zorder=3)
    for i, (r, j) in enumerate(zip(reviewable, judgeable, strict=True)):
        ax.text(j + 1.5, i + 0.19, f"{j:.0f}%", va="center", fontsize=8, color=INK)
        ax.text(r + 1.5, i - 0.19, f"{r:.0f}%", va="center", fontsize=8, color=INK)
    ax.set_yticks(list(y), names)
    ax.invert_yaxis()
    ax.set_xlim(0, 118)
    ax.set_xlabel("share of segments admitted (%)")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], frameon=False, fontsize=8,
              loc="lower left", bbox_to_anchor=(0.0, -0.42), ncol=2)
    _finish(ax, "Figure 2 — Admission policy determines usable output",
            "Provider self-reported confidence, not extraction quality, drives most exclusions.")
    fig.tight_layout()
    fig.savefig(OUT / "fig2_admission.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 3: joint yield collapse -----------------------------------------
# Source: two pilot runs, 2026-09-07.
def figure_joint_yield() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    batch, _, _ = load_batch()
    realised = 100 * batch["yield"]["joint_yield"]
    attempted = batch["yield"]["segments_attempted"]
    labels = [
        "3 generators incl. mistral\nreviewable admission\n(pilot, n=60)",
        "2 generators\njudgeable admission\n(pilot, n=60)",
        f"3 generators\njudgeable admission\n(realised, n={attempted})",
    ]
    values = [1.67, 63.64, realised]
    annotation = ["needs ~19,760 segments", "needs ~519 segments",
                  f"consumed {attempted} segments"]
    bars = ax.bar(labels, values, color=[RED, TEAL, BLUE], width=0.5, zorder=3)
    for bar, value, note in zip(bars, values, annotation, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 2.5,
                f"{value:.1f}%", ha="center", fontsize=10, fontweight="bold", color=INK)
        ax.text(bar.get_x() + bar.get_width() / 2, value + 8,
                note, ha="center", fontsize=8, color=MUTED)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_ylim(0, 92)
    ax.set_ylabel("joint yield (%)")
    ax.text(1.0, 85, "1,320 segments available in the sampling pool",
            fontsize=8, color=AMBER, ha="center")
    _finish(ax, "Figure 3 — Two configuration errors made the target unreachable",
            "Caught by a 60-segment pilot; the corrected configuration then hit the "
            "330-candidate target.")
    fig.tight_layout()
    fig.savefig(OUT / "fig3_joint_yield.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 4: pilot field accuracy (superseded) -----------------------------
# Source: annotations.json, n=31, single annotator. Retained only as motivation.
PILOT_FIELDS = [("behavior", 81), ("domain", 58), ("outcome", 55),
                ("modality", 45), ("prompt_level", 45)]


def figure_pilot_fields() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    names = [f[0] for f in PILOT_FIELDS]
    values = [f[1] for f in PILOT_FIELDS]
    colors = [RED if n == "outcome" else BLUE for n in names]
    bars = ax.bar(names, values, color=colors, width=0.55, zorder=3)
    for bar, value in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 1.5, f"{value}%",
                ha="center", fontsize=9, color=INK)
    ax.set_ylim(0, 100)
    ax.set_ylabel("judged correct (%)")
    ax.text(4.45, 88, "outcome: also the sole locus\nof unsupported values (6/31)",
            fontsize=8, color=RED, ha="right")
    _finish(ax, "Figure 4 — Pilot field accuracy (SUPERSEDED — not a baseline)",
            "n=31, single annotator, 28/31 from one child. Shape motivates the design; "
            "magnitudes do not survive.")
    fig.tight_layout()
    fig.savefig(OUT / "fig4_pilot_superseded.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 5: MARS control flow --------------------------------------------
def figure_pipeline() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.axis("off")
    steps = [
        ("N generators produce candidates", TEAL, "code"),
        ("admission + dedup (generator sets merged)", BLUE, "code"),
        ("K independent judges rank opaque aliases", AMBER, "model"),
        ("deterministic RRF fusion", BLUE, "code"),
        ("provisional winner", BLUE, "code"),
        ("agreement gate (top-choice support)", BLUE, "code"),
        ("integrity check (one whole candidate)", BLUE, "code"),
        ("control_confidence = min(generator, selection)", BLUE, "code"),
        ("existing Validation Engine (unchanged)", MUTED, "code"),
    ]
    for i, (label, color, kind) in enumerate(steps):
        y = len(steps) - i
        style = "round,pad=0.42" if kind == "code" else "round4,pad=0.42"
        ax.text(0.30, y, label, fontsize=9, va="center", ha="left", color="white",
                bbox=dict(boxstyle=style, facecolor=color, edgecolor="none"))
        if i < len(steps) - 1:
            ax.annotate("", xy=(0.27, y - 0.62), xytext=(0.27, y - 0.36),
                        arrowprops=dict(arrowstyle="-|>", color=MUTED, linewidth=1.1))
    ax.text(0.30, len(steps) + 0.9,
            "amber = model judgement (ordering only)    blue = deterministic code",
            fontsize=8, color=MUTED)
    for gate_y in (7, 4, 3):
        ax.annotate("", xy=(2.45, 5.6), xytext=(1.72, gate_y),
                    arrowprops=dict(arrowstyle="-|>", color=RED, linewidth=0.9,
                                    linestyle=(0, (3, 2)), alpha=0.65))
    ax.text(2.5, 7.0, "abstains with a typed reason_code:\n"
                       "  no_reviewable_candidate\n  insufficient_eligible_judges\n"
                       "  insufficient_valid_judge_responses\n  judge_disagreement\n"
                       "  integrity_failure",
            fontsize=8, color=MUTED, va="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f7fa", edgecolor=GRID))
    ax.set_xlim(0.2, 4.0)
    ax.set_ylim(0.2, len(steps) + 1.6)
    ax.set_title("Figure 5 — MARS control flow: models propose and rank, code decides",
                 loc="left", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig5_pipeline.png", bbox_inches="tight")
    plt.close(fig)


# --- Figures 6-8: read the realised batch, do not restate it ----------------
BATCH_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests/eval/extraction/results/annotation_batch.json"
)
FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]
FIELD_LABEL = {"prompt_level": "prompt\nlevel"}


def _norm(value: object) -> str | None:
    """Case- and whitespace-insensitive value key; empty string counts as null."""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def load_batch() -> tuple[dict, list[dict], list[str]]:
    if not BATCH_PATH.exists():
        raise SystemExit(
            f"{BATCH_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.build_annotation_batch` first."
        )
    batch = json.loads(BATCH_PATH.read_text())
    return batch, batch["candidates"], batch["models"]


def _field(candidate: dict, model: str, field: str) -> str | None:
    fields = candidate["candidates"][model].get("extracted_fields") or {}
    return _norm(fields.get(field))


def figure_status_vs_output() -> None:
    """Figure 6 -- the empirical case for the judgeable admission policy."""
    batch, candidates, models = load_batch()
    n = len(candidates)

    abstained, populated_abstentions, mean_conf = [], [], []
    for model in models:
        rows = [c["candidates"][model] for c in candidates]
        abst = [r for r in rows if r["status"] == "abstained"]
        with_values = [
            r for r in abst
            if any(_norm((r.get("extracted_fields") or {}).get(f)) for f in FIELDS)
        ]
        abstained.append(100 * len(abst) / n)
        populated_abstentions.append(100 * len(with_values) / n)
        mean_conf.append(sum(r.get("confidence") or 0.0 for r in rows) / n)

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    y = range(len(models))
    # The two bars are all but identical, which is the finding. Drawing the
    # outer one taller keeps it visible instead of hidden behind the inner.
    ax.barh(list(y), abstained, height=0.52, color=GRID, zorder=3,
            label="status = abstained")
    ax.barh(list(y), populated_abstentions, height=0.26, color=RED, zorder=4,
            label="abstained, yet \u22651 field populated")
    for i, (a, pa, mc) in enumerate(zip(abstained, populated_abstentions, mean_conf, strict=True)):
        ax.text(a + 1.5, i, f"{pa:.0f}% of {a:.0f}%", va="center", fontsize=8, color=INK)
        ax.text(1.5, i - 0.34, f"mean self-reported confidence {mc:.2f}",
                va="center", fontsize=7.5, color=MUTED)
    ax.set_yticks(list(y), [m.replace(":latest", "") for m in models])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of the 330 batch segments (%)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _finish(ax, "Figure 6 \u2014 Self-reported abstention does not mean the model withheld output",
            "Of every abstention across three generators, all but one carried extracted values.")
    fig.tight_layout()
    fig.savefig(OUT / "fig6_status_vs_output.png", bbox_inches="tight")
    plt.close(fig)


def figure_candidate_divergence() -> None:
    """Figure 7 -- generators disagree, so selection is a real decision."""
    _, candidates, models = load_batch()
    n = len(candidates)

    counts = {f: Counter() for f in FIELDS}
    for candidate in candidates:
        for field in FIELDS:
            values = {_field(candidate, m, field) for m in models}
            counts[field][len(values)] += 1

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    labels = [FIELD_LABEL.get(f, f) for f in FIELDS]
    one = [100 * counts[f][1] / n for f in FIELDS]
    two = [100 * counts[f][2] / n for f in FIELDS]
    three = [100 * counts[f][3] / n for f in FIELDS]
    ax.bar(labels, one, color=TEAL, zorder=3, width=0.55, label="1 distinct value (unanimous)")
    ax.bar(labels, two, bottom=one, color=AMBER, zorder=3, width=0.55, label="2 distinct values")
    ax.bar(labels, three, bottom=[a + b for a, b in zip(one, two, strict=True)], color=RED,
           zorder=3, width=0.55, label="3 distinct values")
    for i, value in enumerate(one):
        ax.text(i, value / 2, f"{value:.0f}%", ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_ylabel("share of segments (%)")
    ax.legend(frameon=False, fontsize=8, loc="lower left",
              bbox_to_anchor=(0.0, -0.40), ncol=3)
    _finish(ax, "Figure 7 \u2014 Three generators rarely converge on the same value",
            "behavior is free text, so its exact-match agreement is a floor, not a "
            "semantic measure.")
    fig.tight_layout()
    fig.savefig(OUT / "fig7_divergence.png", bbox_inches="tight")
    plt.close(fig)


def figure_coverage_headroom() -> None:
    """Figure 8 -- what a perfect selector could add in coverage (not accuracy)."""
    _, candidates, models = load_batch()
    n = len(candidates)

    best, union = [], []
    for field in FIELDS:
        per_model = [
            sum(1 for c in candidates if _field(c, m, field) is not None)
            for m in models
        ]
        best.append(100 * max(per_model) / n)
        union.append(
            100 * sum(1 for c in candidates
                      if any(_field(c, m, field) is not None for m in models)) / n
        )

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    labels = [FIELD_LABEL.get(f, f) for f in FIELDS]
    x = range(len(FIELDS))
    ax.bar([i - 0.19 for i in x], best, width=0.36, color=BLUE, zorder=3,
           label="best single generator")
    ax.bar([i + 0.19 for i in x], union, width=0.36, color=TEAL, zorder=3,
           label="\u22651 of 3 generators (coverage ceiling)")
    for i, (b, u) in enumerate(zip(best, union, strict=True)):
        gap = u - b
        ax.text(i + 0.19, u + 1.5, f"+{gap:.1f}", ha="center", fontsize=8,
                color=TEAL if gap >= 1 else MUTED)
    ax.set_xticks(list(x), labels)
    ax.set_ylim(0, 112)
    ax.set_ylabel("segments with the field populated (%)")
    ax.legend(frameon=False, fontsize=8, loc="lower left",
              bbox_to_anchor=(0.0, -0.34), ncol=2)
    _finish(ax, "Figure 8 \u2014 Coverage headroom available to a selector",
            "Populated, not correct. Whether the added values are right is what the "
            "annotation measures.")
    fig.tight_layout()
    fig.savefig(OUT / "fig8_coverage_headroom.png", bbox_inches="tight")
    plt.close(fig)


REPLAY_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests/eval/extraction/results/mars_branch_replay.json"
)


def figure_mars_branches() -> None:
    """Figure 9 -- what MARS is handed, and the one comparison labels are not needed for."""
    if not REPLAY_PATH.exists():
        raise SystemExit(
            f"{REPLAY_PATH} not found. Run "
            "`uv run python -m tests.eval.extraction.mars_branch_replay` first."
        )
    replay = json.loads(REPLAY_PATH.read_text())
    batch, candidates, models = load_batch()
    n = replay["n_segments"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.6, 3.2), width_ratios=[1.15, 1])

    # Panel A -- branch distribution.
    order = ["no_reviewable_candidate", "single_candidate", "rerank_required"]
    labels = ["no reviewable\ncandidate\nabstain",
              "single\ncandidate\nshort-circuit",
              "rerank\nrequired\nranked"]
    values = [100 * replay["branches"].get(b, 0) / n for b in order]
    bars = ax1.bar(labels, values, color=[RED, AMBER, TEAL], width=0.6, zorder=3)
    for bar, value, key in zip(bars, values, order, strict=True):
        ax1.text(bar.get_x() + bar.get_width() / 2, value + 1.6,
                 f"{value:.1f}%", ha="center", fontsize=9, fontweight="bold", color=INK)
        ax1.text(bar.get_x() + bar.get_width() / 2, value / 2,
                 f"n={replay['branches'].get(key, 0)}", ha="center", va="center",
                 fontsize=8, color="white")
    ax1.set_ylim(0, 62)
    ax1.set_ylabel("share of 330 segments (%)")
    ax1.tick_params(axis="x", labelsize=7.5, pad=1)
    ax1.margins(x=0.06)
    _finish(ax1, "A \u2014 MARS candidate stage",
            "Every short-circuit is a lone admitted generator, never consensus.")

    # Panel B -- coverage: MARS ceiling against each single generator.
    def admitted(model: str) -> int:
        return sum(
            1 for c in candidates
            if c["candidates"][model]["status"] in ("success", "partial")
        )

    per_model = sorted(((admitted(m), m) for m in models), reverse=True)
    ceiling = 100 * sum(
        1 for c in candidates
        if any(c["candidates"][m]["status"] in ("success", "partial") for m in models)
    ) / n
    names = ["MARS ceiling\n(\u22651 generator)"] + [
        m.replace(":latest", "") for _, m in per_model
    ]
    shares = [ceiling] + [100 * count / n for count, _ in per_model]
    colors = [TEAL] + [BLUE] * len(per_model)
    bars = ax2.barh(range(len(names)), shares, color=colors, height=0.55, zorder=3)
    for i, value in enumerate(shares):
        ax2.text(value + 1.5, i, f"{value:.1f}%", va="center", fontsize=8.5, color=INK)
    ax2.set_yticks(range(len(names)), names, fontsize=8)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 122)
    ax2.set_xlabel("segments with a reviewable record (%)")
    gap = ceiling - shares[1]
    ax2.annotate("", xy=(ceiling, 0.5), xytext=(shares[1], 0.5),
                 arrowprops=dict(arrowstyle="<|-|>", color=TEAL, linewidth=0.9))
    ax2.text(ceiling + 2.5, 0.5, f"+{gap:.1f} pts", fontsize=8, color=TEAL,
             va="center")
    _finish(ax2, "B \u2014 Coverage, not accuracy",
            "Coverage available to selection; correctness unmeasured.")

    fig.suptitle(
        "Figure 9 \u2014 MARS against single generators on the axis that needs no labels",
        x=0.0, ha="left", fontsize=11, fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / "fig9_mars_branches.png", bbox_inches="tight")
    plt.close(fig)


def print_tables() -> None:
    """Emit the manuscript tables so text and figures share one source."""
    batch, candidates, models = load_batch()
    n = len(candidates)
    print("\nTable 2 -- per-generator admission and field population (n=330)")
    header = f"{'generator':<18}{'succ':>5}{'part':>5}{'abst':>5}{'conf':>6}  " + "".join(
        f"{f[:5]:>7}" for f in FIELDS
    )
    print(header)
    for model in models:
        rows = [c["candidates"][model] for c in candidates]
        status = Counter(r["status"] for r in rows)
        conf = sum(r.get("confidence") or 0.0 for r in rows) / n
        fills = [
            100 * sum(1 for c in candidates if _field(c, model, f) is not None) / n
            for f in FIELDS
        ]
        print(f"{model:<18}{status['success']:>5}{status['partial']:>5}"
              f"{status['abstained']:>5}{conf:>6.2f}  "
              + "".join(f"{v:>6.1f}%" for v in fills))

    print("\nTable 3 -- pairwise exact-match agreement, both generators populated")
    print(f"{'pair':<30}" + "".join(f"{f[:9]:>12}" for f in FIELDS))
    for a, b in itertools.combinations(models, 2):
        cells = []
        for field in FIELDS:
            both = [
                (_field(c, a, field), _field(c, b, field))
                for c in candidates
                if _field(c, a, field) is not None and _field(c, b, field) is not None
            ]
            cells.append(
                f"{100 * sum(x == y for x, y in both) / len(both):>7.0f}% n={len(both)}"
                if both else f"{'n/a':>12}"
            )
        pair = f"{a.replace(':latest', '')}/{b.replace(':latest', '')}"
        print(f"{pair:<30}" + "".join(f"{c:>12}" for c in cells))


# --- Figures 10-12: reliability, read from the recorded artefacts ------------
RESULTS = Path(__file__).resolve().parents[2] / "tests/eval/extraction/results"
RELIABILITY_PATH = RESULTS / "reliability_round1.json"
SELECTION_PATH = RESULTS / "reissue_round2_selection.json"
GOLD_ROUND1 = {
    "A": RESULTS / "gold_annotator_a_round1.json",
    "B": RESULTS / "gold_annotator_b_round1.json",
}
CATEGORICAL = ["domain", "modality", "prompt_level", "outcome"]


def _load(path: Path, what: str) -> dict | None:
    if not path.exists():
        print(f"  (skipped: {what} -- {path.name} not found)")
        return None
    return json.loads(path.read_text())


def _boundary_pairs(selection: dict) -> dict[str, set[frozenset]]:
    """Observed codebook-boundary value pairs, per field, from the selection."""
    pairs: dict[str, set[frozenset]] = {}
    for conflicts in selection["selected"].values():
        for conflict in conflicts:
            left, right = [v.strip() for v in conflict["values"].split("/")]
            pairs.setdefault(conflict["field"], set()).add(frozenset({left, right}))
    return pairs


def figure_reliability() -> None:
    """Figure 10 -- per-field kappa against the ceiling its marginals allow."""
    report = _load(RELIABILITY_PATH, "Figure 10 (reliability)")
    if report is None:
        return

    fields = [f for f in CATEGORICAL if f in report["fields"]]
    stats = [report["fields"][f] for f in fields]
    kappas = [s["kappa"] for s in stats]
    ceilings = [s["kappa_max"] for s in stats]
    lower = [k - s["bootstrap_ci"]["lower"] for k, s in zip(kappas, stats)]
    upper = [s["bootstrap_ci"]["upper"] - k for k, s in zip(kappas, stats)]

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    y = range(len(fields))
    # The ceiling is drawn as the full bar and kappa as the filled portion, so
    # the unreachable part of the scale is visible rather than implied.
    ax.barh(list(y), ceilings, color=GRID, zorder=2, height=0.54)
    ax.barh(list(y), kappas, color=BLUE, zorder=3, height=0.54)
    ax.errorbar(
        kappas, list(y), xerr=[lower, upper], fmt="none",
        ecolor=INK, elinewidth=1.1, capsize=3.5, zorder=4,
    )
    for i, (k, c) in enumerate(zip(kappas, ceilings)):
        ax.text(c + 0.012, i, f"$\\kappa_{{max}}$ {c:.2f}", va="center",
                fontsize=7.5, color=MUTED)
        ax.text(0.012, i, f"{k:.2f}  ({100 * k / c:.0f}% of ceiling)", va="center",
                fontsize=7.5, color="white", fontweight="bold", zorder=5)

    ax.set_yticks(list(y))
    ax.set_yticklabels([FIELD_LABEL.get(f, f).replace("\n", " ") for f in fields])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Cohen's $\\kappa$ (bars: point estimate; whiskers: 95% bootstrap CI)")
    _finish(
        ax,
        "Figure 10 — Round-1 reliability against the ceiling the marginals allow",
        f"n = {report['n_segments']} segments, {report['n_bootstrap']:,} bootstrap "
        f"replicates. Grey = $\\kappa_{{max}}$, the ceiling set by the marginals.",
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig10_reliability_round1.png", bbox_inches="tight")
    plt.close(fig)


def figure_confusion() -> None:
    """Figure 11 -- where the two annotators diverged, field by field."""
    gold = {k: _load(p, "Figure 11 (confusion)") for k, p in GOLD_ROUND1.items()}
    if any(v is None for v in gold.values()):
        return
    selection = _load(SELECTION_PATH, "Figure 11 (confusion)")
    if selection is None:
        return
    boundaries = _boundary_pairs(selection)

    shown = ["modality", "prompt_level", "outcome"]
    segments = sorted(set(gold["A"]) & set(gold["B"]))
    fig, axes = plt.subplots(1, len(shown), figsize=(12.6, 4.1))

    for ax, field in zip(axes, shown):
        observed = [
            (
                gold["A"][s]["field_values"].get(field) or "none",
                gold["B"][s]["field_values"].get(field) or "none",
            )
            for s in segments
        ]
        categories = sorted({v for pair in observed for v in pair})
        index = {c: i for i, c in enumerate(categories)}
        grid = [[0] * len(categories) for _ in categories]
        for a, b in observed:
            grid[index[a]][index[b]] += 1

        peak = max(max(row) for row in grid) or 1
        ax.imshow(grid, cmap="Blues", vmin=0, vmax=peak, aspect="auto", zorder=2)
        for i, row in enumerate(grid):
            for j, count in enumerate(row):
                if not count:
                    continue
                on_boundary = (
                    i != j
                    and frozenset({categories[i], categories[j]}) in boundaries.get(field, set())
                )
                ax.text(
                    j, i, str(count), ha="center", va="center", fontsize=7.5,
                    color="white" if count > peak * 0.55 else INK,
                    fontweight="bold" if on_boundary else "normal", zorder=3,
                )
                if on_boundary:
                    ax.add_patch(
                        plt.Rectangle(
                            (j - 0.5, i - 0.5), 1, 1, fill=False,
                            edgecolor=AMBER, linewidth=1.6, zorder=4,
                        )
                    )

        ax.set_xticks(range(len(categories)))
        ax.set_yticks(range(len(categories)))
        ax.set_xticklabels(categories, rotation=45, ha="right", fontsize=7)
        ax.set_yticklabels(categories, fontsize=7)
        ax.set_xlabel("annotator B", fontsize=8)
        if field == shown[0]:
            ax.set_ylabel("annotator A", fontsize=8)
        ax.set_title(field, loc="left", fontsize=10, fontweight="bold")
        ax.grid(False)

    fig.suptitle(
        "Figure 11 — Round-1 annotator confusion; amber cells are conflicts the codebook resolves",
        x=0.012, ha="left", fontsize=11, fontweight="bold", y=1.04,
    )
    fig.tight_layout(w_pad=2.4)
    fig.savefig(OUT / "fig11_confusion_round1.png", bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)


def figure_conflict_decomposition() -> None:
    """Figure 12 -- how each field's conflicts split by cause."""
    selection = _load(SELECTION_PATH, "Figure 12 (conflict decomposition)")
    if selection is None:
        return

    total = selection["n_shared"]
    on = Counter()
    for conflicts in selection["selected"].values():
        for conflict in conflicts:
            on[conflict["field"]] += 1
    off = Counter(c["field"] for c in selection["off_boundary"])

    fields = CATEGORICAL
    agreed = [total - on[f] - off[f] for f in fields]

    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    y = list(range(len(fields)))
    ax.barh(y, agreed, color=GRID, zorder=3, height=0.56, label="agreed")
    ax.barh(y, [on[f] for f in fields], left=agreed, color=AMBER, zorder=3,
            height=0.56, label="conflict on a codebook boundary (re-issued)")
    ax.barh(y, [off[f] for f in fields],
            left=[a + on[f] for a, f in zip(agreed, fields)], color=RED, zorder=3,
            height=0.56, label="conflict the codebook does not resolve (adjudicated)")

    # A count centred in a bar narrower than this overflows it and lands on a
    # neighbouring segment, where it reads as that segment's count.
    legible = total * 0.04
    for i, field in enumerate(fields):
        if on[field] >= legible:
            ax.text(agreed[i] + on[field] / 2, i, str(on[field]), ha="center",
                    va="center", fontsize=7.5, color=INK, fontweight="bold", zorder=4)
        if off[field] >= legible:
            ax.text(agreed[i] + on[field] + off[field] / 2, i, str(off[field]),
                    ha="center", va="center", fontsize=7.5, color="white",
                    fontweight="bold", zorder=4)

    ax.set_yticks(y)
    ax.set_yticklabels([FIELD_LABEL.get(f, f).replace("\n", " ") for f in fields])
    ax.invert_yaxis()
    ax.set_xlim(0, total)
    ax.set_xlabel(f"segments (n = {total})")
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3,
        fontsize=7.5, frameon=False, columnspacing=1.4, handlelength=1.4,
    )
    _finish(
        ax,
        "Figure 12 — Round-1 conflicts by cause",
        f"{selection['n_on_boundary']} of "
        f"{selection['n_on_boundary'] + selection['n_off_boundary']} field conflicts "
        f"fall on one of three stated definitional boundaries; "
        f"{selection['n_selected']} segments were re-issued.",
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig12_conflict_decomposition.png", bbox_inches="tight")
    plt.close(fig)


def figure_round_comparison() -> None:
    """Figure 13 -- the codebook's effect, against the untreated control field."""
    report = _load(
        RESULTS / "round_comparison.json", "Figure 13 (round comparison)"
    )
    if report is None:
        return

    # Treated fields first, control last and visually separated: the whole
    # point of the figure is the contrast between the two arms.
    entries = sorted(
        report["fields"].items(), key=lambda kv: (kv[1]["arm"] != "treated", kv[0])
    )
    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(10.4, 3.8), gridspec_kw={"width_ratios": [1.55, 1]}
    )

    for i, (field, entry) in enumerate(entries):
        delta = entry["delta"]
        if delta is None:
            continue
        treated = entry["arm"] == "treated"
        colour = BLUE if treated else MUTED
        before, after = delta["kappa_before"], delta["kappa_after"]
        ax.plot([before, after], [i, i], color=colour, linewidth=2.4, zorder=3,
                solid_capstyle="round")
        ax.scatter([before], [i], s=44, color="white", edgecolor=colour,
                   linewidth=1.8, zorder=4)
        ax.scatter([after], [i], s=54, color=colour, zorder=5)
        ax.text(max(before, after) + 0.022, i, f"{delta['delta']:+.3f}",
                va="center", fontsize=8,
                color=INK if treated else MUTED,
                fontweight="bold" if treated else "normal")

    labels = [
        FIELD_LABEL.get(f, f).replace("\n", " ") + ("" if e["arm"] == "treated" else "  (control)")
        for f, e in entries
    ]
    ax.set_yticks(range(len(entries)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Cohen's $\\kappa$   (hollow = round 1, filled = round 2)")
    _finish(
        ax,
        "Figure 13 — Reliability before and after the codebook",
        f"n = {report['n_segments']} re-issued segments, same annotators.",
    )

    # Right panel: the paired interval on each change, which is the estimand.
    for i, (field, entry) in enumerate(entries):
        delta = entry["delta"]
        if delta is None:
            continue
        treated = entry["arm"] == "treated"
        colour = BLUE if treated else MUTED
        ax2.plot([delta["lower"], delta["upper"]], [i, i], color=colour,
                 linewidth=2.2, zorder=3, solid_capstyle="round")
        ax2.scatter([delta["delta"]], [i], s=54, color=colour, zorder=4)
    ax2.axvline(0, color=RED, linewidth=1.1, linestyle="--", zorder=2)
    ax2.set_yticks(range(len(entries)))
    ax2.set_yticklabels([])
    ax2.invert_yaxis()
    ax2.set_xlabel("change in $\\kappa$ (95% paired bootstrap CI)")
    _finish(ax2, "", None)
    ax2.set_title("change, with interval", loc="left", fontsize=9, color=MUTED)

    fig.tight_layout(w_pad=1.6)
    fig.savefig(OUT / "fig13_round_comparison.png", bbox_inches="tight")
    plt.close(fig)


def figure_protocol() -> None:
    """Figure 14 -- the two-round annotation protocol, with realised counts.

    A CONSORT-style accounting: every segment that enters is accounted for
    where it leaves. Counts are read from the artefacts, never restated.
    """
    selection = _load(SELECTION_PATH, "Figure 14 (protocol)")
    comparison = _load(RESULTS / "round_comparison.json", "Figure 14 (protocol)")
    gold1 = {k: _load(p, "Figure 14 (protocol)") for k, p in GOLD_ROUND1.items()}
    if selection is None or comparison is None or any(v is None for v in gold1.values()):
        return
    merged = {
        k: _load(RESULTS / f"gold_annotator_{k}.json", "Figure 14 (protocol)")
        for k in ("a", "b")
    }
    if any(v is None for v in merged.values()):
        return

    segments = sorted(set(gold1["A"]) & set(gold1["B"]))
    cats = ["domain", "modality", "prompt_level", "outcome"]

    def conflicts(first, second):
        total = sum(
            1
            for s in segments
            for f in cats
            if (first[s]["field_values"].get(f) or "none")
            != (second[s]["field_values"].get(f) or "none")
        )
        segs = sum(
            1
            for s in segments
            if any(
                (first[s]["field_values"].get(f) or "none")
                != (second[s]["field_values"].get(f) or "none")
                for f in cats
            )
        )
        return total, segs

    r1_conf, r1_segs = conflicts(gold1["A"], gold1["B"])
    merged_conf, merged_segs = conflicts(merged["a"], merged["b"])
    n = len(segments)
    reissued = selection["n_selected"]
    carried = n - reissued

    fig, ax = plt.subplots(figsize=(8.6, 7.4))
    ax.axis("off")

    def box(x, y, w, h, text, face, edge=None, text_colour="white", size=8.4):
        ax.add_patch(plt.Rectangle(
            (x, y), w, h, facecolor=face,
            edgecolor=edge or face, linewidth=1.3, zorder=3,
            joinstyle="round",
        ))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=size, color=text_colour, zorder=4, linespacing=1.5)

    def arrow(x1, y1, x2, y2, colour=MUTED, style="-|>", dashed=False):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), zorder=2,
                    arrowprops=dict(
                        arrowstyle=style, color=colour, linewidth=1.2,
                        linestyle=(0, (3, 2)) if dashed else "solid",
                    ))

    box(2.4, 9.3, 5.2, 0.78,
        f"frozen annotation batch\n{n} segments, 11 children, 3 generators",
        INK)
    arrow(5.0, 9.3, 5.0, 8.86)

    box(2.4, 8.05, 5.2, 0.78,
        f"ROUND 1 — both annotators, blind, all {n} segments\n"
        f"mean $\\kappa$ 0.610",
        BLUE)
    arrow(5.0, 8.05, 5.0, 7.61)

    box(2.4, 6.8, 5.2, 0.78,
        f"{r1_conf} categorical conflicts on {r1_segs} segments\n"
        "classified against the codebook boundary table",
        MUTED)
    arrow(3.6, 6.8, 2.6, 6.28)
    arrow(6.4, 6.8, 7.4, 6.28)

    box(0.35, 5.5, 4.4, 0.78,
        f"{selection['n_on_boundary']} conflicts on a stated boundary\n"
        f"→ {reissued} segments re-issued",
        AMBER)
    box(5.55, 5.5, 4.1, 0.78,
        f"{selection['n_off_boundary']} conflicts the codebook\n"
        "does not resolve → adjudication",
        RED)

    arrow(2.55, 5.5, 2.55, 5.06)
    box(0.35, 4.28, 4.4, 0.78,
        f"ROUND 2 — same annotators, blind,\nfresh order, all 5 fields re-annotated",
        BLUE)
    arrow(2.55, 4.28, 2.55, 3.84)

    box(0.35, 3.06, 4.4, 0.78,
        "treated fields $\\Delta\\kappa$ +0.29 to +0.48\n"
        "control (domain) $\\Delta\\kappa$ −0.041, n.s.",
        TEAL)

    box(5.55, 4.28, 4.1, 0.78,
        f"{carried} segments never in\nboundary conflict — round-1 values kept",
        MUTED)

    arrow(2.55, 3.06, 2.55, 2.5)
    # The carried-forward segments elbow into the merge; only the final descent
    # takes a head, or the corner reads as an arrow pointing into empty space.
    arrow(7.6, 4.28, 7.6, 2.72, style="-")
    arrow(7.6, 2.72, 5.3, 2.72, style="-")
    arrow(5.3, 2.72, 5.3, 2.5)

    box(2.4, 1.72, 5.2, 0.78,
        f"MERGED GOLD — {n} segments\nmean $\\kappa$ 0.801",
        INK)
    arrow(5.0, 1.72, 5.0, 1.28)

    box(2.4, 0.5, 5.2, 0.78,
        f"{merged_conf} residual conflicts on {merged_segs} segments\n"
        "→ adjudication (not yet performed)",
        RED)

    # The boundary-silent conflicts are never re-annotated; they arrive at
    # adjudication directly, and the dashed path says so rather than leaving
    # that box to dead-end.
    arrow(9.65, 5.89, 9.9, 5.89, colour=RED, style="-", dashed=True)
    arrow(9.9, 5.89, 9.9, 0.89, colour=RED, style="-", dashed=True)
    arrow(9.9, 0.89, 7.6, 0.89, colour=RED, dashed=True)

    ax.text(0.35, 10.35,
            "blue = annotation pass    amber = codebook-selected    "
            "red = to adjudication    teal = measured effect",
            fontsize=8, color=MUTED)

    ax.set_xlim(0.1, 10.25)
    ax.set_ylim(0.2, 10.75)
    ax.set_title(
        "Figure 14 — Two-round annotation protocol, with realised counts",
        loc="left", fontsize=11, fontweight="bold", pad=16,
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig14_protocol.png", bbox_inches="tight")
    plt.close(fig)


# The three rules as stated in docs/annotation_codebook.md. Kept here as the
# figure's only content so the diagram and the codebook are edited together.
CODEBOOK_RULES = [
    (
        "1.  modality",
        "Was the act addressed to a partner?",
        [
            ("point, show, give, reach-to-request, nod", "gestural"),
            ("the same, plus speech carrying the message", "multimodal"),
            ("object handling, self-directed movement", "none"),
            ("communicated, but channel not shown", "unknown"),
        ],
        "Handling an object is the behavior, not a modality.",
    ),
    (
        "2.  outcome",
        "Is there an identifiable target?",
        [
            ("no target — free talk, play narration", "none"),
            ("target, child responded, judgeable", "correct / partial /\nincorrect / approximation"),
            ("target, child did not respond", "no_response"),
            ("target, resolution not visible", "unknown"),
        ],
        "Absent acknowledgement is unknown, never incorrect.",
    ),
    (
        "3.  prompt_level",
        "Was support added after the opportunity?",
        [
            ("child initiated, or right on first ask", "independent"),
            ("adult gestures only", "gestural"),
            ("repeat, hint, rephrase, 'what do you say?'", "verbal"),
            ("adult supplies the target words", "model"),
            ("guided movement", "partial_physical /\nfull_physical"),
        ],
        "Several prompts: record the most supportive.",
    ),
]

PROMPT_HIERARCHY = [
    "independent", "gestural", "verbal", "model", "partial_physical", "full_physical",
]


def figure_codebook_rules() -> None:
    """Figure 15 -- the three codebook rules as decision tests."""
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.5))

    for ax, (title, test, rows, footnote) in zip(axes, CODEBOOK_RULES):
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        ax.text(0, 0.98, title, fontsize=10.5, fontweight="bold", color=INK,
                va="top")
        ax.text(0.5, 0.855, test, fontsize=8.8, ha="center", va="center",
                color="white", linespacing=1.4,
                bbox=dict(boxstyle="round,pad=0.5", facecolor=AMBER,
                          edgecolor="none"))

        top = 0.70
        step = top / len(rows)
        for i, (condition, value) in enumerate(rows):
            y = top - i * step - step / 2 + 0.03
            # Wrapped to a fixed column: unwrapped, the longer conditions run
            # under the arrow and collide with the value they point at.
            ax.text(0.0, y, textwrap.fill(condition, 30), fontsize=7.4,
                    va="center", color=INK, linespacing=1.35)
            ax.annotate("", xy=(0.625, y), xytext=(0.545, y),
                        arrowprops=dict(arrowstyle="-|>", color=MUTED,
                                        linewidth=0.9))
            ax.text(0.655, y, value, fontsize=7.6, va="center", color=BLUE,
                    fontweight="bold", linespacing=1.3)

        ax.text(0, 0.015, footnote, fontsize=7.4, color=MUTED, style="italic",
                va="bottom")

    fig.tight_layout(w_pad=3.4)

    # The ordering the third rule depends on, drawn once beneath all panels.
    # Added after layout: an axes placed in figure coordinates is not something
    # tight_layout can reason about, and it warns if asked to.
    bar = fig.add_axes([0.085, -0.10, 0.83, 0.075])
    bar.axis("off")
    bar.set_xlim(0, len(PROMPT_HIERARCHY))
    bar.set_ylim(0, 1)
    for i, level in enumerate(PROMPT_HIERARCHY):
        shade = 0.22 + 0.72 * i / (len(PROMPT_HIERARCHY) - 1)
        bar.add_patch(plt.Rectangle((i + 0.04, 0.12), 0.92, 0.7,
                                    facecolor=plt.cm.Blues(shade),
                                    edgecolor="none"))
        bar.text(i + 0.5, 0.47, level, ha="center", va="center", fontsize=7.4,
                 color="white" if shade > 0.55 else INK, fontweight="bold")
    bar.text(0, 0.95, "prompt hierarchy, least to most supportive", fontsize=7.6,
             color=MUTED, va="bottom")

    fig.suptitle(
        "Figure 15 — The three codebook rules, as the tests an annotator applies",
        x=0.012, ha="left", fontsize=11, fontweight="bold", y=1.03,
    )
    fig.savefig(OUT / "fig15_codebook_rules.png", bbox_inches="tight",
                pad_inches=0.35)
    plt.close(fig)


# --- Figures 16-19: extraction results against the adjudicated gold ---------
SCORED_PATH = RESULTS / "scored_against_gold.json"
GOLD_LABELS_PATH = RESULTS / "gold_labels.json"

ACCEPTABLE = {"correct", "correctly_null"}
GEN_COLOURS = {0: BLUE, 1: TEAL, 2: AMBER}


def _short(model: str) -> str:
    return model.replace(":latest", "")


def figure_field_accuracy() -> None:
    """Figure 16 -- per-field accuracy of each generator against gold."""
    scored = _load(SCORED_PATH, "Figure 16 (field accuracy)")
    if scored is None:
        return

    fields = scored["scoring_fields"]
    models = scored["models"]
    counts = scored["per_field_counts"]

    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    width = 0.26
    for m, model in enumerate(models):
        values = []
        for field in fields:
            acceptable = sum(
                counts[model].get(f"{field}:{j}", 0) for j in ACCEPTABLE
            )
            total = sum(
                v for k, v in counts[model].items() if k.startswith(f"{field}:")
            )
            values.append(100 * acceptable / total if total else 0.0)
        offsets = [i + (m - 1) * width for i in range(len(fields))]
        ax.bar(offsets, values, width=width * 0.92, color=GEN_COLOURS[m],
               zorder=3, label=_short(model))
        for x, v in zip(offsets, values):
            ax.text(x, v + 1.2, f"{v:.0f}", ha="center", fontsize=7, color=MUTED)

    ax.set_xticks(range(len(fields)))
    ax.set_xticklabels([FIELD_LABEL.get(f, f).replace("\n", " ") for f in fields])
    ax.set_ylim(0, 100)
    ax.set_ylabel("acceptable (%)")
    ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="upper right")
    _finish(
        ax,
        "Figure 16 — Per-field extraction accuracy against the adjudicated gold",
        f"n = {scored['n_segments_scored']} segments. Acceptable = correct or "
        "correctly null. `behavior` excluded (see Figure 19).",
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig16_field_accuracy.png", bbox_inches="tight")
    plt.close(fig)


def figure_unsupported() -> None:
    """Figure 17 -- values asserted where the transcript supports none."""
    scored = _load(SCORED_PATH, "Figure 17 (unsupported extractions)")
    if scored is None:
        return

    models = scored["models"]
    counts = scored["per_field_counts"]

    # A rate needs a denominator. The gold records only 3 null `domain` values
    # and 2 null `prompt_level` values across 330 segments, so "100%
    # unsupported" on those fields is three segments and two segments -- a
    # number that reads as a finding and cannot carry one. Fields below the
    # floor are named in the subtitle with their raw counts instead.
    MIN_NULL_GOLD = 20
    opportunities_by_field = {
        field: max(
            counts[model].get(f"{field}:hallucinated", 0)
            + counts[model].get(f"{field}:correctly_null", 0)
            for model in models
        )
        for field in scored["scoring_fields"]
    }
    fields = [
        f for f in scored["scoring_fields"]
        if opportunities_by_field[f] >= MIN_NULL_GOLD
    ]
    omitted = [
        f"{f} (n={opportunities_by_field[f]})"
        for f in scored["scoring_fields"]
        if opportunities_by_field[f] < MIN_NULL_GOLD
    ]

    fig, ax = plt.subplots(figsize=(5.0, 3.6))
    width = 0.26
    for m, model in enumerate(models):
        values, labels = [], []
        for field in fields:
            hallucinated = counts[model].get(f"{field}:hallucinated", 0)
            correct_null = counts[model].get(f"{field}:correctly_null", 0)
            opportunities = hallucinated + correct_null
            values.append(
                100 * hallucinated / opportunities if opportunities else 0.0
            )
            labels.append(f"{hallucinated}/{opportunities}" if opportunities else "")
        offsets = [i + (m - 1) * width for i in range(len(fields))]
        ax.bar(offsets, values, width=width * 0.92, color=GEN_COLOURS[m],
               zorder=3, label=_short(model))
        for x, v, lab in zip(offsets, values, labels):
            if lab:
                ax.text(x, v + 1.5, lab, ha="center", fontsize=6.4, color=MUTED)

    ax.set_xticks(range(len(fields)))
    ax.set_xticklabels([FIELD_LABEL.get(f, f).replace("\n", " ") for f in fields])
    ax.set_ylim(0, 108)
    ax.set_xlim(-0.6, len(fields) - 0.4)
    ax.set_ylabel("unsupported extractions (%)")
    ax.legend(
        fontsize=7.5, frameon=False, ncol=3,
        loc="upper center", bbox_to_anchor=(0.5, -0.13),
    )
    subtitle = (
        "Denominator: segments gold records as null for that field; "
        "counts above each bar."
    )
    if omitted:
        subtitle += (
            f"\nToo few null-gold segments to rate, not shown: {', '.join(omitted)}."
        )
    _finish(
        ax,
        "Figure 17 — Values asserted where the transcript supports none",
        subtitle,
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig17_unsupported.png", bbox_inches="tight")
    plt.close(fig)


def figure_record_ceiling() -> None:
    """Figure 18 -- whole-record accuracy against the oracle ceiling."""
    scored = _load(SCORED_PATH, "Figure 18 (record accuracy)")
    if scored is None:
        return
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.eval.extraction.mars_evaluation import (  # noqa: E402
        oracle_ceiling,
        per_model_accuracy,
    )

    fields = scored["scoring_fields"]
    models = scored["models"]
    accuracy = per_model_accuracy(scored["gold"], models, fields)
    ceiling = oracle_ceiling(scored["gold"], models, fields)

    ordered = sorted(models, key=lambda m: accuracy[m] or 0.0)
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    y = range(len(ordered))
    ax.barh(list(y), [100 * (accuracy[m] or 0.0) for m in ordered],
            color=BLUE, height=0.5, zorder=3)
    for i, model in enumerate(ordered):
        ax.text(100 * (accuracy[model] or 0.0) + 0.15, i,
                f"{100 * (accuracy[model] or 0.0):.1f}%", va="center",
                fontsize=8, color=INK)
    ax.axvline(100 * ceiling, color=RED, linewidth=1.4, linestyle="--", zorder=4)
    ax.text(100 * ceiling + 0.15, -0.72,
            f"oracle ceiling {100 * ceiling:.1f}%", fontsize=8, color=RED)

    ax.set_yticks(list(y))
    ax.set_yticklabels([_short(m) for m in ordered])
    ax.set_xlim(0, max(100 * ceiling * 1.55, 8))
    ax.set_xlabel("whole-record accuracy (%) — all four categorical fields correct")
    _finish(
        ax,
        "Figure 18 — Whole-record accuracy and the ceiling available to selection",
        f"n = {scored['n_segments_scored']}. The ceiling is the best candidate "
        "per segment: what a perfect selector could reach.",
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig18_record_ceiling.png", bbox_inches="tight")
    plt.close(fig)


def figure_behavior_overlap() -> None:
    """Figure 19 -- free-text behavior against the human-human reference band."""
    scored = _load(SCORED_PATH, "Figure 19 (behavior overlap)")
    gold_labels = _load(GOLD_LABELS_PATH, "Figure 19 (behavior overlap)")
    batch = _load(BATCH_PATH, "Figure 19 (behavior overlap)")
    if scored is None or gold_labels is None or batch is None:
        return
    annotators = {
        k: _load(RESULTS / f"gold_annotator_{k}.json", "Figure 19")
        for k in ("a", "b")
    }
    if any(v is None for v in annotators.values()):
        return

    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.eval.extraction.agreement_report import (  # noqa: E402
        normalize,
        token_overlap,
    )

    gold = gold_labels["gold"]
    entries = {e["segment_id"]: e for e in batch["candidates"]}
    ids = [s for s in gold if s in entries]

    series = [(
        "human vs human",
        [
            token_overlap(
                normalize(annotators["a"][s]["field_values"]["behavior"]),
                normalize(annotators["b"][s]["field_values"]["behavior"]),
            )
            for s in ids
            if s in annotators["a"] and s in annotators["b"]
        ],
        MUTED,
    )]
    for m, model in enumerate(scored["models"]):
        values = []
        for s in ids:
            got = (entries[s]["candidates"][model].get("extracted_fields") or {}).get(
                "behavior"
            )
            if got:
                values.append(
                    token_overlap(
                        normalize(got), normalize(gold[s]["field_values"]["behavior"])
                    )
                )
        series.append((_short(model), values, GEN_COLOURS[m]))

    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    positions = list(range(len(series)))
    parts = ax.violinplot(
        [s[1] for s in series], positions=positions, widths=0.78,
        showextrema=False, showmedians=True,
    )
    for body, (_, _, colour) in zip(parts["bodies"], series):
        body.set_facecolor(colour)
        body.set_alpha(0.55)
        body.set_edgecolor("none")
    parts["cmedians"].set_color(INK)
    parts["cmedians"].set_linewidth(1.3)

    for i, (_, values, _) in enumerate(series):
        median = sorted(values)[len(values) // 2]
        ax.text(i, median + 0.035, f"{median:.2f}", ha="center", fontsize=7.6,
                color=INK, fontweight="bold")

    ax.set_xticks(positions)
    ax.set_xticklabels([s[0] for s in series], fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_ylabel("token overlap with the reference description")
    _finish(
        ax,
        "Figure 19 — Free-text `behavior`: models against the human reference band",
        "Human vs human is the two annotators on the same segment — the most "
        "agreement wording alone permits. Medians labelled.",
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig19_behavior_overlap.png", bbox_inches="tight")
    plt.close(fig)


def figure_mars_outcomes() -> None:
    """Figure 20 -- what MARS returned, and how it compared."""
    evaluation = _load(RESULTS / "mars_evaluation.json", "Figure 20 (MARS)")
    scored = _load(SCORED_PATH, "Figure 20 (MARS)")
    if evaluation is None or scored is None:
        return

    mars = evaluation["mars"]
    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(10.6, 3.5), gridspec_kw={"width_ratios": [1.25, 1]}
    )

    # Left: outcome profile.
    reasons = mars["abstention_reasons"]
    segments = [("record returned", mars["n_returned"], TEAL)]
    segments += [
        (r.replace("_", " "), n, RED if r == "judge_disagreement" else MUTED)
        for r, n in sorted(reasons.items(), key=lambda kv: -kv[1])
    ]
    left = 0
    for label, n, colour in segments:
        ax.barh([0], [n], left=left, color=colour, height=0.5, zorder=3,
                label=f"{label} ({n})")
        if n / mars["n_total"] > 0.05:
            ax.text(left + n / 2, 0, str(n), ha="center", va="center",
                    fontsize=8, color="white", fontweight="bold", zorder=4)
        left += n
    ax.set_yticks([])
    ax.set_xlim(0, mars["n_total"])
    ax.set_xlabel(f"segments (n = {mars['n_total']})")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2,
              fontsize=7.4, frameon=False)
    _finish(ax, "Figure 20 — MARS outcomes and comparison",
            f"coverage {mars['coverage']:.1%}")

    # Right: accuracy, with the ceiling.
    best = evaluation["best_generator_accuracy"]
    ceiling = evaluation["oracle_ceiling"]
    bars = [
        ("MARS\n(over returned)", mars["accuracy_over_returned"], BLUE),
        ("MARS\n(over all)", mars["accuracy_over_all"], BLUE),
        (f"{evaluation['best_generator'].replace(':latest', '')}\n(over all)",
         best, TEAL),
    ]
    ax2.bar(range(len(bars)), [100 * b[1] for b in bars],
            color=[b[2] for b in bars], width=0.56, zorder=3)
    for i, (_, value, _) in enumerate(bars):
        ax2.text(i, 100 * value + 0.12, f"{100 * value:.1f}%", ha="center",
                 fontsize=8, color=INK)
    ax2.axhline(100 * ceiling, color=RED, linewidth=1.3, linestyle="--", zorder=4)
    ax2.text(len(bars) - 0.45, 100 * ceiling + 0.12,
             f"oracle ceiling {100 * ceiling:.1f}%", fontsize=7.6, color=RED,
             ha="right")
    ax2.set_xticks(range(len(bars)))
    ax2.set_xticklabels([b[0] for b in bars], fontsize=7.6)
    ax2.set_ylim(0, 100 * ceiling * 1.35)
    ax2.set_ylabel("whole-record accuracy (%)")
    _finish(ax2, "", None)
    ax2.set_title("reranking vs. the best single generator", loc="left",
                  fontsize=9, color=MUTED)

    fig.tight_layout(w_pad=2.2)
    fig.savefig(OUT / "fig20_mars_outcomes.png", bbox_inches="tight")
    plt.close(fig)


def figure_selection() -> None:
    """Figure 21 -- selection quality against both baselines, field by field."""
    report = _load(
        RESULTS / "mars_selection_analysis.json", "Figure 21 (selection)"
    )
    if report is None:
        return

    fields = report["fields"]
    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(11.2, 3.8), gridspec_kw={"width_ratios": [1.3, 1]}
    )

    # Left: the three policies side by side.
    series = [
        ("best generator", "best_generator", TEAL),
        ("MARS", "mars", BLUE),
        ("random candidate", "random_candidate", MUTED),
    ]
    width = 0.26
    for i, (label, key, colour) in enumerate(series):
        values = [100 * report["per_field"][f][key] for f in fields]
        offsets = [j + (i - 1) * width for j in range(len(fields))]
        ax.bar(offsets, values, width=width * 0.9, color=colour, zorder=3, label=label)
    ax.set_xticks(range(len(fields)))
    ax.set_xticklabels([FIELD_LABEL.get(f, f).replace("\n", " ") for f in fields])
    ax.set_ylabel("acceptable (%)")
    ax.set_ylim(0, 90)
    ax.legend(fontsize=7.4, frameon=False, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.16))
    _finish(
        ax,
        "Figure 21 — Selection quality on the segments where MARS selected",
        f"n = {report['n_judged_segments']} judged segments; the "
        f"{report['n_short_circuit']} short-circuits are excluded.",
    )

    # Right: paired differences with intervals, both baselines.
    ax2.axvline(0, color=INK, linewidth=1.0, zorder=2)
    y = 0
    labels, ticks = [], []
    for key, colour, tag in (
        ("vs_random_candidate", BLUE, "vs random"),
        ("vs_best_generator", RED, "vs best gen."),
    ):
        for field in fields:
            entry = report["per_field"][field][key]
            lo, hi, d = (
                100 * entry["lower"],
                100 * entry["upper"],
                100 * entry["difference"],
            )
            ax2.plot([lo, hi], [y, y], color=colour, linewidth=2.0, zorder=3,
                     solid_capstyle="round",
                     alpha=1.0 if entry["excludes_zero"] else 0.45)
            ax2.scatter([d], [y], s=34, color=colour, zorder=4,
                        alpha=1.0 if entry["excludes_zero"] else 0.45)
            labels.append(f"{field}  ({tag})")
            ticks.append(y)
            y += 1
        y += 0.6

    ax2.set_yticks(ticks)
    ax2.set_yticklabels(labels, fontsize=7.2)
    ax2.invert_yaxis()
    ax2.set_xlabel("difference in accuracy (points, 95% paired CI)")
    _finish(ax2, "", None)
    ax2.set_title("solid = interval excludes zero", loc="left", fontsize=8.4,
                  color=MUTED)

    fig.tight_layout(w_pad=2.0)
    fig.savefig(OUT / "fig21_selection.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    figure_corpus()
    figure_admission()
    figure_joint_yield()
    figure_pilot_fields()
    figure_pipeline()
    figure_status_vs_output()
    figure_candidate_divergence()
    figure_coverage_headroom()
    figure_mars_branches()
    figure_reliability()
    figure_confusion()
    figure_conflict_decomposition()
    figure_round_comparison()
    figure_protocol()
    figure_codebook_rules()
    figure_field_accuracy()
    figure_unsupported()
    figure_record_ceiling()
    figure_behavior_overlap()
    figure_mars_outcomes()
    figure_selection()
    print(f"Wrote {len(list(OUT.glob('*.png')))} figures to {OUT}")
    for f in sorted(OUT.glob("*.png")):
        print(f"  {f.name}")
    print_tables()
