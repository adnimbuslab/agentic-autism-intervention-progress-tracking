"""Unit tests for observation_service — pipeline orchestration, immutability,
clarification flow, max turns, correction versioning."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.ml.schemas import RoutingDecision, ValidationResult
from src.backend.models.observation import (
    ObservationStatus,
    RecordStatus,
    StructuredRecord,
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
from src.backend.services.observation_service import (
    _build_extraction_request,
    _handle_routing,
    build_conversation_json,
    correct_record,
    submit_observation,
)


def _make_observation(**kwargs):
    obs = Mock()
    obs.id = kwargs.get("obs_id", uuid.uuid4())
    obs.child_id = kwargs.get("child_id", uuid.uuid4())
    obs.submitted_by = kwargs.get("submitted_by", uuid.uuid4())
    obs.raw_text = kwargs.get("raw_text", "The child pointed at the toy and said 'car'.")
    obs.source_type = kwargs.get("source_type", "conversational")
    obs.setting = kwargs.get("setting", "home")
    obs.status = kwargs.get("status", ObservationStatus.PENDING)
    obs.submitted_at = datetime.now(UTC)
    obs.finalized_at = None
    obs.conversation_json = None
    obs.extraction_result_json = None
    obs.clarification_turns = kwargs.get("clarification_turns", [])
    obs.structured_records = kwargs.get("structured_records", [])
    return obs


def _make_extraction_result(**kwargs):
    obs_data = StructuredObservation(
        child_id="child-1",
        session_id="session-1",
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior="pointed at toy and said 'car'",
        modality=Modality.VERBAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        setting=Setting.HOME,
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date="2026-01-01",
    )
    return ExtractionResult(
        status=kwargs.get("status", ExtractionStatus.SUCCESS),
        observations=kwargs.get("observations", [obs_data]),
        provider="temporary_llm",
        model="claude-sonnet-4-20250514",
        prompt_version="1.0",
    )


def _make_validation_result(**kwargs):
    return ValidationResult(
        is_valid=kwargs.get("is_valid", True),
        routing=kwargs.get("routing", RoutingDecision.ACCEPT),
        messages=kwargs.get("messages", []),
    )


class TestBuildExtractionRequest:
    def test_preserves_app_known_metadata(self):
        obs = _make_observation(child_id=uuid.uuid4())
        request = _build_extraction_request(
            obs, ContributorRole.INTERVENTIONIST, ["goal-1"]
        )
        assert request.child_id == str(obs.child_id)
        assert request.session_id == str(obs.id)
        assert request.contributor_role == ContributorRole.INTERVENTIONIST
        assert request.setting.value == obs.setting
        assert request.goal_ids == ["goal-1"]

    def test_includes_clarification_history(self):
        obs = _make_observation()
        history = [{"question": "Where?", "answer": "At home"}]
        request = _build_extraction_request(
            obs, ContributorRole.PARENT, [], clarification_history=history
        )
        assert len(request.clarification_history) == 1
        assert request.clarification_history[0]["answer"] == "At home"


class TestHandleRouting:
    async def test_accept_creates_record_and_finalizes(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        obs = _make_observation()
        extraction = _make_extraction_result()
        validation = _make_validation_result()

        with patch("src.backend.services.observation_service._create_record") as mock_cr:
            mock_record = Mock()
            mock_cr.return_value = mock_record

            decision, question = await _handle_routing(
                db, obs, extraction, validation, RoutingDecision.ACCEPT
            )
        assert decision == "accept"
        assert question is None
        assert obs.status == ObservationStatus.FINALIZED
        assert obs.finalized_at is not None
        db.add.assert_called_once_with(mock_record)

    async def test_reject_sets_failed_status(self):
        db = AsyncMock()
        db.add = MagicMock()
        obs = _make_observation()
        extraction = _make_extraction_result()
        validation = _make_validation_result(routing=RoutingDecision.REJECT)

        decision, question = await _handle_routing(
            db, obs, extraction, validation, RoutingDecision.REJECT
        )
        assert decision == "reject"
        assert obs.status == ObservationStatus.FAILED

    async def test_retain_creates_record_and_finalizes(self):
        db = AsyncMock()
        db.add = MagicMock()
        obs = _make_observation()
        extraction = _make_extraction_result()
        validation = _make_validation_result()

        with patch("src.backend.services.observation_service._create_record") as mock_cr:
            mock_cr.return_value = Mock()
            decision, question = await _handle_routing(
                db, obs, extraction, validation, RoutingDecision.RETAIN_WITH_UNKNOWN
            )
        assert decision == "retain_with_unknown"
        assert obs.status == ObservationStatus.FINALIZED

    async def test_review_creates_pending_record(self):
        db = AsyncMock()
        db.add = MagicMock()
        obs = _make_observation()
        extraction = _make_extraction_result()
        validation = _make_validation_result()

        with patch("src.backend.services.observation_service._create_record") as mock_cr:
            mock_record = Mock()
            mock_cr.return_value = mock_record

            decision, _ = await _handle_routing(
                db, obs, extraction, validation, RoutingDecision.INTERVENTIONIST_REVIEW
            )
        assert decision == "interventionist_review"
        mock_cr.assert_called_once()
        assert mock_cr.call_args[0][3] == RecordStatus.PENDING

    async def test_clarify_under_max_turns_creates_turn(self):
        db = AsyncMock()
        db.add = MagicMock()
        obs = _make_observation()
        extraction = _make_extraction_result()
        validation = _make_validation_result()

        with (
            patch(
                "src.backend.services.observation_service.AbstentionRouter"
            ) as MockRouter,
            patch(
                "src.backend.services.observation_service.ClarificationTurn"
            ) as MockTurn,
        ):
            router_inst = MockRouter.return_value
            router_inst.generate_clarification_questions.return_value = [
                "Can you describe the setting?"
            ]
            MockTurn.return_value = Mock()

            decision, question = await _handle_routing(
                db, obs, extraction, validation,
                RoutingDecision.CLARIFY, existing_turn_count=0,
            )
        assert decision == "clarify"
        assert question == "Can you describe the setting?"
        assert obs.status == ObservationStatus.CLARIFYING

    async def test_clarify_at_max_turns_falls_to_retain(self):
        db = AsyncMock()
        db.add = MagicMock()
        obs = _make_observation()
        extraction = _make_extraction_result()
        validation = _make_validation_result()

        with patch("src.backend.services.observation_service._create_record") as mock_cr:
            mock_cr.return_value = Mock()
            decision, question = await _handle_routing(
                db, obs, extraction, validation,
                RoutingDecision.CLARIFY, existing_turn_count=3,
            )
        assert decision == "retain_with_unknown"
        assert question is None
        assert obs.status == ObservationStatus.FINALIZED


class TestBuildConversationJson:
    def test_includes_raw_text(self):
        obs = _make_observation(raw_text="Hello world")
        result = build_conversation_json(obs)
        assert result["raw_text"] == "Hello world"

    def test_includes_clarification_turns(self):
        turn = Mock()
        turn.turn_number = 1
        turn.question = "Where?"
        turn.answer = "At home"
        turn.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        turn.answered_at = datetime(2026, 1, 2, tzinfo=UTC)
        obs = _make_observation(clarification_turns=[turn])
        result = build_conversation_json(obs)
        assert len(result["clarifications"]) == 1
        assert result["clarifications"][0]["question"] == "Where?"
        assert result["clarifications"][0]["answer"] == "At home"

    def test_empty_clarifications_when_none(self):
        obs = _make_observation(clarification_turns=[])
        result = build_conversation_json(obs)
        assert result["clarifications"] == []


class TestCorrectRecord:
    async def test_creates_new_version(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        original = Mock(spec=StructuredRecord)
        original.id = uuid.uuid4()
        original.observation_id = uuid.uuid4()
        original.version = 1
        original.validation_result = {"is_valid": True}
        original.provider = "temporary_llm"
        original.model = "claude-sonnet-4-20250514"
        original.prompt_version = "1.0"
        db.get = AsyncMock(return_value=original)

        with patch("src.backend.services.observation_service.StructuredRecord") as MockSR:
            mock_corrected = Mock()
            mock_corrected.version = 2
            mock_corrected.status = RecordStatus.CORRECTED
            mock_corrected.previous_version_id = original.id
            mock_corrected.correction_reason = "Misidentified behavior"
            mock_corrected.record_data = {"behavior": "corrected behavior"}
            MockSR.return_value = mock_corrected

            corrected = await correct_record(
                db,
                record_id=original.id,
                corrected_by=uuid.uuid4(),
                record_data={"behavior": "corrected behavior"},
                correction_reason="Misidentified behavior",
            )
        assert corrected.version == 2
        assert corrected.status == RecordStatus.CORRECTED
        assert corrected.previous_version_id == original.id
        assert corrected.correction_reason == "Misidentified behavior"

    async def test_raises_for_unknown_record(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await correct_record(
                db, uuid.uuid4(), uuid.uuid4(), {}, "reason"
            )


class TestSubmitObservation:
    async def test_pipeline_failure_sets_failed_status(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with patch("src.backend.services.observation_service.Observation") as MockObs:
            mock_obs = _make_observation()
            MockObs.return_value = mock_obs

            obs, routing, question = await submit_observation(
                db,
                child_id=uuid.uuid4(),
                submitted_by=uuid.uuid4(),
                raw_text="Some observation text",
                setting="home",
                source_type="conversational",
            )
        assert routing == "reject"
        assert obs.status == ObservationStatus.FAILED
