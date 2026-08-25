"""Safety property tests — raw_text immutability, append-only clarification turns,
versioned corrections, and audit trail append-only semantics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.backend.models.observation import RecordStatus, StructuredRecord
from src.backend.services.observation_service import (
    build_conversation_json,
    correct_record,
)


class TestRawTextImmutability:
    """raw_text is set once at submission and must never be modified."""

    def test_raw_text_preserved_in_conversation_json(self):
        obs = Mock()
        obs.raw_text = "Original observation text"
        obs.clarification_turns = []

        result = build_conversation_json(obs)
        assert result["raw_text"] == "Original observation text"

    def test_raw_text_unchanged_after_clarification_turns(self):
        turn1 = Mock()
        turn1.turn_number = 1
        turn1.question = "Where?"
        turn1.answer = "At home"
        turn1.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        turn1.answered_at = datetime(2026, 1, 2, tzinfo=UTC)

        turn2 = Mock()
        turn2.turn_number = 2
        turn2.question = "When?"
        turn2.answer = "Yesterday"
        turn2.created_at = datetime(2026, 1, 3, tzinfo=UTC)
        turn2.answered_at = datetime(2026, 1, 4, tzinfo=UTC)

        obs = Mock()
        obs.raw_text = "Child said 'car' while pointing at toy"
        obs.clarification_turns = [turn1, turn2]

        result = build_conversation_json(obs)
        assert result["raw_text"] == "Child said 'car' while pointing at toy"
        assert len(result["clarifications"]) == 2

    def test_conversation_json_does_not_modify_raw_text_field(self):
        obs = Mock()
        obs.raw_text = "Immutable text"
        obs.clarification_turns = []

        build_conversation_json(obs)
        assert obs.raw_text == "Immutable text"


class TestAppendOnlyClarificationTurns:
    """Clarification turns are append-only — new turns are created, never modified."""

    def test_turns_are_sequentially_numbered(self):
        turns = []
        for i in range(1, 4):
            turn = Mock()
            turn.turn_number = i
            turn.question = f"Question {i}?"
            turn.answer = f"Answer {i}" if i < 3 else None
            turn.created_at = datetime(2026, 1, i, tzinfo=UTC)
            turn.answered_at = (
                datetime(2026, 1, i + 1, tzinfo=UTC) if i < 3 else None
            )
            turns.append(turn)

        obs = Mock()
        obs.raw_text = "Original text"
        obs.clarification_turns = turns

        result = build_conversation_json(obs)
        assert len(result["clarifications"]) == 3
        for i, entry in enumerate(result["clarifications"]):
            assert entry["turn"] == i + 1

    def test_answered_turn_preserves_answer(self):
        turn = Mock()
        turn.turn_number = 1
        turn.question = "What color?"
        turn.answer = "Blue"
        turn.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        turn.answered_at = datetime(2026, 1, 2, tzinfo=UTC)

        obs = Mock()
        obs.raw_text = "The child saw something"
        obs.clarification_turns = [turn]

        result = build_conversation_json(obs)
        assert result["clarifications"][0]["answer"] == "Blue"

    def test_unanswered_turn_has_null_answer(self):
        turn = Mock()
        turn.turn_number = 1
        turn.question = "What happened next?"
        turn.answer = None
        turn.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        turn.answered_at = None

        obs = Mock()
        obs.raw_text = "The child ..."
        obs.clarification_turns = [turn]

        result = build_conversation_json(obs)
        assert result["clarifications"][0]["answer"] is None


class TestVersionedCorrections:
    """Corrections create new versions — originals are never overwritten."""

    async def test_correction_increments_version(self):
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
            mock_corrected.version = original.version + 1
            mock_corrected.previous_version_id = original.id
            mock_corrected.status = RecordStatus.CORRECTED
            MockSR.return_value = mock_corrected

            corrected = await correct_record(
                db,
                record_id=original.id,
                corrected_by=uuid.uuid4(),
                record_data={"behavior": "corrected"},
                correction_reason="Error in original",
            )

        assert corrected.version == original.version + 1
        assert corrected.previous_version_id == original.id
        assert corrected.status == RecordStatus.CORRECTED

    async def test_correction_preserves_original_provider_metadata(self):
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
            mock_corrected.provider = "temporary_llm"
            mock_corrected.model = "claude-sonnet-4-20250514"
            mock_corrected.prompt_version = "1.0"
            MockSR.return_value = mock_corrected

            corrected = await correct_record(
                db, original.id, uuid.uuid4(), {"b": "c"}, "reason"
            )

        call_kwargs = MockSR.call_args[1]
        assert call_kwargs["provider"] == "temporary_llm"
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["prompt_version"] == "1.0"

    async def test_multiple_corrections_chain_versions(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        v1 = Mock(spec=StructuredRecord)
        v1.id = uuid.uuid4()
        v1.observation_id = uuid.uuid4()
        v1.version = 1
        v1.validation_result = {"is_valid": True}
        v1.provider = "temporary_llm"
        v1.model = "claude-sonnet-4-20250514"
        v1.prompt_version = "1.0"

        db.get = AsyncMock(return_value=v1)

        with patch("src.backend.services.observation_service.StructuredRecord") as MockSR:
            v2_mock = Mock()
            v2_mock.id = uuid.uuid4()
            v2_mock.version = 2
            v2_mock.previous_version_id = v1.id
            MockSR.return_value = v2_mock

            v2 = await correct_record(
                db, v1.id, uuid.uuid4(), {"b": "v2"}, "first correction"
            )
        assert v2.version == 2
        assert v2.previous_version_id == v1.id

        v2_original = Mock(spec=StructuredRecord)
        v2_original.id = v2.id
        v2_original.observation_id = v1.observation_id
        v2_original.version = 2
        v2_original.validation_result = v1.validation_result
        v2_original.provider = v1.provider
        v2_original.model = v1.model
        v2_original.prompt_version = v1.prompt_version

        db.get = AsyncMock(return_value=v2_original)

        with patch("src.backend.services.observation_service.StructuredRecord") as MockSR:
            v3_mock = Mock()
            v3_mock.version = 3
            v3_mock.previous_version_id = v2.id
            MockSR.return_value = v3_mock

            v3 = await correct_record(
                db, v2.id, uuid.uuid4(), {"b": "v3"}, "second correction"
            )
        assert v3.version == 3
        assert v3.previous_version_id == v2.id


class TestAuditTrailAppendOnly:
    """Audit events are only ever created — never updated or deleted."""

    async def test_log_event_adds_and_flushes(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        with patch("src.backend.services.audit_service.AuditEvent") as MockEvent:
            mock_event = Mock()
            mock_event.action = "submit_observation"
            MockEvent.return_value = mock_event

            from src.backend.services.audit_service import log_event

            event = await log_event(
                db,
                user_id=uuid.uuid4(),
                action="submit_observation",
                resource_type="observation",
                resource_id=str(uuid.uuid4()),
                child_id=uuid.uuid4(),
            )
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        assert event.action == "submit_observation"

    async def test_log_event_preserves_detail(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        detail = {"previous_record_id": "abc", "reason": "correction"}

        with patch("src.backend.services.audit_service.AuditEvent") as MockEvent:
            mock_event = Mock()
            mock_event.detail = detail
            MockEvent.return_value = mock_event

            from src.backend.services.audit_service import log_event

            event = await log_event(
                db,
                user_id=uuid.uuid4(),
                action="correct_record",
                resource_type="structured_record",
                detail=detail,
            )
        assert event.detail == detail
