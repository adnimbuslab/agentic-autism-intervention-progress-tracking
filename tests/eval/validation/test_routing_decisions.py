from __future__ import annotations

from datetime import date

import pytest

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


def _make_observation(**overrides: object) -> StructuredObservation:
    defaults: dict[str, object] = dict(
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2024, 1, 15),
        setting=Setting.CLINIC,
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior="Child said hello and waved",
        modality=Modality.VERBAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=0.85,
    )
    defaults.update(overrides)
    return StructuredObservation(**defaults)


engine = ValidationEngine()


@pytest.mark.eval
class TestRoutingDecisions:
    @pytest.mark.parametrize(
        "overrides, expected_routing",
        [
            pytest.param(
                {},
                RoutingDecision.ACCEPT,
                id="fully_valid_accepts",
            ),
            pytest.param(
                {"behavior": None, "domain": None},
                RoutingDecision.REJECT,
                id="both_critical_missing_rejects",
            ),
            pytest.param(
                {"behavior": None},
                RoutingDecision.INTERVENTIONIST_REVIEW,
                id="one_critical_missing_reviews",
            ),
            pytest.param(
                {"confidence": 0.3},
                RoutingDecision.INTERVENTIONIST_REVIEW,
                id="low_confidence_reviews",
            ),
            pytest.param(
                {"confidence": 0.5},
                RoutingDecision.RETAIN_WITH_UNKNOWN,
                id="medium_confidence_retains",
            ),
            pytest.param(
                {"modality": None},
                RoutingDecision.RETAIN_WITH_UNKNOWN,
                id="important_field_missing_retains",
            ),
        ],
    )
    def test_routing_path(self, overrides: dict, expected_routing: RoutingDecision) -> None:
        obs = _make_observation(**overrides)
        result = engine.validate(obs)
        assert result.routing == expected_routing

    def test_routing_is_deterministic(self) -> None:
        obs = _make_observation(confidence=0.5, modality=None, outcome=None)
        results = [engine.validate(obs) for _ in range(10)]
        routings = {r.routing for r in results}
        assert len(routings) == 1

    def test_two_warnings_trigger_clarify(self) -> None:
        obs = _make_observation(
            modality=Modality.VERBAL,
            behavior="Child reached for toy",
            prompt_level=PromptLevel.INDEPENDENT,
            prompt_context="some cue",
        )
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.CLARIFY

    def test_accept_requires_high_confidence(self) -> None:
        obs = _make_observation(confidence=0.69)
        result = engine.validate(obs)
        assert result.routing != RoutingDecision.ACCEPT

    def test_none_confidence_allows_accept(self) -> None:
        obs = _make_observation(confidence=None)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.ACCEPT
