"""Tests for Phase 4 stub endpoints — analytics and reports return 501."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest


class TestAnalyticsStub:
    async def test_analytics_returns_501(self, interventionist_client):
        child_id = uuid.uuid4()
        with patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.get(
                f"/children/{child_id}/analytics"
            )
        assert resp.status_code == 501
        assert "Phase 4" in resp.json()["detail"]


class TestReportStubs:
    async def test_generate_report_returns_501(self, interventionist_client):
        child_id = uuid.uuid4()
        with patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/reports/generate"
            )
        assert resp.status_code == 501
        assert "Phase 4" in resp.json()["detail"]

    async def test_get_report_returns_501(self, interventionist_client):
        resp = await interventionist_client.get(
            f"/reports/{uuid.uuid4()}"
        )
        assert resp.status_code == 501

    async def test_flag_report_returns_501(self, interventionist_client):
        resp = await interventionist_client.post(
            f"/reports/{uuid.uuid4()}/flag"
        )
        assert resp.status_code == 501
