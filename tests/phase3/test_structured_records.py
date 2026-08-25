"""Tests for structured record endpoints — list, correct, history."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.backend.models.observation import RecordStatus
from tests.phase3.conftest import make_observation, make_record


class TestListRecords:
    async def test_interventionist_can_list_records(
        self, interventionist_client
    ):
        child_id = uuid.uuid4()
        r1 = make_record()
        r2 = make_record()
        with (
            patch(
                "src.backend.api.structured_records.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.list_records",
                new_callable=AsyncMock,
                return_value=[r1, r2],
            ),
        ):
            resp = await interventionist_client.get(
                f"/children/{child_id}/records"
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_contributor_cannot_list_records(
        self, contributor_client
    ):
        child_id = uuid.uuid4()
        resp = await contributor_client.get(f"/children/{child_id}/records")
        assert resp.status_code == 403


class TestCorrectRecord:
    async def test_creates_new_version(
        self, interventionist_client, interventionist_user
    ):
        record = make_record(version=1)
        obs = make_observation()
        corrected = make_record(
            observation_id=record.observation_id, version=2
        )
        corrected.status = RecordStatus.CORRECTED
        corrected.corrected_by = interventionist_user.id
        corrected.correction_reason = "Fixed behavior"
        corrected.previous_version_id = record.id

        with (
            patch(
                "src.backend.services.observation_service.get_record",
                new_callable=AsyncMock,
                return_value=record,
            ),
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.structured_records.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.correct_record",
                new_callable=AsyncMock,
                return_value=corrected,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/records/{record.id}/correct",
                json={
                    "record_data": {"behavior": "corrected"},
                    "correction_reason": "Fixed behavior",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        assert data["correction_reason"] == "Fixed behavior"

    async def test_record_not_found_returns_404(
        self, interventionist_client
    ):
        with patch(
            "src.backend.services.observation_service.get_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await interventionist_client.post(
                f"/records/{uuid.uuid4()}/correct",
                json={
                    "record_data": {"behavior": "x"},
                    "correction_reason": "test",
                },
            )
        assert resp.status_code == 404

    async def test_contributor_cannot_correct(self, contributor_client):
        resp = await contributor_client.post(
            f"/records/{uuid.uuid4()}/correct",
            json={
                "record_data": {"behavior": "x"},
                "correction_reason": "test",
            },
        )
        assert resp.status_code == 403


class TestRecordHistory:
    async def test_returns_version_chain(
        self, interventionist_client
    ):
        obs = make_observation()
        r1 = make_record(observation_id=obs.id, version=1)
        r2 = make_record(observation_id=obs.id, version=2)
        r2.previous_version_id = r1.id
        r2.status = RecordStatus.CORRECTED

        with (
            patch(
                "src.backend.services.observation_service.get_record",
                new_callable=AsyncMock,
                return_value=r1,
            ),
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.structured_records.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.get_record_history",
                new_callable=AsyncMock,
                return_value=[r1, r2],
            ),
        ):
            resp = await interventionist_client.get(
                f"/records/{r1.id}/history"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["version"] == 1
        assert data[1]["version"] == 2

    async def test_contributor_cannot_view_history(self, contributor_client):
        resp = await contributor_client.get(
            f"/records/{uuid.uuid4()}/history"
        )
        assert resp.status_code == 403
