"""Tests for gold-standard assembly from two annotators' judgements.

The risk this file guards is not a crash. It is a gold standard that quietly
contains labels no human made -- from a tie-break rule, a partially resolved
item, or two annotators' files that were never about the same thing.
"""

from __future__ import annotations

import pytest

from tests.eval.extraction.adjudicate import (
    FIELDS,
    build_gold,
    split_by_consensus,
)
from tests.eval.extraction.annotate_batch import annotation_key


def _judged(**fields: str) -> dict:
    complete = {f: "correct" for f in FIELDS}
    complete.update(fields)
    return complete


def _annotations(*items: tuple[str, str, dict]) -> dict:
    return {
        annotation_key(segment_id, model): {
            "segment_id": segment_id,
            "model": model,
            "field_judgments": judgments,
        }
        for segment_id, model, judgments in items
    }


class TestConsensus:
    def test_identical_judgements_are_all_agreed(self) -> None:
        annotations = _annotations(("s1", "m", _judged()))
        agreed, conflicts = split_by_consensus(
            annotations, annotations, list(annotations)
        )

        assert agreed["s1::m"] == _judged()
        assert conflicts == {}

    def test_only_the_differing_field_is_a_conflict(self) -> None:
        first = _annotations(("s1", "m", _judged(outcome="correct")))
        second = _annotations(("s1", "m", _judged(outcome="hallucinated")))
        agreed, conflicts = split_by_consensus(first, second, list(first))

        assert conflicts == {"s1::m": ["outcome"]}
        assert "outcome" not in agreed["s1::m"]
        assert agreed["s1::m"]["domain"] == "correct"


class TestGoldAssembly:
    def test_agreed_items_enter_the_gold_keyed_by_segment_and_model(self) -> None:
        annotations = _annotations(("s1", "model_a", _judged()))
        agreed, _ = split_by_consensus(annotations, annotations, list(annotations))
        gold, counts = build_gold(agreed, {}, annotations)

        assert gold == {"s1": {"model_a": _judged()}}
        assert counts["agreed"] == 1

    def test_one_segment_holds_a_label_per_model(self) -> None:
        annotations = _annotations(
            ("s1", "model_a", _judged()),
            ("s1", "model_b", _judged(domain="incorrect")),
        )
        agreed, _ = split_by_consensus(annotations, annotations, list(annotations))
        gold, _ = build_gold(agreed, {}, annotations)

        assert sorted(gold["s1"]) == ["model_a", "model_b"]
        assert gold["s1"]["model_b"]["domain"] == "incorrect"

    def test_an_unresolved_conflict_is_excluded_not_defaulted(self) -> None:
        first = _annotations(("s1", "m", _judged(outcome="correct")))
        second = _annotations(("s1", "m", _judged(outcome="hallucinated")))
        agreed, conflicts = split_by_consensus(first, second, list(first))

        gold, counts = build_gold(agreed, {}, first)

        assert conflicts == {"s1::m": ["outcome"]}
        assert gold == {}
        assert counts["unresolved"] == 1

    def test_an_adjudicated_conflict_enters_the_gold_with_the_resolved_value(
        self,
    ) -> None:
        first = _annotations(("s1", "m", _judged(outcome="correct")))
        second = _annotations(("s1", "m", _judged(outcome="hallucinated")))
        agreed, _ = split_by_consensus(first, second, list(first))

        gold, counts = build_gold(agreed, {"s1::m": {"outcome": "missing"}}, first)

        assert gold["s1"]["m"]["outcome"] == "missing"
        assert counts["adjudicated"] == 1
        assert counts["unresolved"] == 0

    def test_a_partially_adjudicated_item_stays_out(self) -> None:
        """Two disputed fields, one resolved: still not a label."""
        first = _annotations(("s1", "m", _judged(outcome="correct", domain="correct")))
        second = _annotations(
            ("s1", "m", _judged(outcome="hallucinated", domain="incorrect"))
        )
        agreed, _ = split_by_consensus(first, second, list(first))

        gold, counts = build_gold(agreed, {"s1::m": {"outcome": "missing"}}, first)

        assert gold == {}
        assert counts["unresolved"] == 1


class TestEndToEnd:
    """The assembled gold must be the shape mars_evaluation consumes."""

    def test_gold_feeds_the_evaluation_metrics(self) -> None:
        from tests.eval.extraction.mars_evaluation import (
            oracle_ceiling,
            per_model_accuracy,
        )

        annotations = _annotations(
            ("s1", "model_a", _judged()),
            ("s1", "model_b", _judged(domain="hallucinated")),
        )
        agreed, _ = split_by_consensus(annotations, annotations, list(annotations))
        gold, _ = build_gold(agreed, {}, annotations)

        accuracy = per_model_accuracy(gold, ["model_a", "model_b"])

        assert accuracy["model_a"] == pytest.approx(1.0)
        assert accuracy["model_b"] == pytest.approx(0.0)
        assert oracle_ceiling(gold, ["model_a", "model_b"]) == pytest.approx(1.0)
