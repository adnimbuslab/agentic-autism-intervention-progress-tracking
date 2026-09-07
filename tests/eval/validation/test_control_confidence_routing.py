"""Routing gates read `control_confidence`, not a provider's internal confidence.

Covers VALID-011 and VALID-013 after the EXTRACT-020 migration. The property
under test is that a routing threshold means the same thing regardless of which
provider produced the result: for a provider that generates directly the two
quantities are equal (EXTRACT-022), so existing behavior is unchanged, while a
composing provider supplies a control confidence that combines generator and
selection confidence (MARS-032).
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.schemas import ControlConfidenceState
from src.backend.ml.schemas import RoutingDecision
from src.backend.ml.validation_engine import ValidationEngine
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)


def _observation(confidence: float | None) -> StructuredObservation:
    """A fully-populated, otherwise-clean observation, so confidence is the
    only quantity that can move the routing decision."""
    return StructuredObservation(
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2026, 9, 7),
        setting=Setting.CLINIC,
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior="Child pointed to the requested item",
        modality=Modality.GESTURAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=confidence,
    )


class TestGeneratingProviderBehaviorUnchanged:
    """The migration must be behavior-preserving for single-model providers."""

    # @spec VALID-011, VALID-013
    @pytest.mark.parametrize(
        ("confidence", "expected"),
        [
            (0.39, RoutingDecision.INTERVENTIONIST_REVIEW),
            (0.4, RoutingDecision.RETAIN_WITH_UNKNOWN),
            (0.69, RoutingDecision.RETAIN_WITH_UNKNOWN),
            (0.7, RoutingDecision.ACCEPT),
            (0.95, RoutingDecision.ACCEPT),
        ],
    )
    def test_routing_from_observation_confidence_alone(
        self, confidence: float, expected: RoutingDecision
    ) -> None:
        """Callers that pass no control confidence keep the previous behavior."""
        result = ValidationEngine().validate(_observation(confidence))

        assert result.routing is expected

    # @spec VALID-011, VALID-013, EXTRACT-022
    @pytest.mark.parametrize("confidence", [0.2, 0.39, 0.4, 0.5, 0.69, 0.7, 0.9])
    def test_equal_control_confidence_gives_identical_routing(
        self, confidence: float
    ) -> None:
        """EXTRACT-022 makes the two equal for a generating provider, so supplying
        it explicitly must not change any decision."""
        engine = ValidationEngine()

        implicit = engine.validate(_observation(confidence))
        explicit = engine.validate(
            _observation(confidence), control_confidence=confidence
        )

        assert implicit.routing is explicit.routing


class TestControlConfidenceGates:
    """VALID-011/013 gate on the supplied control confidence."""

    # @spec VALID-011
    @pytest.mark.parametrize(
        ("control", "expected"),
        [
            (0.0, RoutingDecision.INTERVENTIONIST_REVIEW),
            (0.39, RoutingDecision.INTERVENTIONIST_REVIEW),
            (0.4, RoutingDecision.RETAIN_WITH_UNKNOWN),
        ],
    )
    def test_low_control_confidence_routes_to_review(
        self, control: float, expected: RoutingDecision
    ) -> None:
        """Boundary is exclusive at 0.4 — exactly 0.4 is not "less than 0.4"."""
        result = ValidationEngine().validate(
            _observation(0.99), control_confidence=control
        )

        assert result.routing is expected

    # @spec VALID-013
    @pytest.mark.parametrize(
        ("control", "expected"),
        [
            (0.69, RoutingDecision.RETAIN_WITH_UNKNOWN),
            (0.7, RoutingDecision.ACCEPT),
            (1.0, RoutingDecision.ACCEPT),
        ],
    )
    def test_control_confidence_gates_retain_with_unknown(
        self, control: float, expected: RoutingDecision
    ) -> None:
        """Boundary is exclusive at 0.7."""
        result = ValidationEngine().validate(
            _observation(0.99), control_confidence=control
        )

        assert result.routing is expected

    # @spec VALID-011
    def test_control_confidence_overrides_a_high_observation_confidence(self) -> None:
        """The whole point: a confident-looking observation cannot bypass the gate
        when the control quantity says otherwise."""
        result = ValidationEngine().validate(
            _observation(0.99), control_confidence=0.1
        )

        assert result.routing is RoutingDecision.INTERVENTIONIST_REVIEW


class TestControlConfidenceRegression:
    """Why `control_confidence` exists at all.

    Each case would route to ACCEPT if the gate read whichever single quantity
    happened to be high. Reading the conservative combination catches both.
    """

    # @spec VALID-011, MARS-032
    def test_confident_generator_but_judges_disagree(self) -> None:
        generator_confidence = 0.95
        mars_selection_confidence = 0.35
        control = min(generator_confidence, mars_selection_confidence)

        result = ValidationEngine().validate(
            _observation(generator_confidence), control_confidence=control
        )

        assert control == 0.35
        assert result.routing is RoutingDecision.INTERVENTIONIST_REVIEW

    # @spec VALID-011, MARS-032
    def test_judges_agree_but_generator_was_unsure(self) -> None:
        generator_confidence = 0.35
        mars_selection_confidence = 0.95
        control = min(generator_confidence, mars_selection_confidence)

        result = ValidationEngine().validate(
            _observation(generator_confidence), control_confidence=control
        )

        assert control == 0.35
        assert result.routing is RoutingDecision.INTERVENTIONIST_REVIEW


class TestRoutingGateFailsLoudly:
    """Omitting the control confidence must be a loud error, not a quiet skip.

    The failure mode this guards against: a future caller reaches
    `_determine_routing` without supplying a control confidence, both gates
    silently evaluate as if no confidence existed, and a low-confidence
    observation routes to ACCEPT. Fail-safe requires the omission to raise.
    """

    # @spec VALID-011, VALID-013
    def test_determine_routing_requires_control_confidence(self) -> None:
        with pytest.raises(TypeError):
            ValidationEngine._determine_routing(_observation(0.1), [])

    # @spec VALID-011, VALID-013
    def test_determine_routing_rejects_positional_control_confidence(self) -> None:
        """Keyword-only, so it cannot be supplied by accident of argument order."""
        with pytest.raises(TypeError):
            ValidationEngine._determine_routing(_observation(0.1), [], 0.1)

    # @spec VALID-011
    def test_explicit_none_is_a_value_not_an_omission(self) -> None:
        """An observation genuinely carrying no confidence is legitimate, and is
        distinct from failing to pass the argument."""
        routing = ValidationEngine._determine_routing(
            _observation(None), [], control_confidence=None
        )

        assert routing is RoutingDecision.ACCEPT

    # @spec VALID-011
    def test_public_validate_still_accepts_observation_alone(self) -> None:
        """The compatibility boundary keeps its fallback."""
        result = ValidationEngine().validate(_observation(0.1))

        assert result.routing is RoutingDecision.INTERVENTIONIST_REVIEW


class TestUnavailableControlConfidence:
    """VALID-015: an explicitly unavailable control confidence forces review.

    The failure this closes: a MARS short-circuit result carries no judge
    evidence, so `control_confidence` is None, so the confidence gates never
    fired and the record routed to ACCEPT — weaker handling than the
    single-model provider MARS replaces. Absence of evidence must not read as
    evidence of confidence.
    """

    # @spec VALID-015
    @pytest.mark.parametrize(
        "state",
        [
            ControlConfidenceState.NOT_AVAILABLE_SHORT_CIRCUIT,
            ControlConfidenceState.NOT_AVAILABLE_ABSTAINED,
        ],
    )
    def test_explicit_unavailability_routes_to_review(
        self, state: ControlConfidenceState
    ) -> None:
        result = ValidationEngine().validate(
            _observation(0.99),
            control_confidence=None,
            control_confidence_state=state,
        )

        assert result.routing is RoutingDecision.INTERVENTIONIST_REVIEW

    # @spec VALID-015
    def test_high_generator_confidence_does_not_rescue_it(self) -> None:
        """v1 is deliberately conservative: no generator consensus substitutes
        for absent reranking evidence."""
        result = ValidationEngine().validate(
            _observation(0.99),
            control_confidence=None,
            control_confidence_state=(
                ControlConfidenceState.NOT_AVAILABLE_SHORT_CIRCUIT
            ),
        )

        assert result.routing is RoutingDecision.INTERVENTIONIST_REVIEW

    # @spec VALID-015
    @pytest.mark.parametrize("confidence", [0.1, 0.99])
    def test_outcome_is_the_same_whatever_the_generator_reported(
        self, confidence: float
    ) -> None:
        """Routing must not quietly recreate EXTRACT-013 through this path."""
        result = ValidationEngine().validate(
            _observation(confidence),
            control_confidence=None,
            control_confidence_state=(
                ControlConfidenceState.NOT_AVAILABLE_SHORT_CIRCUIT
            ),
        )

        assert result.routing is RoutingDecision.INTERVENTIONIST_REVIEW

    # @spec VALID-015
    def test_available_state_gates_on_the_value_as_before(self) -> None:
        engine = ValidationEngine()

        accepted = engine.validate(
            _observation(0.9),
            control_confidence=0.9,
            control_confidence_state=ControlConfidenceState.AVAILABLE,
        )
        reviewed = engine.validate(
            _observation(0.9),
            control_confidence=0.2,
            control_confidence_state=ControlConfidenceState.AVAILABLE,
        )

        assert accepted.routing is RoutingDecision.ACCEPT
        assert reviewed.routing is RoutingDecision.INTERVENTIONIST_REVIEW

    # @spec VALID-015
    def test_legacy_providers_are_unaffected(self) -> None:
        """A provider that does not participate in control-confidence routing
        passes no state, and keeps its previous behavior — including when its
        observation carries no confidence at all."""
        engine = ValidationEngine()

        assert engine.validate(_observation(0.9)).routing is RoutingDecision.ACCEPT
        assert engine.validate(_observation(None)).routing is RoutingDecision.ACCEPT

    # @spec VALID-015
    def test_absent_state_and_unavailable_state_are_distinguishable(self) -> None:
        """The distinction the whole patch rests on: `None` means "not part of
        my contract", an explicit NOT_AVAILABLE means "I could not establish
        one"."""
        engine = ValidationEngine()

        legacy = engine.validate(_observation(None), control_confidence=None)
        declared = engine.validate(
            _observation(None),
            control_confidence=None,
            control_confidence_state=(
                ControlConfidenceState.NOT_AVAILABLE_SHORT_CIRCUIT
            ),
        )

        assert legacy.routing is RoutingDecision.ACCEPT
        assert declared.routing is RoutingDecision.INTERVENTIONIST_REVIEW
