"""Observation routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from src.backend.api.deps import (
    CurrentUser,
    DBSession,
    RequireInterventionist,
    authorize_child_access,
)
from src.backend.models.user import Role
from src.backend.schemas.api_schemas import (
    ClarificationSubmit,
    ClarificationTurnResponse,
    ConversationResponse,
    ObservationCreate,
    ObservationDetail,
    ObservationResponse,
    ObservationSubmitResponse,
    RecordResponse,
)
from src.backend.services import audit_service, observation_service

router = APIRouter(tags=["observations"])


@router.post(
    "/children/{child_id}/observations",
    response_model=ObservationSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_observation(
    child_id: uuid.UUID,
    body: ObservationCreate,
    user: CurrentUser,
    db: DBSession,
) -> ObservationSubmitResponse:
    await authorize_child_access(user, child_id, db)
    observation, routing_decision, clarification_question = (
        await observation_service.submit_observation(
            db,
            child_id=child_id,
            submitted_by=user.id,
            raw_text=body.raw_text,
            setting=body.setting.value,
            source_type=body.source_type,
            goal_id=body.goal_id,
        )
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="submit_observation",
        resource_type="observation",
        resource_id=str(observation.id),
        child_id=child_id,
    )
    await db.commit()
    return ObservationSubmitResponse(
        observation=ObservationResponse.model_validate(observation),
        routing_decision=routing_decision,
        clarification_question=clarification_question,
    )


@router.post(
    "/observations/{observation_id}/clarifications",
    response_model=ObservationSubmitResponse,
)
async def submit_clarification(
    observation_id: uuid.UUID,
    body: ClarificationSubmit,
    user: CurrentUser,
    db: DBSession,
) -> ObservationSubmitResponse:
    observation = await observation_service.get_observation(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found",
        )
    await authorize_child_access(user, observation.child_id, db)
    if observation.submitted_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the original submitter may respond to clarifications",
        )
    observation, routing_decision, clarification_question = (
        await observation_service.submit_clarification(
            db,
            observation_id=observation_id,
            answer=body.answer,
            declined=body.declined,
        )
    )
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="submit_clarification",
        resource_type="observation",
        resource_id=str(observation.id),
        child_id=observation.child_id,
    )
    await db.commit()
    return ObservationSubmitResponse(
        observation=ObservationResponse.model_validate(observation),
        routing_decision=routing_decision,
        clarification_question=clarification_question,
    )


@router.get(
    "/observations/{observation_id}/conversation",
    response_model=ConversationResponse,
)
async def get_conversation(
    observation_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> ConversationResponse:
    observation = await observation_service.get_observation(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found",
        )
    await authorize_child_access(user, observation.child_id, db)
    conversation = await observation_service.get_conversation(db, observation_id)
    turns = [
        ClarificationTurnResponse.model_validate(t)
        for t in conversation.get("clarification_turns", [])
    ]
    return ConversationResponse(
        observation_id=conversation["observation_id"],
        raw_text=conversation["raw_text"],
        status=conversation["status"],
        clarification_turns=turns,
        pending_question=conversation.get("pending_question"),
    )


@router.post(
    "/observations/{observation_id}/finalize",
    response_model=ObservationResponse,
)
async def finalize_observation(
    observation_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> ObservationResponse:
    observation = await observation_service.get_observation(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found",
        )
    await authorize_child_access(user, observation.child_id, db)
    if observation.submitted_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the original submitter may finalize an observation",
        )
    observation = await observation_service.finalize_observation(db, observation_id)
    await audit_service.log_event(
        db,
        user_id=user.id,
        action="finalize_observation",
        resource_type="observation",
        resource_id=str(observation.id),
        child_id=observation.child_id,
    )
    await db.commit()
    return ObservationResponse.model_validate(observation)


@router.get(
    "/children/{child_id}/observations",
    response_model=list[ObservationResponse],
)
async def list_observations(
    child_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> list[ObservationResponse]:
    await authorize_child_access(user, child_id, db)
    user_id_filter = None if user.role == Role.INTERVENTIONIST else user.id
    observations = await observation_service.list_observations(
        db, child_id, user_id=user_id_filter,
    )
    return [ObservationResponse.model_validate(o) for o in observations]


@router.get(
    "/observations/{observation_id}",
    response_model=ObservationDetail,
)
async def get_observation(
    observation_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> ObservationDetail:
    observation = await observation_service.get_observation(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found",
        )
    await authorize_child_access(user, observation.child_id, db)
    turns = [
        ClarificationTurnResponse.model_validate(t)
        for t in observation.clarification_turns
    ]
    record = None
    if user.role == Role.INTERVENTIONIST and observation.structured_records:
        latest = max(observation.structured_records, key=lambda r: r.version)
        record = RecordResponse.model_validate(latest)
    return ObservationDetail(
        id=observation.id,
        child_id=observation.child_id,
        submitted_by=observation.submitted_by,
        raw_text=observation.raw_text,
        source_type=observation.source_type,
        setting=observation.setting,
        status=observation.status,
        submitted_at=observation.submitted_at,
        finalized_at=observation.finalized_at,
        clarification_turns=turns,
        structured_record=record,
    )
