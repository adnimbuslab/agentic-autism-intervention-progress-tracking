"""Interventionist end-to-end workflow: full lifecycle from child creation
through report generation and audit trail verification.

Exercises real API/service/database. Only the external LLM boundary is mocked.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.phase6.integration.conftest import _make_mock_extraction


@pytest.mark.integration
class TestInterventionistE2E:

    async def test_interventionist_login(self, client: AsyncClient, seed_users):
        resp = await client.post("/auth/login", json={
            "email": "test-interventionist@example.com",
            "password": "TestPass123!",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_create_child(self, client: AsyncClient, interventionist_token, seed_users):
        resp = await client.post(
            "/children/",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"display_name": "New Test Child"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "New Test Child"
        return data["id"]

    async def test_list_children(
        self, client: AsyncClient, interventionist_token, seed_child,
    ):
        resp = await client.get(
            "/children/",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_create_goals(
        self, client: AsyncClient, interventionist_token, seed_child,
    ):
        resp = await client.post(
            f"/children/{seed_child.id}/goals",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={
                "goal_type": "long_term",
                "domain": "social_communication",
                "title": "Integration Test Goal",
                "description": "Test goal for integration testing.",
            },
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_invite_actor(
        self, client: AsyncClient, interventionist_token, seed_child, seed_users,
    ):
        resp = await client.post(
            f"/children/{seed_child.id}/actors",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"email": "test-teacher@example.com", "role": "teacher"},
        )
        assert resp.status_code in (201, 409)

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_full_observation_to_record_flow(
        self, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, seed_actors, seed_child,
        seed_goals, seed_review_period, mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        resp = await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Child said 'want juice' while pointing at the fridge.",
                "setting": "home",
                "source_type": "conversational",
            },
        )
        assert resp.status_code == 201
        obs_data = resp.json()
        obs_id = obs_data["observation"]["id"]
        assert obs_data["routing_decision"] == "accept"

        resp = await client.get(
            f"/observations/{obs_id}",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["raw_text"] == "Child said 'want juice' while pointing at the fridge."
        assert detail["structured_record"] is not None
        record_id = detail["structured_record"]["id"]

        resp = await client.get(
            f"/records/{record_id}",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        record = resp.json()
        assert record["version"] == 1
        original_raw_text = detail["raw_text"]

        corrected_data = dict(record["record_data"])
        corrected_data["prompt_level"] = "gestural"
        resp = await client.post(
            f"/records/{record_id}/correct",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={
                "record_data": corrected_data,
                "correction_reason": "Parent clarified gestural prompt was used.",
            },
        )
        assert resp.status_code == 200
        new_record = resp.json()
        assert new_record["version"] == 2
        assert new_record["record_data"]["prompt_level"] == "gestural"
        new_record_id = new_record["id"]

        resp = await client.get(
            f"/records/{new_record_id}/history",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 2
        assert history[0]["version"] == 1
        assert history[1]["version"] == 2

        resp = await client.get(
            f"/observations/{obs_id}",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["raw_text"] == original_raw_text

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_list_records_for_child(
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
                "raw_text": "Record listing test observation.",
                "setting": "school",
                "source_type": "conversational",
            },
        )

        resp = await client.get(
            f"/children/{seed_child.id}/records",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) >= 1

    async def test_create_review_period(
        self, client: AsyncClient, interventionist_token, seed_child,
    ):
        resp = await client.post(
            f"/children/{seed_child.id}/review-periods",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={
                "start_date": (date.today() - timedelta(days=30)).isoformat(),
                "end_date": date.today().isoformat(),
            },
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    @patch("src.backend.services.observation_service.get_extraction_provider")
    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_full_analytics_report_flow(
        self, mock_call_llm, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, teacher_token,
        seed_actors, seed_child, seed_goals, seed_review_period,
        mock_extraction_provider, mock_reporting_llm,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        mock_call_llm.side_effect = mock_reporting_llm

        for i in range(6):
            token = parent_token if i % 2 == 0 else teacher_token
            setting = "home" if i % 2 == 0 else "school"
            await client.post(
                f"/children/{seed_child.id}/observations",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "raw_text": f"Test observation {i} for analytics flow.",
                    "setting": setting,
                    "source_type": "conversational",
                },
            )

        resp = await client.post(
            f"/children/{seed_child.id}/analytics",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"review_period_id": str(seed_review_period.id)},
        )
        assert resp.status_code == 200
        analytics = resp.json()
        assert "kpis" in analytics
        assert "adequacy" in analytics

        resp = await client.post(
            f"/children/{seed_child.id}/reports/generate",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"review_period_id": str(seed_review_period.id)},
        )
        assert resp.status_code == 201
        report = resp.json()
        report_id = report["id"]
        assert len(report["sections"]) >= 2

        resp = await client.get(
            f"/reports/{report_id}",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/reports/{report_id}/evidence",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        evidence = resp.json()
        assert evidence["observation_count"] >= 1

        resp = await client.post(
            f"/reports/{report_id}/flag",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"reason": "Flagged for review during integration test."},
        )
        assert resp.status_code == 200
        flagged = resp.json()
        assert flagged["flagged"] is True
        assert flagged["flagged_reason"] == "Flagged for review during integration test."

        resp = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) >= 1
        actions = [e["action"] for e in events]
        assert "submit_observation" in actions
