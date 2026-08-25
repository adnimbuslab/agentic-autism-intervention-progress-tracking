"""Tests for Phase 4 safety constraints and deterministic invariants."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from src.backend.ml.adequacy_router import AdequacyRouter
from src.backend.ml.analytics_engine import AnalyticsEngine
from src.backend.ml.reporting_client import PROHIBITED_PATTERNS, validate_report
from src.backend.ml.schemas import (
    AdequacyLevel,
    ReportSection,
)
from tests.phase4.conftest import make_adequate_result, make_evidence_packet, make_record_dict


class TestAnalyticsDeterminism:
    """Analytics must produce identical results for identical inputs."""

    def test_same_input_same_output(self):
        engine = AnalyticsEngine()
        records = [make_record_dict() for _ in range(5)]
        adequacy = make_adequate_result()

        result1 = engine.compute("c1", "rp1", records, adequacy)
        result2 = engine.compute("c1", "rp1", records, adequacy)

        assert len(result1.kpis) == len(result2.kpis)
        for k1, k2 in zip(result1.kpis, result2.kpis):
            assert k1.name == k2.name
            assert k1.value == k2.value
            assert k1.numerator == k2.numerator
            assert k1.denominator == k2.denominator

    def test_adequacy_deterministic(self):
        router = AdequacyRouter()
        records = [make_record_dict() for _ in range(5)]
        r1 = router.assess(records, [], date(2026, 6, 1), date(2026, 6, 30))
        r2 = router.assess(records, [], date(2026, 6, 1), date(2026, 6, 30))
        assert r1.level == r2.level
        assert r1.eligible == r2.eligible
        assert r1.quality_flags == r2.quality_flags


class TestAnalyticsNeverLLM:
    """All KPIs must be computed by code, never by LLM."""

    def test_no_llm_imports_in_analytics_engine(self):
        import inspect
        from src.backend.ml import analytics_engine

        source = inspect.getsource(analytics_engine)
        assert "anthropic" not in source
        assert "openai" not in source
        assert "langchain" not in source

    def test_no_llm_imports_in_adequacy_router(self):
        import inspect
        from src.backend.ml import adequacy_router

        source = inspect.getsource(adequacy_router)
        assert "anthropic" not in source
        assert "openai" not in source
        assert "langchain" not in source


class TestReportSafetyPatterns:
    """Prohibited patterns must catch unsafe language."""

    @pytest.mark.parametrize("text", [
        "The child was diagnosed with autism.",
        "We recommend therapy twice weekly.",
        "The improvement was caused by autism intervention.",
        "The child has a deficit in social skills.",
        "The prognosis for communication is favorable.",
        "Results are abnormal for this age group.",
        "You should change the goal to focus on verbal skills.",
    ])
    def test_prohibited_text_detected(self, text):
        sections = [ReportSection(heading="Test", body=text)]
        ep = make_evidence_packet()
        errors = validate_report(sections, ep)
        assert len(errors) > 0, f"Should have flagged: {text}"

    @pytest.mark.parametrize("text", [
        "Observations indicate improvement in requesting behavior.",
        "Records show 80% positive outcome rate across the review period.",
        "Evidence was collected from home and school settings.",
        "The observation count was 5 for this period.",
    ])
    def test_safe_text_passes(self, text):
        sections = [ReportSection(heading="Test", body=text)]
        ep = make_evidence_packet()
        errors = validate_report(sections, ep)
        assert len(errors) == 0, f"Should not have flagged: {text}"


class TestAdequacyGating:
    """Insufficient adequacy must prevent analytics and force abstention."""

    def test_insufficient_blocks_analytics(self):
        engine = AnalyticsEngine()
        from src.backend.ml.schemas import AdequacyResult

        inadequate = AdequacyResult(
            level=AdequacyLevel.INSUFFICIENT,
            eligible=False,
            checks=[],
        )
        result = engine.compute("c1", "rp1", [], inadequate)
        assert len(result.kpis) == 1
        assert result.kpis[0].abstained

    def test_limited_allows_analytics(self):
        engine = AnalyticsEngine()
        from src.backend.ml.schemas import AdequacyResult

        limited = AdequacyResult(
            level=AdequacyLevel.LIMITED,
            eligible=True,
            checks=[],
        )
        records = [make_record_dict() for _ in range(3)]
        result = engine.compute("c1", "rp1", records, limited)
        assert len(result.kpis) > 1


class TestCurrentVersionRecordSelection:
    """Corrected records must supersede prior versions — no double-counting."""

    def test_only_latest_version_counted(self):
        engine = AnalyticsEngine()
        obs_id = str(uuid.uuid4())
        v1 = make_record_dict(obs_id=obs_id, version=1, outcome="incorrect")
        v2 = make_record_dict(obs_id=obs_id, version=2, outcome="correct")
        other = make_record_dict(version=1, outcome="correct")

        records = [v2, other]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        count_kpi = next(k for k in result.kpis if k.name == "observation_count")
        assert count_kpi.value == 2.0


class TestAbstentionAsFirstClass:
    """Abstention must be a first-class output, not silently omitted."""

    def test_abstained_kpi_has_reason(self):
        engine = AnalyticsEngine()
        records = [make_record_dict(prompt_level=None) for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        indep = next(k for k in result.kpis if k.name == "independence_rate")
        assert indep.abstained
        assert indep.abstention_reason is not None
        assert len(indep.abstention_reason) > 0

    def test_partial_abstention_in_adequacy(self):
        router = AdequacyRouter()
        records = [make_record_dict() for _ in range(5)]
        result = router.assess(records, [], date(2026, 6, 1), date(2026, 6, 30))
        if result.partial_abstentions:
            for key, reason in result.partial_abstentions.items():
                assert len(reason) > 0


class TestEdgeCases:
    def test_unknown_outcome_excluded(self):
        engine = AnalyticsEngine()
        records = [make_record_dict(outcome="unknown") for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        rate_kpi = next(k for k in result.kpis if k.name == "positive_outcome_rate")
        assert rate_kpi.abstained

    def test_missing_dates_handled(self):
        engine = AnalyticsEngine()
        records = [make_record_dict(observation_date=None) for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        trend = next(k for k in result.kpis if k.name == "prompt_support_trend")
        assert trend.abstained

    def test_empty_records_handled(self):
        router = AdequacyRouter()
        result = router.assess([], [], date(2026, 6, 1), date(2026, 6, 30))
        assert result.level == AdequacyLevel.INSUFFICIENT
