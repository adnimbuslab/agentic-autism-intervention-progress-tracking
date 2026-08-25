"""Tests for audit trail endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.phase3.conftest import make_audit_event


class TestGetAuditTrail:
    async def test_interventionist_can_read_audit(
        self, interventionist_client
    ):
        child_id = uuid.uuid4()
        e1 = make_audit_event(child_id=child_id)
        e2 = make_audit_event(child_id=child_id)
        with (
            patch(
                "src.backend.api.audit.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.audit_service.get_audit_trail",
                new_callable=AsyncMock,
                return_value=[e1, e2],
            ),
        ):
            resp = await interventionist_client.get(
                f"/children/{child_id}/audit"
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_contributor_cannot_read_audit(
        self, contributor_client
    ):
        child_id = uuid.uuid4()
        resp = await contributor_client.get(
            f"/children/{child_id}/audit"
        )
        assert resp.status_code == 403

    async def test_audit_supports_limit_and_offset(
        self, interventionist_client
    ):
        child_id = uuid.uuid4()
        e1 = make_audit_event(child_id=child_id)
        with (
            patch(
                "src.backend.api.audit.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.audit_service.get_audit_trail",
                new_callable=AsyncMock,
                return_value=[e1],
            ) as mock_trail,
        ):
            resp = await interventionist_client.get(
                f"/children/{child_id}/audit?limit=10&offset=5"
            )
        assert resp.status_code == 200
        mock_trail.assert_awaited_once()
        call_kwargs = mock_trail.call_args
        assert call_kwargs.kwargs.get("limit") == 10 or call_kwargs[1].get("limit") == 10
