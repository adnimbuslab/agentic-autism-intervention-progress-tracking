"""Shared ML pipeline data contracts — validation, routing, adequacy, analytics, reporting."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Validation ---


class ValidationSeverity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FieldValidation(BaseModel):
    field_name: str
    is_valid: bool
    severity: ValidationSeverity = ValidationSeverity.ERROR
    message: Optional[str] = None


class RoutingDecision(str, enum.Enum):
    ACCEPT = "accept"
    CLARIFY = "clarify"
    RETAIN_WITH_UNKNOWN = "retain_with_unknown"
    INTERVENTIONIST_REVIEW = "interventionist_review"
    REJECT = "reject"


class ValidationResult(BaseModel):
    is_valid: bool
    routing: RoutingDecision
    field_validations: list[FieldValidation] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


# --- Adequacy ---


class AdequacyLevel(str, enum.Enum):
    ADEQUATE = "adequate"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class AdequacyCheck(str, enum.Enum):
    COVERAGE = "coverage"
    TIMELINESS = "timeliness"
    SETTING_REPRESENTATION = "setting_representation"
    CONTRIBUTOR_REPRESENTATION = "contributor_representation"
    FIELD_COMPLETENESS = "field_completeness"
    CONSISTENCY = "consistency"
    GOAL_COVERAGE = "goal_coverage"
    TEMPORAL_DISTRIBUTION = "temporal_distribution"


class AdequacyCheckResult(BaseModel):
    check: AdequacyCheck
    passed: bool
    detail: str
    value: Optional[float] = None
    threshold: Optional[float] = None


class AdequacyResult(BaseModel):
    level: AdequacyLevel = AdequacyLevel.INSUFFICIENT
    eligible: bool
    checks: list[AdequacyCheckResult] = Field(default_factory=list)
    partial_abstentions: dict[str, str] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)


# --- Analytics ---


class KpiResult(BaseModel):
    name: str
    numerator: float
    denominator: float
    value: Optional[float] = None
    prerequisites_met: bool = True
    display_eligible: bool = True
    abstained: bool = False
    abstention_reason: Optional[str] = None


class AnalyticsResult(BaseModel):
    child_id: str
    review_period_id: str
    goal_id: Optional[str] = None
    kpis: list[KpiResult] = Field(default_factory=list)
    adequacy: AdequacyResult
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- Reporting ---


class EvidencePacket(BaseModel):
    child_id: str
    review_period_id: str
    review_period_start: str
    review_period_end: str
    goals: list[dict[str, object]] = Field(default_factory=list)
    structured_records: list[dict[str, object]] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    record_versions: dict[str, int] = Field(default_factory=dict)
    analytics: Optional[AnalyticsResult] = None
    adequacy: AdequacyResult
    quality_flags: list[str] = Field(default_factory=list)
    contributor_summary: dict[str, int] = Field(default_factory=dict)
    setting_summary: dict[str, int] = Field(default_factory=dict)
    observation_count: int = 0
    abstained_count: int = 0
    review_count: int = 0


class ReportSection(BaseModel):
    heading: str
    body: str
    evidence_refs: list[str] = Field(default_factory=list)
    abstention_note: Optional[str] = None


class GeneratedReportData(BaseModel):
    child_id: str
    review_period_id: str
    sections: list[ReportSection] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    prompt_version: str = "1.0"
    validation_passed: bool = False
    validation_errors: list[str] = Field(default_factory=list)
