"""Tests for observation API endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.backend.models.observation import ObservationStatus, RecordStatus
from tests.phase3.conftest import make_observation, make_record


class TestSubmitObservation:
    async def test_submit_returns_201(
        self, interventionist_client, interventionist_user
    ):
        child_id = uuid.uuid4()
        obs = make_observation(
            child_id=child_id, submitted_by=interventionist_user.id
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
            resp = await interventionist_client.post(
                f"/children/{child_id}/observations",
                json={
                    "raw_text": "The child pointed at the toy.",
                    "setting": "home",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["routing_decision"] == "accept"

    async def test_submit_with_clarification_question(
        self, interventionist_client, interventionist_user
    ):
        child_id = uuid.uuid4()
        obs = make_observation(
            child_id=child_id,
            submitted_by=interventionist_user.id,
            status=ObservationStatus.CLARIFYING,
        )
        with (
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.submit_observation",
                new_callable=AsyncMock,
                return_value=(obs, "clarify", "Can you describe the setting?"),
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/children/{child_id}/observations",
                json={
                    "raw_text": "The child pointed at the toy.",
                    "setting": "home",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["routing_decision"] == "clarify"
        assert data["clarification_question"] == "Can you describe the setting?"


class TestSubmitClarification:
    async def test_submitter_can_clarify(
        self, interventionist_client, interventionist_user
    ):
        obs = make_observation(
            submitted_by=interventionist_user.id,
            status=ObservationStatus.CLARIFYING,
        )
        with (
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.submit_clarification",
                new_callable=AsyncMock,
                return_value=(obs, "accept", None),
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/observations/{obs.id}/clarifications",
                json={"answer": "It was at home."},
            )
        assert resp.status_code == 200

    async def test_non_submitter_cannot_clarify(
        self, interventionist_client, interventionist_user
    ):
        obs = make_observation(
            submitted_by=uuid.uuid4(),
            status=ObservationStatus.CLARIFYING,
        )
        with (
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/observations/{obs.id}/clarifications",
                json={"answer": "Some answer"},
            )
        assert resp.status_code == 403

    async def test_clarification_not_found_returns_404(
        self, interventionist_client
    ):
        with patch(
            "src.backend.services.observation_service.get_observation",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await interventionist_client.post(
                f"/observations/{uuid.uuid4()}/clarifications",
                json={"answer": "Something"},
            )
        assert resp.status_code == 404


class TestFinalizeObservation:
    async def test_submitter_can_finalize(
        self, interventionist_client, interventionist_user
    ):
        obs = make_observation(
            submitted_by=interventionist_user.id,
            status=ObservationStatus.CLARIFYING,
        )
        finalized_obs = make_observation(
            obs_id=obs.id,
            submitted_by=interventionist_user.id,
            status=ObservationStatus.FINALIZED,
        )
        with (
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.finalize_observation",
                new_callable=AsyncMock,
                return_value=finalized_obs,
            ),
            patch(
                "src.backend.services.audit_service.log_event",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/observations/{obs.id}/finalize"
            )
        assert resp.status_code == 200

    async def test_non_submitter_cannot_finalize(
        self, interventionist_client, interventionist_user
    ):
        obs = make_observation(submitted_by=uuid.uuid4())
        with (
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.post(
                f"/observations/{obs.id}/finalize"
            )
        assert resp.status_code == 403


class TestListObservations:
    async def test_interventionist_sees_all(
        self, interventionist_client, interventionist_user
    ):
        child_id = uuid.uuid4()
        obs1 = make_observation(child_id=child_id, submitted_by=uuid.uuid4())
        obs2 = make_observation(child_id=child_id, submitted_by=uuid.uuid4())
        with (
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
            patch(
                "src.backend.services.observation_service.list_observations",
                new_callable=AsyncMock,
                return_value=[obs1, obs2],
            ),
        ):
            resp = await interventionist_client.get(
                f"/children/{child_id}/observations"
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_contributor_sees_only_own(
        self, contributor_client, contributor_user
    ):
        child_id = uuid.uuid4()
        obs1 = make_observation(
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
                return_value=[obs1],
            ),
        ):
            resp = await contributor_client.get(
                f"/children/{child_id}/observations"
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestGetObservationDetail:
    async def test_interventionist_sees_structured_record(
        self, interventionist_client, interventionist_user
    ):
        record = make_record(version=1)
        obs = make_observation(
            submitted_by=interventionist_user.id,
            status=ObservationStatus.FINALIZED,
        )
        obs.structured_records = [record]
        with (
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
        ):
            resp = await interventionist_client.get(
                f"/observations/{obs.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["structured_record"] is not None

    async def test_contributor_does_not_see_structured_record(
        self, contributor_client, contributor_user
    ):
        record = make_record(version=1)
        obs = make_observation(
            submitted_by=contributor_user.id,
            status=ObservationStatus.FINALIZED,
        )
        obs.structured_records = [record]
        with (
            patch(
                "src.backend.services.observation_service.get_observation",
                new_callable=AsyncMock,
                return_value=obs,
            ),
            patch(
                "src.backend.api.observations.authorize_child_access",
                new_callable=AsyncMock,
            ),
        ):
            resp = await contributor_client.get(
                f"/observations/{obs.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["structured_record"] is None
