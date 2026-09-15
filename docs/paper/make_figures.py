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
    print(f"Wrote {len(list(OUT.glob('*.png')))} figures to {OUT}")
    for f in sorted(OUT.glob("*.png")):
        print(f"  {f.name}")
    print_tables()
