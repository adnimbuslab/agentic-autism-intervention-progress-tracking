"""Tests for evidence packet construction and traceability."""

from __future__ import annotations

import uuid

import pytest

from src.backend.ml.schemas import (
    AdequacyLevel,
    AnalyticsResult,
    EvidencePacket,
    KpiResult,
)
from tests.phase4.conftest import make_adequate_result, make_evidence_packet, make_record_dict


class TestEvidencePacketStructure:
    def test_contains_all_required_fields(self):
        ep = make_evidence_packet()
        assert ep.child_id
        assert ep.review_period_id
        assert ep.review_period_start
        assert ep.review_period_end
        assert ep.structured_records
        assert ep.record_ids
        assert ep.record_versions
        assert ep.adequacy
        assert ep.observation_count > 0

    def test_record_ids_match_records(self):
        records = [make_record_dict() for _ in range(5)]
        ep = make_evidence_packet(records=records)
        assert len(ep.record_ids) == len(records)
        for rec in records:
            assert rec["_record_id"] in ep.record_ids

    def test_record_versions_track_all(self):
        records = [make_record_dict(version=i + 1) for i in range(3)]
        ep = make_evidence_packet(records=records)
        for rec in records:
            assert ep.record_versions[rec["_record_id"]] == rec["_version"]


class TestEvidenceTraceability:
    def test_analytics_embedded_in_packet(self):
        ep = make_evidence_packet()
        assert ep.analytics is not None
        assert len(ep.analytics.kpis) > 0

    def test_adequacy_embedded_in_packet(self):
        ep = make_evidence_packet()
        assert ep.adequacy.level == AdequacyLevel.ADEQUATE
        assert ep.adequacy.eligible

    def test_quality_flags_from_adequacy(self):
        adequacy = make_adequate_result()
        adequacy.quality_flags = ["coverage: Only 3/5 observations received"]
        ep = make_evidence_packet(adequacy=adequacy)
        assert len(ep.quality_flags) == 1
        assert "coverage" in ep.quality_flags[0]


class TestContributorAndSettingSummary:
    def test_contributor_summary_populated(self):
        ep = make_evidence_packet()
        assert "parent" in ep.contributor_summary
        assert ep.contributor_summary["parent"] > 0

    def test_setting_summary_populated(self):
        ep = make_evidence_packet()
        assert "home" in ep.setting_summary

    def test_counts_match_observations(self):
        ep = make_evidence_packet()
        total_contrib = sum(ep.contributor_summary.values())
        total_setting = sum(ep.setting_summary.values())
        assert total_contrib == ep.observation_count
        assert total_setting == ep.observation_count


class TestPacketSerialization:
    def test_roundtrip_json(self):
        ep = make_evidence_packet()
        json_data = ep.model_dump(mode="json")
        restored = EvidencePacket.model_validate(json_data)
        assert restored.child_id == ep.child_id
        assert restored.observation_count == ep.observation_count
        assert len(restored.record_ids) == len(ep.record_ids)

    def test_no_raw_records_in_packet_json(self):
        ep = make_evidence_packet()
        json_data = ep.model_dump(mode="json")
        for rec in json_data["structured_records"]:
            assert "_record_id" in rec
            assert "_version" in rec
