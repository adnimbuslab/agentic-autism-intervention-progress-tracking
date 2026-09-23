"""Figures for the reviewer-response document.

These are response-specific: they answer a reviewer's question rather than
carrying the manuscript's argument, so they are numbered and stored separately
(`figures/response/`) and do not disturb the manuscript's figure sequence.

Every plotted number is read from a recorded artefact. The two diagrams carry
no data; they draw code paths that are asserted by tests named in the caption.

    uv run python docs/paper/make_response_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tests/eval/extraction/results"
REPORTING = ROOT / "tests/eval/reporting/results"
OUT = Path(__file__).parent / "figures" / "response"
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


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def _finish(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold",
                 pad=14 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=8, color=MUTED)
    ax.grid(axis="both", color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)


def _short(model: str) -> str:
    return model.replace(":latest", "")


def _box(ax, x, y, w, h, label, colour, *, size=7.6, fill=False, dashed=False):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.3, edgecolor=colour,
        facecolor=colour if fill else "white",
        linestyle="--" if dashed else "-", zorder=3,
    ))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=size, color="white" if fill else INK, zorder=4)


def _arrow(ax, x1, y1, x2, y2, colour=MUTED, dashed=False):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9,
        linewidth=1.1, color=colour,
        linestyle="--" if dashed else "-", zorder=2,
    ))


# --- R2: the selection effect, measured -------------------------------------
def figure_holdout() -> None:
    """Batch against the model-independent held-out set, same scoring policy."""
    hm = _load(RESULTS / "holdout_metrics.json")
    if hm is None:
        return
    models = hm["models_compared"]
    delta = hm["delta"]

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11.2, 3.9))
    width = 0.36
    xs = range(len(models))

    for offset, side, colour in ((-width / 2, "batch", BLUE), (width / 2, "holdout", AMBER)):
        values = [100 * delta[m]["mean_field_accuracy"][side] for m in models]
        ax.bar([x + offset for x in xs], values, width=width * 0.92, color=colour,
               zorder=3, label="model-conditioned batch (n=330)" if side == "batch"
               else "model-independent held-out (n=132)")
        for x, v in zip(xs, values):
            ax.text(x + offset, v + 1.0, f"{v:.1f}", ha="center", fontsize=7, color=MUTED)

    for x, m in zip(xs, models):
        d = 100 * delta[m]["mean_field_accuracy"]["delta"]
        ax.text(x, 2.0, f"{d:+.1f}", ha="center", fontsize=7.6, color=RED, fontweight="bold")

    ax.set_xticks(list(xs))
    ax.set_xticklabels([_short(m) for m in models], fontsize=8)
    ax.set_ylim(0, 52)
    ax.set_ylabel("merged mean agreement (%)")
    ax.legend(fontsize=7.2, frameon=False, loc="upper left")
    _finish(
        ax,
        "Agreement falls on segments not selected for model tractability",
        "mean over the four categorical fields; red = change in points",
    )

    for offset, side, colour in ((-width / 2, "batch", BLUE), (width / 2, "holdout", AMBER)):
        values = [100 * delta[m]["unsupported_rate"][side] for m in models]
        ax2.bar([x + offset for x in xs], values, width=width * 0.92, color=colour, zorder=3)
        for x, v in zip(xs, values):
            ax2.text(x + offset, v + 1.5, f"{v:.1f}", ha="center", fontsize=7, color=MUTED)

    ax2.set_xticks(list(xs))
    ax2.set_xticklabels([_short(m) for m in models], fontsize=8)
    ax2.set_ylim(0, 112)
    ax2.set_ylabel("unsupported assertion (%)")
    _finish(
        ax2,
        "The safety finding does not improve on the unbiased sample",
        "values asserted where the standard records that the transcript supports none",
    )

    fig.tight_layout(w_pad=2.4)
    fig.savefig(OUT / "r2_holdout_selection_effect.png", bbox_inches="tight")
    plt.close(fig)


# --- R3: what the reporting governance check found --------------------------
def figure_reporting() -> None:
    """The governance outcome that removed the generative layer from the path."""
    g = _load(REPORTING / "reporting_groundedness.json")
    if g is None:
        return
    s = g["summary"]
    n = g["n_llm_reports"]

    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(11.2, 3.5), gridspec_kw={"width_ratios": [1.35, 1]}
    )

    # Structural conformance is derived, not asserted: every report was produced
    # by the generative path (no fallbacks) and none errored, so all n parsed
    # into the required structure.
    checks = [
        ("Structurally conformant", n - g["n_errors"], TEAL),
        ("No prohibited diagnostic,\ntreatment or causal content",
         n - s["prohibited_content_reports"], TEAL),
        ("Every asserted number\ntraceable to the packet", s["reports_fully_grounded"], AMBER),
        ("Withheld analyses\nacknowledged as withheld", s["reports_passing_validation"], RED),
        ("Passed governance validation", s["reports_passing_validation"], RED),
    ]
    ys = range(len(checks))
    ax.barh([len(checks) - 1 - y for y in ys], [c[1] for c in checks],
            color=[c[2] for c in checks], height=0.62, zorder=3)
    for y, (label, value, _) in zip(ys, checks):
        ax.text(value + 0.15, len(checks) - 1 - y, f"{value}/{n}",
                va="center", fontsize=7.8, color=MUTED)
    ax.set_yticks([len(checks) - 1 - y for y in ys])
    ax.set_yticklabels([c[0] for c in checks], fontsize=7.6)
    ax.set_xlim(0, n + 1.6)
    ax.set_xlabel(f"reports (n = {n}, one per child)")
    _finish(
        ax,
        "Conformant and non-prohibited, yet nothing passed",
        "the failure is silence about withholding, not fabricated content",
    )

    # Counts differ by an order of magnitude (122 against 836), so these are
    # drawn as shares: a stacked count bar renders the smaller row invisible
    # and the failing fraction is the point of the panel.
    rows = [
        (1, "numbers asserted", s["total_numbers_asserted"],
         s["total_numbers_ungrounded"], "not traceable to the packet"),
        (0, "evidence references", s["evidence_references"],
         s["evidence_references_invalid"], "invalid reference"),
    ]
    for y, _, total, bad, label in rows:
        ax2.barh([y], [100 * (total - bad) / total], color=TEAL, height=0.45,
                 zorder=3, label="traceable" if y == 1 else None)
        ax2.barh([y], [100 * bad / total], left=[100 * (total - bad) / total],
                 color=RED, height=0.45, zorder=3,
                 label="fails grounding" if y == 1 else None)
        ax2.text(101, y, f"{100 * bad / total:.2f}% {label}", va="center",
                 fontsize=7.2, color=RED)
    ax2.set_yticks([1, 0])
    ax2.set_yticklabels([
        f"numbers asserted\n({s['total_numbers_ungrounded']} of "
        f"{s['total_numbers_asserted']})",
        f"evidence references\n({s['evidence_references_invalid']} of "
        f"{s['evidence_references']})",
    ], fontsize=7.4)
    ax2.set_xlim(0, 100)
    ax2.set_ylim(-0.6, 1.7)
    ax2.set_xlabel("share of assertions (%)")
    ax2.legend(fontsize=7, frameon=False, loc="upper left", ncol=2)
    _finish(ax2, "Grounding was close, but not closed", None)

    fig.tight_layout(w_pad=2.0)
    fig.savefig(OUT / "r3_reporting_governance.png", bbox_inches="tight")
    plt.close(fig)


# --- R4: evaluation scope against analytics scope ----------------------------
def figure_field_scope() -> None:
    """Eight fields generated, five evaluated, and where each may travel."""
    fig, ax = plt.subplots(figsize=(11.0, 4.3))
    ax.axis("off")

    evaluated = ["behavior", "domain", "modality", "prompt_level", "outcome"]
    unevaluated = ["goal_context", "prompt_context", "duration_seconds"]

    ax.text(0.15, 8.15, "Extractor output — 8 fields", fontsize=8.6,
            fontweight="bold", color=INK)
    for i, f in enumerate(evaluated):
        _box(ax, 0.15, 6.9 - i * 0.72, 2.25, 0.58, f, TEAL)
    for i, f in enumerate(unevaluated):
        _box(ax, 0.15, 3.0 - i * 0.72, 2.25, 0.58, f, RED, dashed=True)

    _box(ax, 3.5, 5.3, 2.5, 1.5,
         "Scored against the\nadjudicated gold\nstandard", TEAL)
    _box(ax, 3.5, 1.6, 2.5, 1.5,
         "No reference\nstandard in\nthis study", RED, dashed=True)

    for i in range(len(evaluated)):
        _arrow(ax, 2.4, 7.19 - i * 0.72, 3.5, 6.05, TEAL)
    for i in range(len(unevaluated)):
        _arrow(ax, 2.4, 3.29 - i * 0.72, 3.5, 2.35, RED)

    consumers = [
        ("KPIs and longitudinal\nanalytics", 7.05, TEAL),
        ("Adequacy / abstention\nrouter", 5.35, TEAL),
        ("Deterministic reporter\n(operational)", 3.65, TEAL),
        ("Evidence packet →\nexperimental generative\nreporter (not operational)", 1.6, AMBER),
    ]
    for label, y, colour in consumers:
        _box(ax, 7.4, y, 3.4, 1.35 if "packet" not in label else 1.6, label, colour)

    _arrow(ax, 6.0, 6.05, 7.4, 7.72, TEAL)
    _arrow(ax, 6.0, 6.05, 7.4, 6.02, TEAL)
    _arrow(ax, 6.0, 6.05, 7.4, 4.32, TEAL)
    _arrow(ax, 6.0, 2.35, 7.4, 2.4, RED, dashed=True)

    ax.text(7.4, 0.85,
            "The three unevaluated fields reach no KPI, no adequacy check and no "
            "deterministic report section.\nThey are visible only inside the evidence "
            "packet — one further reason that path is not operational.",
            fontsize=7.4, color=MUTED, va="top")

    ax.set_xlim(0, 11.2)
    ax.set_ylim(0.2, 8.6)
    ax.set_title(
        "Evaluation scope against analytics scope, as enforced in code",
        loc="left", fontsize=10.5, fontweight="bold", pad=10,
    )
    fig.tight_layout()
    fig.savefig(OUT / "r4_field_scope.png", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# --- R5: the contribution hierarchy -----------------------------------------
def figure_contribution() -> None:
    """One primary contribution; everything else subordinate to it."""
    fig, ax = plt.subplots(figsize=(11.0, 3.9))
    ax.axis("off")

    _box(ax, 1.4, 6.0, 8.4, 1.0,
         "PRIMARY CONTRIBUTION — a governance-aware evaluation framework",
         BLUE, size=9.0, fill=True)

    elements = [
        "Explicit-null annotation\n(an opportunity to count\ninvented values against)",
        "Controlled codebook\nrevision (untreated control\nfield separates the effect)",
        "Oracle-bounded selection\nanalysis + model-independent\nheld-out set",
        "Governance check kept\nseparate from schema\nconformance",
    ]
    for i, text in enumerate(elements):
        _box(ax, 0.45 + i * 2.6, 3.5, 2.35, 1.75, text, BLUE, size=7.0)
        _arrow(ax, 1.6 + i * 2.6, 6.0, 1.6 + i * 2.6, 5.25, BLUE)

    _box(ax, 0.45, 1.7, 5.05, 1.2,
         "Objects measured, not parallel contributions:\nannotation scheme · four generators ·\n"
         "MARS reranking · reporting layer", MUTED, size=7.0, dashed=True)
    _box(ax, 5.95, 1.7, 4.75, 1.2,
         "Setting that motivates the measurements:\nthe longitudinal intervention-support\napplication",
         MUTED, size=7.0, dashed=True)

    ax.set_xlim(0, 11.2)
    ax.set_ylim(1.3, 7.6)
    ax.set_title(
        "What the paper claims as its contribution, and what it does not",
        loc="left", fontsize=10.5, fontweight="bold", pad=10,
    )
    fig.tight_layout()
    fig.savefig(OUT / "r5_contribution_hierarchy.png", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


if __name__ == "__main__":
    figure_holdout()
    figure_reporting()
    figure_field_scope()
    figure_contribution()
    for path in sorted(OUT.glob("*.png")):
        print(f"Wrote {path.relative_to(ROOT)}")
