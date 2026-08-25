from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.schemas import ValidationSeverity
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
        behavior="Child waved hello",
        modality=Modality.GESTURAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=0.85,
    )
    defaults.update(overrides)
    return StructuredObservation(**defaults)


engine = ValidationEngine()


@pytest.mark.eval
class TestCrossFieldLogic:
    def test_verbal_modality_without_speech_words_warns(self) -> None:
        obs = _make_observation(modality=Modality.VERBAL, behavior="Child reached for cookie")
        result = engine.validate(obs)
        modality_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "modality" and fv.severity == ValidationSeverity.WARNING
        ]
        assert len(modality_warnings) == 1

    def test_verbal_modality_with_speech_words_ok(self) -> None:
        obs = _make_observation(modality=Modality.VERBAL, behavior="Child said 'want cookie'")
        result = engine.validate(obs)
        modality_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "modality" and fv.severity == ValidationSeverity.WARNING
        ]
        assert len(modality_warnings) == 0

    def test_verbal_with_utterance_keyword_ok(self) -> None:
        obs = _make_observation(modality=Modality.VERBAL, behavior="Child produced a two-word utterance")
        result = engine.validate(obs)
        modality_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "modality" and fv.severity == ValidationSeverity.WARNING
        ]
        assert len(modality_warnings) == 0

    def test_independent_prompt_with_context_warns(self) -> None:
        obs = _make_observation(
            prompt_level=PromptLevel.INDEPENDENT,
            prompt_context="Therapist gave a verbal cue",
        )
        result = engine.validate(obs)
        prompt_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "prompt_context" and fv.severity == ValidationSeverity.WARNING
        ]
        assert len(prompt_warnings) == 1

    def test_independent_prompt_no_context_ok(self) -> None:
        obs = _make_observation(prompt_level=PromptLevel.INDEPENDENT, prompt_context=None)
        result = engine.validate(obs)
        prompt_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "prompt_context" and not fv.is_valid
        ]
        assert len(prompt_warnings) == 0

    def test_outcome_present_behavior_missing_errors(self) -> None:
        obs = _make_observation(outcome=Outcome.CORRECT, behavior=None)
        result = engine.validate(obs)
        outcome_errors = [
            fv for fv in result.field_validations
            if fv.field_name == "outcome" and fv.severity == ValidationSeverity.ERROR
        ]
        assert len(outcome_errors) == 1

    def test_gestural_modality_no_speech_no_warning(self) -> None:
        obs = _make_observation(modality=Modality.GESTURAL, behavior="Child pointed to toy")
        result = engine.validate(obs)
        modality_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "modality" and fv.severity == ValidationSeverity.WARNING
        ]
        assert len(modality_warnings) == 0

    def test_verbal_with_null_behavior_no_cross_field_warning(self) -> None:
        obs = _make_observation(modality=Modality.VERBAL, behavior=None)
        result = engine.validate(obs)
        modality_warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "modality" and fv.severity == ValidationSeverity.WARNING
        ]
        assert len(modality_warnings) == 0
