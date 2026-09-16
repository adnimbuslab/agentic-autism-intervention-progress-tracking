"""Tests for the MARS evaluation metrics.

These numbers go into the manuscript, so the edge cases that would silently
produce a plausible-but-wrong figure matter more than the happy path.
"""

from __future__ import annotations

import pytest

from tests.eval.extraction.mars_evaluation import (
    build_evaluation,
    is_fully_correct,
    mars_accuracy,
    oracle_capture_rate,
    oracle_ceiling,
    per_model_accuracy,
)

MODELS = ["model_a", "model_b", "model_c"]


def _judgments(*, all_correct: bool = True, **overrides: str) -> dict[str, str]:
    base = dict.fromkeys(
        ["domain", "behavior", "modality", "prompt_level", "outcome"],
        "correct" if all_correct else "incorrect",
    )
    base.update(overrides)
    return base


class TestFullCorrectness:
    def test_all_correct_counts(self) -> None:
        assert is_fully_correct(_judgments())

    def test_correctly_null_counts_as_acceptable(self) -> None:
        assert is_fully_correct(_judgments(outcome="correctly_null"))

    @pytest.mark.parametrize("bad", ["incorrect", "hallucinated", "missing"])
    def test_one_bad_field_fails_the_whole_record(self, bad: str) -> None:
        """MARS selects whole candidates, so whole-record correctness is the
        unit that matches what the system returns."""
        assert not is_fully_correct(_judgments(outcome=bad))

    def test_hallucinated_and_missing_are_both_failures(self) -> None:
        """One invents unsupported evidence, the other omits supported
        evidence; neither is a usable record."""
        assert not is_fully_correct(_judgments(domain="hallucinated"))
        assert not is_fully_correct(_judgments(domain="missing"))

    def test_empty_judgments_are_not_correct(self) -> None:
        assert not is_fully_correct({})


class TestGeneratorAccuracyAndCeiling:
    def _gold(self) -> dict:
        return {
            # only A correct
            "s1": {"model_a": _judgments(), "model_b": _judgments(all_correct=False),
                   "model_c": _judgments(all_correct=False)},
            # only B correct
            "s2": {"model_a": _judgments(all_correct=False), "model_b": _judgments(),
                   "model_c": _judgments(all_correct=False)},
            # none correct
            "s3": {m: _judgments(all_correct=False) for m in MODELS},
            # all correct
            "s4": {m: _judgments() for m in MODELS},
        }

    def test_per_model_accuracy(self) -> None:
        accuracy = per_model_accuracy(self._gold(), MODELS)

        assert accuracy["model_a"] == pytest.approx(0.5)
        assert accuracy["model_b"] == pytest.approx(0.5)
        assert accuracy["model_c"] == pytest.approx(0.25)

    def test_oracle_exceeds_every_single_generator(self) -> None:
        """The ceiling counts a segment when *any* generator got it right, so
        complementary errors raise it above the best individual model."""
        gold = self._gold()

        assert oracle_ceiling(gold, MODELS) == pytest.approx(0.75)
        assert oracle_ceiling(gold, MODELS) > max(
            a for a in per_model_accuracy(gold, MODELS).values() if a is not None
        )

    def test_a_model_missing_from_a_segment_is_not_counted_against_it(self) -> None:
        gold = {"s1": {"model_a": _judgments()}, "s2": {"model_b": _judgments()}}

        accuracy = per_model_accuracy(gold, MODELS)

        assert accuracy["model_a"] == pytest.approx(1.0)
        assert accuracy["model_c"] is None

    def test_empty_gold_yields_no_ceiling(self) -> None:
        assert oracle_ceiling({}, MODELS) is None


class TestCaptureRate:
    def test_matches_the_worked_example(self) -> None:
        assert oracle_capture_rate(0.82, 0.75, 0.88) == pytest.approx(7 / 13)

    def test_capturing_everything_is_one(self) -> None:
        assert oracle_capture_rate(0.88, 0.75, 0.88) == pytest.approx(1.0)

    def test_capturing_nothing_is_zero(self) -> None:
        assert oracle_capture_rate(0.75, 0.75, 0.88) == pytest.approx(0.0)

    def test_reranking_worse_than_the_best_generator_is_negative(self) -> None:
        assert oracle_capture_rate(0.70, 0.75, 0.88) < 0

    def test_no_headroom_is_undefined_not_zero(self) -> None:
        """When the oracle equals the best generator there was nothing for
        reranking to capture; a number here would invent a result."""
        assert oracle_capture_rate(0.75, 0.75, 0.75) is None

    @pytest.mark.parametrize(
        ("mars", "best", "oracle"), [(None, 0.7, 0.8), (0.7, None, 0.8), (0.7, 0.8, None)]
    )
    def test_any_missing_input_is_undefined(self, mars, best, oracle) -> None:
        assert oracle_capture_rate(mars, best, oracle) is None


