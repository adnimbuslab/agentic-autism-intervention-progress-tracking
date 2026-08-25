"""All SQLAlchemy models — import here so Alembic auto-discovers them."""

from src.backend.models.actor import ActorAssignment
from src.backend.models.audit import AuditEvent
from src.backend.models.child import Child
from src.backend.models.goal import Goal, ReviewPeriod
from src.backend.models.observation import (
    ClarificationTurn,
    Observation,
    StructuredRecord,
)
from src.backend.models.report import GeneratedReport
from src.backend.models.schedule import OverdueEvent, ReportingExpectation
from src.backend.models.user import User

__all__ = [
    "ActorAssignment",
    "AuditEvent",
    "Child",
    "ClarificationTurn",
    "GeneratedReport",
    "Goal",
    "Observation",
    "OverdueEvent",
    "ReportingExpectation",
    "ReviewPeriod",
    "StructuredRecord",
    "User",
]
