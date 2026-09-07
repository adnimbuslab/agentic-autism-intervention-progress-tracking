"""Deterministic validation engine for structured observations -- no LLM involvement."""

from __future__ import annotations

from src.backend.ml.extraction.schemas import ControlConfidenceState
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
    # @spec VALID-011, VALID-013
    def validate(
        self,
        observation: StructuredObservation,
        goal_ids: list[str] | None = None,
        control_confidence: float | None = None,
        control_confidence_state: ControlConfidenceState | None = None,
    ) -> ValidationResult:
        """Validate an observation and determine routing.

        ``control_confidence`` is the quantity the routing gates read
        (EXTRACT-020) -- the same quantity whichever provider produced the
        result, so a threshold means one thing system-wide. A provider that
        generates directly sets it equal to the observation's own confidence
        (EXTRACT-022); a composing provider combines its generator and
        selection confidences (MARS-032). Omitting it falls back to the
        observation's confidence, which is that same value for every
        single-model provider and keeps existing callers unchanged.

        ``control_confidence_state`` distinguishes two different silences.
        ``None`` means the provider does not participate in control-confidence
        routing, and its previous behavior is preserved exactly. An explicit
        ``NOT_AVAILABLE_*`` means the provider does participate and could not
        establish a confidence -- which routes to interventionist review,
        because absence of evidence is not evidence of confidence.
        """
        field_validations: list[FieldValidation] = []

        self._validate_enums(observation, field_validations)
        self._validate_critical_fields(observation, field_validations)
        self._validate_cross_field(observation, field_validations)
        self._validate_goal_context(observation, goal_ids, field_validations)
        self._validate_confidence(observation, field_validations)
        completeness_msg = self._validate_completeness(observation, field_validations)

        # Fallback lives here, at the compatibility boundary -- never inside
        # the gate itself. A caller that omits control_confidence gets the
        # observation's own confidence, which EXTRACT-022 makes the same value
        # for every single-model provider.
        effective_confidence = (
            observation.confidence if control_confidence is None else control_confidence
        )
        routing = self._determine_routing(
            observation,
            field_validations,
            control_confidence=effective_confidence,
            control_confidence_state=control_confidence_state,
        )
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
        *,
        control_confidence: float | None,
        control_confidence_state: ControlConfidenceState | None = None,
    ) -> RoutingDecision:
        """Deterministic routing gate.

        ``control_confidence`` is keyword-only and has no default: omitting it
        is a programming error that raises immediately, rather than silently
        disabling both confidence gates. A missing confidence must never be
        the quiet path through a safety decision. ``None`` remains a legitimate
        *value* -- an observation genuinely carrying no confidence -- and is
        distinct from failing to pass the argument at all.
        """
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

        # VALID-015: a provider that participates in control-confidence
        # routing but could not establish one has produced no evidence for
        # automatic acceptance. Handled here, at the same tier as a
        # below-threshold confidence, and independently of whatever the
        # generator reported -- routing must not recreate EXTRACT-013 by
        # another route.
        unavailable = control_confidence_state in {
            ControlConfidenceState.NOT_AVAILABLE_SHORT_CIRCUIT,
            ControlConfidenceState.NOT_AVAILABLE_ABSTAINED,
        }
        if errors or unavailable or (
            control_confidence is not None
            and control_confidence < _LOW_CONFIDENCE_THRESHOLD
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
            control_confidence is not None
            and control_confidence < _CONFIDENCE_THRESHOLD
        ):
            return RoutingDecision.RETAIN_WITH_UNKNOWN

        return RoutingDecision.ACCEPT
