"""Phase 6: Security and RBAC hardening tests.

Tests unauthenticated access, invalid tokens, role escalation,
cross-child access (IDOR), revoked actors, and malformed IDs.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.backend.api.deps import get_current_user, get_session
from src.backend.main import app
from src.backend.models.user import Role

from tests.phase3.conftest import make_child, make_mock_session, make_user


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


class TestUnauthenticatedAccess:
    """All critical endpoints must return 401 without a valid token."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        mock_db = make_mock_session()

        async def _override_session():
            yield mock_db

        app.dependency_overrides[get_session] = _override_session
        yield
        app.dependency_overrides.clear()

    @pytest.mark.parametrize("method,path", [
        ("GET", "/children/"),
        ("POST", "/children/"),
        ("GET", f"/children/{uuid.uuid4()}/goals"),
        ("POST", f"/children/{uuid.uuid4()}/observations"),
        ("POST", f"/children/{uuid.uuid4()}/analytics"),
        ("GET", f"/children/{uuid.uuid4()}/audit"),
        ("POST", f"/children/{uuid.uuid4()}/reports/generate"),
        ("GET", f"/children/{uuid.uuid4()}/records"),
        ("GET", f"/children/{uuid.uuid4()}/schedules"),
        ("GET", f"/children/{uuid.uuid4()}/actors"),
    ])
    async def test_endpoint_requires_auth(self, method, path):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.request(method, path)
        assert resp.status_code == 401


class TestInvalidToken:
    """Requests with garbage or malformed tokens must return 401."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        mock_db = make_mock_session()
        mock_db.get = AsyncMock(return_value=None)

        async def _override_session():
            yield mock_db

        app.dependency_overrides[get_session] = _override_session
        yield
        app.dependency_overrides.clear()

    @pytest.mark.parametrize("token", [
        "garbage-token",
        "eyJhbGciOiJIUzI1NiJ9.invalid.signature",
        "",
    ])
    async def test_invalid_token_rejected(self, token):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/children/",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Contributor → Interventionist endpoint denial
# ---------------------------------------------------------------------------


class TestContributorCannotAccessInterventionistEndpoints:
    """Contributors should get 403 on interventionist-only endpoints."""

    async def test_create_child(self, contributor_client):
        resp = await contributor_client.post(
            "/children/",
            json={"display_name": "Unauthorized Child"},
        )
        assert resp.status_code == 403

    async def test_list_records(self, contributor_client):
        resp = await contributor_client.get(f"/children/{uuid.uuid4()}/records")
        assert resp.status_code == 403

    async def test_correct_record(self, contributor_client):
        resp = await contributor_client.post(
            f"/records/{uuid.uuid4()}/correct",
            json={"record_data": {}, "correction_reason": "test"},
        )
        assert resp.status_code == 403

    async def test_analytics(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/analytics",
            json={"review_period_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    async def test_generate_report(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/reports/generate",
            json={"review_period_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    async def test_audit_trail(self, contributor_client):
        resp = await contributor_client.get(f"/children/{uuid.uuid4()}/audit")
        assert resp.status_code == 403

    async def test_invite_actor(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/actors",
            json={"email": "someone@example.com", "role": "parent"},
        )
        assert resp.status_code == 403

    async def test_revoke_actor(self, contributor_client):
        resp = await contributor_client.delete(f"/actors/{uuid.uuid4()}")
        assert resp.status_code == 403

    async def test_create_schedule(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/schedules",
            json={"cadence_days": 7},
        )
        assert resp.status_code == 403

    async def test_create_review_period(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/review-periods",
            json={"start_date": "2026-01-01", "end_date": "2026-03-31"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Cross-child access (IDOR)
# ---------------------------------------------------------------------------


class TestCrossChildAccess:
    """User A cannot access child owned by user B."""

    async def test_cross_child_goals(self, interventionist_client, mock_db):
        other_child_id = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=[])))))
        resp = await interventionist_client.get(f"/children/{other_child_id}/goals")
        assert resp.status_code == 403

    async def test_cross_child_observations(self, interventionist_client, mock_db):
        other_child_id = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=[])))))
        resp = await interventionist_client.get(f"/children/{other_child_id}/observations")
        assert resp.status_code == 403

    async def test_cross_child_audit(self, interventionist_client, mock_db):
        other_child_id = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=[])))))
        resp = await interventionist_client.get(f"/children/{other_child_id}/audit")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Manipulated / nonexistent IDs
# ---------------------------------------------------------------------------


class TestNonexistentResources:
    """Random UUIDs should return 404 or 403, never crash."""

    async def test_nonexistent_report(self, interventionist_client, mock_db):
        mock_db.get = AsyncMock(return_value=None)
        resp = await interventionist_client.get(f"/reports/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_nonexistent_record(self, interventionist_client, mock_db):
        mock_db.get = AsyncMock(return_value=None)
        resp = await interventionist_client.get(f"/records/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_nonexistent_record_history(self, interventionist_client, mock_db):
        mock_db.get = AsyncMock(return_value=None)
        resp = await interventionist_client.get(f"/records/{uuid.uuid4()}/history")
        assert resp.status_code == 404


class TestMalformedUUIDs:
    """Non-UUID path parameters should return 422."""

    async def test_malformed_child_id(self, interventionist_client):
        resp = await interventionist_client.get("/children/not-a-uuid/goals")
        assert resp.status_code == 422

    async def test_malformed_record_id(self, interventionist_client):
        resp = await interventionist_client.get("/records/not-a-uuid")
        assert resp.status_code == 422

    async def test_malformed_report_id(self, interventionist_client):
        resp = await interventionist_client.get("/reports/not-a-uuid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Deactivated user
# ---------------------------------------------------------------------------


class TestDeactivatedUser:
    """A deactivated user's token should be rejected."""

    async def test_deactivated_user_rejected(self):
        deactivated = make_user(Role.INTERVENTIONIST, is_active=False)
        mock_db = make_mock_session()
        mock_db.get = AsyncMock(return_value=deactivated)

        async def _override_session():
            yield mock_db

        app.dependency_overrides[get_session] = _override_session
        app.dependency_overrides.pop(get_current_user, None)

        try:
            from src.backend.services.auth_service import create_access_token
            token = create_access_token(deactivated.id)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(
                    "/children/",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
