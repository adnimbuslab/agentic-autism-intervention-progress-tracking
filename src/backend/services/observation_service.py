"""Observation service — pipeline orchestration for observation submission,
clarification, structured record management, and evidence tracing."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.backend.config import settings
from src.backend.ml.abstention_router import AbstentionRouter
from src.backend.ml.extraction import ExtractionRequest, ExtractionResult, get_extraction_provider
from src.backend.ml.extraction.schemas import ExtractionStatus, SourceType
from src.backend.ml.schemas import RoutingDecision, ValidationResult
from src.backend.ml.validation_engine import ValidationEngine
from src.backend.models.observation import (
    ClarificationTurn,
    Observation,
    ObservationStatus,
    RecordStatus,
    StructuredRecord,
)
from src.backend.models.user import User
from src.backend.schemas.observation_schema import ContributorRole, Setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_extraction_request(
    observation: Observation,
    contributor_role: ContributorRole,
    goal_ids: list[str],
    clarification_history: list[dict[str, str]] | None = None,
) -> ExtractionRequest:
    return ExtractionRequest(
        source_type=SourceType(observation.source_type),
        text=observation.raw_text,
        child_id=str(observation.child_id),
        session_id=str(observation.id),
        contributor_role=contributor_role,
        observation_date=date.today(),
        setting=Setting(observation.setting),
        goal_ids=goal_ids,
        clarification_history=clarification_history or [],
    )


def _create_record(
    observation: Observation,
    extraction: ExtractionResult,
    validation: ValidationResult,
    status: RecordStatus,
) -> StructuredRecord:
    record_data: dict = {}
    if extraction.observations:
        record_data = extraction.observations[0].model_dump(mode="json")
    return StructuredRecord(
        observation_id=observation.id,
        record_data=record_data,
        validation_result=validation.model_dump(mode="json"),
        provider=extraction.provider,
        model=extraction.model,
        prompt_version=extraction.prompt_version,
        status=status,
    )


async def _run_pipeline(
    observation: Observation,
    contributor_role: ContributorRole,
    goal_ids: list[str],
    clarification_history: list[dict[str, str]] | None = None,
) -> tuple[ExtractionResult, ValidationResult, RoutingDecision]:
    request = _build_extraction_request(
        observation, contributor_role, goal_ids, clarification_history
    )
    provider = get_extraction_provider(
        settings.extraction_provider,
        api_key=settings.anthropic_api_key,
    )
    extraction = await provider.extract(request)

    validation_engine = ValidationEngine()
    if extraction.observations:
        validation = validation_engine.validate(
            extraction.observations[0],
            goal_ids=goal_ids,
        )
    else:
        validation = ValidationResult(
            is_valid=False,
            routing=RoutingDecision.REJECT,
            messages=["No observations extracted"],
        )

    router = AbstentionRouter()
    routing = router.route(extraction, validation)

    return extraction, validation, routing


async def _handle_routing(
    db: AsyncSession,
    observation: Observation,
    extraction: ExtractionResult,
    validation: ValidationResult,
    routing: RoutingDecision,
    existing_turn_count: int = 0,
) -> tuple[str, str | None]:
    question: str | None = None

    if routing == RoutingDecision.ACCEPT:
        record = _create_record(observation, extraction, validation, RecordStatus.VALIDATED)
        db.add(record)
        observation.status = ObservationStatus.FINALIZED
        observation.finalized_at = datetime.now(UTC)

    elif routing == RoutingDecision.CLARIFY:
        if existing_turn_count >= settings.clarification_max_turns:
            record = _create_record(observation, extraction, validation, RecordStatus.VALIDATED)
            db.add(record)
            observation.status = ObservationStatus.FINALIZED
            observation.finalized_at = datetime.now(UTC)
            return RoutingDecision.RETAIN_WITH_UNKNOWN.value, None

        router = AbstentionRouter()
        if extraction.observations:
            questions = router.generate_clarification_questions(
                extraction.observations[0], validation
            )
        else:
            questions = []
        question = questions[0] if questions else None

        if question:
            turn = ClarificationTurn(
                observation_id=observation.id,
                turn_number=existing_turn_count + 1,
                question=question,
            )
            db.add(turn)
            observation.status = ObservationStatus.CLARIFYING
        else:
            record = _create_record(observation, extraction, validation, RecordStatus.VALIDATED)
            db.add(record)
            observation.status = ObservationStatus.FINALIZED
            observation.finalized_at = datetime.now(UTC)
            return RoutingDecision.RETAIN_WITH_UNKNOWN.value, None

    elif routing == RoutingDecision.RETAIN_WITH_UNKNOWN:
        record = _create_record(observation, extraction, validation, RecordStatus.VALIDATED)
        db.add(record)
        observation.status = ObservationStatus.FINALIZED
        observation.finalized_at = datetime.now(UTC)

    elif routing == RoutingDecision.INTERVENTIONIST_REVIEW:
        record = _create_record(observation, extraction, validation, RecordStatus.PENDING)
        db.add(record)
        observation.status = ObservationStatus.FINALIZED
        observation.finalized_at = datetime.now(UTC)

    elif routing == RoutingDecision.REJECT:
        observation.status = ObservationStatus.FAILED

    return routing.value, question


def build_conversation_json(observation: Observation) -> dict:
    turns: list[dict] = []
    if observation.clarification_turns:
        for ct in observation.clarification_turns:
            entry: dict = {
                "turn": ct.turn_number,
                "question": ct.question,
                "answer": ct.answer,
                "asked_at": ct.created_at.isoformat() if ct.created_at else None,
                "answered_at": ct.answered_at.isoformat() if ct.answered_at else None,
            }
            turns.append(entry)
    return {
        "raw_text": observation.raw_text,
        "clarifications": turns,
    }


def _gather_clarification_history(
    clarification_turns: list[ClarificationTurn],
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for turn in clarification_turns:
        if turn.answer is not None:
            history.append({"question": turn.question, "answer": turn.answer})
    return history


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def submit_observation(
    db: AsyncSession,
    child_id: uuid.UUID,
    submitted_by: uuid.UUID,
    raw_text: str,
    setting: str,
    source_type: str,
    goal_id: uuid.UUID | None = None,
) -> tuple[Observation, str, str | None]:
    observation = Observation(
        child_id=child_id,
        submitted_by=submitted_by,
        raw_text=raw_text,
        source_type=source_type,
        setting=setting,
        status=ObservationStatus.PENDING,
    )
    db.add(observation)
    await db.flush()

    user = await db.get(User, submitted_by)
    if user is None:
        observation.status = ObservationStatus.FAILED
        await db.flush()
        return observation, RoutingDecision.REJECT.value, None

    contributor_role = ContributorRole(user.role.value)
    goal_ids = [str(goal_id)] if goal_id else []

    try:
        extraction, validation, routing = await _run_pipeline(
            observation, contributor_role, goal_ids
        )
    except Exception:
        logger.exception("Extraction pipeline failed for observation %s", observation.id)
        observation.status = ObservationStatus.FAILED
        await db.flush()
        return observation, RoutingDecision.REJECT.value, None

    observation.extraction_result_json = extraction.model_dump(mode="json")
    observation.status = ObservationStatus.EXTRACTING

    routing_value, question = await _handle_routing(
        db, observation, extraction, validation, routing
    )

    observation.conversation_json = build_conversation_json(observation)
    await db.flush()

    return observation, routing_value, question


async def submit_clarification(
    db: AsyncSession,
    observation_id: uuid.UUID,
    answer: str | None,
    declined: bool = False,
) -> tuple[Observation, str, str | None]:
    stmt = (
        select(Observation)
        .options(selectinload(Observation.clarification_turns))
        .where(Observation.id == observation_id)
    )
    result = await db.execute(stmt)
    observation = result.scalar_one_or_none()
    if observation is None:
        raise ValueError(f"Observation {observation_id} not found")
    if observation.status != ObservationStatus.CLARIFYING:
        raise ValueError(f"Observation {observation_id} is not in CLARIFYING state")

    unanswered = [
        ct for ct in observation.clarification_turns if ct.answer is None
    ]
    if not unanswered:
        raise ValueError(f"No unanswered clarification turns for observation {observation_id}")

    latest_turn = unanswered[-1]
    latest_turn.answer = answer if not declined else None
    latest_turn.answered_at = datetime.now(UTC)

    turn_count = len(observation.clarification_turns)

    if declined or answer is None:
        extraction = ExtractionResult.model_validate(observation.extraction_result_json)
        validation_engine = ValidationEngine()
        if extraction.observations:
            validation = validation_engine.validate(extraction.observations[0])
        else:
            validation = ValidationResult(
                is_valid=False,
                routing=RoutingDecision.REJECT,
                messages=["No observations extracted"],
            )
        record = _create_record(observation, extraction, validation, RecordStatus.VALIDATED)
        db.add(record)
        observation.status = ObservationStatus.FINALIZED
        observation.finalized_at = datetime.now(UTC)
        observation.conversation_json = build_conversation_json(observation)
        await db.flush()
        return observation, RoutingDecision.RETAIN_WITH_UNKNOWN.value, None

    user = await db.get(User, observation.submitted_by)
    contributor_role = ContributorRole(user.role.value) if user else ContributorRole.PARENT
    goal_ids: list[str] = []
    history = _gather_clarification_history(observation.clarification_turns)

    try:
        extraction, validation, routing = await _run_pipeline(
            observation, contributor_role, goal_ids, history
        )
    except Exception:
        logger.exception("Re-extraction failed for observation %s", observation.id)
        observation.status = ObservationStatus.FAILED
        observation.conversation_json = build_conversation_json(observation)
        await db.flush()
        return observation, RoutingDecision.REJECT.value, None

    observation.extraction_result_json = extraction.model_dump(mode="json")

    routing_value, question = await _handle_routing(
        db, observation, extraction, validation, routing,
        existing_turn_count=turn_count,
    )

    observation.conversation_json = build_conversation_json(observation)
    await db.flush()

    return observation, routing_value, question


async def finalize_observation(
    db: AsyncSession,
    observation_id: uuid.UUID,
) -> Observation:
    stmt = (
        select(Observation)
        .options(selectinload(Observation.clarification_turns))
        .where(Observation.id == observation_id)
    )
    result = await db.execute(stmt)
    observation = result.scalar_one_or_none()
    if observation is None:
        raise ValueError(f"Observation {observation_id} not found")
    if observation.status != ObservationStatus.CLARIFYING:
        raise ValueError(f"Observation {observation_id} is not in CLARIFYING state")

    if observation.extraction_result_json:
        extraction = ExtractionResult.model_validate(observation.extraction_result_json)
        validation_engine = ValidationEngine()
        if extraction.observations:
            validation = validation_engine.validate(extraction.observations[0])
        else:
            validation = ValidationResult(
                is_valid=False,
                routing=RoutingDecision.REJECT,
                messages=["No observations extracted"],
            )
        record = _create_record(observation, extraction, validation, RecordStatus.VALIDATED)
        db.add(record)

    observation.status = ObservationStatus.FINALIZED
    observation.finalized_at = datetime.now(UTC)
    observation.conversation_json = build_conversation_json(observation)
    await db.flush()
    return observation


async def get_observation(
    db: AsyncSession,
    observation_id: uuid.UUID,
) -> Observation | None:
    stmt = (
        select(Observation)
        .options(
            selectinload(Observation.clarification_turns),
            selectinload(Observation.structured_records),
        )
        .where(Observation.id == observation_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_observations(
    db: AsyncSession,
    child_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> list[Observation]:
    stmt = select(Observation).where(Observation.child_id == child_id)
    if user_id is not None:
        stmt = stmt.where(Observation.submitted_by == user_id)
    stmt = stmt.order_by(Observation.submitted_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_conversation(
    db: AsyncSession,
    observation_id: uuid.UUID,
) -> dict:
    stmt = (
        select(Observation)
        .options(selectinload(Observation.clarification_turns))
        .where(Observation.id == observation_id)
    )
    result = await db.execute(stmt)
    observation = result.scalar_one_or_none()
    if observation is None:
        raise ValueError(f"Observation {observation_id} not found")

    turns = []
    pending_question: str | None = None
    for ct in observation.clarification_turns:
        turns.append({
            "turn_number": ct.turn_number,
            "question": ct.question,
            "answer": ct.answer,
            "created_at": ct.created_at,
            "answered_at": ct.answered_at,
        })
        if ct.answer is None:
            pending_question = ct.question

    return {
        "observation_id": observation.id,
        "raw_text": observation.raw_text,
        "status": observation.status,
        "clarification_turns": turns,
        "pending_question": pending_question,
    }


# ---------------------------------------------------------------------------
# Structured records
# ---------------------------------------------------------------------------


async def correct_record(
    db: AsyncSession,
    record_id: uuid.UUID,
    corrected_by: uuid.UUID,
    record_data: dict,
    correction_reason: str,
) -> StructuredRecord:
    original = await db.get(StructuredRecord, record_id)
    if original is None:
        raise ValueError(f"StructuredRecord {record_id} not found")

    corrected = StructuredRecord(
        observation_id=original.observation_id,
        version=original.version + 1,
        status=RecordStatus.CORRECTED,
        record_data=record_data,
        validation_result=original.validation_result,
        corrected_by=corrected_by,
        correction_reason=correction_reason,
        previous_version_id=original.id,
        provider=original.provider,
        model=original.model,
        prompt_version=original.prompt_version,
    )
    db.add(corrected)
    await db.flush()
    return corrected


async def get_record(
    db: AsyncSession,
    record_id: uuid.UUID,
) -> StructuredRecord | None:
    return await db.get(StructuredRecord, record_id)


async def list_records(
    db: AsyncSession,
    child_id: uuid.UUID,
) -> list[StructuredRecord]:
    stmt = (
        select(StructuredRecord)
        .join(Observation, StructuredRecord.observation_id == Observation.id)
        .where(Observation.child_id == child_id)
        .order_by(StructuredRecord.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_record_history(
    db: AsyncSession,
    record_id: uuid.UUID,
) -> list[StructuredRecord]:
    record = await db.get(StructuredRecord, record_id)
    if record is None:
        raise ValueError(f"StructuredRecord {record_id} not found")
    stmt = (
        select(StructuredRecord)
        .where(StructuredRecord.observation_id == record.observation_id)
        .order_by(StructuredRecord.version)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
