"""Tests for the inter-annotator agreement computation.

Kappa is the number the annotation protocol is reported on, so its edge cases
matter more than its happy path -- particularly the ones where a naive
implementation silently returns something plausible but wrong.
"""

from __future__ import annotations

import pytest

from tests.eval.extraction.agreement_report import (
    MismatchedAnnotationItemsError,
    build_report,
    cohens_kappa,
    expected_agreement,
    observed_agreement,
    paired_judgments,
)
from tests.eval.extraction.annotate_batch import annotation_key


def _annotations(**segments: dict) -> dict:
    return {
        segment_id: {"field_judgments": judgments}
        for segment_id, judgments in segments.items()
    }


class TestCohensKappa:
    def test_perfect_agreement_is_one(self) -> None:
        pairs = [("correct", "correct"), ("incorrect", "incorrect")]

        assert cohens_kappa(pairs) == pytest.approx(1.0)

    def test_chance_level_agreement_is_zero(self) -> None:
        """Two annotators agreeing exactly as often as their marginals predict
        have demonstrated no reliability."""
        pairs = [
            ("correct", "correct"),
            ("correct", "incorrect"),
            ("incorrect", "correct"),
            ("incorrect", "incorrect"),
        ]

        assert cohens_kappa(pairs) == pytest.approx(0.0)

    def test_systematic_disagreement_is_negative(self) -> None:
        pairs = [("correct", "incorrect"), ("incorrect", "correct")]

        assert cohens_kappa(pairs) < 0

    def test_matches_the_formula_on_a_worked_case(self) -> None:
        pairs = [
            *[("correct", "correct")] * 6,
            *[("correct", "incorrect")] * 2,
            *[("incorrect", "correct")] * 1,
            *[("incorrect", "incorrect")] * 1,
        ]
        p_o = 7 / 10
        p_e = (8 / 10) * (7 / 10) + (2 / 10) * (3 / 10)

        assert observed_agreement(pairs) == pytest.approx(p_o)
        assert expected_agreement(pairs) == pytest.approx(p_e)
        assert cohens_kappa(pairs) == pytest.approx((p_o - p_e) / (1 - p_e))

    def test_single_category_is_undefined_not_perfect(self) -> None:
        """Both annotators labelling everything the same way leaves no room to
        measure agreement beyond chance. Returning 1.0 would overstate
        reliability; returning 0.0 would understate it."""
        pairs = [("correct", "correct")] * 20

        assert cohens_kappa(pairs) is None

    def test_no_pairs_is_undefined(self) -> None:
        assert cohens_kappa([]) is None

    def test_high_but_imperfect_agreement_is_penalised_by_skew(self) -> None:
        """The property kappa exists for: 90% raw agreement on a heavily skewed
        distribution is much weaker evidence than 90% on a balanced one."""
        skewed = [
            *[("correct", "correct")] * 18,
            ("correct", "incorrect"),
            ("incorrect", "correct"),
        ]
        balanced = [
            *[("correct", "correct")] * 9,
            *[("incorrect", "incorrect")] * 9,
            ("correct", "incorrect"),
            ("incorrect", "correct"),
        ]

        assert observed_agreement(skewed) == pytest.approx(observed_agreement(balanced))
        assert cohens_kappa(skewed) < cohens_kappa(balanced)


class TestPairing:
    def test_only_shared_segments_are_paired(self) -> None:
        first = _annotations(s1={"domain": "correct"}, s2={"domain": "incorrect"})
        second = _annotations(s2={"domain": "incorrect"}, s3={"domain": "correct"})

        assert paired_judgments(first, second, "domain") == [("incorrect", "incorrect")]

    def test_a_field_missing_from_one_annotator_is_skipped(self) -> None:
        first = _annotations(s1={"domain": "correct", "outcome": "correct"})
        second = _annotations(s1={"domain": "correct"})

        assert paired_judgments(first, second, "outcome") == []


class TestReport:
    def test_reports_overlap_and_exclusive_counts(self) -> None:
        first = _annotations(
            s1={"domain": "correct"}, s2={"domain": "correct"}, s3={"domain": "correct"}
        )
        second = _annotations(s2={"domain": "correct"}, s4={"domain": "correct"})

        report = build_report(first, second)

        assert report["n_overlap_segments"] == 1
        assert report["n_annotator_a_only"] == 2
        assert report["n_annotator_b_only"] == 1

    def test_disputed_segments_are_listed_for_adjudication(self) -> None:
        """An unadjudicated disagreement is not a label, so it must be findable."""
        first = _annotations(
            s1={"domain": "correct", "outcome": "correct"},
            s2={"domain": "correct", "outcome": "correct"},
        )
        second = _annotations(
            s1={"domain": "correct", "outcome": "hallucinated"},
            s2={"domain": "correct", "outcome": "correct"},
        )

        report = build_report(first, second)

        assert report["n_disputed_segments"] == 1
        assert report["disputed_segments"] == ["s1"]

    def test_undefined_kappa_is_reported_not_hidden(self) -> None:
        first = _annotations(s1={"domain": "correct"}, s2={"domain": "correct"})
        second = _annotations(s1={"domain": "correct"}, s2={"domain": "correct"})

        report = build_report(first, second)

        assert report["per_field"]["domain"]["kappa"] is None
        assert report["per_field"]["domain"]["interpretation"] == "undefined"

    def test_fields_with_no_overlap_report_n_zero(self) -> None:
        report = build_report(_annotations(s1={"domain": "correct"}), _annotations())

        assert report["per_field"]["outcome"]["n"] == 0
        assert report["per_field"]["outcome"]["kappa"] is None


