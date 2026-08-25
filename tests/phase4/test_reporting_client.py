"""Tests for ReportingClient — LLM report generation with safety validation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.backend.ml.reporting_client import (
    PROHIBITED_PATTERNS,
    ReportingClient,
    validate_report,
)
from src.backend.ml.schemas import (
    AdequacyLevel,
    GeneratedReportData,
    KpiResult,
    ReportSection,
)
from tests.phase4.conftest import make_adequate_result, make_evidence_packet


class TestValidateReport:
    def test_clean_report_passes(self):
        sections = [
            ReportSection(heading="Review Period Summary", body="Observations were recorded from June 1 to June 30."),
            ReportSection(heading="Evidence Coverage", body="5 observations were included."),
        ]
        ep = make_evidence_packet()
        errors = validate_report(sections, ep)
        assert len(errors) == 0

    def test_diagnostic_language_flagged(self):
        sections = [
            ReportSection(heading="Summary", body="The child was diagnosed with ASD."),
        ]
        ep = make_evidence_packet()
        errors = validate_report(sections, ep)
        assert any("Prohibited content" in e for e in errors)

    def test_recommendation_language_flagged(self):
        sections = [
            ReportSection(heading="Summary", body="We recommend therapy sessions twice weekly."),
        ]
        ep = make_evidence_packet()
        errors = validate_report(sections, ep)
        assert any("Prohibited content" in e for e in errors)

    def test_causal_language_flagged(self):
        sections = [
            ReportSection(heading="Summary", body="Progress was caused by autism interventions."),
        ]
        ep = make_evidence_packet()
        errors = validate_report(sections, ep)
        assert any("Prohibited content" in e for e in errors)

    def test_deficit_language_flagged(self):
        sections = [
            ReportSection(heading="Summary", body="The child shows a deficit in communication."),
        ]
        ep = make_evidence_packet()
        errors = validate_report(sections, ep)
        assert any("Prohibited content" in e for e in errors)

    def test_insufficient_evidence_must_be_acknowledged(self):
        inadequate = make_adequate_result(AdequacyLevel.INSUFFICIENT)
        ep = make_evidence_packet(adequacy=inadequate)
        sections = [
            ReportSection(heading="Summary", body="Everything looks great."),
        ]
        errors = validate_report(sections, ep)
        assert any("insufficient evidence" in e.lower() for e in errors)

    def test_insufficient_acknowledged_passes(self):
        inadequate = make_adequate_result(AdequacyLevel.INSUFFICIENT)
        ep = make_evidence_packet(adequacy=inadequate)
        sections = [
            ReportSection(heading="Summary", body="Evidence was insufficient for comprehensive analysis."),
        ]
        errors = validate_report(sections, ep)
        insufficient_errors = [e for e in errors if "insufficient evidence" in e.lower()]
        assert len(insufficient_errors) == 0


class TestFallbackSections:
    def test_fallback_contains_review_period(self):
        client = ReportingClient(api_key="test-key")
        ep = make_evidence_packet()
        sections = client._build_fallback_sections(ep)
        assert any("Review Period" in s["heading"] for s in sections)

    def test_fallback_contains_evidence_coverage(self):
        client = ReportingClient(api_key="test-key")
        ep = make_evidence_packet()
        sections = client._build_fallback_sections(ep)
        assert any("Evidence Coverage" in s["heading"] for s in sections)

    def test_fallback_includes_quality_flags(self):
        adequacy = make_adequate_result()
        adequacy.quality_flags = ["coverage: Only 3/5 observations"]
        ep = make_evidence_packet(adequacy=adequacy)
        client = ReportingClient(api_key="test-key")
        sections = client._build_fallback_sections(ep)
        limitation_section = next((s for s in sections if "Limitation" in s["heading"]), None)
        assert limitation_section is not None
        assert "coverage" in limitation_section["body"]


class TestReportGeneration:
    @pytest.mark.asyncio
    async def test_generate_calls_llm(self):
        ep = make_evidence_packet()

        mock_sections = [
            {
                "heading": "Review Period Summary",
                "body": "Observations collected from June 1 to June 30.",
                "evidence_refs": [],
                "abstention_note": None,
            },
            {
                "heading": "Evidence Coverage",
                "body": "5 observations recorded across 2 settings.",
                "evidence_refs": [],
                "abstention_note": None,
            },
        ]

        client = ReportingClient(api_key="test-key")
        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_sections
            report = await client.generate_report(ep)

        assert isinstance(report, GeneratedReportData)
        assert len(report.sections) == 2
        assert report.provider == "anthropic"
        mock_llm.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self):
        ep = make_evidence_packet()
        client = ReportingClient(api_key="test-key")

        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API error")
            report = await client.generate_report(ep)

        assert isinstance(report, GeneratedReportData)
        assert len(report.sections) >= 2

    @pytest.mark.asyncio
    async def test_validation_errors_recorded(self):
        ep = make_evidence_packet()
        bad_sections = [
            {
                "heading": "Summary",
                "body": "The child was diagnosed with communication deficit.",
                "evidence_refs": [],
                "abstention_note": None,
            },
        ]

        client = ReportingClient(api_key="test-key")
        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = bad_sections
            report = await client.generate_report(ep)

        assert not report.validation_passed
        assert len(report.validation_errors) > 0


class TestReportProvenance:
    @pytest.mark.asyncio
    async def test_provenance_fields(self):
        ep = make_evidence_packet()
        client = ReportingClient(api_key="test-key", model="claude-sonnet-4-20250514")

        mock_sections = [
            {"heading": "Summary", "body": "Report content.", "evidence_refs": [], "abstention_note": None},
        ]
        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_sections
            report = await client.generate_report(ep)

        assert report.provider == "anthropic"
        assert report.model == "claude-sonnet-4-20250514"
        assert report.prompt_version == "1.0"
        assert report.generated_at is not None
