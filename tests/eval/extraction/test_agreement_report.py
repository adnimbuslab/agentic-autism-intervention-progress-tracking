"""Tests for the inter-annotator agreement computation.

Kappa is the number the annotation protocol is reported on, so its edge cases
matter more than its happy path -- particularly the ones where a naive
implementation silently returns something plausible but wrong.
"""

from __future__ import annotations

import pytest

from tests.eval.extraction.agreement_report import (
    build_report,
    cohens_kappa,
    expected_agreement,
    observed_agreement,
    paired_values,
    token_overlap,
)


def _annotations(**segments: dict) -> dict:
    """Gold annotations: field values authored from the transcript."""
    return {
        segment_id: {"segment_id": segment_id, "field_values": values}
        for segment_id, values in segments.items()
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
        first = _annotations(s1={"domain": "language"}, s2={"domain": "play"})
        second = _annotations(s2={"domain": "play"}, s3={"domain": "language"})

        assert paired_values(first, second, "domain") == [("play", "play")]

    def test_a_field_missing_from_one_annotator_is_skipped(self) -> None:
        first = _annotations(s1={"domain": "language", "outcome": "correct"})
        second = _annotations(s1={"domain": "language"})

        assert paired_values(first, second, "outcome") == []

    def test_case_and_spacing_do_not_manufacture_disagreement(self) -> None:
        first = _annotations(s1={"domain": "Social_Communication"})
        second = _annotations(s1={"domain": "social_communication "})

        assert observed_agreement(paired_values(first, second, "domain")) == 1.0


class TestNullsAreACategory:
    """A null gold value is a claim about the transcript, not missing data."""

    def test_two_nulls_agree(self) -> None:
        first = _annotations(s1={"prompt_level": None})
        second = _annotations(s1={"prompt_level": None})

        assert observed_agreement(paired_values(first, second, "prompt_level")) == 1.0

    def test_a_null_against_a_value_disagrees(self) -> None:
        first = _annotations(s1={"prompt_level": None})
        second = _annotations(s1={"prompt_level": "verbal"})

        assert observed_agreement(paired_values(first, second, "prompt_level")) == 0.0

    def test_a_recorded_null_pairs_but_an_unreached_field_does_not(self) -> None:
        first = _annotations(s1={"outcome": None})
        second_recorded = _annotations(s1={"outcome": None})
        second_unreached = _annotations(s1={})

        assert len(paired_values(first, second_recorded, "outcome")) == 1
        assert paired_values(first, second_unreached, "outcome") == []


class TestFreeTextBehaviour:
    def test_token_overlap_rewards_shared_wording(self) -> None:
        assert token_overlap("child asks for juice", "child asks for juice") == 1.0
        assert token_overlap("child asks for juice", "asks for juice") > 0.5
        assert token_overlap("child asks for juice", "stacks blocks quietly") == 0.0

    def test_behavior_is_reported_without_a_kappa(self) -> None:
        first = _annotations(s1={"behavior": "asks for juice"})
        second = _annotations(s1={"behavior": "asks for the juice"})
        report = build_report(first, second)["per_field"]["behavior"]

        assert report["kappa"] is None
        assert report["interpretation"] == "not applicable (free text)"
        assert report["mean_token_overlap"] > 0.0

    def test_behavior_is_excluded_from_the_mean_kappa(self) -> None:
        values = {"domain": "language", "modality": "verbal",
                  "prompt_level": "independent", "outcome": "correct"}
        first = _annotations(s1={**values, "behavior": "asks for juice"},
                             s2={**values, "domain": "play", "behavior": "x"})
        second = _annotations(s1={**values, "behavior": "totally different words"},
                              s2={**values, "domain": "play", "behavior": "y"})
        overall = build_report(first, second)["overall"]

        assert overall["fields_in_mean"] == ["domain", "modality", "prompt_level", "outcome"]
        assert "behavior" not in overall["fields_in_mean"]


class TestReport:
    def test_reports_overlap_and_exclusive_counts(self) -> None:
        first = _annotations(
            s1={"domain": "language"}, s2={"domain": "play"}, s3={"domain": "motor"}
        )
        second = _annotations(s2={"domain": "play"}, s4={"domain": "language"})
        report = build_report(first, second)

        assert report["n_overlap_segments"] == 1
        assert report["n_annotator_a_only"] == 2
        assert report["n_annotator_b_only"] == 1

    def test_disputed_segments_are_listed_for_adjudication(self) -> None:
        first = _annotations(s1={"domain": "language"}, s2={"domain": "play"})
        second = _annotations(s1={"domain": "language"}, s2={"domain": "motor"})
        report = build_report(first, second)

        assert report["disputed_segments"] == ["s2"]
        assert report["n_disputed_segments"] == 1

    def test_kappa_is_not_pooled_across_fields(self) -> None:
        """Fields use different category sets; a pooled correction is meaningless."""
        first = _annotations(s1={"modality": "verbal", "prompt_level": "verbal"})
        second = _annotations(s1={"modality": "verbal", "prompt_level": "verbal"})
        report = build_report(first, second)

        assert set(report["per_field"]) == {
            "domain", "behavior", "modality", "prompt_level", "outcome"
        }
        assert "pooled_kappa" not in report["overall"]
        assert report["overall"]["fields_in_mean"] == [
            "domain", "modality", "prompt_level", "outcome"
        ]

    def test_record_exact_agreement_counts_whole_records(self) -> None:
        complete = {"domain": "language", "behavior": "asks", "modality": "verbal",
                    "prompt_level": "independent", "outcome": "correct"}
        first = _annotations(s1=complete, s2=complete)
        second = _annotations(s1=complete, s2={**complete, "outcome": "partial"})
        report = build_report(first, second)

        assert report["overall"]["record_exact_agreement"] == 0.5

    def test_undefined_kappa_is_reported_not_hidden(self) -> None:
        """Every annotator picked one category: no room to measure beyond chance."""
        first = _annotations(s1={"domain": "language"}, s2={"domain": "language"})
        second = _annotations(s1={"domain": "language"}, s2={"domain": "language"})
        report = build_report(first, second)

        assert report["per_field"]["domain"]["kappa"] is None
        assert report["per_field"]["domain"]["interpretation"] == "undefined"

    def test_fields_with_no_overlap_report_n_zero(self) -> None:
        first = _annotations(s1={"domain": "language"})
        second = _annotations(s1={"domain": "language"})
        report = build_report(first, second)

        assert report["per_field"]["outcome"]["n"] == 0
