"""Tests for structured record endpoints — list, correct, verify, history."""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
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


class TestVerifyRecord:
    """Verification is the only route by which an unmodified extraction
    becomes analytics-eligible, so the checks here are the access-control
    boundary for the analytics gate, not just endpoint plumbing."""

    def _patches(self, record, obs, verified=None, error=None):
        verify = (
            AsyncMock(side_effect=error)
            if error is not None
            else AsyncMock(return_value=verified)
        )
        return (
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
                "src.backend.services.observation_service.verify_record",
                verify,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        )

    async def test_marks_a_validated_record_verified(
        self, interventionist_client, interventionist_user
    ):
        record = make_record(status=RecordStatus.VALIDATED)
        obs = make_observation()
        verified = make_record(
            record_id=record.id, observation_id=record.observation_id
        )
        verified.status = RecordStatus.VERIFIED
        verified.verified_by = interventionist_user.id
        verified.verified_at = datetime.now(UTC)

        with ExitStack() as stack:
            for ctx in self._patches(record, obs, verified=verified):
                stack.enter_context(ctx)
            resp = await interventionist_client.post(
                f"/records/{record.id}/verify"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert data["verified_by"] == str(interventionist_user.id)
        assert data["verified_at"] is not None

    async def test_verification_is_audited_with_the_real_prior_status(
        self, interventionist_client, interventionist_user
    ):
        record = make_record(status=RecordStatus.VALIDATED)
        obs = make_observation()
        verified = make_record(
            record_id=record.id, observation_id=record.observation_id
        )
        verified.status = RecordStatus.VERIFIED

        log_event = AsyncMock()
        with ExitStack() as stack:
            for ctx in self._patches(record, obs, verified=verified)[:-1]:
                stack.enter_context(ctx)
            stack.enter_context(
                patch("src.backend.services.audit_service.log_event", log_event)
            )
            resp = await interventionist_client.post(
                f"/records/{record.id}/verify"
            )
        assert resp.status_code == 200
        kwargs = log_event.await_args.kwargs
        assert kwargs["action"] == "verify_record"
        assert kwargs["user_id"] == interventionist_user.id
        assert kwargs["child_id"] == obs.child_id
        assert kwargs["detail"]["previous_status"] == "validated"

    async def test_pending_record_cannot_be_verified(
        self, interventionist_client
    ):
        # A PENDING record was routed to review because the evidence was
        # inadequate; accepting it unchanged would defeat that routing.
        record = make_record(status=RecordStatus.PENDING)
        obs = make_observation()
        with ExitStack() as stack:
            for ctx in self._patches(
                record, obs, error=ValueError("Only a validated record can be verified")
            ):
                stack.enter_context(ctx)
            resp = await interventionist_client.post(
                f"/records/{record.id}/verify"
            )
        assert resp.status_code == 409
        assert "validated" in resp.json()["detail"]

    async def test_record_not_found_returns_404(self, interventionist_client):
        with patch(
            "src.backend.services.observation_service.get_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await interventionist_client.post(
                f"/records/{uuid.uuid4()}/verify"
            )
        assert resp.status_code == 404

    async def test_missing_parent_observation_returns_404(
        self, interventionist_client
    ):
        record = make_record(status=RecordStatus.VALIDATED)
        with (
            patch(
                "src.backend.services.observation_service.get_record",
                new_callable=AsyncMock,
                return_value=record,
            ),
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            resp = await interventionist_client.post(
                f"/records/{record.id}/verify"
            )
        assert resp.status_code == 404

    async def test_contributor_cannot_verify(self, contributor_client):
        resp = await contributor_client.post(f"/records/{uuid.uuid4()}/verify")
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_verify(self, unauth_client):
        resp = await unauth_client.post(f"/records/{uuid.uuid4()}/verify")
        assert resp.status_code in (401, 403)

    async def test_child_authorization_is_enforced(
        self, interventionist_client
    ):
        # An interventionist not assigned to this child must be refused even
        # though the role check passes.
        from fastapi import HTTPException

        record = make_record(status=RecordStatus.VALIDATED)
        obs = make_observation()
        verify = AsyncMock()
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
                side_effect=HTTPException(status_code=403, detail="Forbidden"),
            ),
            patch(
                "src.backend.services.observation_service.verify_record", verify
            ),
        ):
            resp = await interventionist_client.post(
                f"/records/{record.id}/verify"
            )
        assert resp.status_code == 403
        verify.assert_not_awaited()


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
