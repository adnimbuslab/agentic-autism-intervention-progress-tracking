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
    print(f"Wrote {len(list(OUT.glob('*.png')))} figures to {OUT}")
    for f in sorted(OUT.glob("*.png")):
        print(f"  {f.name}")
    print_tables()
