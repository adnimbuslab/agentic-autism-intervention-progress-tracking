"""Deterministic validation engine for structured observations -- no LLM involvement."""

from __future__ import annotations

from src.backend.ml.schemas import (
    FieldValidation,
    RoutingDecision,
    ValidationResult,
    ValidationSeverity,
)
from src.backend.schemas.observation_schema import (
    LLM_EXTRACTED_FIELDS,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    StructuredObservation,
)

_CONFIDENCE_THRESHOLD = 0.7
_LOW_CONFIDENCE_THRESHOLD = 0.4
_CRITICAL_FIELDS: frozenset[str] = frozenset({"behavior", "domain"})
_IMPORTANT_FIELDS: frozenset[str] = frozenset({"modality", "prompt_level", "outcome"})

_VERBAL_KEYWORDS = frozenset({
    "said", "say", "says", "spoke", "speak", "speaks", "told", "tell", "tells",
    "word", "words", "sentence", "sentences", "utterance", "utterances",
    "verbal", "vocali", "speech",
})


class ValidationEngine:
    """Pure deterministic validation for StructuredObservation records."""

    # @spec VALID-001
    def validate(
        self,
        observation: StructuredObservation,
        goal_ids: list[str] | None = None,
    ) -> ValidationResult:
        """Validate an observation and determine routing."""
        field_validations: list[FieldValidation] = []

        self._validate_enums(observation, field_validations)
        self._validate_critical_fields(observation, field_validations)
        self._validate_cross_field(observation, field_validations)
        self._validate_goal_context(observation, goal_ids, field_validations)
        self._validate_confidence(observation, field_validations)
        completeness_msg = self._validate_completeness(observation, field_validations)

        routing = self._determine_routing(observation, field_validations)
        messages = [fv.message for fv in field_validations if not fv.is_valid and fv.message]
        if completeness_msg:
            messages.append(completeness_msg)

        return ValidationResult(
            is_valid=routing == RoutingDecision.ACCEPT,
            routing=routing,
            field_validations=field_validations,
            messages=messages,
        )

    @staticmethod
    def _validate_enums(
        observation: StructuredObservation,
        results: list[FieldValidation],
    ) -> None:
        enum_fields = {
            "domain": Domain,
            "modality": Modality,
            "prompt_level": PromptLevel,
            "outcome": Outcome,
        }
        for field_name, enum_cls in enum_fields.items():
            value = getattr(observation, field_name, None)
            if value is not None and not isinstance(value, enum_cls):
                results.append(FieldValidation(
                    field_name=field_name,
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"{field_name} has invalid value '{value}'",
                ))

    @staticmethod
    def _validate_critical_fields(
        observation: StructuredObservation,
        results: list[FieldValidation],
    ) -> None:
        for field_name in _CRITICAL_FIELDS:
            value = getattr(observation, field_name, None)
            if value is None:
                results.append(FieldValidation(
                    field_name=field_name,
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Critical field '{field_name}' is missing",
                ))

    # @spec VALID-020, VALID-021, VALID-022
    @staticmethod
    def _validate_cross_field(
        observation: StructuredObservation,
        results: list[FieldValidation],
    ) -> None:
        if (
            observation.modality == Modality.VERBAL
            and observation.behavior is not None
        ):
            behavior_lower = observation.behavior.lower()
            if not any(kw in behavior_lower for kw in _VERBAL_KEYWORDS):
                results.append(FieldValidation(
                    field_name="modality",
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message="Modality is 'verbal' but behavior description does not mention speech or words",
                ))

        if (
            observation.prompt_level == PromptLevel.INDEPENDENT
            and observation.prompt_context is not None
        ):
            results.append(FieldValidation(
                field_name="prompt_context",
                is_valid=False,
                severity=ValidationSeverity.WARNING,
                message="Prompt context is present but prompt level is 'independent'",
            ))

        if observation.outcome is not None and observation.behavior is None:
            results.append(FieldValidation(
                field_name="outcome",
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message="Outcome is set but behavior is missing",
            ))

    # @spec VALID-023
    @staticmethod
    def _validate_goal_context(
        observation: StructuredObservation,
        goal_ids: list[str] | None,
        results: list[FieldValidation],
    ) -> None:
        if not goal_ids or not observation.goal_context:
            return
        if observation.goal_context not in goal_ids:
            results.append(FieldValidation(
                field_name="goal_context",
                is_valid=False,
                severity=ValidationSeverity.WARNING,
                message=f"Goal context '{observation.goal_context}' not in known goal IDs",
            ))

    # @spec VALID-024
    @staticmethod
    def _validate_confidence(
        observation: StructuredObservation,
        results: list[FieldValidation],
    ) -> None:
        if observation.confidence is not None and (
            observation.confidence < 0.0 or observation.confidence > 1.0
        ):
            results.append(FieldValidation(
                field_name="confidence",
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message=f"Confidence {observation.confidence} outside valid range [0.0, 1.0]",
            ))

    @staticmethod
    def _validate_completeness(
        observation: StructuredObservation,
        results: list[FieldValidation],
    ) -> str | None:
        null_fields = [
            f for f in LLM_EXTRACTED_FIELDS
            if getattr(observation, f, None) is None
        ]
        if null_fields:
            return f"{len(null_fields)}/{len(LLM_EXTRACTED_FIELDS)} extracted fields are null: {', '.join(sorted(null_fields))}"
        return None

    # @spec VALID-010, VALID-011, VALID-012, VALID-013, VALID-014
    @staticmethod
    def _determine_routing(
        observation: StructuredObservation,
        field_validations: list[FieldValidation],
    ) -> RoutingDecision:
        errors = [
            fv for fv in field_validations
            if not fv.is_valid and fv.severity == ValidationSeverity.ERROR
        ]
        warnings = [
            fv for fv in field_validations
            if not fv.is_valid and fv.severity == ValidationSeverity.WARNING
        ]

        critical_missing = sum(
            1 for f in _CRITICAL_FIELDS
            if getattr(observation, f, None) is None
        )

        if critical_missing == len(_CRITICAL_FIELDS):
            return RoutingDecision.REJECT

        if errors or (
            observation.confidence is not None
            and observation.confidence < _LOW_CONFIDENCE_THRESHOLD
        ):
            return RoutingDecision.INTERVENTIONIST_REVIEW

        if critical_missing > 0 or len(warnings) > 1:
            return RoutingDecision.CLARIFY

        important_missing = any(
            getattr(observation, f, None) is None for f in _IMPORTANT_FIELDS
        )
        if important_missing:
            return RoutingDecision.RETAIN_WITH_UNKNOWN

        if (
            observation.confidence is not None
            and observation.confidence < _CONFIDENCE_THRESHOLD
        ):
            return RoutingDecision.RETAIN_WITH_UNKNOWN

        return RoutingDecision.ACCEPT
