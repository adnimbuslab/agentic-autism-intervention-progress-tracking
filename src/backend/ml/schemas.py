"""Shared ML pipeline data contracts — validation, routing, adequacy, analytics, reporting."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

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
    message: str | None = None


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
    value: float | None = None
    threshold: float | None = None


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
    value: float | None = None
    prerequisites_met: bool = True
    display_eligible: bool = True
    abstained: bool = False
    abstention_reason: str | None = None


class AnalyticsResult(BaseModel):
    child_id: str
    review_period_id: str
    goal_id: str | None = None
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
    analytics: AnalyticsResult | None = None
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
    abstention_note: str | None = None


# --- Goal-Attainment Forecasting (Phase 1: deterministic trajectory only) ---


class GoalForecastResult(BaseModel):
    """Phase 1 deterministic trajectory projection for one KPI toward a goal's
    target threshold. No ML model is involved -- see docs/lld/Goal_Attainment_Forecasting.md.

    ``attainment_window`` is always ``None`` in Phase 1: the uncertainty-quantification
    method is an explicitly undefined open question in the owning LLD, and this
    component abstains on it rather than fabricating a band.
    """

    goal_id: str | None = None
    kpi_name: str
    current_value: float | None = None
    target_threshold: float
    slope_per_week: float | None = None
    already_met: bool = False
    projected_weeks_to_threshold: float | None = None
    projected_crossing_date: str | None = None
    attainment_window: tuple[str, str] | None = None
    abstained: bool = False
    abstention_reason: str | None = None
    caveat: str = (
        "This is a trajectory estimate conditional on the recent trend, "
        "not a committed prediction or clinical outcome."
    )


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
    # True when the prose came from the reporting LLM. That layer has not
    # passed its governance contract, so anything it writes is an experimental
    # artefact and must be labelled as one wherever it is shown.
    is_experimental: bool = False
