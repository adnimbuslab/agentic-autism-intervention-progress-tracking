"""Tests for goal endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.phase3.conftest import make_goal


class TestCreateGoal:
    async def test_create_goal_returns_201(
        self, interventionist_client, interventionist_user
    ):
        child_id = uuid.uuid4()
        goal_mock = make_goal(child_id=child_id, created_by=interventionist_user.id)
        with (
            patch(
                "src.backend.api.goals.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.workspace_service.create_goal",
                new_callable=AsyncMock,
                return_value=goal_mock,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/goals",
                json={
                    "goal_type": "short_term",
                    "domain": "social_communication",
                    "title": "Test Goal",
                    "description": "Increase social communication skills",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Test Goal"

    async def test_contributor_cannot_create_goal(self, contributor_client):
        child_id = uuid.uuid4()
        resp = await contributor_client.post(
            f"/children/{child_id}/goals",
            json={
                "goal_type": "short_term",
                "domain": "language",
                "title": "Forbidden Goal",
                "description": "Should not be allowed",
            },
        )
        assert resp.status_code == 403


class TestListGoals:
    async def test_list_goals(self, interventionist_client):
        child_id = uuid.uuid4()
        g1 = make_goal(child_id=child_id)
        g2 = make_goal(child_id=child_id)
        with (
            patch(
                "src.backend.api.goals.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.workspace_service.list_goals",
                new_callable=AsyncMock,
                return_value=[g1, g2],
            ),
        ):
            resp = await interventionist_client.get(f"/children/{child_id}/goals")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestUpdateGoal:
    async def test_update_goal(self, interventionist_client, interventionist_user):
        goal_mock = make_goal(created_by=interventionist_user.id)
        updated = make_goal(
            goal_id=goal_mock.id,
            child_id=goal_mock.child_id,
            created_by=interventionist_user.id,
        )
        updated.title = "Updated Goal"
        updated.version = 2
        with (
            patch(
                "src.backend.services.workspace_service.get_goal",
                new_callable=AsyncMock,
                return_value=goal_mock,
            ),
            patch(
                "src.backend.api.goals.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.workspace_service.update_goal",
                new_callable=AsyncMock,
                return_value=updated,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.patch(
                f"/goals/{goal_mock.id}",
                json={"title": "Updated Goal"},
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Goal"
        assert resp.json()["version"] == 2
