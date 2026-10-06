"""Tests for gold-standard assembly from two annotators' field values.

The risk here is not a crash. It is a gold standard that quietly contains
values nobody chose -- from a tie-break rule, a partially resolved segment, or
a null treated as an absence.
"""

from __future__ import annotations

from tests.eval.extraction.adjudicate import build_gold, split_by_consensus
from tests.eval.extraction.agreement_report import FIELDS

COMPLETE = {
    "domain": "language",
    "behavior": "asks for juice",
    "modality": "verbal",
    "prompt_level": "independent",
    "outcome": "correct",
}


def _annotations(**segments: dict) -> dict:
    return {
        segment_id: {"segment_id": segment_id, "child_id": "c1", "field_values": values}
        for segment_id, values in segments.items()
    }


class TestConsensus:
    def test_identical_values_are_all_agreed(self) -> None:
        annotations = _annotations(s1=COMPLETE)
        agreed, conflicts = split_by_consensus(annotations, annotations, ["s1"])

        assert agreed["s1"] == COMPLETE
        assert conflicts == {}

    def test_only_the_differing_field_is_a_conflict(self) -> None:
        first = _annotations(s1=COMPLETE)
        second = _annotations(s1={**COMPLETE, "outcome": "partial"})
        agreed, conflicts = split_by_consensus(first, second, ["s1"])

        assert conflicts == {"s1": ["outcome"]}
        assert "outcome" not in agreed["s1"]
        assert agreed["s1"]["domain"] == "language"

    def test_casing_differences_are_not_conflicts(self) -> None:
        first = _annotations(s1=COMPLETE)
        second = _annotations(s1={**COMPLETE, "domain": "Language"})
        _, conflicts = split_by_consensus(first, second, ["s1"])

        assert conflicts == {}

    def test_two_nulls_agree_rather_than_both_being_absent(self) -> None:
        nulled = {**COMPLETE, "prompt_level": None}
        annotations = _annotations(s1=nulled)
        agreed, conflicts = split_by_consensus(annotations, annotations, ["s1"])

        assert conflicts == {}
        assert agreed["s1"]["prompt_level"] is None

    def test_a_null_against_a_value_is_a_conflict(self) -> None:
        first = _annotations(s1={**COMPLETE, "prompt_level": None})
        second = _annotations(s1=COMPLETE)
        _, conflicts = split_by_consensus(first, second, ["s1"])

        assert conflicts == {"s1": ["prompt_level"]}


class TestGoldAssembly:
    def test_agreed_segments_enter_the_gold_with_their_values(self) -> None:
        annotations = _annotations(s1=COMPLETE)
        agreed, _ = split_by_consensus(annotations, annotations, ["s1"])
        gold, counts = build_gold(agreed, {}, annotations)

        assert gold["s1"]["field_values"] == COMPLETE
        assert gold["s1"]["source"] == "agreed"
        assert counts["agreed"] == 1

    def test_gold_is_one_value_set_per_segment_not_per_model(self) -> None:
        """The property that lets one reference score every generator."""
        annotations = _annotations(s1=COMPLETE)
        agreed, _ = split_by_consensus(annotations, annotations, ["s1"])
        gold, _ = build_gold(agreed, {}, annotations)

        assert set(gold["s1"]["field_values"]) == set(FIELDS)
        assert "model" not in gold["s1"]

    def test_an_unresolved_conflict_is_excluded_not_defaulted(self) -> None:
        first = _annotations(s1=COMPLETE)
        second = _annotations(s1={**COMPLETE, "outcome": "partial"})
        agreed, _ = split_by_consensus(first, second, ["s1"])

        gold, counts = build_gold(agreed, {}, first)

        assert gold == {}
        assert counts["unresolved"] == 1

    def test_an_adjudicated_conflict_enters_with_the_resolved_value(self) -> None:
        first = _annotations(s1=COMPLETE)
        second = _annotations(s1={**COMPLETE, "outcome": "partial"})
        agreed, _ = split_by_consensus(first, second, ["s1"])

        gold, counts = build_gold(agreed, {"s1": {"outcome": "approximation"}}, first)

        assert gold["s1"]["field_values"]["outcome"] == "approximation"
        assert gold["s1"]["source"] == "adjudicated"
        assert counts["adjudicated"] == 1

    def test_an_adjudicated_null_is_a_resolution_not_an_omission(self) -> None:
        first = _annotations(s1=COMPLETE)
        second = _annotations(s1={**COMPLETE, "prompt_level": "verbal"})
        agreed, _ = split_by_consensus(first, second, ["s1"])

        gold, counts = build_gold(agreed, {"s1": {"prompt_level": None}}, first)

        assert gold["s1"]["field_values"]["prompt_level"] is None
        assert counts["adjudicated"] == 1
        assert counts["unresolved"] == 0

    def test_a_partially_adjudicated_segment_stays_out(self) -> None:
        first = _annotations(s1=COMPLETE)
        second = _annotations(s1={**COMPLETE, "outcome": "partial", "domain": "play"})
        agreed, _ = split_by_consensus(first, second, ["s1"])

        gold, counts = build_gold(agreed, {"s1": {"outcome": "correct"}}, first)

        assert gold == {}
        assert counts["unresolved"] == 1
