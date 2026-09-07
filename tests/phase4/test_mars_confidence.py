"""MARS confidence composition.

Covers MARS-022 (two quantities preserved distinctly), MARS-023 (selection
confidence derived without generator confidence) and MARS-032 (control
confidence is their conservative combination).

Confidence is descriptive, not authoritative. Nothing here selects a candidate,
overrides the agreement gate, or decides whether a result may be returned.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.mars.agreement import (
    AgreementDecision,
    AgreementFailure,
)
from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.extraction.mars.confidence import (
    GeneratorConfidencePolicy,
    MarsConfidence,
    aggregate_generator_confidence,
    compose_confidence,
    derive_selection_confidence,
)
from src.backend.ml.extraction.mars.safety import MarsAbstentionReason
from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)

MIN = GeneratorConfidencePolicy.MINIMUM


def _obs(behavior: str, confidence: float | None) -> StructuredObservation:
    return StructuredObservation(
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2026, 9, 7),
        setting=Setting.CLINIC,
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior=behavior,
        modality=Modality.GESTURAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=confidence,
    )


def _result(model: str, behavior: str, confidence: float | None) -> ExtractionResult:
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[_obs(behavior, confidence)],
        provider="test_provider",
        model=model,
        prompt_version="1.0",
    )


def _decision(
    support: float | None,
    *,
    passed: bool = True,
    valid_judge_count: int = 3,
    failure: AgreementFailure | None = None,
) -> AgreementDecision:
    return AgreementDecision(
        passed=passed,
        provisional_internal_id="cand_1",
        valid_judge_count=valid_judge_count,
        first_choice_support=support,
        is_modal_first_choice=passed,
        modal_internal_ids=["cand_1"] if passed else [],
        threshold=0.5,
        failure=failure,
        reason_code=(
            MarsAbstentionReason.JUDGE_DISAGREEMENT if failure and not passed else None
        ),
    )


class TestSelectionConfidence:
    """MARS-023: derived from judge evidence, never from generator confidence."""

    # @spec MARS-023
    @pytest.mark.parametrize("support", [0.0, 1 / 3, 0.5, 2 / 3, 1.0])
    def test_selection_confidence_is_the_top_choice_support(self, support: float) -> None:
        """No weighting, no free parameter — the agreement statistic itself."""
        assert derive_selection_confidence(_decision(support)) == pytest.approx(support)

    # @spec MARS-023
    def test_generator_confidence_cannot_influence_it(self) -> None:
        """The signature admits no generator input at all, so the independence
        is structural rather than promised."""
        import inspect

        params = set(inspect.signature(derive_selection_confidence).parameters)

        assert "generator_confidence" not in params
        assert params == {"agreement"}

    # @spec MARS-023
    def test_absent_judge_evidence_yields_none_not_zero(self) -> None:
        """Unknown is not the same claim as "no confidence"."""
        assert derive_selection_confidence(_decision(None, valid_judge_count=0)) is None

    # @spec MARS-023
    @pytest.mark.parametrize("support", [0.0, 0.5, 1.0])
    def test_bounded_to_the_unit_interval(self, support: float) -> None:
        value = derive_selection_confidence(_decision(support))

        assert value is not None
        assert 0.0 <= value <= 1.0


class TestGeneratorConfidenceAggregation:
    """A merged candidate carries one confidence per contributing generator."""

    # @spec MARS-022
    def test_policy_is_required(self) -> None:
        """The aggregation rule for merged candidates is not fixed by any MARS
        requirement, so there is no default to fall back on."""
        candidate = build_candidates([_result("model_a", "A", 0.8)])[0]

        with pytest.raises(TypeError):
            aggregate_generator_confidence(candidate)  # type: ignore[call-arg]

    # @spec MARS-022
    def test_single_generator_returns_its_own_confidence(self) -> None:
        candidate = build_candidates([_result("model_a", "A", 0.82)])[0]

        assert aggregate_generator_confidence(candidate, policy=MIN) == pytest.approx(0.82)

    # @spec MARS-022
    @pytest.mark.parametrize(
        ("policy", "expected"),
        [
            (GeneratorConfidencePolicy.MINIMUM, 0.82),
            (GeneratorConfidencePolicy.MAXIMUM, 0.91),
            (GeneratorConfidencePolicy.MEAN, (0.82 + 0.91) / 2),
        ],
    )
    def test_each_policy_is_explicit_and_pinned(
        self, policy: GeneratorConfidencePolicy, expected: float
    ) -> None:
        candidate = build_candidates(
            [_result("model_a", "A", 0.82), _result("model_b", "A", 0.91)]
        )[0]

        assert candidate.multiplicity == 2
        assert aggregate_generator_confidence(candidate, policy=policy) == pytest.approx(
            expected
        )

    # @spec MARS-022
    def test_no_reported_confidence_yields_none(self) -> None:
        candidate = build_candidates([_result("model_a", "A", None)])[0]

        assert aggregate_generator_confidence(candidate, policy=MIN) is None

    # @spec MARS-022
    def test_partial_reporting_uses_only_the_present_values(self) -> None:
        candidate = build_candidates(
            [_result("model_a", "A", None), _result("model_b", "A", 0.7)]
        )[0]

        assert aggregate_generator_confidence(candidate, policy=MIN) == pytest.approx(0.7)

    # @spec MARS-021, MARS-022
    def test_multiplicity_does_not_inflate_confidence(self) -> None:
        """Three generators agreeing at 0.8 is still 0.8, not more."""
        one = build_candidates([_result("model_a", "A", 0.8)])[0]
        three = build_candidates(
            [
                _result("model_a", "A", 0.8),
                _result("model_b", "A", 0.8),
                _result("model_c", "A", 0.8),
            ]
        )[0]

        assert three.multiplicity == 3
        assert aggregate_generator_confidence(three, policy=MIN) == aggregate_generator_confidence(
            one, policy=MIN
        )


class TestControlConfidence:
    """MARS-032: the conservative combination, initially the minimum."""

    # @spec MARS-032
    @pytest.mark.parametrize(
        ("generator", "selection", "expected"),
        [
            (0.95, 0.35, 0.35),
            (0.35, 0.95, 0.35),
            (0.80, 0.80, 0.80),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 1.0),
        ],
    )
    def test_control_confidence_is_the_minimum(
        self, generator: float, selection: float, expected: float
    ) -> None:
        candidate = build_candidates([_result("model_a", "A", generator)])[0]

        confidence = compose_confidence(
            candidate=candidate,
            agreement=_decision(selection),
            generator_policy=MIN,
        )

        assert confidence.control_confidence == pytest.approx(expected)

    # @spec MARS-022, MARS-032
    def test_both_quantities_are_preserved_distinctly(self) -> None:
        candidate = build_candidates([_result("model_a", "A", 0.95)])[0]

        confidence = compose_confidence(
            candidate=candidate, agreement=_decision(0.35), generator_policy=MIN
        )

        assert confidence.generator_confidence == pytest.approx(0.95)
        assert confidence.mars_selection_confidence == pytest.approx(0.35)
        assert confidence.control_confidence == pytest.approx(0.35)
        assert confidence.generator_confidence != confidence.control_confidence

    # @spec MARS-032
    def test_neither_quantity_is_written_alone(self) -> None:
        """A high generator confidence never reaches control confidence intact
        when selection confidence is lower, and vice versa."""
        candidate = build_candidates([_result("model_a", "A", 0.99)])[0]

        confidence = compose_confidence(
            candidate=candidate, agreement=_decision(0.10), generator_policy=MIN
        )

        assert confidence.control_confidence != confidence.generator_confidence
        assert confidence.control_confidence == confidence.mars_selection_confidence

    # @spec MARS-032
    @pytest.mark.parametrize(
        ("generator", "selection"),
        [(None, 0.9), (0.9, None), (None, None)],
    )
    def test_missing_evidence_yields_none_not_zero(
        self, generator: float | None, selection: float | None
    ) -> None:
        """MARS-032 forbids writing either quantity alone, so an absent input
        leaves control confidence unknown rather than asserting zero — which
        would be a false claim that MARS measured no confidence."""
        candidate = build_candidates([_result("model_a", "A", generator)])[0]

        confidence = compose_confidence(
            candidate=candidate,
            agreement=_decision(selection, valid_judge_count=0 if selection is None else 3),
            generator_policy=MIN,
        )

        assert confidence.control_confidence is None

    # @spec MARS-032
    def test_control_confidence_stays_in_the_unit_interval(self) -> None:
        candidate = build_candidates([_result("model_a", "A", 1.0)])[0]

        confidence = compose_confidence(
            candidate=candidate, agreement=_decision(1.0), generator_policy=MIN
        )

        assert 0.0 <= confidence.control_confidence <= 1.0


class TestConfidenceIsDescriptiveOnly:
    """Confidence composes a signal. It decides nothing."""

    # @spec MARS-032
    def test_failed_agreement_is_not_overridden(self) -> None:
        """A perfect generator confidence cannot rescue a rejected candidate."""
        candidate = build_candidates([_result("model_a", "A", 1.0)])[0]
        rejected = _decision(
            0.2, passed=False, failure=AgreementFailure.BELOW_THRESHOLD
        )

        confidence = compose_confidence(
            candidate=candidate, agreement=rejected, generator_policy=MIN
        )

        assert not rejected.passed
        assert confidence.agreement_passed is False
        assert confidence.control_confidence == pytest.approx(0.2)

    # @spec MARS-032
    def test_result_carries_no_candidate_or_decision(self) -> None:
        """Nothing on the confidence object could be mistaken for a selection or
        a permission to return."""
        fields = set(MarsConfidence.model_fields)

        assert fields.isdisjoint({"observation", "candidate", "passed", "status"})

    # @spec MARS-032
    def test_composition_does_not_mutate_the_agreement_decision(self) -> None:
        candidate = build_candidates([_result("model_a", "A", 0.5)])[0]
        agreement = _decision(0.9)
        before = agreement.model_dump()

        compose_confidence(
            candidate=candidate, agreement=agreement, generator_policy=MIN
        )

        assert agreement.model_dump() == before


class TestDeterminism:
    """Identical inputs, identical output."""

    # @spec MARS-032
    def test_composition_is_reproducible(self) -> None:
        candidate = build_candidates(
            [_result("model_a", "A", 0.7), _result("model_b", "A", 0.9)]
        )[0]

        first = compose_confidence(
            candidate=candidate, agreement=_decision(0.8), generator_policy=MIN
        )
        second = compose_confidence(
            candidate=candidate, agreement=_decision(0.8), generator_policy=MIN
        )

        assert first == second

    # @spec MARS-022
    def test_generator_order_does_not_change_aggregation(self) -> None:
        forward = build_candidates(
            [_result("model_a", "A", 0.7), _result("model_b", "A", 0.9)]
        )[0]
        reverse = build_candidates(
            [_result("model_b", "A", 0.9), _result("model_a", "A", 0.7)]
        )[0]

        for policy in GeneratorConfidencePolicy:
            assert aggregate_generator_confidence(
                forward, policy=policy
            ) == pytest.approx(aggregate_generator_confidence(reverse, policy=policy))
