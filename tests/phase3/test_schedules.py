"""Tests for schedule endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.phase3.conftest import make_schedule


class TestCreateSchedule:
    async def test_create_returns_201(
        self, interventionist_client
    ):
        child_id = uuid.uuid4()
        schedule = make_schedule(child_id=child_id)
        with (
            patch(
                "src.backend.api.schedules.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.schedule_service.create_schedule",
                new_callable=AsyncMock,
                return_value=schedule,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/schedules",
                json={"cadence_days": 7, "description": "Weekly observation"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["cadence_days"] == 7

    async def test_contributor_cannot_create_schedule(
        self, contributor_client
    ):
        child_id = uuid.uuid4()
        resp = await contributor_client.post(
            f"/children/{child_id}/schedules",
            json={"cadence_days": 7},
        )
        assert resp.status_code == 403


class TestListSchedules:
    async def test_interventionist_can_list(
        self, interventionist_client
    ):
        child_id = uuid.uuid4()
        s1 = make_schedule(child_id=child_id)
        s2 = make_schedule(child_id=child_id)
        with (
            patch(
                "src.backend.api.schedules.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.schedule_service.list_schedules",
                new_callable=AsyncMock,
                return_value=[s1, s2],
            ),
        ):
            resp = await interventionist_client.get(
                f"/children/{child_id}/schedules"
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_contributor_cannot_list_schedules(
        self, contributor_client
    ):
        child_id = uuid.uuid4()
        resp = await contributor_client.get(
            f"/children/{child_id}/schedules"
        )
        assert resp.status_code == 403
