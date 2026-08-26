"""Reporting + provenance E2E: structured evidence → adequacy → analytics →
EvidencePacket → mocked ReportingClient → validation → persistence →
API retrieval → evidence chain verification.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.backend.ml.adequacy_router import AdequacyRouter
from src.backend.ml.analytics_engine import AnalyticsEngine
from src.backend.ml.reporting_client import (
    PROHIBITED_PATTERNS,
    ReportingClient,
    validate_report,
)
from src.backend.ml.schemas import (
    AdequacyLevel,
    EvidencePacket,
    ReportSection,
)
from tests.phase6.integration.conftest import _make_mock_extraction


def _build_evidence_packet(
    *,
    adequacy_level=AdequacyLevel.ADEQUATE,
    observation_count=8,
    record_ids=None,
) -> EvidencePacket:
    from src.backend.ml.schemas import (
        AdequacyCheckResult,
        AdequacyCheck,
        AdequacyResult,
        AnalyticsResult,
        KpiResult,
    )

    adequacy = AdequacyResult(
        level=adequacy_level,
        eligible=adequacy_level != AdequacyLevel.INSUFFICIENT,
        checks=[],
        quality_flags=[] if adequacy_level == AdequacyLevel.ADEQUATE else [
            "coverage: Only 2/5 observations received"
        ],
    )

    kpis = [
        KpiResult(name="observation_count", numerator=float(observation_count),
                  denominator=1.0, value=float(observation_count)),
        KpiResult(name="independence_rate", numerator=6.0, denominator=8.0,
                  value=0.75),
    ]

    if adequacy_level == AdequacyLevel.INSUFFICIENT:
        kpis = [KpiResult(name="all_analytics", numerator=0, denominator=0,
                          abstained=True,
                          abstention_reason="Evidence level: insufficient",
                          prerequisites_met=False, display_eligible=False)]

    analytics = AnalyticsResult(
        child_id="test-child",
        review_period_id="test-period",
        kpis=kpis,
        adequacy=adequacy,
    )

    return EvidencePacket(
        child_id="test-child",
        review_period_id="test-period",
        review_period_start=(date.today() - timedelta(days=60)).isoformat(),
        review_period_end=date.today().isoformat(),
        goals=[{"id": "g1", "domain": "social_communication", "title": "Test Goal"}],
        structured_records=[],
        record_ids=record_ids or [f"rec-{i}" for i in range(observation_count)],
        record_versions={f"rec-{i}": 1 for i in range(observation_count)},
        analytics=analytics,
        adequacy=adequacy,
        quality_flags=adequacy.quality_flags,
        contributor_summary={"parent": 4, "teacher": 4},
        setting_summary={"home": 4, "school": 4},
        observation_count=observation_count,
        abstained_count=0,
        review_count=0,
    )


@pytest.mark.integration
class TestReportingProvenanceE2E:

    def test_validate_clean_report(self):
        ep = _build_evidence_packet()
        sections = [
            ReportSection(
                heading="Review Period Summary",
                body="During the review period, observations were recorded across settings.",
                evidence_refs=[],
            ),
            ReportSection(
                heading="Observed Patterns",
                body="Records show the independence rate was 0.75. Observations indicate progress.",
                evidence_refs=["rec-0", "rec-1"],
            ),
            ReportSection(
                heading="Evidence Limitations",
                body="No significant limitations for this review period.",
                evidence_refs=[],
            ),
        ]
        errors = validate_report(sections, ep)
        assert len(errors) == 0

    def test_validate_detects_prohibited_content(self):
        ep = _build_evidence_packet()
        sections = [
            ReportSection(
                heading="Summary",
                body="The child has been diagnosed with autism and we recommend therapy changes.",
                evidence_refs=[],
            ),
        ]
        errors = validate_report(sections, ep)
        assert len(errors) >= 1
        assert any("Prohibited" in e for e in errors)

    def test_validate_detects_missing_insufficient_acknowledgment(self):
        ep = _build_evidence_packet(
            adequacy_level=AdequacyLevel.INSUFFICIENT,
            observation_count=0,
        )
        sections = [
            ReportSection(
                heading="Summary",
                body="Everything is great and well documented.",
                evidence_refs=[],
            ),
        ]
        errors = validate_report(sections, ep)
        assert any("insufficient" in e.lower() for e in errors)

    def test_validate_accepts_insufficient_acknowledgment(self):
        ep = _build_evidence_packet(
            adequacy_level=AdequacyLevel.INSUFFICIENT,
            observation_count=0,
        )
        sections = [
            ReportSection(
                heading="Summary",
                body="Evidence was insufficient for meaningful analysis.",
                evidence_refs=[],
            ),
        ]
        errors = validate_report(sections, ep)
        insufficient_errors = [e for e in errors if "insufficient" in e.lower()]
        assert len(insufficient_errors) == 0

    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_reporting_client_generates_valid_report(self, mock_call_llm):
        async def _mock_llm(user_message):
            return [
                {"heading": "Review Period Summary",
                 "body": "During the review period, observations indicate engagement.",
                 "evidence_refs": [], "abstention_note": None},
                {"heading": "Evidence Coverage",
                 "body": "Observations collected from multiple contributors and settings.",
                 "evidence_refs": [], "abstention_note": None},
                {"heading": "Observed Patterns",
                 "body": "Records show the independence rate was 0.75.",
                 "evidence_refs": [], "abstention_note": None},
                {"heading": "Evidence Limitations",
                 "body": "No significant limitations noted.",
                 "evidence_refs": [], "abstention_note": None},
            ]
        mock_call_llm.side_effect = _mock_llm

        ep = _build_evidence_packet()
        client = ReportingClient(api_key="test-key")
        report_data = await client.generate_report(ep)
        assert len(report_data.sections) >= 4
        assert report_data.validation_passed is True
        assert len(report_data.validation_errors) == 0
        assert report_data.provider == "anthropic"

    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_reporting_client_catches_prohibited(self, mock_call_llm):
        async def _mock_llm(user_message):
            return [
                {"heading": "Summary",
                 "body": "The child has been diagnosed with ASD. We recommend therapy intervention.",
                 "evidence_refs": [], "abstention_note": None},
            ]
        mock_call_llm.side_effect = _mock_llm

        ep = _build_evidence_packet()
        client = ReportingClient(api_key="test-key")
        report_data = await client.generate_report(ep)
        assert report_data.validation_passed is False
        assert len(report_data.validation_errors) >= 1

    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_reporting_fallback_on_failure(self, mock_call_llm):
        mock_call_llm.side_effect = Exception("LLM call failed")

        ep = _build_evidence_packet()
        client = ReportingClient(api_key="test-key")
        report_data = await client.generate_report(ep)
        assert len(report_data.sections) >= 2
        headings = [s.heading for s in report_data.sections]
        assert "Review Period Summary" in headings
        assert "Evidence Coverage" in headings

    @patch("src.backend.services.observation_service.get_extraction_provider")
    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_full_report_via_api(
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
                    "raw_text": f"Report test observation {i}.",
                    "setting": setting,
                    "source_type": "conversational",
                },
            )

        resp = await client.post(
            f"/children/{seed_child.id}/reports/generate",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"review_period_id": str(seed_review_period.id)},
        )
        assert resp.status_code == 201
        report = resp.json()
        report_id = report["id"]
        assert len(report["sections"]) >= 2

        resp2 = await client.get(
            f"/reports/{report_id}/evidence",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp2.status_code == 200
        evidence = resp2.json()
        assert "record_ids" in evidence
        assert "contributor_summary" in evidence
        assert "setting_summary" in evidence
        assert evidence["observation_count"] >= 1

        assert "child_id" in evidence
        assert "review_period_id" in evidence
        assert "review_period_start" in evidence
        assert "review_period_end" in evidence

    @patch("src.backend.services.observation_service.get_extraction_provider")
    @patch("src.backend.ml.reporting_client.ReportingClient._call_llm")
    async def test_report_flag_and_audit(
        self, mock_call_llm, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, seed_actors, seed_child,
        seed_goals, seed_review_period, mock_extraction_provider,
        mock_reporting_llm,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)
        mock_call_llm.side_effect = mock_reporting_llm

        for i in range(4):
            await client.post(
                f"/children/{seed_child.id}/observations",
                headers={"Authorization": f"Bearer {parent_token}"},
                json={
                    "raw_text": f"Flag test obs {i}.",
                    "setting": "home",
                    "source_type": "conversational",
                },
            )

        resp = await client.post(
            f"/children/{seed_child.id}/reports/generate",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"review_period_id": str(seed_review_period.id)},
        )
        assert resp.status_code == 201
        report_id = resp.json()["id"]

        resp2 = await client.post(
            f"/reports/{report_id}/flag",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"reason": "Flagged during provenance E2E test."},
        )
        assert resp2.status_code == 200
        assert resp2.json()["flagged"] is True

        resp3 = await client.get(
            f"/children/{seed_child.id}/audit",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp3.status_code == 200
        events = resp3.json()
        actions = [e["action"] for e in events]
        assert "generate_report" in actions
        assert "flag_report" in actions
