"""Shared fixtures for Phase 3 backend API and service tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from src.backend.api.deps import get_current_user
from src.backend.database import get_session
from src.backend.main import app
from src.backend.models.observation import ObservationStatus, RecordStatus
from src.backend.models.user import Role, User


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_user(
    role: Role = Role.INTERVENTIONIST,
    user_id: uuid.UUID | None = None,
    is_active: bool = True,
    email: str | None = None,
) -> Mock:
    user = Mock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = email or f"test_{role.value}@example.com"
    user.full_name = f"Test {role.value.replace('_', ' ').title()}"
    user.role = role
    user.is_active = is_active
    user.hashed_password = "$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake"
    return user


def make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    return session


def make_child(
    child_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    display_name: str = "Test Child",
) -> Mock:
    m = Mock()
    m.id = child_id or uuid.uuid4()
    m.display_name = display_name
    m.date_of_birth = None
    m.created_by = created_by or uuid.uuid4()
    m.created_at = datetime.now(UTC)
    m.is_active = True
    return m


def make_observation(
    obs_id: uuid.UUID | None = None,
    child_id: uuid.UUID | None = None,
    submitted_by: uuid.UUID | None = None,
    status: ObservationStatus = ObservationStatus.PENDING,
) -> Mock:
    m = Mock()
    m.id = obs_id or uuid.uuid4()
    m.child_id = child_id or uuid.uuid4()
    m.submitted_by = submitted_by or uuid.uuid4()
    m.raw_text = "The child pointed at the toy and said 'car'."
    m.source_type = "conversational"
    m.setting = "home"
    m.status = status
    m.submitted_at = datetime.now(UTC)
    m.finalized_at = None
    m.conversation_json = None
    m.extraction_result_json = None
    m.clarification_turns = []
    m.structured_records = []
    return m


def make_record(
    record_id: uuid.UUID | None = None,
    observation_id: uuid.UUID | None = None,
    version: int = 1,
    status: RecordStatus = RecordStatus.VALIDATED,
) -> Mock:
    m = Mock()
    m.id = record_id or uuid.uuid4()
    m.observation_id = observation_id or uuid.uuid4()
    m.version = version
    m.status = status
    m.record_data = {"behavior": "pointed at toy"}
    m.validation_result = {"is_valid": True}
    m.corrected_by = None
    m.correction_reason = None
    # Explicitly None: a bare Mock would auto-create these attributes and the
    # response schema would try to validate a Mock as a UUID.
    m.verified_by = None
    m.verified_at = None
    m.previous_version_id = None
    m.provider = "temporary_llm"
    m.model = "claude-sonnet-4-20250514"
    m.prompt_version = "1.0"
    m.created_at = datetime.now(UTC)
    return m


def make_goal(
    goal_id: uuid.UUID | None = None,
    child_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> Mock:
    m = Mock()
    m.id = goal_id or uuid.uuid4()
    m.child_id = child_id or uuid.uuid4()
    m.goal_type = "short_term"
    m.domain = "social_communication"
    m.title = "Test Goal"
    m.description = "Increase social communication skills"
    m.criteria = None
    m.parent_goal_id = None
    m.start_date = None
    m.target_date = None
    m.is_active = True
    m.version = 1
    m.created_by = created_by or uuid.uuid4()
    m.created_at = datetime.now(UTC)
    return m


def make_actor(
    assignment_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    child_id: uuid.UUID | None = None,
    invited_by: uuid.UUID | None = None,
) -> Mock:
    m = Mock()
    m.id = assignment_id or uuid.uuid4()
    m.user_id = user_id or uuid.uuid4()
    m.child_id = child_id or uuid.uuid4()
    m.role = Role.PARENT
    m.invited_by = invited_by or uuid.uuid4()
    m.invited_at = datetime.now(UTC)
    m.invitation_email = "actor@example.com"
    m.revoked_at = None
    return m


def make_audit_event(
    event_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    child_id: uuid.UUID | None = None,
) -> Mock:
    m = Mock()
    m.id = event_id or uuid.uuid4()
    m.user_id = user_id or uuid.uuid4()
    m.child_id = child_id or uuid.uuid4()
    m.action = "create_child"
    m.resource_type = "child"
    m.resource_id = str(uuid.uuid4())
    m.detail = None
    m.created_at = datetime.now(UTC)
    return m


def make_schedule(
    schedule_id: uuid.UUID | None = None,
    child_id: uuid.UUID | None = None,
) -> Mock:
    m = Mock()
    m.id = schedule_id or uuid.uuid4()
    m.child_id = child_id or uuid.uuid4()
    m.goal_id = None
    m.actor_id = None
    m.setting = None
    m.cadence_days = 7
    m.description = "Weekly observation"
    m.is_active = True
    m.created_at = datetime.now(UTC)
    m.overdue = None
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def interventionist_user() -> Mock:
    return make_user(Role.INTERVENTIONIST)


@pytest.fixture
def contributor_user() -> Mock:
    return make_user(Role.PARENT)


@pytest.fixture
def mock_db() -> AsyncMock:
    return make_mock_session()


@pytest.fixture
async def interventionist_client(interventionist_user, mock_db):
    async def _override_session():
        yield mock_db

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: interventionist_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def contributor_client(contributor_user, mock_db):
    async def _override_session():
        yield mock_db

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: contributor_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def unauth_client(mock_db):
    """Client with session override only (no auth override)."""

    async def _override_session():
        yield mock_db

    app.dependency_overrides[get_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
