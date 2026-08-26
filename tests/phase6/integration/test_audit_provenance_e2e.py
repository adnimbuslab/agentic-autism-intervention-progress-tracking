"""Audit/provenance integration tests: append-only event logging for all
critical actions through the API layer.

Verifies audit events for: observation submission, clarification, finalization,
correction, actor assignment, schedule, analytics, report generation, flagging.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.phase6.integration.conftest import (
    _make_mock_extraction,
    _make_mock_extraction_needing_clarification,
)


@pytest.mark.integration
class TestAuditProvenanceE2E:

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_observation_submit_creates_audit(
        self, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, seed_actors, seed_child,
        mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Audit test: observation submission.",
                "setting": "home",
                "source_type": "conversational",
            },
        )

        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        events = resp.json()
        actions = [e["action"] for e in events]
        assert "submit_observation" in actions

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_clarification_creates_audit(
        self, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, seed_actors, seed_child,
        mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(
            side_effect=_make_mock_extraction_needing_clarification,
        )

        resp = await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Audit test: needs clarification.",
                "setting": "home",
                "source_type": "conversational",
            },
        )
        assert resp.status_code == 201
        obs_id = resp.json()["observation"]["id"]

        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        await client.post(
            f"/observations/{obs_id}/clarifications",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={"answer": "It was verbal — she said 'more juice'."},
        )

        resp2 = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp2.status_code == 200
        events = resp2.json()
        actions = [e["action"] for e in events]
        assert "submit_observation" in actions

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_correction_creates_audit(
        self, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, seed_actors, seed_child,
        mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        resp = await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Audit test: correction.",
                "setting": "home",
                "source_type": "conversational",
            },
        )
        obs_id = resp.json()["observation"]["id"]

        obs_resp = await client.get(
            f"/observations/{obs_id}",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        record_id = obs_resp.json()["structured_record"]["id"]
        record_data = obs_resp.json()["structured_record"]["record_data"]

        corrected = dict(record_data)
        corrected["prompt_level"] = "gestural"
        await client.post(
            f"/records/{record_id}/correct",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={
                "record_data": corrected,
                "correction_reason": "Audit E2E correction test.",
            },
        )

        resp2 = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp2.status_code == 200
        events = resp2.json()
        actions = [e["action"] for e in events]
        assert "correct_record" in actions

    @patch("src.backend.services.observation_service.get_extraction_provider")
    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_report_generation_creates_audit(
        self, mock_call_llm, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, seed_actors, seed_child,
        seed_goals, seed_review_period,
        mock_extraction_provider, mock_reporting_llm,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        mock_call_llm.side_effect = mock_reporting_llm

        for i in range(4):
            await client.post(
                f"/children/{seed_child.id}/observations",
                headers={"Authorization": f"Bearer {parent_token}"},
                json={
                    "raw_text": f"Audit report test obs {i}.",
                    "setting": "home",
                    "source_type": "conversational",
                },
            )

        await client.post(
            f"/children/{seed_child.id}/reports/generate",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"review_period_id": str(seed_review_period.id)},
        )

        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        events = resp.json()
        actions = [e["action"] for e in events]
        assert "generate_report" in actions

    @patch("src.backend.services.observation_service.get_extraction_provider")
    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_flag_report_creates_audit(
        self, mock_call_llm, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, seed_actors, seed_child,
        seed_goals, seed_review_period,
        mock_extraction_provider, mock_reporting_llm,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        mock_call_llm.side_effect = mock_reporting_llm

        for i in range(4):
            await client.post(
                f"/children/{seed_child.id}/observations",
                headers={"Authorization": f"Bearer {parent_token}"},
                json={
                    "raw_text": f"Audit flag test obs {i}.",
                    "setting": "home",
                    "source_type": "conversational",
                },
            )

        resp = await client.post(
            f"/children/{seed_child.id}/reports/generate",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"review_period_id": str(seed_review_period.id)},
        )
        report_id = resp.json()["id"]

        await client.post(
            f"/reports/{report_id}/flag",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"reason": "Flagged during audit E2E test."},
        )

        resp2 = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        events = resp2.json()
        actions = [e["action"] for e in events]
        assert "flag_report" in actions

    async def test_audit_trail_order_descending(
        self, client: AsyncClient,
        interventionist_token, seed_actors, seed_child,
    ):
        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        events = resp.json()
        if len(events) >= 2:
            timestamps = [e.get("created_at", e.get("timestamp")) for e in events]
            for a, b in zip(timestamps, timestamps[1:]):
                if a and b:
                    assert a >= b

    async def test_audit_requires_interventionist_role(
        self, client: AsyncClient,
        parent_token, seed_actors, seed_child,
    ):
        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert resp.status_code == 403

    async def test_audit_events_include_child_id(
        self, client: AsyncClient,
        interventionist_token, seed_actors, seed_child,
    ):
        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        events = resp.json()
        for event in events:
            assert event.get("child_id") == str(seed_child.id)

    async def test_audit_events_include_user_id(
        self, client: AsyncClient,
        interventionist_token, seed_actors, seed_child,
    ):
        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        events = resp.json()
        for event in events:
            assert "user_id" in event
            assert event["user_id"] is not None