class TestMarsAccuracy:
    def _gold(self) -> dict:
        return {
            "s1": {"model_a": _judgments(), "model_b": _judgments(all_correct=False)},
            "s2": {"model_a": _judgments(all_correct=False), "model_b": _judgments()},
            "s3": {"model_a": _judgments(all_correct=False),
                   "model_b": _judgments(all_correct=False)},
        }

    def test_accuracy_over_returned_excludes_abstentions(self) -> None:
        outcomes = {
            "s1": {"status": "success", "selected_generator_ids": ["model_a"]},
            "s2": {"status": "success", "selected_generator_ids": ["model_b"]},
            "s3": {"status": "abstained", "reason_code": "judge_disagreement"},
        }

        result = mars_accuracy(self._gold(), outcomes)

        assert result["accuracy_over_returned"] == pytest.approx(1.0)
        assert result["accuracy_over_all"] == pytest.approx(2 / 3)
        assert result["coverage"] == pytest.approx(2 / 3)

    def test_abstention_reasons_are_broken_out(self) -> None:
        outcomes = {
            "s1": {"status": "abstained", "reason_code": "judge_disagreement"},
            "s2": {"status": "abstained", "reason_code": "judge_disagreement"},
            "s3": {"status": "abstained", "reason_code": "integrity_failure"},
        }

        result = mars_accuracy(self._gold(), outcomes)

        assert result["abstention_reasons"] == {
            "judge_disagreement": 2,
            "integrity_failure": 1,
        }
        assert result["accuracy_over_returned"] is None

    def test_abstaining_on_everything_hard_inflates_returned_accuracy(self) -> None:
        """The reason both figures are reported: perfect accuracy on 1 of 3
        segments is not a better system than 2 of 3 correct."""
        outcomes = {
            "s1": {"status": "success", "selected_generator_ids": ["model_a"]},
            "s2": {"status": "abstained", "reason_code": "judge_disagreement"},
            "s3": {"status": "abstained", "reason_code": "judge_disagreement"},
        }

        result = mars_accuracy(self._gold(), outcomes)

        assert result["accuracy_over_returned"] == pytest.approx(1.0)
        assert result["accuracy_over_all"] == pytest.approx(1 / 3)
        assert result["coverage"] == pytest.approx(1 / 3)

    def test_a_merged_candidate_resolves_through_any_of_its_generators(self) -> None:
        """Deduplicated candidates carry several generators that produced
        identical fields, so any of them supplies the same judgment."""
        gold = {"s1": {"model_b": _judgments()}}
        outcomes = {
            "s1": {"status": "success", "selected_generator_ids": ["model_a", "model_b"]}
        }

        assert mars_accuracy(gold, outcomes)["accuracy_over_returned"] == pytest.approx(1.0)

    def test_a_selection_with_no_gold_label_is_not_counted_correct(self) -> None:
        outcomes = {
            "s9": {"status": "success", "selected_generator_ids": ["model_a"]}
        }

        assert mars_accuracy(self._gold(), outcomes)["accuracy_over_returned"] == 0.0


class TestFullReport:
    def test_reports_all_four_headline_numbers(self) -> None:
        gold = {
            "s1": {"model_a": _judgments(), "model_b": _judgments(all_correct=False)},
            "s2": {"model_a": _judgments(all_correct=False), "model_b": _judgments()},
            "s3": {"model_a": _judgments(), "model_b": _judgments()},
            "s4": {"model_a": _judgments(all_correct=False),
                   "model_b": _judgments(all_correct=False)},
        }
        outcomes = {
            s: {"status": "success", "selected_generator_ids": ["model_a"]}
            for s in ("s1", "s2", "s3", "s4")
        }

        report = build_evaluation(gold, ["model_a", "model_b"], outcomes)

        assert report["best_generator_accuracy"] == pytest.approx(0.5)
        assert report["oracle_ceiling"] == pytest.approx(0.75)
        assert report["mars"]["accuracy_over_returned"] == pytest.approx(0.5)
        assert report["oracle_capture_rate"] == pytest.approx(0.0)

    def test_capture_rate_is_none_when_no_headroom_exists(self) -> None:
        gold = {"s1": {"model_a": _judgments(), "model_b": _judgments()}}
        outcomes = {"s1": {"status": "success", "selected_generator_ids": ["model_a"]}}

        report = build_evaluation(gold, ["model_a", "model_b"], outcomes)

        assert report["oracle_ceiling"] == report["best_generator_accuracy"]
        assert report["oracle_capture_rate"] is None


class TestPartialRunGuard:
    """A MARS metric over part of the batch is a different number wearing the
    same name. The first outcomes file covered 3 of 330 segments and produced
    an accuracy of 0.000 and a capture rate of -3.0 against a best generator of
    0.045 -- figures that read as findings and were noise."""

    def test_the_threshold_is_strict(self) -> None:
        from tests.eval.extraction.mars_evaluation import MIN_OUTCOME_COVERAGE

        assert MIN_OUTCOME_COVERAGE >= 0.95

    def test_a_partial_outcomes_file_is_refused(self, tmp_path) -> None:
        import json
        import subprocess
        import sys
        from pathlib import Path

        import tests.eval.extraction.mars_evaluation as module

        results = Path(module.__file__).parent / "results"
        scored = results / "scored_against_gold.json"
        outcomes = results / "mars_outcomes.json"
        if not scored.exists() or not outcomes.exists():
            pytest.skip("scoring artefacts not produced yet")

        n_gold = len(json.loads(scored.read_text())["gold"])
        n_outcomes = len(json.loads(outcomes.read_text()))
        if n_outcomes / n_gold >= module.MIN_OUTCOME_COVERAGE:
            pytest.skip("outcomes now cover the batch; guard not exercised")

        result = subprocess.run(
            [sys.executable, "-m", "tests.eval.extraction.mars_evaluation"],
            capture_output=True, text=True,
            cwd=Path(module.__file__).parents[4],
        )
        assert result.returncode != 0
        assert "Refusing to report MARS metrics" in result.stdout + result.stderr

    def test_allow_partial_opts_back_in(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        import tests.eval.extraction.mars_evaluation as module

        root = Path(module.__file__).parents[4]
        if not (Path(module.__file__).parent / "results" / "scored_against_gold.json").exists():
            pytest.skip("scoring artefacts not produced yet")
        result = subprocess.run(
            [sys.executable, "-m", "tests.eval.extraction.mars_evaluation",
             "--allow-partial"],
            capture_output=True, text=True, cwd=root,
        )
        assert result.returncode == 0, result.stdout + result.stderr