class TestBatchAssignment:
    """The annotation tool must keep the two annotators independent."""

    def _batch(self) -> dict:
        return {
            "models": ["llama3.2:latest"],
            "assignments": {"annotator_a": ["s1", "s2"], "annotator_b": ["s2", "s3"]},
            "candidates": [
                {"segment_id": s, "child_id": "carl", "corpus": "rollins",
                 "chat_text": "*CHI:\tbus .",
                 "candidates": {"llama3.2:latest": {"extracted_fields": {}}}}
                for s in ("s1", "s2", "s3")
            ],
        }

    def test_each_annotator_sees_only_their_assignment(self) -> None:
        from tests.eval.extraction.annotate_batch import assigned_candidates

        batch = self._batch()
        a = [c["segment_id"] for c in assigned_candidates(batch, "annotator_a")]
        b = [c["segment_id"] for c in assigned_candidates(batch, "annotator_b")]

        assert a == ["s1", "s2"]
        assert b == ["s2", "s3"]

    def test_the_overlap_is_what_kappa_is_computed_on(self) -> None:
        from tests.eval.extraction.annotate_batch import assigned_candidates

        batch = self._batch()
        a = {c["segment_id"] for c in assigned_candidates(batch, "annotator_a")}
        b = {c["segment_id"] for c in assigned_candidates(batch, "annotator_b")}

        assert a & b == {"s2"}

    def test_an_unknown_annotator_is_rejected(self) -> None:
        from tests.eval.extraction.annotate_batch import assigned_candidates

        with pytest.raises(SystemExit, match="no assignment"):
            assigned_candidates(self._batch(), "annotator_c")

    def test_annotators_write_to_separate_files(self) -> None:
        """Otherwise the second annotator overwrites the first and no
        independent judgment survives to compare."""
        from tests.eval.extraction.annotate_batch import annotations_path

        assert annotations_path("annotator_a") != annotations_path("annotator_b")

    def test_multi_model_batch_requires_an_explicit_choice(self) -> None:
        """Judging several models in one pass would make the labels ambiguous."""
        from tests.eval.extraction.annotate_batch import choose_model

        batch = self._batch() | {"models": ["llama3.2:latest", "qwen2.5:latest"]}

        with pytest.raises(SystemExit, match="Pass --model"):
            choose_model(batch, None)
        assert choose_model(batch, "qwen2.5:latest") == "qwen2.5:latest"

    def test_single_model_batch_needs_no_choice(self) -> None:
        from tests.eval.extraction.annotate_batch import choose_model

        assert choose_model(self._batch(), None) == "llama3.2:latest"


def _model_annotations(*items: tuple[str, str, dict]) -> dict:
    """Annotations keyed the way annotate_batch writes them."""
    return {
        annotation_key(segment_id, model): {
            "segment_id": segment_id,
            "model": model,
            "field_judgments": judgments,
        }
        for segment_id, model, judgments in items
    }


class TestModelAwareness:
    """A judgement is about one model's output, not about a segment.

    Keying on segment alone let a second generator's pass be skipped as
    already-done, and let two annotators' files pair across different models.
    """

    def test_the_same_segment_under_two_models_is_two_items(self) -> None:
        first = _model_annotations(
            ("s1", "model_a", {"domain": "correct"}),
            ("s1", "model_b", {"domain": "incorrect"}),
        )
        report = build_report(first, first)

        assert report["n_overlap_segments"] == 2
        assert sorted(report["per_model"]) == ["model_a", "model_b"]

    def test_kappa_is_reported_per_generator(self) -> None:
        judged = _model_annotations(
            ("s1", "model_a", {"domain": "correct"}),
            ("s2", "model_a", {"domain": "incorrect"}),
            ("s1", "model_b", {"domain": "correct"}),
            ("s2", "model_b", {"domain": "incorrect"}),
        )
        report = build_report(judged, judged)

        assert report["per_model"]["model_a"]["n_items"] == 2
        assert report["per_model"]["model_a"]["per_field"]["domain"]["n"] == 2

    def test_pairing_different_models_under_one_key_is_refused(self) -> None:
        first = {"s1::model_a": {"model": "model_a", "field_judgments": {"domain": "correct"}}}
        second = {"s1::model_a": {"model": "model_b", "field_judgments": {"domain": "correct"}}}

        with pytest.raises(MismatchedAnnotationItemsError):
            build_report(first, second)

    def test_a_disputed_item_names_the_model(self) -> None:
        first = _model_annotations(("s1", "model_a", {"domain": "correct"}))
        second = _model_annotations(("s1", "model_a", {"domain": "hallucinated"}))
        report = build_report(first, second)

        assert report["disputed_segments"] == ["s1::model_a"]
