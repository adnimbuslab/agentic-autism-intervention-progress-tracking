"""Abstention router -- decides final routing and generates clarification questions."""

from __future__ import annotations

from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.ml.schemas import (
    FieldValidation,
    RoutingDecision,
    ValidationResult,
)
from src.backend.schemas.observation_schema import StructuredObservation

_MAX_CLARIFICATION_QUESTIONS = 3
_CRITICAL_FIELDS: frozenset[str] = frozenset({"behavior", "domain"})

_QUESTION_TEMPLATES: dict[str, str] = {
    "behavior": "Can you describe what the child did or said during this observation?",
    "domain": "What skill area was this observation related to (e.g., communication, play, motor skills)?",
    "modality": "How did the child communicate -- through speech, gestures, or another way?",
    "prompt_level": "Was any prompting or assistance provided? If so, what kind?",
    "outcome": "What was the result of the child's attempt?",
    "goal_context": "Was this observation related to a specific goal or objective?",
    "prompt_context": "Can you describe the support or prompt that was given?",
}


class AbstentionRouter:
    """Final routing gate combining extraction status and validation results."""

    # @spec ABSTAIN-001, ABSTAIN-002, ABSTAIN-003, ABSTAIN-004, ABSTAIN-005, ABSTAIN-006
    def route(
        self,
        extraction: ExtractionResult,
        validation: ValidationResult,
    ) -> RoutingDecision:
        """Determine the final routing decision."""
        if extraction.status == ExtractionStatus.FAILED:
            return RoutingDecision.REJECT

        if validation.routing == RoutingDecision.REJECT:
            return RoutingDecision.REJECT

        if validation.routing == RoutingDecision.CLARIFY:
            observation = extraction.observations[0] if extraction.observations else None
            if observation and self._has_recoverable_fields(observation, validation):
                return RoutingDecision.CLARIFY

        if (
            extraction.status == ExtractionStatus.PARTIAL
            and extraction.clarification_questions
            and validation.routing in (
                RoutingDecision.RETAIN_WITH_UNKNOWN,
                RoutingDecision.INTERVENTIONIST_REVIEW,
            )
        ):
            return RoutingDecision.CLARIFY

        return validation.routing

    # @spec ABSTAIN-010, ABSTAIN-011, ABSTAIN-012, ABSTAIN-013
    def generate_clarification_questions(
        self,
        observation: StructuredObservation,
        validation: ValidationResult,
    ) -> list[str]:
        """Generate focused, non-leading clarification questions."""
        failed_fields = {
            fv.field_name
            for fv in validation.field_validations
            if not fv.is_valid
        }

        candidate_fields: list[str] = []
        for field_name in _CRITICAL_FIELDS:
            if field_name in failed_fields or getattr(observation, field_name, None) is None:
                candidate_fields.append(field_name)

        for field_name in ("modality", "prompt_level", "outcome", "goal_context", "prompt_context"):
            if field_name in failed_fields or getattr(observation, field_name, None) is None:
                candidate_fields.append(field_name)

        questions: list[str] = []
        seen: set[str] = set()
        for field_name in candidate_fields:
            if field_name in seen:
                continue
            seen.add(field_name)
            template = _QUESTION_TEMPLATES.get(field_name)
            if template:
                questions.append(template)
            if len(questions) >= _MAX_CLARIFICATION_QUESTIONS:
                break

        return questions

    @staticmethod
    def _has_recoverable_fields(
        observation: StructuredObservation,
        validation: ValidationResult,
    ) -> bool:
        """Check whether any failed field has a question template available."""
        failed_fields = {
            fv.field_name
            for fv in validation.field_validations
            if not fv.is_valid
        }
        null_critical = {
            f for f in _CRITICAL_FIELDS
            if getattr(observation, f, None) is None
        }
        recoverable = (failed_fields | null_critical) & set(_QUESTION_TEMPLATES)
        return len(recoverable) > 0
