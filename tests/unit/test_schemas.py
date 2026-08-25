"""Contract tests for data schemas — ObservationSchema, ExtractionRequest/Result."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    SourceType,
)
from src.backend.schemas.observation_schema import (
    APP_KNOWN_FIELDS,
    LLM_EXTRACTED_FIELDS,
    PROVIDER_GENERATED_FIELDS,
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)


class TestStructuredObservation:
    def test_valid_full_observation(self) -> None:
        obs = StructuredObservation(
            child_id="child-1",
            session_id="session-1",
            contributor_role=ContributorRole.PARENT,
            observation_date=date(2026, 8, 1),
            setting=Setting.HOME,
            domain=Domain.LANGUAGE,
            goal_context="Increase spontaneous speech",
            behavior="Said 'want cookie' without prompting",
            modality=Modality.VERBAL,
            prompt_context="During snack time",
            prompt_level=PromptLevel.INDEPENDENT,
            outcome=Outcome.CORRECT,
            duration_seconds=5,
            confidence=0.85,
        )
        assert obs.child_id == "child-1"
        assert obs.domain == Domain.LANGUAGE

    def test_minimal_observation_with_app_known_only(self) -> None:
        obs = StructuredObservation(
            child_id="child-1",
            session_id="session-1",
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2026, 8, 1),
            setting=Setting.CLINIC,
        )
        assert obs.domain is None
        assert obs.behavior is None
        assert obs.confidence is None

    def test_confidence_range_valid(self) -> None:
        obs = StructuredObservation(
            child_id="c1", session_id="s1",
            contributor_role=ContributorRole.PARENT,
            observation_date=date(2026, 1, 1),
            setting=Setting.HOME,
            confidence=0.0,
        )
        assert obs.confidence == 0.0

        obs2 = StructuredObservation(
            child_id="c1", session_id="s1",
            contributor_role=ContributorRole.PARENT,
            observation_date=date(2026, 1, 1),
            setting=Setting.HOME,
            confidence=1.0,
        )
        assert obs2.confidence == 1.0

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuredObservation(
                child_id="c1", session_id="s1",
                contributor_role=ContributorRole.PARENT,
                observation_date=date(2026, 1, 1),
                setting=Setting.HOME,
                confidence=1.5,
            )

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuredObservation(
                child_id="c1", session_id="s1",
                contributor_role=ContributorRole.PARENT,
                observation_date=date(2026, 1, 1),
                setting=Setting.HOME,
                duration_seconds=-1,
            )

    def test_invalid_enum_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuredObservation(
                child_id="c1", session_id="s1",
                contributor_role="not_a_role",  # type: ignore[arg-type]
                observation_date=date(2026, 1, 1),
                setting=Setting.HOME,
            )


class TestFieldCategorization:
    def test_no_field_overlap(self) -> None:
        assert APP_KNOWN_FIELDS & LLM_EXTRACTED_FIELDS == set()
        assert APP_KNOWN_FIELDS & PROVIDER_GENERATED_FIELDS == set()
        assert LLM_EXTRACTED_FIELDS & PROVIDER_GENERATED_FIELDS == set()

    def test_all_fields_categorized(self) -> None:
        all_fields = set(StructuredObservation.model_fields.keys())
        categorized = APP_KNOWN_FIELDS | LLM_EXTRACTED_FIELDS | PROVIDER_GENERATED_FIELDS
        assert all_fields == categorized, f"Uncategorized fields: {all_fields - categorized}"


class TestExtractionRequest:
    def test_valid_conversational_request(self) -> None:
        req = ExtractionRequest(
            source_type=SourceType.CONVERSATIONAL,
            text="The child said 'want juice' during morning snack",
            child_id="child-1",
            session_id="session-1",
            contributor_role=ContributorRole.PARENT,
            observation_date=date(2026, 8, 1),
            setting=Setting.HOME,
        )
        assert req.source_type == SourceType.CONVERSATIONAL
        assert req.metadata == {}

    def test_valid_chat_segment_request(self) -> None:
        req = ExtractionRequest(
            source_type=SourceType.CHAT_SEGMENT,
            text="*CHI: want juice .\n%spa: $req",
            child_id="child-1",
            session_id="session-1",
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2026, 8, 1),
            setting=Setting.CLINIC,
            metadata={"speaker_codes": ["CHI", "INV"], "corpus": "rollins"},
        )
        assert req.source_type == SourceType.CHAT_SEGMENT

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExtractionRequest(
                source_type=SourceType.CONVERSATIONAL,
                text="",
                child_id="c1",
                session_id="s1",
                contributor_role=ContributorRole.PARENT,
                observation_date=date(2026, 1, 1),
                setting=Setting.HOME,
            )

    def test_carries_goal_ids(self) -> None:
        req = ExtractionRequest(
            source_type=SourceType.CONVERSATIONAL,
            text="some observation text",
            child_id="c1",
            session_id="s1",
            contributor_role=ContributorRole.TEACHER,
            observation_date=date(2026, 8, 1),
            setting=Setting.SCHOOL,
            goal_ids=["goal-1", "goal-2"],
        )
        assert len(req.goal_ids) == 2


class TestExtractionResult:
    def test_valid_success_result(self) -> None:
        result = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            observations=[
                StructuredObservation(
                    child_id="c1", session_id="s1",
                    contributor_role=ContributorRole.PARENT,
                    observation_date=date(2026, 8, 1),
                    setting=Setting.HOME,
                    domain=Domain.LANGUAGE,
                    behavior="Said 'want juice'",
                    modality=Modality.VERBAL,
                    prompt_level=PromptLevel.INDEPENDENT,
                    outcome=Outcome.CORRECT,
                    confidence=0.9,
                ),
            ],
            provider="temporary_llm",
            model="claude-sonnet-4-20250514",
            prompt_version="1.0",
        )
        assert result.status == ExtractionStatus.SUCCESS
        assert len(result.observations) == 1

    def test_abstained_result_with_questions(self) -> None:
        result = ExtractionResult(
            status=ExtractionStatus.ABSTAINED,
            observations=[],
            provider="temporary_llm",
            model="claude-sonnet-4-20250514",
            prompt_version="1.0",
            clarification_questions=["What activity was the child engaged in?"],
        )
        assert result.status == ExtractionStatus.ABSTAINED
        assert len(result.clarification_questions) == 1
        assert len(result.observations) == 0

    def test_result_has_timestamp(self) -> None:
        result = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            provider="temporary_llm",
            model="test",
            prompt_version="1.0",
        )
        assert isinstance(result.generated_at, datetime)
