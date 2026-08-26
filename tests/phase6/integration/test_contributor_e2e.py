"""Contributor end-to-end workflow: login → observe → clarify → finalize → history.

Exercises the real API/service/database path. Only the external LLM
boundary (Anthropic API) is mocked.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.phase6.integration.conftest import (
    _make_mock_extraction,
    _make_mock_extraction_needing_clarification,
)


@pytest.mark.integration
class TestContributorE2E:

    async def test_contributor_login(self, client: AsyncClient, seed_users, seed_actors):
        resp = await client.post("/auth/login", json={
            "email": "test-parent@example.com",
            "password": "TestPass123!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data.get("token_type") == "bearer"

    async def test_contributor_list_authorized_children(
        self, client: AsyncClient, parent_token, seed_actors, seed_child,
    ):
        resp = await client.get(
            "/children/",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 200
        children = resp.json()
        assert len(children) >= 1
        child_ids = [c["id"] for c in children]
        assert str(seed_child.id) in child_ids

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_contributor_submit_observation_accept(
        self, mock_get_provider, client: AsyncClient,
        parent_token, seed_actors, seed_child, mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        resp = await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Child pointed at cookie and said want cookie without any help.",
                "setting": "home",
                "source_type": "conversational",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["routing_decision"] == "accept"
        assert data["observation"]["status"] == "finalized"
        return data["observation"]["id"]

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_contributor_submit_observation_clarify(
        self, mock_get_provider, client: AsyncClient,
        parent_token, seed_actors, seed_child, mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(
            side_effect=_make_mock_extraction_needing_clarification,
        )

        resp = await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Child did something interesting today.",
                "setting": "home",
                "source_type": "conversational",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["routing_decision"] == "clarify"
        assert data["observation"]["status"] == "clarifying"
        assert data["clarification_question"] is not None
        obs_id = data["observation"]["id"]

        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        resp2 = await client.post(
            f"/observations/{obs_id}/clarifications",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={"answer": "It was verbal — she said 'more juice'."},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["routing_decision"] == "accept"
        assert data2["observation"]["status"] == "finalized"

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_contributor_sees_own_history(
        self, mock_get_provider, client: AsyncClient,
        parent_token, seed_actors, seed_child, seed_users, mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Test observation for history check.",
                "setting": "home",
                "source_type": "conversational",
            },
        )

        resp = await client.get(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 200
        observations = resp.json()
        assert len(observations) >= 1
        assert all(o["submitted_by"] == str(seed_users["parent"].id) for o in observations)

    async def test_contributor_cannot_see_records(
        self, client: AsyncClient, parent_token, seed_actors, seed_child,
    ):
        resp = await client.get(
            f"/children/{seed_child.id}/records",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_see_analytics(
        self, client: AsyncClient, parent_token, seed_actors, seed_child,
    ):
        resp = await client.post(
            f"/children/{seed_child.id}/analytics",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={"review_period_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_see_reports(
        self, client: AsyncClient, parent_token, seed_actors, seed_child,
    ):
        resp = await client.post(
            f"/children/{seed_child.id}/reports/generate",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={"review_period_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_see_audit(
        self, client: AsyncClient, parent_token, seed_actors, seed_child,
    ):
        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_see_actors(
        self, client: AsyncClient, parent_token, seed_actors, seed_child,
    ):
        resp = await client.post(
            f"/children/{seed_child.id}/actors",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={"email": "someone@example.com", "role": "parent"},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_access_unauthorized_child(
        self, client: AsyncClient, parent_token, seed_actors,
    ):
        fake_child_id = uuid.uuid4()
        resp = await client.post(
            f"/children/{fake_child_id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Some observation text.",
                "setting": "home",
                "source_type": "conversational",
            },
        )
        assert resp.status_code == 403

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_other_contributor_cannot_see_parent_observations(
        self, mock_get_provider, client: AsyncClient,
        parent_token, teacher_token, seed_actors, seed_child, seed_users, mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Parent-only observation.",
                "setting": "home",
                "source_type": "conversational",
            },
        )

        resp = await client.get(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {teacher_token}"},
        )
        assert resp.status_code == 200
        teacher_obs = resp.json()
        for obs in teacher_obs:
            assert obs["submitted_by"] != str(seed_users["parent"].id)
