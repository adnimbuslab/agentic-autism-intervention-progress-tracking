"""Tests for deriving per-model judgements from model-independent gold.

This is the bridge the study's design rests on: annotators author gold once,
and every generator is scored against it. Two properties matter -- the
derivation must be faithful (especially for nulls, which carry the
unsupported-extraction rate), and the oracle ceiling must come out over a
common set.
"""

from __future__ import annotations

import pytest

from tests.eval.extraction.mars_evaluation import oracle_ceiling, per_model_accuracy
from tests.eval.extraction.score_against_gold import judge_field, score

GOLD = {
    "domain": "language",
    "behavior": "asks for juice",
    "modality": "verbal",
    "prompt_level": "independent",
    "outcome": "correct",
}


def _gold_payload(**segments: dict) -> dict:
    return {
        "gold": {
            segment_id: {"field_values": values, "child_id": "c1", "source": "agreed"}
            for segment_id, values in segments.items()
        }
    }


def _batch(models: list[str], **segments: dict) -> dict:
    return {
        "models": models,
        "candidates": [
            {
                "segment_id": segment_id,
                "child_id": "c1",
                "candidates": {
                    model: {"extracted_fields": fields}
                    for model, fields in per_model.items()
                },
            }
            for segment_id, per_model in segments.items()
        ],
    }


class TestFieldDerivation:
    @pytest.mark.parametrize(
        ("gold_value", "model_value", "expected"),
        [
            (None, None, "correctly_null"),
            (None, "verbal", "hallucinated"),
            ("verbal", None, "missing"),
            ("verbal", "verbal", "correct"),
            ("verbal", "gestural", "incorrect"),
        ],
    )
    def test_the_five_cases(self, gold_value, model_value, expected) -> None:
        judgment = judge_field(
            "modality", gold_value, model_value,
            behavior_match="exact", threshold=0.5,
        )
        assert judgment == expected

    def test_an_unsupported_value_is_hallucinated_not_incorrect(self) -> None:
        """Null gold is what makes the unsupported-extraction rate measurable."""
        assert judge_field(
            "prompt_level", None, "full_physical",
            behavior_match="exact", threshold=0.5,
        ) == "hallucinated"

    def test_casing_does_not_make_a_correct_value_incorrect(self) -> None:
        assert judge_field(
            "domain", "language", "Language",
            behavior_match="exact", threshold=0.5,
        ) == "correct"


class TestBehaviorMatching:
    def test_overlap_accepts_a_reworded_match(self) -> None:
        assert judge_field(
            "behavior", "child asks for juice", "asks for juice",
            behavior_match="overlap", threshold=0.5,
        ) == "correct"

    def test_overlap_rejects_a_different_behaviour(self) -> None:
        assert judge_field(
            "behavior", "child asks for juice", "stacks blocks quietly",
            behavior_match="overlap", threshold=0.5,
        ) == "incorrect"

    def test_exact_matching_rejects_rewording(self) -> None:
        assert judge_field(
            "behavior", "child asks for juice", "asks for juice",
            behavior_match="exact", threshold=0.5,
        ) == "incorrect"

    def test_excluding_behavior_drops_it_from_the_scored_fields(self) -> None:
        report = score(
            _gold_payload(s1=GOLD),
            _batch(["m1"], s1={"m1": GOLD}),
            behavior_match="excluded",
            threshold=0.5,
        )

        assert "behavior" not in report["scoring_fields"]
        # Still judged and recorded -- excluded from scoring, not from evidence.
        assert "behavior" in report["gold"]["s1"]["m1"]


class TestCommonReference:
    def test_every_generator_is_scored_against_the_same_gold(self) -> None:
        report = score(
            _gold_payload(s1=GOLD),
            _batch(
                ["m1", "m2"],
                s1={"m1": GOLD, "m2": {**GOLD, "domain": "play"}},
            ),
            behavior_match="overlap",
            threshold=0.5,
        )
        accuracy = per_model_accuracy(
            report["gold"], report["models"], report["scoring_fields"]
        )

        assert accuracy["m1"] == pytest.approx(1.0)
        assert accuracy["m2"] == pytest.approx(0.0)

    def test_the_oracle_ceiling_comes_out_over_the_common_set(self) -> None:
        report = score(
            _gold_payload(s1=GOLD, s2=GOLD),
            _batch(
                ["m1", "m2"],
                s1={"m1": GOLD, "m2": {**GOLD, "domain": "play"}},
                s2={"m1": {**GOLD, "outcome": "partial"}, "m2": GOLD},
            ),
            behavior_match="overlap",
            threshold=0.5,
        )
        fields = report["scoring_fields"]

        assert per_model_accuracy(report["gold"], ["m1"], fields)["m1"] == pytest.approx(0.5)
        assert per_model_accuracy(report["gold"], ["m2"], fields)["m2"] == pytest.approx(0.5)
        # Neither model alone is right on both, but one of them is right on each.
        assert oracle_ceiling(report["gold"], ["m1", "m2"], fields) == pytest.approx(1.0)

    def test_a_missing_candidate_scores_as_missing_not_as_absent(self) -> None:
        report = score(
            _gold_payload(s1=GOLD),
            _batch(["m1", "m2"], s1={"m1": GOLD}),
            behavior_match="overlap",
            threshold=0.5,
        )

        assert set(report["gold"]["s1"]) == {"m1", "m2"}
        assert report["gold"]["s1"]["m2"]["domain"] == "missing"

    def test_gold_for_a_segment_outside_the_batch_is_reported_not_dropped(self) -> None:
        report = score(
            _gold_payload(s1=GOLD, ghost=GOLD),
            _batch(["m1"], s1={"m1": GOLD}),
            behavior_match="overlap",
            threshold=0.5,
        )

        assert report["n_segments_scored"] == 1
        assert report["gold_segments_absent_from_batch"] == ["ghost"]
