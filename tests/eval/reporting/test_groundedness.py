"""Tests for the reporting groundedness instrument.

The instrument must not flag a grounded number, or its output is noise; and it
must not score the deterministic fallback, or it reports the template's
groundedness as the model's. Both are checked against the recorded run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.reporting.groundedness import (
    STRUCTURAL_NUMBERS,
    is_grounded,
    prose_numbers,
)

RESULTS = Path(__file__).parent / "results" / "reporting_groundedness.json"


@pytest.fixture(scope="module")
def run() -> dict:
    if not RESULTS.exists():
        pytest.skip("groundedness run not recorded yet")
    return json.loads(RESULTS.read_text())


class TestGroundingRule:
    def test_a_value_printed_at_lower_precision_is_grounded(self) -> None:
        # The report renders a stored 0.9412 as "94.1%".
        assert is_grounded("94.1", {94.12})

    def test_a_fabricated_value_is_not_grounded(self) -> None:
        assert not is_grounded("94.1", {12.0, 87.5})

    def test_a_magnitude_matches_a_negative_packet_value(self) -> None:
        # "decreased by 0.5333" against a stored delta of -0.5333.
        assert is_grounded("0.5333", {0.5333})

    def test_precision_is_taken_from_the_printed_number(self) -> None:
        assert is_grounded("0.9", {0.94})
        assert not is_grounded("0.94", {0.9})

    def test_record_ids_are_not_read_as_claims(self) -> None:
        assert prose_numbers("see carl-017 and brett-004") == []

    def test_iso_dates_are_not_read_as_claims(self) -> None:
        assert prose_numbers("from 2026-01-05 to 2026-03-09") == []

    def test_ordinary_numbers_are_read(self) -> None:
        assert prose_numbers("30 records, 94.1% independent") == ["30", "94.1"]

    def test_structural_numbers_are_excluded_by_convention(self) -> None:
        assert {0, 1, 2, 3, 4, 5, 100} <= STRUCTURAL_NUMBERS


class TestCalibration:
    def test_the_fallback_is_perfectly_grounded(self, run) -> None:
        # The fallback composes prose from packet values only, so any number it
        # asserts that the rule rejects is a false positive of the rule.
        fallbacks = [e for e in run["per_child"] if e.get("used_fallback")]
        if not fallbacks:
            pytest.skip("no fallback reports in this run")
        for entry in fallbacks:
            assert entry["n_numbers_ungrounded"] == 0, (
                f"{entry['child_id']}: rule rejected "
                f"{entry['ungrounded_examples']} in grounded-by-construction prose"
            )

    def test_the_fallback_cites_only_real_records(self, run) -> None:
        for entry in run["per_child"]:
            if entry.get("used_fallback"):
                assert entry["n_invalid_refs"] == 0


class TestScoringDiscipline:
    def test_fallback_reports_are_excluded_from_the_score(self, run) -> None:
        scored = run["n_llm_reports"]
        fallback = run["n_fallback_reports"]
        assert scored + fallback + run["n_errors"] == run["n_children"]
        # The headline mean must be computed over LLM reports only.
        if scored == 0:
            assert run["summary"]["mean_numeric_groundedness"] is None

    def test_every_child_is_accounted_for(self, run) -> None:
        assert len(run["per_child"]) == run["n_children"]

    def test_the_derived_metadata_is_disclosed(self, run) -> None:
        note = run["metadata_note"].lower()
        assert "derived from corpus structure" in note
        assert "not from real intervention records" in note


class TestPooledRates:
    """A rate printed beside a count and a denominator must be that ratio.

    The summary carries two estimators: pooled over assertions, and the mean
    of per-report rates. They differ — 8/122 is 6.6%, while the mean of the
    eleven per-report rates is 6.8% — because one weights assertions equally
    and the other weights reports equally. Reporting a count, a denominator
    and the *other* estimator's percentage in one row is the error this guards.
    """

    def test_the_pooled_rate_is_the_ratio_it_is_printed_beside(self, run) -> None:
        s = run["summary"]
        assert s["numeric_assertions"] > 0
        assert s["pooled_ungrounded_rate"] == pytest.approx(
            s["numeric_ungrounded"] / s["numeric_assertions"], abs=5e-5
        )

    def test_the_reference_rate_has_a_denominator(self, run) -> None:
        s = run["summary"]
        # A bare "2 invalid references" is uninterpretable without the total.
        assert s["evidence_references"] > 0
        assert s["pooled_invalid_reference_rate"] == pytest.approx(
            s["evidence_references_invalid"] / s["evidence_references"], abs=5e-5
        )

    def test_both_estimators_are_retained_and_distinguishable(self, run) -> None:
        s = run["summary"]
        assert "pooled_ungrounded_rate" in s
        assert "mean_of_per_report_groundedness" in s

    def test_the_counts_agree_with_the_per_report_rows(self, run) -> None:
        rows = [
            e for e in run["per_child"]
            if not e.get("used_fallback") and "error" not in e
        ]
        s = run["summary"]
        assert s["numeric_assertions"] == sum(e["n_numbers_asserted"] for e in rows)
        assert s["numeric_ungrounded"] == sum(e["n_numbers_ungrounded"] for e in rows)
        assert s["evidence_references"] == sum(e["n_evidence_refs"] for e in rows)
