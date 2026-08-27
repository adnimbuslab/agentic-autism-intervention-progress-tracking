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
from tests.phase4.conftest import (
    make_adequate_result,
    make_evidence_packet,
    make_rich_evidence_packet,
)


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

    # @spec REPORT-021
    def test_insufficient_evidence_must_be_acknowledged(self):
        inadequate = make_adequate_result(AdequacyLevel.INSUFFICIENT)
        ep = make_evidence_packet(adequacy=inadequate)
        sections = [
            ReportSection(heading="Summary", body="Everything looks great."),
        ]
        errors = validate_report(sections, ep)
        assert any("insufficient evidence" in e.lower() for e in errors)

    # @spec REPORT-021
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
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        assert any("Review Period" in s["heading"] for s in sections)

    def test_fallback_contains_evidence_coverage(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        assert any("Evidence Coverage" in s["heading"] for s in sections)

    def test_fallback_includes_quality_flags(self):
        adequacy = make_adequate_result()
        adequacy.quality_flags = ["coverage: Only 3/5 observations"]
        ep = make_rich_evidence_packet(adequacy=adequacy)
        client = ReportingClient(api_key="test-key")
        sections = client._build_fallback_sections(ep)
        limitation_section = next((s for s in sections if "Limitation" in s["heading"]), None)
        assert limitation_section is not None
        assert "coverage" in limitation_section["body"]

    def test_fallback_includes_independence_rate(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        key_section = next((s for s in sections if s["heading"] == "Key Indicators"), None)
        assert key_section is not None
        assert "5 of 8" in key_section["body"]
        assert "62.5%" in key_section["body"]

    def test_fallback_includes_positive_outcome_rate(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        key_section = next((s for s in sections if s["heading"] == "Key Indicators"), None)
        assert key_section is not None
        assert "6 of 7" in key_section["body"]
        assert "85.7%" in key_section["body"]

    def test_fallback_includes_distributions(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        patterns_section = next((s for s in sections if s["heading"] == "Observed Patterns"), None)
        assert patterns_section is not None
        assert "goal domains" in patterns_section["body"]
        assert "modalities" in patterns_section["body"]
        assert "prompt levels" in patterns_section["body"]

    def test_fallback_includes_trends(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        progress_section = next((s for s in sections if s["heading"] == "Progress Indicators"), None)
        assert progress_section is not None
        assert "increased" in progress_section["body"]
        assert "0.2500" in progress_section["body"]
        assert "0.0833" in progress_section["body"]

    def test_fallback_includes_cross_observations(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        cross_section = next((s for s in sections if "Cross-Setting" in s["heading"]), None)
        assert cross_section is not None
        assert "2 distinct settings" in cross_section["body"]
        assert "2 distinct contributor roles" in cross_section["body"]

    def test_fallback_includes_goals_in_summary(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        summary = next(s for s in sections if s["heading"] == "Review Period Summary")
        assert "Improve requests" in summary["body"]
        assert "social_communication" in summary["body"]

    def test_fallback_includes_review_count(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        coverage = next(s for s in sections if s["heading"] == "Evidence Coverage")
        assert "1 observations require interventionist review" in coverage["body"]

    def test_fallback_handles_abstained_kpis(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        ep.analytics.kpis = [
            KpiResult(name="observation_count", numerator=3.0, denominator=1.0, value=3.0),
            KpiResult(
                name="independence_rate", numerator=0, denominator=0,
                abstained=True, abstention_reason="No records with prompt level data",
                prerequisites_met=False, display_eligible=False,
            ),
            KpiResult(
                name="positive_outcome_rate", numerator=0, denominator=0,
                abstained=True, abstention_reason="No records with outcome data",
                prerequisites_met=False, display_eligible=False,
            ),
            KpiResult(
                name="prompt_support_trend", numerator=0, denominator=0,
                abstained=True, abstention_reason="Insufficient data for trend (need >=4 records with prompt level)",
                prerequisites_met=False, display_eligible=False,
            ),
            KpiResult(
                name="outcome_trend", numerator=0, denominator=0,
                abstained=True, abstention_reason="Insufficient data for trend (need >=4 records with outcome)",
                prerequisites_met=False, display_eligible=False,
            ),
        ]
        sections = client._build_fallback_sections(ep)

        key_section = next((s for s in sections if s["heading"] == "Key Indicators"), None)
        assert key_section is not None
        assert "withheld" in key_section["body"].lower()
        assert "No records with prompt level data" in key_section["body"]

        limitations = next(s for s in sections if s["heading"] == "Evidence Limitations")
        assert "independence rate" in limitations["body"].lower()

    def test_fallback_preserves_numerator_denominator(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        key_section = next(s for s in sections if s["heading"] == "Key Indicators")
        assert "5 of 8" in key_section["body"]
        assert "6 of 7" in key_section["body"]

    def test_fallback_section_count(self):
        client = ReportingClient(api_key="test-key")
        ep = make_rich_evidence_packet()
        sections = client._build_fallback_sections(ep)
        headings = [s["heading"] for s in sections]
        assert "Review Period Summary" in headings
        assert "Evidence Coverage" in headings
        assert "Key Indicators" in headings
        assert "Observed Patterns" in headings
        assert "Progress Indicators" in headings
        assert "Cross-Setting and Cross-Contributor Observations" in headings
        assert "Evidence Limitations" in headings
        assert len(sections) == 7


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
    # @spec REPORT-010
    async def test_fallback_on_llm_failure(self):
        ep = make_rich_evidence_packet()
        client = ReportingClient(api_key="test-key")

        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API error")
            report = await client.generate_report(ep)

        assert isinstance(report, GeneratedReportData)
        assert len(report.sections) >= 5

    @pytest.mark.asyncio
    # @spec REPORT-012, REPORT-020
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

    @pytest.mark.asyncio
    # @spec REPORT-012
    async def test_validation_runs_on_fallback(self):
        ep = make_rich_evidence_packet()
        client = ReportingClient(api_key="test-key")

        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API error")
            report = await client.generate_report(ep)

        assert report.validation_passed is True
        assert len(report.validation_errors) == 0


class TestReportProvenance:
    @pytest.mark.asyncio
    async def test_llm_success_provenance(self):
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

    @pytest.mark.asyncio
    # @spec REPORT-011
    async def test_fallback_provenance(self):
        ep = make_rich_evidence_packet()
        client = ReportingClient(api_key="test-key", model="claude-sonnet-4-20250514")

        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API key invalid")
            report = await client.generate_report(ep)

        assert report.provider == "deterministic_fallback"
        assert report.model == "deterministic_fallback_v1"
        assert report.prompt_version == "N/A"

    @pytest.mark.asyncio
    async def test_llm_and_fallback_provenance_differ(self):
        ep = make_rich_evidence_packet()
        client = ReportingClient(api_key="test-key", model="claude-sonnet-4-20250514")

        mock_sections = [
            {"heading": "Summary", "body": "Report content.", "evidence_refs": [], "abstention_note": None},
        ]

        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_sections
            llm_report = await client.generate_report(ep)

        with patch.object(client, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("fail")
            fallback_report = await client.generate_report(ep)

        assert llm_report.provider != fallback_report.provider
        assert llm_report.model != fallback_report.model
        assert llm_report.prompt_version != fallback_report.prompt_version
