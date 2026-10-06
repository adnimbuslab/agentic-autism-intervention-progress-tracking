"""Every number in the reliability manuscript section must match its artefact.

Figures are generated from the recorded JSON and so cannot drift. Prose tables
are typed, and can: a value edited in the markdown, or an artefact regenerated
under a changed input, leaves the two disagreeing with nothing to catch it. A
submission is the wrong place to discover that.

These tests parse the markdown tables in `docs/paper/results_reliability.md`
and re-derive each cell from `reliability_round1.json`, the round-1 gold files
and `reissue_round2_selection.json`. They are skipped rather than failed where
an artefact has not been produced, so a fresh clone does not report false
failures.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

RESULTS = Path(__file__).parent / "results"
MANUSCRIPT = Path(__file__).parents[3] / "docs/paper/results_reliability.md"
RELIABILITY = RESULTS / "reliability_round1.json"
SELECTION = RESULTS / "reissue_round2_selection.json"
CURRENT = RESULTS / "reliability_current.json"
COMPARISON = RESULTS / "round_comparison.json"
GOLD = {
    "a": RESULTS / "gold_annotator_a_round1.json",
    "b": RESULTS / "gold_annotator_b_round1.json",
}
CATEGORICAL = ["domain", "modality", "prompt_level", "outcome"]


def _require(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not produced yet")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def prose() -> str:
    if not MANUSCRIPT.exists():
        pytest.skip("manuscript section not written")
    return MANUSCRIPT.read_text()


def _rounds_to(printed: str, actual: float) -> bool:
    """Is `printed` a correct rounding of `actual` at the precision it shows?

    The manuscript prints 3 decimals where the artefact carries 4, so exact
    equality would fail on every legitimately rounded cell. Half a unit in the
    last printed place is the right tolerance: it admits either rounding
    convention and still rejects a transcription error, which moves a digit.
    """
    text = printed.strip().strip("*` ")
    decimals = len(text.split(".")[1]) if "." in text else 0
    return abs(float(text) - actual) <= 0.5 * 10 ** -decimals + 1e-9


def _numbers(cell: str) -> list[str]:
    return re.findall(r"-?\d+\.\d+", cell)


def _table_rows(
    text: str, header_cell: str, occurrence: int = 0
) -> dict[str, list[str]]:
    """Rows of a markdown table located by its header's first cell.

    Tables R1 and R5 share a header — they report the same quantities before
    and after the codebook — so `occurrence` selects which one. Matching on the
    header alone and silently taking the first would have left R5 unverified.
    """
    tables: list[dict[str, list[str]]] = []
    rows: dict[str, list[str]] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"| {header_cell} |"):
            rows = {}
            tables.append(rows)
            continue
        if rows is not None:
            if not stripped.startswith("|"):
                rows = None
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if set(cells[0]) <= set("-: "):
                continue
            rows[cells[0].strip("*` ")] = cells[1:]
    if len(tables) <= occurrence:
        raise AssertionError(
            f"no table #{occurrence} with header cell {header_cell!r} "
            f"(found {len(tables)})"
        )
    return tables[occurrence]


@pytest.fixture(scope="module")
def report() -> dict:
    return _require(RELIABILITY)


@pytest.fixture(scope="module")
def forced() -> dict[str, tuple[int, int]]:
    """Observed and marginal-forced disagreements per field, from the gold files."""
    gold = {k: _require(p) for k, p in GOLD.items()}
    segments = sorted(set(gold["a"]) & set(gold["b"]))
    out: dict[str, tuple[int, int]] = {}
    for field in CATEGORICAL:
        pairs = [
            (
                gold["a"][s]["field_values"].get(field) or "none",
                gold["b"][s]["field_values"].get(field) or "none",
            )
            for s in segments
        ]
        first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
        overlap = sum(min(first[c], second[c]) for c in set(first) | set(second))
        observed = sum(1 for a, b in pairs if a != b)
        out[field] = (observed, len(pairs) - overlap)
    return out


@pytest.fixture(scope="module")
def current() -> dict:
    return _require(CURRENT)


@pytest.fixture(scope="module")
def comparison() -> dict:
    return _require(COMPARISON)


@pytest.fixture(scope="module")
def merged_conflicts() -> Counter:
    """Residual categorical conflicts per field in the merged gold."""
    gold = {
        "a": _require(RESULTS / "gold_annotator_a.json"),
        "b": _require(RESULTS / "gold_annotator_b.json"),
    }
    segments = sorted(set(gold["a"]) & set(gold["b"]))
    counts = Counter()
    for field in CATEGORICAL:
        for segment in segments:
            if (gold["a"][segment]["field_values"].get(field) or "none") != (
                gold["b"][segment]["field_values"].get(field) or "none"
            ):
                counts[field] += 1
    return counts


@pytest.fixture(scope="module")
def selection() -> dict:
    return _require(SELECTION)


@pytest.fixture(scope="module")
def counts(selection) -> tuple[Counter, Counter]:
    """Boundary and silent conflicts per field, from the recorded selection."""
    on = Counter()
    for conflicts in selection["selected"].values():
        for conflict in conflicts:
            on[conflict["field"]] += 1
    off = Counter(c["field"] for c in selection["off_boundary"])
    return on, off


class TestTableR1:
    """Round-1 reliability, against reliability_round1.json."""

    def test_every_categorical_field_has_a_row(self, prose, report) -> None:
        rows = _table_rows(prose, "field | categories used")
        assert set(rows) == set(CATEGORICAL)

    @pytest.mark.parametrize("field", CATEGORICAL)
    def test_the_point_estimates_match(self, prose, report, field) -> None:
        cells = _table_rows(prose, "field | categories used")[field]
        stats = report["fields"][field]
        categories, p_o, p_e, kappa = cells[0], cells[1], cells[2], cells[3]
        assert int(categories) == stats["n_categories_used"]
        assert _rounds_to(p_o, stats["observed_agreement"]), f"p_o {p_o}"
        assert _rounds_to(p_e, stats["expected_agreement"]), f"p_e {p_e}"
        assert _rounds_to(kappa, stats["kappa"]), f"kappa {kappa}"

    @pytest.mark.parametrize("field", CATEGORICAL)
    def test_the_intervals_and_ceiling_match(self, prose, report, field) -> None:
        cells = _table_rows(prose, "field | categories used")[field]
        stats = report["fields"][field]
        boot, asym = _numbers(cells[4]), _numbers(cells[5])
        assert len(boot) == 2 and len(asym) == 2
        assert _rounds_to(boot[0], stats["bootstrap_ci"]["lower"]), f"boot lower {boot[0]}"
        assert _rounds_to(boot[1], stats["bootstrap_ci"]["upper"]), f"boot upper {boot[1]}"
        assert _rounds_to(asym[0], stats["asymptotic_ci"]["lower"]), f"asym lower {asym[0]}"
        assert _rounds_to(asym[1], stats["asymptotic_ci"]["upper"]), f"asym upper {asym[1]}"
        assert _rounds_to(cells[6], stats["asymptotic_ci"]["se"]), f"se {cells[6]}"
        assert _rounds_to(cells[7], stats["kappa_max"]), f"kappa_max {cells[7]}"
        assert _rounds_to(cells[8], stats["kappa_over_kappa_max"]), f"ratio {cells[8]}"

    def test_the_mean_kappa_in_the_prose_matches(self, prose, report) -> None:
        assert f"{report['mean_kappa']:.3f}" in prose

    def test_the_claim_that_the_two_estimators_agree_holds(self, prose, report) -> None:
        # The methods section claims agreement to within 0.005 on every bound.
        assert "within 0.005" in prose
        for field in CATEGORICAL:
            stats = report["fields"][field]
            for side in ("lower", "upper"):
                gap = abs(stats["bootstrap_ci"][side] - stats["asymptotic_ci"][side])
                assert gap <= 0.005, f"{field} {side} differs by {gap:.4f}"

    def test_all_bootstrap_replicates_were_valid_as_claimed(self, prose, report) -> None:
        assert "all valid" in prose
        for field in CATEGORICAL:
            boot = report["fields"][field]["bootstrap_ci"]
            assert boot["n_valid"] == boot["n_requested"]


class TestTableR2:
    """Marginal decomposition, recomputed from the round-1 gold files."""

    @pytest.mark.parametrize("field", CATEGORICAL)
    def test_the_counts_and_share_match(self, prose, forced, field) -> None:
        cells = _table_rows(prose, "field | observed disagreements")[field]
        observed, forced_count = forced[field]
        assert int(cells[0]) == observed
        assert int(cells[1].strip("*")) == forced_count
        stated = int(re.search(r"(\d+)", cells[2]).group(1))
        assert stated == round(100 * forced_count / observed)

    def test_forced_never_exceeds_observed(self, forced) -> None:
        for field, (observed, forced_count) in forced.items():
            assert forced_count <= observed, field


class TestTableR3:
    """Conflict attribution, against reissue_round2_selection.json."""

    @pytest.mark.parametrize("field", CATEGORICAL)
    def test_the_per_field_split_matches(self, prose, counts, field) -> None:
        on, off = counts
        cells = _table_rows(prose, "field | conflicts")[field]
        assert int(cells[0]) == on[field] + off[field]
        assert int(re.match(r"(\d+)", cells[1]).group(1)) == on[field]
        assert int(cells[2]) == off[field]

    def test_the_totals_row_matches(self, prose, counts, selection) -> None:
        on, off = counts
        cells = _table_rows(prose, "field | conflicts")["total"]
        assert int(cells[0].strip("* ")) == sum(on.values()) + sum(off.values())
        assert int(re.search(r"(\d+)", cells[1]).group(1)) == selection["n_on_boundary"]
        assert int(re.search(r"(\d+)", cells[2]).group(1)) == selection["n_off_boundary"]

    def test_the_re_issued_segment_count_appears_in_the_prose(
        self, prose, selection
    ) -> None:
        assert str(selection["n_selected"]) in prose

    def test_the_headline_share_matches(self, prose, selection) -> None:
        total = selection["n_on_boundary"] + selection["n_off_boundary"]
        share = 100 * selection["n_on_boundary"] / total
        assert f"{share:.1f}%" in prose


class TestProseClaims:
    """Claims made in prose rather than in a table."""

    def test_the_modality_marginal_claim_matches_the_gold(self, prose) -> None:
        gold = {k: _require(p) for k, p in GOLD.items()}
        segments = sorted(set(gold["a"]) & set(gold["b"]))
        counts = {
            key: Counter(
                gold[key][s]["field_values"].get("modality") or "none" for s in segments
            )
            for key in ("a", "b")
        }
        # "annotator A recorded `none` ... 75 times; annotator B ... zero times"
        assert counts["a"]["none"] == 75
        assert counts["b"]["none"] == 0
        assert counts["b"]["gestural"] == 81 and counts["a"]["gestural"] == 17
        assert counts["b"]["multimodal"] == 54 and counts["a"]["multimodal"] == 39
        for claim in ("75 times", "`gestural` (81 uses against", "54 against 39"):
            assert claim in prose

    def test_the_segment_conflict_counts_match(self, prose) -> None:
        gold = {k: _require(p) for k, p in GOLD.items()}
        segments = sorted(set(gold["a"]) & set(gold["b"]))
        with_conflict = sum(
            1
            for s in segments
            if any(
                (gold["a"][s]["field_values"].get(f) or "none")
                != (gold["b"][s]["field_values"].get(f) or "none")
                for f in CATEGORICAL
            )
        )
        assert with_conflict == 215
        assert "215" in prose

    def test_no_adjudicated_result_is_claimed(self, prose) -> None:
        # Adjudication has not been run; no gold-standard accuracy may appear.
        lowered = prose.lower()
        for phrase in ("adjudicated gold standard is", "per-generator accuracy of"):
            assert phrase not in lowered
        assert "Adjudication of the residual conflicts has not been performed" in prose


class TestTableR4:
    """Round comparison, against round_comparison.json."""

    @pytest.mark.parametrize("field", CATEGORICAL)
    def test_the_change_and_interval_match(self, prose, comparison, field) -> None:
        cells = _table_rows(prose, "field | arm")[field]
        entry = comparison["fields"][field]
        delta = entry["delta"]
        assert cells[0] == entry["arm"]
        assert _rounds_to(cells[1], delta["kappa_before"]), f"before {cells[1]}"
        assert _rounds_to(cells[2], delta["kappa_after"]), f"after {cells[2]}"
        # The minus sign in the prose is a unicode dash for a negative change.
        assert _rounds_to(cells[3].replace("\u2212", "-"), delta["delta"]), cells[3]
        bounds = _numbers(cells[4].replace("\u2212", "-"))
        assert len(bounds) == 2
        assert _rounds_to(bounds[0], delta["lower"]), f"lower {bounds[0]}"
        assert _rounds_to(bounds[1], delta["upper"]), f"upper {bounds[1]}"

    def test_the_treated_fields_improved_and_the_control_did_not(
        self, comparison
    ) -> None:
        # The claim the section rests on, checked against the data rather than
        # against the sentence that states it.
        for field, entry in comparison["fields"].items():
            delta = entry["delta"]
            if entry["arm"] == "treated":
                assert delta["delta"] > 0 and delta["excludes_zero"], field
            else:
                assert not delta["excludes_zero"], field

    def test_the_comparison_covers_the_re_issued_segments(
        self, comparison, selection
    ) -> None:
        assert comparison["n_segments"] == selection["n_selected"]
        assert str(comparison["n_segments"]) in MANUSCRIPT.read_text()


class TestTableR5:
    """Post-codebook full-batch reliability, against reliability_current.json."""

    @pytest.mark.parametrize("field", CATEGORICAL)
    def test_the_row_matches(self, prose, current, field) -> None:
        cells = _table_rows(prose, "field | categories used", occurrence=1)[field]
        stats = current["fields"][field]
        assert int(cells[0]) == stats["n_categories_used"]
        assert _rounds_to(cells[1], stats["observed_agreement"]), f"p_o {cells[1]}"
        assert _rounds_to(cells[2], stats["expected_agreement"]), f"p_e {cells[2]}"
        assert _rounds_to(cells[3], stats["kappa"]), f"kappa {cells[3]}"
        boot, asym = _numbers(cells[4]), _numbers(cells[5])
        assert _rounds_to(boot[0], stats["bootstrap_ci"]["lower"])
        assert _rounds_to(boot[1], stats["bootstrap_ci"]["upper"])
        assert _rounds_to(asym[0], stats["asymptotic_ci"]["lower"])
        assert _rounds_to(asym[1], stats["asymptotic_ci"]["upper"])
        assert _rounds_to(cells[6], stats["asymptotic_ci"]["se"]), f"se {cells[6]}"
        assert _rounds_to(cells[7], stats["kappa_max"]), f"kappa_max {cells[7]}"
        assert _rounds_to(cells[8], stats["kappa_over_kappa_max"]), f"ratio {cells[8]}"

    def test_the_post_codebook_values_all_appear_in_the_prose(
        self, prose, current
    ) -> None:
        for field, stats in current["fields"].items():
            assert f"{stats['kappa']:.3f}" in prose, f"{field} kappa"
            assert f"{stats['kappa_max']:.3f}" in prose, f"{field} kappa_max"

    def test_the_mean_kappa_rose_as_stated(self, prose, current, report) -> None:
        assert f"{report['mean_kappa']:.3f} to {current['mean_kappa']:.3f}" in prose

    def test_the_two_estimators_still_agree_within_the_stated_bound(
        self, current
    ) -> None:
        for field, stats in current["fields"].items():
            for side in ("lower", "upper"):
                gap = abs(stats["bootstrap_ci"][side] - stats["asymptotic_ci"][side])
                assert gap <= 0.005, f"{field} {side} differs by {gap:.4f}"

    def test_all_replicates_were_valid(self, current) -> None:
        for stats in current["fields"].values():
            assert stats["bootstrap_ci"]["n_valid"] == stats["bootstrap_ci"]["n_requested"]


class TestResidualConflicts:
    """The remaining-disagreement table, recomputed from the merged gold."""

    @pytest.mark.parametrize("field", CATEGORICAL)
    def test_the_merged_count_matches(self, prose, merged_conflicts, field) -> None:
        cells = _table_rows(prose, "field | conflicts round 1")[field]
        assert int(cells[1]) == merged_conflicts[field]

    def test_the_total_matches(self, prose, merged_conflicts) -> None:
        cells = _table_rows(prose, "field | conflicts round 1")["total"]
        assert int(cells[1].strip("* ")) == sum(merged_conflicts.values())

    def test_the_reduction_claim_holds(self, prose, merged_conflicts, counts) -> None:
        on, off = counts
        before = sum(on.values()) + sum(off.values())
        after = sum(merged_conflicts.values())
        assert after < before
        assert f"{round(100 * (before - after) / before)}% reduction" in prose
