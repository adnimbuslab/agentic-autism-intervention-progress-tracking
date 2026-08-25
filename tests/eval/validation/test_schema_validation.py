from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.schemas import RoutingDecision, ValidationSeverity
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
        domain=Domain.LANGUAGE,
        behavior="Child said 'more juice please'",
        modality=Modality.VERBAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=0.85,
    )
    defaults.update(overrides)
    return StructuredObservation(**defaults)


engine = ValidationEngine()


@pytest.mark.eval
class TestSchemaValidation:
    def test_valid_record_passes_all_checks(self) -> None:
        obs = _make_observation()
        result = engine.validate(obs)
        assert result.is_valid is True
        assert result.routing == RoutingDecision.ACCEPT
        errors = [fv for fv in result.field_validations if not fv.is_valid]
        assert len(errors) == 0

    def test_missing_behavior_flags_error(self) -> None:
        obs = _make_observation(behavior=None)
        result = engine.validate(obs)
        behavior_errors = [
            fv for fv in result.field_validations
            if fv.field_name == "behavior" and not fv.is_valid
        ]
        assert len(behavior_errors) == 1
        assert behavior_errors[0].severity == ValidationSeverity.ERROR

    def test_missing_domain_flags_error(self) -> None:
        obs = _make_observation(domain=None)
        result = engine.validate(obs)
        domain_errors = [
            fv for fv in result.field_validations
            if fv.field_name == "domain" and not fv.is_valid
        ]
        assert len(domain_errors) == 1
        assert domain_errors[0].severity == ValidationSeverity.ERROR

    def test_valid_enum_values_pass(self) -> None:
        for domain in Domain:
            obs = _make_observation(domain=domain)
            result = engine.validate(obs)
            enum_errors = [
                fv for fv in result.field_validations
                if fv.field_name == "domain" and not fv.is_valid
                and "invalid value" in (fv.message or "")
            ]
            assert len(enum_errors) == 0

    def test_null_optional_fields_accepted(self) -> None:
        obs = _make_observation(
            goal_context=None, prompt_context=None, duration_seconds=None,
        )
        result = engine.validate(obs)
        assert result.routing in (RoutingDecision.ACCEPT, RoutingDecision.RETAIN_WITH_UNKNOWN)

    def test_is_valid_matches_routing(self) -> None:
        obs_accept = _make_observation()
        assert engine.validate(obs_accept).is_valid is True

        obs_reject = _make_observation(behavior=None, domain=None)
        assert engine.validate(obs_reject).is_valid is False
