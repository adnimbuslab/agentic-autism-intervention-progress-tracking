"""Tests for the pre-registered before/after comparison.

The comparison must be correct before round 2 exists, because that is when it
is being fixed. These tests run it against synthetic rounds whose answer is
known by construction.
"""

from __future__ import annotations

import pytest

from tests.eval.extraction.round_comparison import (
    CONTROL_FIELDS,
    TREATED_FIELDS,
    compare,
    round2_present,
)

FIELDS = ["domain", "modality", "prompt_level", "outcome"]


def _gold(values_by_segment: dict[str, dict[str, str]], round_number: int = 1) -> dict:
    return {
        segment: {
            "segment_id": segment,
            "child_id": "carl",
            "field_values": {
                "behavior": "did a thing",
                **{f: values.get(f, "language" if f == "domain" else "verbal") for f in FIELDS},
            },
            "notes": "",
            "annotator": "x",
            "source": "spreadsheet",
            "round": round_number,
        }
        for segment, values in values_by_segment.items()
    }


def _segments(n: int) -> list[str]:
    return [f"s{i}" for i in range(n)]


class TestArms:
    def test_domain_is_the_control_not_a_treated_field(self) -> None:
        assert "domain" in CONTROL_FIELDS
        assert "domain" not in TREATED_FIELDS

    def test_the_three_codebook_fields_are_treated(self) -> None:
        assert set(TREATED_FIELDS) == {"modality", "prompt_level", "outcome"}


class TestRound2Detection:
    def test_an_unmerged_gold_reads_as_round_one(self) -> None:
        segments = _segments(4)
        gold = _gold({s: {} for s in segments}, round_number=1)
        assert round2_present(gold, gold, segments) is False

    def test_a_single_round_two_record_is_enough_to_detect(self) -> None:
        segments = _segments(4)
        first = _gold({s: {} for s in segments}, round_number=1)
        second = _gold({s: {} for s in segments}, round_number=1)
        second["s0"]["round"] = 2
        assert round2_present(first, second, segments) is True

    def test_a_record_with_no_round_key_is_treated_as_round_one(self) -> None:
        segments = _segments(3)
        gold = _gold({s: {} for s in segments})
        for record in gold.values():
            del record["round"]
        assert round2_present(gold, gold, segments) is False


class TestComparison:
    def test_convergence_on_a_treated_field_shows_a_positive_delta(self) -> None:
        segments = _segments(80)
        # Round 1: the annotators split on modality exactly as A and B did,
        # one recording `none` where the other recorded `gestural`.
        before_a = _gold({s: {"modality": "none"} for s in segments})
        before_b = _gold({s: {"modality": "gestural"} for s in segments})
        # Round 2: both apply the rule and record `none`.
        after_a = _gold({s: {"modality": "none"} for s in segments}, 2)
        after_b = _gold({s: {"modality": "none"} for s in segments}, 2)

        report = compare(before_a, before_b, after_a, after_b, segments, n_boot=200)
        modality = report["fields"]["modality"]
        assert modality["arm"] == "treated"
        # Round 1 has no agreement at all on this field; round 2 is unanimous,
        # which leaves kappa undefined (one category) rather than 1.0.
        assert modality["round1"]["observed_agreement"] == 0.0
        assert modality["round2"]["observed_agreement"] == 1.0

    def test_a_real_partial_improvement_is_measured_with_an_interval(self) -> None:
        segments = _segments(120)
        before_a, before_b = {}, {}
        after_a, after_b = {}, {}
        for i, s in enumerate(segments):
            # Both annotators must use more than one category, or kappa is 0 by
            # construction and the comparison measures nothing.
            truth = "correct" if i % 2 else "none"
            flipped = "none" if truth == "correct" else "correct"
            before_a[s] = {"outcome": truth}
            after_a[s] = {"outcome": truth}
            # Round 1: B departs from A on 40% of segments; round 2, on 10%.
            before_b[s] = {"outcome": flipped if i % 10 < 4 else truth}
            after_b[s] = {"outcome": flipped if i % 10 < 1 else truth}

        report = compare(
            _gold(before_a), _gold(before_b), _gold(after_a, 2), _gold(after_b, 2),
            segments, n_boot=400,
        )
        delta = report["fields"]["outcome"]["delta"]
        assert delta["delta"] > 0
        assert delta["lower"] < delta["delta"] < delta["upper"]

    def test_an_unchanged_control_field_reports_a_delta_of_zero(self) -> None:
        segments = _segments(100)
        values = {
            s: {"domain": "language" if i % 3 else "play"}
            for i, s in enumerate(segments)
        }
        other = {
            s: {"domain": "language" if i % 4 else "play"}
            for i, s in enumerate(segments)
        }
        report = compare(
            _gold(values), _gold(other), _gold(values, 2), _gold(other, 2),
            segments, n_boot=300,
        )
        domain = report["fields"]["domain"]
        assert domain["arm"] == "control"
        assert domain["delta"]["delta"] == pytest.approx(0.0)
        assert domain["delta"]["excludes_zero"] is False

    def test_every_categorical_field_is_reported(self) -> None:
        segments = _segments(30)
        gold = _gold({s: {} for s in segments})
        report = compare(gold, gold, gold, gold, segments, n_boot=50)
        assert set(report["fields"]) == set(FIELDS)
        assert report["n_segments"] == 30

    def test_the_comparison_is_restricted_to_the_segments_given(self) -> None:
        # Segments outside the re-issued set must not enter the estimand.
        all_segments = _segments(50)
        gold = _gold({s: {} for s in all_segments})
        report = compare(gold, gold, gold, gold, all_segments[:10], n_boot=50)
        assert report["n_segments"] == 10
        assert report["fields"]["modality"]["round1"]["n"] == 10
