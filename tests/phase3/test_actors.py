"""Tests for actor assignment endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tests.phase3.conftest import make_actor, make_user
from src.backend.models.user import Role


class TestInviteActor:
    async def test_invite_actor_returns_201(
        self, interventionist_client, interventionist_user
    ):
        child_id = uuid.uuid4()
        target = make_user(Role.PARENT, email="parent@example.com")
        actor_mock = make_actor(
            child_id=child_id,
            user_id=target.id,
            invited_by=interventionist_user.id,
        )
        with (
            patch(
                "src.backend.api.actors.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.auth_service.get_user_by_email",
                new_callable=AsyncMock,
                return_value=target,
            ),
            patch(
                "src.backend.services.workspace_service.invite_actor",
                new_callable=AsyncMock,
                return_value=actor_mock,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/actors",
                json={"email": "parent@example.com", "role": "parent"},
            )
        assert resp.status_code == 201

    async def test_invite_unknown_email_returns_404(
        self, interventionist_client
    ):
        child_id = uuid.uuid4()
        with (
            patch(
                "src.backend.api.actors.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.auth_service.get_user_by_email",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/actors",
                json={"email": "nobody@example.com", "role": "parent"},
            )
        assert resp.status_code == 404


class TestListActors:
    async def test_list_actors(self, interventionist_client):
        child_id = uuid.uuid4()
        a1 = make_actor(child_id=child_id)
        with (
            patch(
                "src.backend.api.actors.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.workspace_service.list_actors",
                new_callable=AsyncMock,
                return_value=[a1],
            ),
        ):
            resp = await interventionist_client.get(f"/children/{child_id}/actors")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestRevokeActor:
    async def test_revoke_actor(self, interventionist_client, mock_db):
        actor_mock = make_actor()
        # db.get for the ActorModel lookup in the route
        mock_db.get = AsyncMock(return_value=actor_mock)
        revoked = make_actor(
            assignment_id=actor_mock.id,
            child_id=actor_mock.child_id,
        )
        from datetime import UTC, datetime

        revoked.revoked_at = datetime.now(UTC)
        with (
            patch(
                "src.backend.api.actors.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.workspace_service.revoke_actor",
                new_callable=AsyncMock,
                return_value=revoked,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.delete(f"/actors/{actor_mock.id}")
        assert resp.status_code == 200
        assert resp.json()["revoked_at"] is not None
