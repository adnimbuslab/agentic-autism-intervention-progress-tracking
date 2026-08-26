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


def make_rich_evidence_packet(
    child_id: str | None = None,
    review_period_id: str | None = None,
    adequacy: AdequacyResult | None = None,
) -> EvidencePacket:
    """Evidence packet with the full set of KPIs for fallback report testing."""
    records = [
        make_record_dict(prompt_level="independent", outcome="correct", domain="social_communication", modality="verbal", setting="home", contributor_role="parent", observation_date="2026-06-05"),
        make_record_dict(prompt_level="verbal", outcome="correct", domain="social_communication", modality="verbal", setting="home", contributor_role="parent", observation_date="2026-06-08"),
        make_record_dict(prompt_level="independent", outcome="partial", domain="daily_living", modality="gestural", setting="school", contributor_role="teacher", observation_date="2026-06-12"),
        make_record_dict(prompt_level="physical", outcome="no_response", domain="social_communication", modality="verbal", setting="school", contributor_role="teacher", observation_date="2026-06-15"),
        make_record_dict(prompt_level="independent", outcome="correct", domain="daily_living", modality="verbal", setting="home", contributor_role="parent", observation_date="2026-06-20"),
        make_record_dict(prompt_level="verbal", outcome="correct", domain="social_communication", modality="gestural", setting="school", contributor_role="teacher", observation_date="2026-06-22"),
        make_record_dict(prompt_level="independent", outcome="approximation", domain="daily_living", modality="verbal", setting="home", contributor_role="parent", observation_date="2026-06-25"),
        make_record_dict(prompt_level="independent", outcome="correct", domain="social_communication", modality="verbal", setting="home", contributor_role="parent", observation_date="2026-06-28"),
    ]
    _adequacy = adequacy or make_adequate_result()
    _cid = child_id or str(uuid.uuid4())
    _rpid = review_period_id or str(uuid.uuid4())
    kpis = [
        KpiResult(name="observation_count", numerator=8.0, denominator=1.0, value=8.0),
        KpiResult(name="independence_rate", numerator=5.0, denominator=8.0, value=0.625),
        KpiResult(name="positive_outcome_rate", numerator=6.0, denominator=7.0, value=0.8571),
        KpiResult(name="domain_distribution", numerator=2.0, denominator=8.0, value=2.0),
        KpiResult(name="modality_distribution", numerator=2.0, denominator=8.0, value=2.0),
        KpiResult(name="prompt_level_distribution", numerator=3.0, denominator=8.0, value=3.0),
        KpiResult(name="outcome_distribution", numerator=4.0, denominator=8.0, value=4.0),
        KpiResult(name="missing_data_rate", numerator=0.0, denominator=40.0, value=0.0),
        KpiResult(name="contributor_distribution", numerator=2.0, denominator=8.0, value=2.0),
        KpiResult(name="setting_distribution", numerator=2.0, denominator=8.0, value=2.0),
        KpiResult(name="prompt_support_trend", numerator=3.0, denominator=4.0, value=0.25),
        KpiResult(name="outcome_trend", numerator=3.0, denominator=4.0, value=0.0833),
        KpiResult(name="cross_setting_comparison", numerator=2.0, denominator=8.0, value=2.0),
        KpiResult(name="cross_contributor_comparison", numerator=2.0, denominator=8.0, value=2.0),
    ]
    return EvidencePacket(
        child_id=_cid,
        review_period_id=_rpid,
        review_period_start="2026-06-01",
        review_period_end="2026-06-30",
        goals=[
            {"id": str(uuid.uuid4()), "domain": "social_communication", "title": "Improve requests"},
            {"id": str(uuid.uuid4()), "domain": "daily_living", "title": "Self-care routines"},
        ],
        structured_records=records,
        record_ids=[r["_record_id"] for r in records],
        record_versions={r["_record_id"]: r["_version"] for r in records},
        analytics=AnalyticsResult(
            child_id=_cid,
            review_period_id=_rpid,
            kpis=kpis,
            adequacy=_adequacy,
        ),
        adequacy=_adequacy,
        quality_flags=_adequacy.quality_flags,
        contributor_summary={"parent": 5, "teacher": 3},
        setting_summary={"home": 5, "school": 3},
        observation_count=8,
        abstained_count=0,
        review_count=1,
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
