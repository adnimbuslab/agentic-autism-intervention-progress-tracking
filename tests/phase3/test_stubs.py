"""Tests verifying Phase 4 endpoints are now implemented (no longer 501 stubs).

These tests confirm that the analytics and report endpoints return proper
responses rather than 501 Not Implemented, validating the Phase 3→4 transition.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestAnalyticsNoLongerStub:
    async def test_analytics_requires_body(self, interventionist_client):
        child_id = uuid.uuid4()
        with patch(
            "src.backend.api.analytics.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/analytics"
            )
        assert resp.status_code == 422


class TestReportsNoLongerStubs:
    async def test_generate_report_requires_body(self, interventionist_client):
        child_id = uuid.uuid4()
        with patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/reports/generate"
            )
        assert resp.status_code == 422

    async def test_get_report_no_longer_501(self, interventionist_client):
        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await interventionist_client.get(f"/reports/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_flag_report_requires_body(self, interventionist_client):
        report = Mock()
        report.id = uuid.uuid4()
        report.child_id = uuid.uuid4()

        with patch(
            "src.backend.api.reports.report_service.get_report",
            new_callable=AsyncMock,
            return_value=report,
        ), patch(
            "src.backend.api.reports.authorize_child_access",
            new_callable=AsyncMock,
        ):
            resp = await interventionist_client.post(
                f"/reports/{report.id}/flag"
            )
        assert resp.status_code == 422
