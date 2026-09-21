"""API request/response schemas for all endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from src.backend.models.goal import GoalType
from src.backend.models.observation import ObservationStatus, RecordStatus
from src.backend.models.user import Role
from src.backend.schemas.observation_schema import Domain, Setting


# --- Auth ---


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    role: Role


# --- Children ---


class ChildCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    date_of_birth: Optional[date] = None


class ChildUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    date_of_birth: Optional[date] = None
    is_active: Optional[bool] = None


class ChildResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    date_of_birth: Optional[datetime] = None
    created_by: uuid.UUID
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# --- Goals ---


class GoalCreate(BaseModel):
    goal_type: GoalType
    domain: Domain
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1)
    criteria: Optional[str] = None
    parent_goal_id: Optional[uuid.UUID] = None
    start_date: Optional[date] = None
    target_date: Optional[date] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, min_length=1)
    criteria: Optional[str] = None
    is_active: Optional[bool] = None


class GoalResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    goal_type: GoalType
    domain: Domain
    title: str
    description: str
    criteria: Optional[str]
    parent_goal_id: Optional[uuid.UUID]
    start_date: Optional[date]
    target_date: Optional[date]
    is_active: bool
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Actors ---


class ActorInvite(BaseModel):
    email: str
    role: Role


class ActorResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    child_id: uuid.UUID
    role: Role
    invited_by: uuid.UUID
    invited_at: datetime
    invitation_email: Optional[str]
    revoked_at: Optional[datetime]

    model_config = {"from_attributes": True}


# --- Observations ---


class ObservationCreate(BaseModel):
    raw_text: str = Field(min_length=1)
    setting: Setting
    source_type: str = "conversational"
    goal_id: Optional[uuid.UUID] = None


class ClarificationSubmit(BaseModel):
    answer: Optional[str] = None
    declined: bool = False


class ClarificationTurnResponse(BaseModel):
    turn_number: int
    question: str
    answer: Optional[str]
    created_at: datetime
    answered_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ObservationResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    submitted_by: uuid.UUID
    raw_text: str
    source_type: str
    setting: str
    status: ObservationStatus
    submitted_at: datetime
    finalized_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ObservationDetail(ObservationResponse):
    clarification_turns: list[ClarificationTurnResponse] = Field(default_factory=list)
    structured_record: Optional[RecordResponse] = None


class ConversationResponse(BaseModel):
    observation_id: uuid.UUID
    raw_text: str
    status: ObservationStatus
    clarification_turns: list[ClarificationTurnResponse] = Field(default_factory=list)
    pending_question: Optional[str] = None


class ObservationSubmitResponse(BaseModel):
    observation: ObservationResponse
    routing_decision: str
    clarification_question: Optional[str] = None


# --- Structured Records ---


class RecordResponse(BaseModel):
    id: uuid.UUID
    observation_id: uuid.UUID
    version: int
    status: RecordStatus
    record_data: dict
    validation_result: Optional[dict]
    corrected_by: Optional[uuid.UUID]
    correction_reason: Optional[str]
    # Defaulted: records created before verification existed carry neither,
    # and a required field would 500 on every one of them.
    verified_by: Optional[uuid.UUID] = None
    verified_at: Optional[datetime] = None
    provider: str
    model: str
    prompt_version: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RecordCorrection(BaseModel):
    record_data: dict
    correction_reason: str = Field(min_length=1)


# --- Schedules ---


class ScheduleCreate(BaseModel):
    goal_id: Optional[uuid.UUID] = None
    actor_id: Optional[uuid.UUID] = None
    setting: Optional[str] = None
    cadence_days: int = Field(ge=1)
    description: Optional[str] = None


class ScheduleUpdate(BaseModel):
    cadence_days: Optional[int] = Field(default=None, ge=1)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OverdueInfo(BaseModel):
    is_overdue: bool
    due_date: Optional[date] = None
    days_overdue: int = 0


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    goal_id: Optional[uuid.UUID]
    actor_id: Optional[uuid.UUID]
    setting: Optional[str]
    cadence_days: int
    description: Optional[str]
    is_active: bool
    created_at: datetime
    overdue: Optional[OverdueInfo] = None

    model_config = {"from_attributes": True}


# --- Audit ---


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    child_id: Optional[uuid.UUID]
    action: str
    resource_type: str
    resource_id: Optional[str]
    detail: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Generic ---


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int = 1
    page_size: int = 50


# --- Analytics (Phase 4) ---


class AnalyticsRequest(BaseModel):
    review_period_id: uuid.UUID
    goal_id: Optional[uuid.UUID] = None


class KpiResponse(BaseModel):
    name: str
    numerator: float
    denominator: float
    value: Optional[float] = None
    abstained: bool = False
    abstention_reason: Optional[str] = None
    display_eligible: bool = True


class AdequacyCheckResponse(BaseModel):
    check: str
    passed: bool
    detail: str
    value: Optional[float] = None
    threshold: Optional[float] = None


class AdequacyResponse(BaseModel):
    level: str
    eligible: bool
    checks: list[AdequacyCheckResponse] = Field(default_factory=list)
    partial_abstentions: dict[str, str] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)


class AnalyticsResponse(BaseModel):
    child_id: uuid.UUID
    review_period_id: uuid.UUID
    goal_id: Optional[uuid.UUID] = None
    kpis: list[KpiResponse] = Field(default_factory=list)
    adequacy: AdequacyResponse
    computed_at: datetime


# --- Reports (Phase 4) ---


class ReportGenerateRequest(BaseModel):
    review_period_id: uuid.UUID
    goal_id: Optional[uuid.UUID] = None


class ReportSectionResponse(BaseModel):
    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=list)
    abstention_note: Optional[str] = None


class ReportResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    review_period_id: uuid.UUID
    sections: list[ReportSectionResponse] = Field(default_factory=list)
    provider: str
    model: str
    prompt_version: str
    version: int
    validation_passed: bool
    validation_errors: Optional[dict] = None
    flagged: bool
    flagged_reason: Optional[str] = None
    flagged_by: Optional[uuid.UUID] = None
    generated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_experimental(self) -> bool:
        """True when the reporting LLM wrote this report.

        Derived from the stored provider rather than a column of its own, so
        it cannot drift away from what actually produced the prose. The
        generative layer has not passed its governance contract, so its output
        is an experimental artefact and the UI must say so.
        """
        return self.provider != "deterministic"


class ReportListItem(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    review_period_id: uuid.UUID
    version: int
    validation_passed: bool
    flagged: bool
    generated_at: datetime

    model_config = {"from_attributes": True}


class ReportFlagRequest(BaseModel):
    reason: str = Field(min_length=1)


class EvidencePacketResponse(BaseModel):
    child_id: str
    review_period_id: str
    review_period_start: str
    review_period_end: str
    goals: list[dict] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    record_versions: dict[str, int] = Field(default_factory=dict)
    contributor_summary: dict[str, int] = Field(default_factory=dict)
    setting_summary: dict[str, int] = Field(default_factory=dict)
    observation_count: int = 0
    abstained_count: int = 0
    review_count: int = 0
    quality_flags: list[str] = Field(default_factory=list)


# --- Review Periods ---


class ReviewPeriodCreate(BaseModel):
    start_date: date
    end_date: date


class ReviewPeriodResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    start_date: date
    end_date: date
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
