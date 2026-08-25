"""Tests for child workspace endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.phase3.conftest import make_child
from src.backend.models.user import Role


class TestCreateChild:
    async def test_create_child_returns_201(
        self, interventionist_client, interventionist_user
    ):
        child_mock = make_child(created_by=interventionist_user.id)
        with (
            patch(
                "src.backend.services.workspace_service.create_child",
                new_callable=AsyncMock,
                return_value=child_mock,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                "/children/", json={"display_name": "Test Child"}
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "Test Child"
        assert data["is_active"] is True

    async def test_contributor_cannot_create_child(self, contributor_client):
        resp = await contributor_client.post(
            "/children/", json={"display_name": "Forbidden Child"}
        )
        assert resp.status_code == 403


class TestListChildren:
    async def test_list_children_returns_authorized(
        self, interventionist_client, interventionist_user
    ):
        c1 = make_child(created_by=interventionist_user.id, display_name="Child A")
        c2 = make_child(created_by=interventionist_user.id, display_name="Child B")
        with (
            patch(
                "src.backend.api.children.get_authorized_children",
                new_callable=AsyncMock,
                return_value=[c1.id, c2.id],
            ),
            patch(
                "src.backend.services.workspace_service.list_children",
                new_callable=AsyncMock,
                return_value=[c1, c2],
            ),
        ):
            resp = await interventionist_client.get("/children/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


class TestGetChild:
    async def test_get_child_authorized(
        self, interventionist_client, interventionist_user
    ):
        child_mock = make_child(created_by=interventionist_user.id)
        with (
            patch(
                "src.backend.api.children.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.workspace_service.get_child",
                new_callable=AsyncMock,
                return_value=child_mock,
            ),
        ):
            resp = await interventionist_client.get(f"/children/{child_mock.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(child_mock.id)

    async def test_get_child_not_authorized_returns_403(
        self, interventionist_client
    ):
        from fastapi import HTTPException, status

        async def deny(*a, **kw):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this child",
            )

        child_id = uuid.uuid4()
        with patch(
            "src.backend.api.children.authorize_child_access",
            new_callable=AsyncMock,
            side_effect=deny,
        ):
            resp = await interventionist_client.get(f"/children/{child_id}")
        assert resp.status_code == 403


class TestUpdateChild:
    async def test_update_child(
        self, interventionist_client, interventionist_user
    ):
        child_mock = make_child(created_by=interventionist_user.id)
        updated = make_child(
            child_id=child_mock.id,
            created_by=interventionist_user.id,
            display_name="Updated Name",
        )
        with (
            patch(
                "src.backend.api.children.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.workspace_service.get_child",
                new_callable=AsyncMock,
                return_value=child_mock,
            ),
            patch(
                "src.backend.services.workspace_service.update_child",
                new_callable=AsyncMock,
                return_value=updated,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.patch(
                f"/children/{child_mock.id}",
                json={"display_name": "Updated Name"},
            )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"
