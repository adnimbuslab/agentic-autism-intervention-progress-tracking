from __future__ import annotations

from datetime import date

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


class TestValidationRouting:
    def test_valid_observation_accepts(self) -> None:
        obs = _make_observation()
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.ACCEPT
        assert result.is_valid is True

    def test_all_critical_missing_rejects(self) -> None:
        obs = _make_observation(behavior=None, domain=None)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.REJECT

    def test_one_critical_missing_routes_to_review(self) -> None:
        obs = _make_observation(behavior=None)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.INTERVENTIONIST_REVIEW

    def test_domain_missing_routes_to_review(self) -> None:
        obs = _make_observation(domain=None)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.INTERVENTIONIST_REVIEW

    def test_low_confidence_routes_to_review(self) -> None:
        obs = _make_observation(confidence=0.2)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.INTERVENTIONIST_REVIEW

    def test_medium_confidence_retains(self) -> None:
        obs = _make_observation(confidence=0.5)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.RETAIN_WITH_UNKNOWN

    def test_important_fields_missing_retains(self) -> None:
        obs = _make_observation(modality=None, prompt_level=None, outcome=None)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.RETAIN_WITH_UNKNOWN

    def test_none_confidence_with_all_fields_accepts(self) -> None:
        obs = _make_observation(confidence=None)
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.ACCEPT


class TestCrossFieldValidation:
    def test_verbal_no_speech_warning(self) -> None:
        obs = _make_observation(modality=Modality.VERBAL, behavior="Child reached for cookie")
        result = engine.validate(obs)
        warnings = [fv for fv in result.field_validations if fv.severity == ValidationSeverity.WARNING]
        assert any(fv.field_name == "modality" for fv in warnings)

    def test_verbal_with_speech_no_warning(self) -> None:
        obs = _make_observation(modality=Modality.VERBAL, behavior="Child said hello")
        result = engine.validate(obs)
        modality_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "modality" and fv.severity == ValidationSeverity.WARNING
        ]
        assert len(modality_warnings) == 0

    def test_independent_with_prompt_context_warning(self) -> None:
        obs = _make_observation(prompt_level=PromptLevel.INDEPENDENT, prompt_context="verbal cue given")
        result = engine.validate(obs)
        warnings = [fv for fv in result.field_validations if fv.severity == ValidationSeverity.WARNING]
        assert any(fv.field_name == "prompt_context" for fv in warnings)

    def test_independent_no_context_ok(self) -> None:
        obs = _make_observation(prompt_level=PromptLevel.INDEPENDENT, prompt_context=None)
        result = engine.validate(obs)
        prompt_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "prompt_context" and not fv.is_valid
        ]
        assert len(prompt_warnings) == 0

    def test_outcome_without_behavior_error(self) -> None:
        obs = _make_observation(outcome=Outcome.CORRECT, behavior=None)
        result = engine.validate(obs)
        errors = [
            fv for fv in result.field_validations
            if fv.field_name == "outcome" and fv.severity == ValidationSeverity.ERROR
        ]
        assert len(errors) == 1


class TestGoalValidation:
    def test_invalid_goal_context_warning(self) -> None:
        obs = _make_observation(goal_context="G999")
        result = engine.validate(obs, goal_ids=["G1", "G2"])
        warnings = [fv for fv in result.field_validations if fv.field_name == "goal_context"]
        assert len(warnings) == 1
        assert warnings[0].severity == ValidationSeverity.WARNING

    def test_valid_goal_context_no_warning(self) -> None:
        obs = _make_observation(goal_context="G1")
        result = engine.validate(obs, goal_ids=["G1", "G2"])
        goal_issues = [fv for fv in result.field_validations if fv.field_name == "goal_context" and not fv.is_valid]
        assert len(goal_issues) == 0

    def test_no_goal_ids_skips_check(self) -> None:
        obs = _make_observation(goal_context="anything")
        result = engine.validate(obs, goal_ids=None)
        goal_issues = [fv for fv in result.field_validations if fv.field_name == "goal_context"]
        assert len(goal_issues) == 0


class TestCompleteness:
    def test_completeness_message_when_fields_null(self) -> None:
        obs = _make_observation(goal_context=None, prompt_context=None, duration_seconds=None)
        result = engine.validate(obs)
        completeness_msgs = [m for m in result.messages if "extracted fields are null" in m]
        assert len(completeness_msgs) == 1

    def test_no_completeness_message_when_all_present(self) -> None:
        obs = _make_observation(
            goal_context="G1", prompt_context="none", duration_seconds=30,
        )
        result = engine.validate(obs)
        completeness_msgs = [m for m in result.messages if "extracted fields are null" in m]
        assert len(completeness_msgs) == 0


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        obs = _make_observation(confidence=0.5, modality=None)
        results = [engine.validate(obs) for _ in range(10)]
        routings = {r.routing for r in results}
        assert len(routings) == 1
        field_counts = {len(r.field_validations) for r in results}
        assert len(field_counts) == 1
