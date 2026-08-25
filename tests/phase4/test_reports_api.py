"""Tests for Phase 4 report API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.backend.models.user import Role
from tests.phase4.conftest import make_user


CHILD_ID = uuid.uuid4()
REVIEW_PERIOD_ID = uuid.uuid4()


def _make_report_model(
    child_id: uuid.UUID = CHILD_ID,
    review_period_id: uuid.UUID = REVIEW_PERIOD_ID,
    flagged: bool = False,
) -> Mock:
    m = Mock()
    m.id = uuid.uuid4()
    m.child_id = child_id
    m.review_period_id = review_period_id
    m.report_json = {
        "sections": [
            {"heading": "Review Period Summary", "body": "Content.", "evidence_refs": [], "abstention_note": None},
        ],
    }
    m.evidence_packet_json = {
        "child_id": str(child_id),
        "review_period_id": str(review_period_id),
        "review_period_start": "2026-06-01",
        "review_period_end": "2026-06-30",
        "goals": [],
        "record_ids": [],
        "record_versions": {},
        "contributor_summary": {"parent": 3},
        "setting_summary": {"home": 3},
        "observation_count": 3,
        "abstained_count": 0,
        "review_count": 0,
        "quality_flags": [],
    }
    m.provider = "anthropic"
    m.model = "claude-sonnet-4-20250514"
    m.prompt_version = "1.0"
    m.version = 1
    m.validation_passed = True
    m.validation_errors = None
    m.flagged = flagged
    m.flagged_reason = None
    m.flagged_by = None
    m.generated_at = datetime.now(UTC)
    return m


@pytest.mark.asyncio
class TestGenerateReport:
    async def test_generate_returns_201(self, interventionist_client, mock_db):
        report = _make_report_model()

        with patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ), patch(
            "src.backend.api.reports.report_service.generate_report",
            new_callable=AsyncMock,
            return_value=report,
        ):
            resp = await interventionist_client.post(
                f"/children/{CHILD_ID}/reports/generate",
                json={"review_period_id": str(REVIEW_PERIOD_ID)},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "anthropic"
        assert data["validation_passed"] is True
        assert len(data["sections"]) == 1

    async def test_generate_404_for_missing_period(self, interventionist_client, mock_db):
        with patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ), patch(
            "src.backend.api.reports.report_service.generate_report",
            new_callable=AsyncMock,
            side_effect=ValueError("ReviewPeriod not found"),
        ):
            resp = await interventionist_client.post(
                f"/children/{CHILD_ID}/reports/generate",
                json={"review_period_id": str(uuid.uuid4())},
            )
        assert resp.status_code == 404

    async def test_contributor_denied_generate(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{CHILD_ID}/reports/generate",
            json={"review_period_id": str(REVIEW_PERIOD_ID)},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestGetReport:
    async def test_get_returns_200(self, interventionist_client, mock_db):
        report = _make_report_model()
        report_id = report.id

        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=report,
        ), patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.get(f"/reports/{report_id}")
        assert resp.status_code == 200

    async def test_get_404_not_found(self, interventionist_client, mock_db):
        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await interventionist_client.get(f"/reports/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestListReports:
    async def test_list_returns_200(self, interventionist_client, mock_db):
        reports = [_make_report_model() for _ in range(3)]

        with patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ), patch(
            "src.backend.api.reports.report_service.list_reports",
            new_callable=AsyncMock,
            return_value=reports,
        ):
            resp = await interventionist_client.get(f"/children/{CHILD_ID}/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_contributor_denied_list(self, contributor_client):
        resp = await contributor_client.get(f"/children/{CHILD_ID}/reports")
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestGetEvidence:
    async def test_evidence_returns_200(self, interventionist_client, mock_db):
        report = _make_report_model()

        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=report,
        ), patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.get(f"/reports/{report.id}/evidence")
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_period_start"] == "2026-06-01"
        assert "record_ids" in data

    async def test_evidence_404_not_found(self, interventionist_client, mock_db):
        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await interventionist_client.get(f"/reports/{uuid.uuid4()}/evidence")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestFlagReport:
    async def test_flag_returns_200(self, interventionist_client, mock_db):
        report = _make_report_model()

        flagged_report = _make_report_model(flagged=True)
        flagged_report.id = report.id
        flagged_report.flagged = True
        flagged_report.flagged_reason = "Inaccurate summary"
        flagged_report.flagged_by = uuid.uuid4()

        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=report,
        ), patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ), patch(
            "src.backend.api.reports.report_service.flag_report",
            new_callable=AsyncMock,
            return_value=flagged_report,
        ):
            resp = await interventionist_client.post(
                f"/reports/{report.id}/flag",
                json={"reason": "Inaccurate summary"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flagged"] is True
        assert data["flagged_reason"] == "Inaccurate summary"

    async def test_flag_404_not_found(self, interventionist_client, mock_db):
        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await interventionist_client.post(
                f"/reports/{uuid.uuid4()}/flag",
                json={"reason": "Test reason"},
            )
        assert resp.status_code == 404

    async def test_contributor_denied_flag(self, contributor_client):
        resp = await contributor_client.post(
            f"/reports/{uuid.uuid4()}/flag",
            json={"reason": "Should be denied"},
        )
        assert resp.status_code == 403
