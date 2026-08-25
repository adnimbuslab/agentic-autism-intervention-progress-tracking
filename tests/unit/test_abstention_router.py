from __future__ import annotations

from datetime import UTC, date, datetime

from src.backend.ml.abstention_router import AbstentionRouter
from src.backend.ml.extraction.schemas import (
    ExtractionResult,
    ExtractionStatus,
)
from src.backend.ml.schemas import (
    FieldValidation,
    RoutingDecision,
    ValidationResult,
    ValidationSeverity,
)
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
        behavior="Child said hello",
        modality=Modality.VERBAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=0.85,
    )
    defaults.update(overrides)
    return StructuredObservation(**defaults)


def _make_extraction(
    status: ExtractionStatus = ExtractionStatus.SUCCESS,
    observations: list[StructuredObservation] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        status=status,
        observations=observations or [],
        provider="test",
        model="test-model",
        prompt_version="1.0.0",
        generated_at=datetime.now(UTC),
    )


def _make_validation(
    routing: RoutingDecision = RoutingDecision.ACCEPT,
    field_validations: list[FieldValidation] | None = None,
) -> ValidationResult:
    return ValidationResult(
        is_valid=routing == RoutingDecision.ACCEPT,
        routing=routing,
        field_validations=field_validations or [],
    )


router = AbstentionRouter()


class TestRouting:
    def test_failed_extraction_rejects(self) -> None:
        extraction = _make_extraction(status=ExtractionStatus.FAILED)
        validation = _make_validation(routing=RoutingDecision.ACCEPT)
        assert router.route(extraction, validation) == RoutingDecision.REJECT

    def test_validation_reject_preserved(self) -> None:
        obs = _make_observation()
        extraction = _make_extraction(observations=[obs])
        validation = _make_validation(routing=RoutingDecision.REJECT)
        assert router.route(extraction, validation) == RoutingDecision.REJECT

    def test_clarify_with_recoverable_fields(self) -> None:
        obs = _make_observation(behavior=None)
        extraction = _make_extraction(observations=[obs])
        validation = _make_validation(
            routing=RoutingDecision.CLARIFY,
            field_validations=[
                FieldValidation(field_name="behavior", is_valid=False, severity=ValidationSeverity.ERROR),
            ],
        )
        assert router.route(extraction, validation) == RoutingDecision.CLARIFY

    def test_clarify_without_observations_falls_back(self) -> None:
        extraction = _make_extraction(observations=[])
        validation = _make_validation(routing=RoutingDecision.CLARIFY)
        result = router.route(extraction, validation)
        assert result == RoutingDecision.CLARIFY

    def test_accept_passes_through(self) -> None:
        obs = _make_observation()
        extraction = _make_extraction(observations=[obs])
        validation = _make_validation(routing=RoutingDecision.ACCEPT)
        assert router.route(extraction, validation) == RoutingDecision.ACCEPT

    def test_retain_passes_through(self) -> None:
        obs = _make_observation()
        extraction = _make_extraction(observations=[obs])
        validation = _make_validation(routing=RoutingDecision.RETAIN_WITH_UNKNOWN)
        assert router.route(extraction, validation) == RoutingDecision.RETAIN_WITH_UNKNOWN

    def test_interventionist_review_passes_through(self) -> None:
        obs = _make_observation()
        extraction = _make_extraction(observations=[obs])
        validation = _make_validation(routing=RoutingDecision.INTERVENTIONIST_REVIEW)
        assert router.route(extraction, validation) == RoutingDecision.INTERVENTIONIST_REVIEW


class TestClarificationQuestions:
    def test_behavior_missing_generates_question(self) -> None:
        obs = _make_observation(behavior=None)
        validation = _make_validation(
            field_validations=[
                FieldValidation(field_name="behavior", is_valid=False, severity=ValidationSeverity.ERROR),
            ],
        )
        questions = router.generate_clarification_questions(obs, validation)
        assert any("describe" in q.lower() and "did" in q.lower() for q in questions)

    def test_domain_missing_generates_question(self) -> None:
        obs = _make_observation(domain=None)
        validation = _make_validation(
            field_validations=[
                FieldValidation(field_name="domain", is_valid=False, severity=ValidationSeverity.ERROR),
            ],
        )
        questions = router.generate_clarification_questions(obs, validation)
        assert any("skill area" in q.lower() for q in questions)

    def test_max_three_questions(self) -> None:
        obs = _make_observation(
            behavior=None, domain=None, modality=None,
            prompt_level=None, outcome=None, goal_context=None,
        )
        validation = _make_validation(
            field_validations=[
                FieldValidation(field_name=f, is_valid=False, severity=ValidationSeverity.ERROR)
                for f in ("behavior", "domain", "modality", "prompt_level", "outcome", "goal_context")
            ],
        )
        questions = router.generate_clarification_questions(obs, validation)
        assert len(questions) <= 3

    def test_critical_fields_first(self) -> None:
        obs = _make_observation(behavior=None, domain=None, modality=None)
        validation = _make_validation(
            field_validations=[
                FieldValidation(field_name="modality", is_valid=False, severity=ValidationSeverity.WARNING),
                FieldValidation(field_name="behavior", is_valid=False, severity=ValidationSeverity.ERROR),
                FieldValidation(field_name="domain", is_valid=False, severity=ValidationSeverity.ERROR),
            ],
        )
        questions = router.generate_clarification_questions(obs, validation)
        assert len(questions) >= 2
        assert "describe" in questions[0].lower() or "skill area" in questions[0].lower()

    def test_questions_not_leading(self) -> None:
        obs = _make_observation(behavior=None, domain=None, modality=None)
        validation = _make_validation(
            field_validations=[
                FieldValidation(field_name=f, is_valid=False, severity=ValidationSeverity.ERROR)
                for f in ("behavior", "domain", "modality")
            ],
        )
        questions = router.generate_clarification_questions(obs, validation)
        for q in questions:
            assert not q.startswith("Did the child")
            assert not q.startswith("Was the child")

    def test_no_questions_when_all_fields_present(self) -> None:
        obs = _make_observation(goal_context="G1", prompt_context="none needed")
        validation = _make_validation()
        questions = router.generate_clarification_questions(obs, validation)
        assert len(questions) == 0
