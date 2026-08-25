"""Shared fixtures for Phase 4 tests."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from src.backend.api.deps import get_current_user
from src.backend.database import get_session
from src.backend.main import app
from src.backend.ml.schemas import (
    AdequacyCheck,
    AdequacyCheckResult,
    AdequacyLevel,
    AdequacyResult,
    AnalyticsResult,
    EvidencePacket,
    KpiResult,
)
from src.backend.models.user import Role, User


def make_user(
    role: Role = Role.INTERVENTIONIST,
    user_id: uuid.UUID | None = None,
) -> Mock:
    user = Mock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = f"test_{role.value}@example.com"
    user.full_name = f"Test {role.value.replace('_', ' ').title()}"
    user.role = role
    user.is_active = True
    return user


def make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


def make_record_dict(
    obs_id: str | None = None,
    record_id: str | None = None,
    version: int = 1,
    **overrides,
) -> dict:
    base = {
        "_record_id": record_id or str(uuid.uuid4()),
        "_observation_id": obs_id or str(uuid.uuid4()),
        "_version": version,
        "behavior": "pointed at toy and said car",
        "domain": "social_communication",
        "modality": "verbal",
        "prompt_level": "independent",
        "outcome": "correct",
        "setting": "home",
        "contributor_role": "parent",
        "observation_date": "2026-06-15",
    }
    base.update(overrides)
    return base


def make_adequate_result(
    level: AdequacyLevel = AdequacyLevel.ADEQUATE,
) -> AdequacyResult:
    return AdequacyResult(
        level=level,
        eligible=level != AdequacyLevel.INSUFFICIENT,
        checks=[
            AdequacyCheckResult(check=AdequacyCheck.COVERAGE, passed=True, detail="5/5"),
            AdequacyCheckResult(check=AdequacyCheck.FIELD_COMPLETENESS, passed=True, detail="100%"),
        ],
        partial_abstentions={},
        quality_flags=[],
    )


def make_evidence_packet(
    child_id: str | None = None,
    review_period_id: str | None = None,
    records: list[dict] | None = None,
    adequacy: AdequacyResult | None = None,
) -> EvidencePacket:
    _records = records or [make_record_dict() for _ in range(5)]
    _adequacy = adequacy or make_adequate_result()
    _cid = child_id or str(uuid.uuid4())
    _rpid = review_period_id or str(uuid.uuid4())
    return EvidencePacket(
        child_id=_cid,
        review_period_id=_rpid,
        review_period_start="2026-06-01",
        review_period_end="2026-06-30",
        goals=[{"id": str(uuid.uuid4()), "domain": "social_communication", "title": "Improve requests"}],
        structured_records=_records,
        record_ids=[r["_record_id"] for r in _records],
        record_versions={r["_record_id"]: r["_version"] for r in _records},
        analytics=AnalyticsResult(
            child_id=_cid,
            review_period_id=_rpid,
            kpis=[KpiResult(name="observation_count", numerator=5.0, denominator=1.0, value=5.0)],
            adequacy=_adequacy,
        ),
        adequacy=_adequacy,
        quality_flags=_adequacy.quality_flags,
        contributor_summary={"parent": 3, "teacher": 2},
        setting_summary={"home": 3, "school": 2},
        observation_count=5,
        abstained_count=0,
        review_count=0,
    )


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
