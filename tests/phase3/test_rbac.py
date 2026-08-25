"""Comprehensive RBAC tests — role enforcement across all endpoint groups."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.phase3.conftest import make_observation


class TestContributorDeniedEndpoints:
    """Contributors must be denied access to interventionist-only endpoints."""

    async def test_contributor_cannot_create_child(self, contributor_client):
        resp = await contributor_client.post(
            "/children/", json={"display_name": "Blocked"}
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_update_child(self, contributor_client):
        resp = await contributor_client.patch(
            f"/children/{uuid.uuid4()}", json={"display_name": "New"}
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_create_goal(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/goals",
            json={
                "goal_type": "short_term",
                "domain": "language",
                "title": "Goal",
                "description": "Desc",
            },
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_update_goal(self, contributor_client):
        resp = await contributor_client.patch(
            f"/goals/{uuid.uuid4()}", json={"title": "Updated"}
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_invite_actor(self, contributor_client):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/actors",
            json={"email": "someone@test.com", "role": "parent"},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_list_actors(self, contributor_client):
        resp = await contributor_client.get(
            f"/children/{uuid.uuid4()}/actors"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_revoke_actor(self, contributor_client):
        resp = await contributor_client.delete(
            f"/actors/{uuid.uuid4()}"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_list_records(self, contributor_client):
        resp = await contributor_client.get(
            f"/children/{uuid.uuid4()}/records"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_correct_record(self, contributor_client):
        resp = await contributor_client.post(
            f"/records/{uuid.uuid4()}/correct",
            json={"record_data": {}, "correction_reason": "test"},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_view_record_history(
        self, contributor_client
    ):
        resp = await contributor_client.get(
            f"/records/{uuid.uuid4()}/history"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_create_schedule(
        self, contributor_client
    ):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/schedules",
            json={"cadence_days": 7},
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_list_schedules(
        self, contributor_client
    ):
        resp = await contributor_client.get(
            f"/children/{uuid.uuid4()}/schedules"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_view_analytics(
        self, contributor_client
    ):
        resp = await contributor_client.get(
            f"/children/{uuid.uuid4()}/analytics"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_generate_report(
        self, contributor_client
    ):
        resp = await contributor_client.post(
            f"/children/{uuid.uuid4()}/reports/generate"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_view_report(
        self, contributor_client
    ):
        resp = await contributor_client.get(
            f"/reports/{uuid.uuid4()}"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_flag_report(
        self, contributor_client
    ):
        resp = await contributor_client.post(
            f"/reports/{uuid.uuid4()}/flag"
        )
        assert resp.status_code == 403

    async def test_contributor_cannot_view_audit_trail(
        self, contributor_client
    ):
        resp = await contributor_client.get(
            f"/children/{uuid.uuid4()}/audit"
        )
        assert resp.status_code == 403


class TestContributorAllowedEndpoints:
    """Contributors CAN access certain endpoints when authorized for the child."""

    async def test_contributor_can_list_children(
        self, contributor_client, contributor_user
    ):
        with (
            patch(
                "src.backend.api.children.get_authorized_children",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.backend.services.workspace_service.list_children",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            resp = await contributor_client.get("/children/")
        assert resp.status_code == 200

    async def test_contributor_can_submit_observation(
        self, contributor_client, contributor_user
    ):
        child_id = uuid.uuid4()
        obs = make_observation(
            child_id=child_id, submitted_by=contributor_user.id,
        )
        with (
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.submit_observation",
                new_callable=AsyncMock,
                return_value=(obs, "accept", None),
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await contributor_client.post(
                f"/children/{child_id}/observations",
                json={
                    "raw_text": "The child waved hello.",
                    "setting": "home",
                },
            )
        assert resp.status_code == 201

    async def test_contributor_can_list_own_observations(
        self, contributor_client, contributor_user
    ):
        child_id = uuid.uuid4()
        obs = make_observation(
            child_id=child_id, submitted_by=contributor_user.id
        )
        with (
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.list_observations",
                new_callable=AsyncMock,
                return_value=[obs],
            ),
        ):
            resp = await contributor_client.get(
                f"/children/{child_id}/observations"
            )
        assert resp.status_code == 200


class TestUnauthenticatedAccess:
    """Unauthenticated requests to protected endpoints must return 401."""

    async def test_unauth_cannot_list_children(self, unauth_client):
        resp = await unauth_client.get("/children/")
        assert resp.status_code == 401

    async def test_unauth_cannot_submit_observation(self, unauth_client):
        resp = await unauth_client.post(
            f"/children/{uuid.uuid4()}/observations",
            json={"raw_text": "test", "setting": "home"},
        )
        assert resp.status_code == 401

    async def test_unauth_cannot_view_audit(self, unauth_client):
        resp = await unauth_client.get(
            f"/children/{uuid.uuid4()}/audit"
        )
        assert resp.status_code == 401
