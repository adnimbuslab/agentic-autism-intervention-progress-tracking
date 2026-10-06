"""Integration test fixtures — real database, real services, mocked external LLM only.

Uses a dedicated test database created fresh for each test session. All FastAPI
routes, SQLAlchemy persistence, validation, adequacy, and analytics run against
real code. Only the external Anthropic API boundary is mocked.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.asyncio(loop_scope="session")

from src.backend.config import settings
from src.backend.database import Base, get_session
from src.backend.main import app
from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus, SourceType
from src.backend.ml.schemas import ReportSection
from src.backend.models import __all__ as _models_imported  # noqa: F401
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)
from src.backend.services.auth_service import create_access_token, hash_password

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/autism_tracker_integration_test",
)

test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
TestSessionFactory = async_sessionmaker(test_engine, expire_on_commit=False)


def _make_mock_extraction(
    request=None,
    *,
    domain=Domain.SOCIAL_COMMUNICATION,
    behavior="pointed and said want cookie",
    modality=Modality.VERBAL,
    prompt_level=PromptLevel.INDEPENDENT,
    outcome=Outcome.CORRECT,
    confidence=0.85,
    status=ExtractionStatus.SUCCESS,
    clarification_questions=None,
) -> ExtractionResult:
    obs = StructuredObservation(
        child_id=request.child_id if request else "test-child",
        session_id=request.session_id if request else "test-session",
        contributor_role=request.contributor_role if request else ContributorRole.PARENT,
        observation_date=request.observation_date if request else date.today(),
        setting=request.setting if request else Setting.HOME,
        domain=domain,
        behavior=behavior,
        modality=modality,
        prompt_level=prompt_level,
        outcome=outcome,
        confidence=confidence,
    )
    return ExtractionResult(
        status=status,
        observations=[obs],
        provider="test_mock_extraction",
        model="mock-model-v1",
        prompt_version="test-1.0",
        generated_at=datetime.now(UTC),
        clarification_questions=clarification_questions or [],
    )


def _make_mock_extraction_needing_clarification(request=None) -> ExtractionResult:
    obs = StructuredObservation(
        child_id=request.child_id if request else "test-child",
        session_id=request.session_id if request else "test-session",
        contributor_role=request.contributor_role if request else ContributorRole.PARENT,
        observation_date=request.observation_date if request else date.today(),
        setting=request.setting if request else Setting.HOME,
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior="child did something",
        modality=None,
        prompt_level=None,
        outcome=None,
        confidence=0.45,
    )
    return ExtractionResult(
        status=ExtractionStatus.PARTIAL,
        observations=[obs],
        provider="test_mock_extraction",
        model="mock-model-v1",
        prompt_version="test-1.0",
        generated_at=datetime.now(UTC),
        clarification_questions=["Could you clarify what modality was used?"],
    )


@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.DefaultEventLoopPolicy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database(event_loop):
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = TEST_DB_URL.rsplit("/", 1)[1]
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(sa_text(f"DROP DATABASE IF EXISTS {db_name}"))
            await conn.execute(sa_text(f"CREATE DATABASE {db_name}"))
    finally:
        await admin_engine.dispose()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception:
        pass
    finally:
        try:
            await test_engine.dispose()
        except Exception:
            pass

    try:
        admin_engine2 = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        async with admin_engine2.connect() as conn:
            await conn.execute(sa_text(f"DROP DATABASE IF EXISTS {db_name}"))
        await admin_engine2.dispose()
    except Exception:
        pass


_SEED_USERS = None
_SEED_CHILD = None
_SEED_ACTORS = None
_SEED_GOALS = None
_SEED_REVIEW_PERIOD = None


@pytest.fixture(scope="session", autouse=True)
async def _seed_all(setup_test_database):
    """Insert shared seed data once per session."""
    global _SEED_USERS, _SEED_CHILD, _SEED_ACTORS, _SEED_GOALS, _SEED_REVIEW_PERIOD

    from src.backend.models.actor import ActorAssignment
    from src.backend.models.child import Child
    from src.backend.models.goal import Goal, GoalType, ReviewPeriod
    from src.backend.models.user import Role, User

    async with TestSessionFactory() as session:
        interventionist = User(
            id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
            email="test-interventionist@example.com",
            hashed_password=hash_password("TestPass123!"),
            full_name="Test Interventionist",
            role=Role.INTERVENTIONIST,
        )
        parent = User(
            id=uuid.UUID("10000000-0000-0000-0000-000000000002"),
            email="test-parent@example.com",
            hashed_password=hash_password("TestPass123!"),
            full_name="Test Parent",
            role=Role.PARENT,
        )
        teacher = User(
            id=uuid.UUID("10000000-0000-0000-0000-000000000003"),
            email="test-teacher@example.com",
            hashed_password=hash_password("TestPass123!"),
            full_name="Test Teacher",
            role=Role.TEACHER,
        )
        session.add_all([interventionist, parent, teacher])
        await session.flush()

        child = Child(
            id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
            display_name="Test Child Alpha",
            date_of_birth=datetime(2020, 6, 15, tzinfo=UTC),
            created_by=interventionist.id,
        )
        session.add(child)
        await session.flush()

        aa_parent = ActorAssignment(
            user_id=parent.id,
            child_id=child.id,
            role=parent.role,
            invited_by=interventionist.id,
            invitation_email="test-parent@example.com",
        )
        aa_teacher = ActorAssignment(
            user_id=teacher.id,
            child_id=child.id,
            role=teacher.role,
            invited_by=interventionist.id,
            invitation_email="test-teacher@example.com",
        )
        session.add_all([aa_parent, aa_teacher])
        await session.flush()

        goal = Goal(
            child_id=child.id,
            goal_type=GoalType.LONG_TERM,
            domain=Domain.SOCIAL_COMMUNICATION,
            title="Functional requesting",
            description="Test Child will independently request desired items.",
            created_by=interventionist.id,
        )
        session.add(goal)
        await session.flush()

        # Review-period dates are UTC days in the backend (observations are
        # matched on submitted_at in UTC), so the period is built from the UTC
        # date. The local date lags it in the evening west of UTC and would
        # leave every observation submitted then outside the period.
        today_utc = datetime.now(UTC).date()
        period = ReviewPeriod(
            child_id=child.id,
            start_date=today_utc - timedelta(days=60),
            end_date=today_utc,
        )
        session.add(period)
        await session.flush()

        await session.commit()

        _SEED_USERS = {"interventionist": interventionist, "parent": parent, "teacher": teacher}
        _SEED_CHILD = child
        _SEED_ACTORS = [aa_parent, aa_teacher]
        _SEED_GOALS = [goal]
        _SEED_REVIEW_PERIOD = period


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def override_db():
    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionFactory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def seed_users():
    return _SEED_USERS


@pytest.fixture
def seed_child():
    return _SEED_CHILD


@pytest.fixture
def seed_actors():
    return _SEED_ACTORS


@pytest.fixture
def seed_goals():
    return _SEED_GOALS


@pytest.fixture
def seed_review_period():
    return _SEED_REVIEW_PERIOD


@pytest.fixture
def interventionist_token():
    return create_access_token(_SEED_USERS["interventionist"].id)


@pytest.fixture
def parent_token():
    return create_access_token(_SEED_USERS["parent"].id)


@pytest.fixture
def teacher_token():
    return create_access_token(_SEED_USERS["teacher"].id)


@pytest.fixture
async def client(override_db) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_extraction_provider():
    mock_provider = AsyncMock()
    mock_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
    mock_provider.get_info.return_value = MagicMock(
        name="test_mock_extraction", provider_type="temporary_llm",
        model_id="mock-model-v1", version="test-1.0",
    )
    return mock_provider


@pytest.fixture
def mock_extraction_clarify():
    mock_provider = AsyncMock()
    mock_provider.extract = AsyncMock(side_effect=_make_mock_extraction_needing_clarification)
    mock_provider.get_info.return_value = MagicMock(
        name="test_mock_extraction", provider_type="temporary_llm",
        model_id="mock-model-v1", version="test-1.0",
    )
    return mock_provider


@pytest.fixture
def mock_reporting_llm():
    async def _mock_call_llm(user_message):
        return [
            {
                "heading": "Review Period Summary",
                "body": "During the review period, observations were recorded across multiple settings.",
                "evidence_refs": [],
                "abstention_note": None,
            },
            {
                "heading": "Evidence Coverage",
                "body": "Observations collected from contributors in home and school settings.",
                "evidence_refs": [],
                "abstention_note": None,
            },
            {
                "heading": "Observed Patterns",
                "body": "Records show engagement in social communication activities. "
                "The independence rate was 0.75 based on qualifying observations.",
                "evidence_refs": [],
                "abstention_note": None,
            },
            {
                "heading": "Evidence Limitations",
                "body": "No significant limitations identified for this review period.",
                "evidence_refs": [],
                "abstention_note": None,
            },
        ]

    return _mock_call_llm


@pytest.fixture
def mock_reporting_llm_insufficient():
    async def _mock_call_llm(user_message):
        return [
            {
                "heading": "Review Period Summary",
                "body": "Evidence was insufficient for this review period.",
                "evidence_refs": [],
                "abstention_note": None,
            },
            {
                "heading": "Evidence Limitations",
                "body": "Evidence was insufficient and limited. Analytics were withheld.",
                "evidence_refs": [],
                "abstention_note": None,
            },
        ]

    return _mock_call_llm
