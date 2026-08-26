"""Tests for Phase 4 analytics and reports API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.backend.ml.schemas import AdequacyLevel
from src.backend.models.user import Role
from tests.phase4.conftest import make_adequate_result, make_evidence_packet, make_record_dict, make_user


CHILD_ID = uuid.uuid4()
REVIEW_PERIOD_ID = uuid.uuid4()


@pytest.mark.asyncio
class TestAnalyticsEndpoint:
    async def test_analytics_returns_200(self, interventionist_client, mock_db):
        from src.backend.ml.schemas import AdequacyResult, AnalyticsResult, KpiResult

        analytics = AnalyticsResult(
            child_id=str(CHILD_ID),
            review_period_id=str(REVIEW_PERIOD_ID),
            kpis=[KpiResult(name="observation_count", numerator=5.0, denominator=1.0, value=5.0)],
            adequacy=make_adequate_result(),
        )
        adequacy = make_adequate_result()
        records = [Mock() for _ in range(5)]

        with patch(
            "src.backend.api.analytics.analytics_service.compute_analytics",
            new_callable=AsyncMock,
            return_value=(analytics, adequacy, records),
        ), patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
        ), patch(
            "src.backend.api.analytics.audit_service.log_event",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.post(
                f"/children/{CHILD_ID}/analytics",
                json={
                    "review_period_id": str(REVIEW_PERIOD_ID),
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["child_id"] == str(CHILD_ID)
        assert len(data["kpis"]) >= 1
        assert data["adequacy"]["level"] == "adequate"

    async def test_analytics_returns_404_for_missing_period(self, interventionist_client, mock_db):
        with patch(
            "src.backend.api.analytics.analytics_service.compute_analytics",
            new_callable=AsyncMock,
            side_effect=ValueError("ReviewPeriod not found"),
        ), patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.post(
                f"/children/{CHILD_ID}/analytics",
                json={"review_period_id": str(uuid.uuid4())},
            )
        assert resp.status_code == 404

    async def test_contributor_denied_analytics(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{CHILD_ID}/analytics",
            json={"review_period_id": str(REVIEW_PERIOD_ID)},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestListReviewPeriods:
    async def test_list_review_periods_returns_200(self, interventionist_client, mock_db):
        period_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_period = Mock()
        mock_period.id = period_id
        mock_period.child_id = CHILD_ID
        mock_period.start_date = date(2026, 6, 1)
        mock_period.end_date = date(2026, 6, 30)
        mock_period.is_active = True
        mock_period.created_at = now

        mock_scalars = Mock()
        mock_scalars.all.return_value = [mock_period]
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.get(
                f"/children/{CHILD_ID}/review-periods",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(period_id)
        assert data[0]["child_id"] == str(CHILD_ID)
        assert data[0]["start_date"] == "2026-06-01"
        assert data[0]["end_date"] == "2026-06-30"

    async def test_list_review_periods_empty(self, interventionist_client, mock_db):
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.get(
                f"/children/{CHILD_ID}/review-periods",
            )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_review_periods_unauthorized_child(self, interventionist_client, mock_db):
        with patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
            side_effect=__import__("fastapi").HTTPException(status_code=403, detail="Not authorized"),
        ):
            resp = await interventionist_client.get(
                f"/children/{uuid.uuid4()}/review-periods",
            )
        assert resp.status_code == 403

    async def test_contributor_denied_list_review_periods(self, contributor_client):
        resp = await contributor_client.get(
            f"/children/{CHILD_ID}/review-periods",
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestReviewPeriodEndpoint:
    async def test_create_review_period_201(self, interventionist_client, mock_db):
        period_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_period = Mock()
        mock_period.id = period_id
        mock_period.child_id = CHILD_ID
        mock_period.start_date = date(2026, 6, 1)
        mock_period.end_date = date(2026, 6, 30)
        mock_period.is_active = True
        mock_period.created_at = now

        async def mock_refresh(obj):
            obj.id = mock_period.id
            obj.child_id = mock_period.child_id
            obj.start_date = mock_period.start_date
            obj.end_date = mock_period.end_date
            obj.is_active = mock_period.is_active
            obj.created_at = mock_period.created_at

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
        ), patch(
            "src.backend.api.analytics.audit_service.log_event",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.post(
                f"/children/{CHILD_ID}/review-periods",
                json={"start_date": "2026-06-01", "end_date": "2026-06-30"},
            )
        assert resp.status_code == 201
