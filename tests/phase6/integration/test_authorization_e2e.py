"""Child-level and role-level authorization, end to end on a real database.

Complements the mocked-DB RBAC suites (tests/phase3/test_rbac.py,
tests/phase6/test_security_rbac.py) with the cases those cannot show: that a
contributor's access is confined to the children they are assigned to, that
revoking an assignment ends access on the very next request with an already
issued token, and that a professional with no relationship to a child cannot
reach its analytics or reports. Every refusal here is decided by the API
against rows in Postgres, not by the UI.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.backend.models.user import Role, User
from src.backend.services.auth_service import create_access_token, hash_password
from tests.phase6.integration.conftest import TestSessionFactory, _make_mock_extraction

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _child(client: AsyncClient, i_token: str, name: str) -> str:
    r = await client.post("/children/", headers=_auth(i_token), json={"display_name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _assign(client: AsyncClient, i_token: str, child_id: str, email: str, role: str) -> str:
    r = await client.post(f"/children/{child_id}/actors", headers=_auth(i_token),
                          json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _period(client: AsyncClient, i_token: str, child_id: str) -> str:
    r = await client.post(f"/children/{child_id}/review-periods", headers=_auth(i_token), json={
        "start_date": (date.today() - timedelta(days=30)).isoformat(),
        "end_date": date.today().isoformat(),
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.usefixtures("override_db")
class TestAuthorizationE2E:

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_contributor_confined_to_assigned_child(
        self, mock_get_provider, client: AsyncClient, interventionist_token, parent_token,
        mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        assigned = await _child(client, interventionist_token, "Authz assigned")
        other = await _child(client, interventionist_token, "Authz other")
        await _assign(client, interventionist_token, assigned, "test-parent@example.com", "parent")

        ok = await client.post(f"/children/{assigned}/observations", headers=_auth(parent_token),
                               json={"raw_text": "Said 'ball' while pointing.", "setting": "home",
                                     "source_type": "conversational"})
        assert ok.status_code == 201, ok.text

        listed = await client.get("/children/", headers=_auth(parent_token))
        ids = {c["id"] for c in listed.json()}
        assert assigned in ids and other not in ids

        assert (await client.get(f"/children/{other}", headers=_auth(parent_token))).status_code == 403
        assert (await client.get(f"/children/{other}/observations",
                                 headers=_auth(parent_token))).status_code == 403
        r = await client.post(f"/children/{other}/observations", headers=_auth(parent_token),
                              json={"raw_text": "x", "setting": "home", "source_type": "conversational"})
        assert r.status_code == 403
        assert (await client.get(f"/children/{other}/goals", headers=_auth(parent_token))).status_code == 403

    async def test_contributor_cannot_create_or_edit_goals(
        self, client: AsyncClient, interventionist_token, parent_token,
    ):
        child = await _child(client, interventionist_token, "Authz goals")
        await _assign(client, interventionist_token, child, "test-parent@example.com", "parent")
        g = await client.post(f"/children/{child}/goals", headers=_auth(interventionist_token), json={
            "goal_type": "long_term", "domain": "language", "title": "Goal", "description": "d"})
        assert g.status_code == 201, g.text
        goal_id = g.json()["id"]

        create = await client.post(f"/children/{child}/goals", headers=_auth(parent_token), json={
            "goal_type": "long_term", "domain": "language", "title": "Mine", "description": "d"})
        assert create.status_code == 403
        edit = await client.patch(f"/goals/{goal_id}", headers=_auth(parent_token),
                                  json={"title": "Changed by contributor"})
        assert edit.status_code == 403
        after = await client.get(f"/children/{child}/goals", headers=_auth(interventionist_token))
        assert [x["title"] for x in after.json() if x["id"] == goal_id] == ["Goal"]

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_revoked_contributor_loses_access_immediately(
        self, mock_get_provider, client: AsyncClient, interventionist_token, parent_token,
        mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        child = await _child(client, interventionist_token, "Authz revoke")
        assignment = await _assign(client, interventionist_token, child, "test-parent@example.com", "parent")

        before = await client.get(f"/children/{child}", headers=_auth(parent_token))
        assert before.status_code == 200

        rv = await client.delete(f"/actors/{assignment}", headers=_auth(interventionist_token))
        assert rv.status_code == 200, rv.text
        assert rv.json()["revoked_at"] is not None

        # Same token as before revocation: enforcement is per request, not per login.
        assert (await client.get(f"/children/{child}", headers=_auth(parent_token))).status_code == 403
        assert (await client.get(f"/children/{child}/observations",
                                 headers=_auth(parent_token))).status_code == 403
        r = await client.post(f"/children/{child}/observations", headers=_auth(parent_token),
                              json={"raw_text": "x", "setting": "home", "source_type": "conversational"})
        assert r.status_code == 403
        listed = await client.get("/children/", headers=_auth(parent_token))
        assert child not in {c["id"] for c in listed.json()}

    async def test_unrelated_professional_cannot_reach_analytics_or_reports(
        self, client: AsyncClient, interventionist_token,
    ):
        child = await _child(client, interventionist_token, "Authz professional")
        period = await _period(client, interventionist_token, child)

        async with TestSessionFactory() as session:
            outsider = User(id=uuid.uuid4(), email=f"outsider-{uuid.uuid4().hex[:8]}@example.com",
                            hashed_password=hash_password("TestPass123!"), full_name="Unrelated Interventionist",
                            role=Role.INTERVENTIONIST)
            session.add(outsider)
            await session.commit()
            outsider_token = create_access_token(outsider.id)

        for method, path, body in [
            ("get", f"/children/{child}", None),
            ("post", f"/children/{child}/analytics", {"review_period_id": period}),
            ("post", f"/children/{child}/reports/generate", {"review_period_id": period}),
            ("get", f"/children/{child}/reports", None),
            ("get", f"/children/{child}/records", None),
            ("get", f"/children/{child}/audit", None),
        ]:
            r = await client.request(method, path, headers=_auth(outsider_token), json=body)
            assert r.status_code == 403, f"{method.upper()} {path} -> {r.status_code}"
