"""Tests for AnalyticsEngine — deterministic KPI computation."""

from __future__ import annotations

import pytest

from src.backend.ml.analytics_engine import AnalyticsEngine
from src.backend.ml.schemas import AdequacyLevel, AdequacyResult, KpiResult
from tests.phase4.conftest import make_adequate_result, make_record_dict


@pytest.fixture
def engine() -> AnalyticsEngine:
    return AnalyticsEngine()


def _kpi(result, name: str) -> KpiResult:
    return next(k for k in result.kpis if k.name == name)


class TestInsufficientAdequacy:
    def test_returns_single_abstained_kpi(self, engine: AnalyticsEngine):
        adequacy = AdequacyResult(
            level=AdequacyLevel.INSUFFICIENT,
            eligible=False,
            checks=[],
        )
        result = engine.compute("child1", "rp1", [], adequacy)
        assert len(result.kpis) == 1
        assert result.kpis[0].abstained
        assert "insufficient" in result.kpis[0].abstention_reason.lower()

    def test_no_records_insufficient(self, engine: AnalyticsEngine):
        adequacy = AdequacyResult(
            level=AdequacyLevel.INSUFFICIENT,
            eligible=False,
            checks=[],
        )
        result = engine.compute("child1", "rp1", [], adequacy)
        assert result.kpis[0].name == "all_analytics"


class TestObservationCount:
    def test_correct_count(self, engine: AnalyticsEngine):
        records = [make_record_dict() for _ in range(7)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "observation_count")
        assert kpi.value == 7.0


class TestIndependenceRate:
    def test_all_independent(self, engine: AnalyticsEngine):
        records = [make_record_dict(prompt_level="independent") for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "independence_rate")
        assert kpi.value == 1.0

    def test_mixed(self, engine: AnalyticsEngine):
        records = [make_record_dict(prompt_level="independent") for _ in range(3)]
        records += [make_record_dict(prompt_level="verbal_prompt") for _ in range(2)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "independence_rate")
        assert kpi.value == 0.6

    def test_no_prompt_data_abstains(self, engine: AnalyticsEngine):
        records = [make_record_dict(prompt_level=None) for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "independence_rate")
        assert kpi.abstained


class TestPositiveOutcomeRate:
    def test_all_correct(self, engine: AnalyticsEngine):
        records = [make_record_dict(outcome="correct") for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "positive_outcome_rate")
        assert kpi.value == 1.0

    def test_mixed_outcomes(self, engine: AnalyticsEngine):
        records = [
            make_record_dict(outcome="correct"),
            make_record_dict(outcome="correct"),
            make_record_dict(outcome="approximation"),
            make_record_dict(outcome="incorrect"),
            make_record_dict(outcome="no_response"),
        ]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "positive_outcome_rate")
        assert kpi.value == 0.6

    def test_no_outcome_data_abstains(self, engine: AnalyticsEngine):
        records = [make_record_dict(outcome=None) for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "positive_outcome_rate")
        assert kpi.abstained


class TestMissingDataRate:
    def test_complete_data_zero_rate(self, engine: AnalyticsEngine):
        records = [make_record_dict() for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "missing_data_rate")
        assert kpi.value == 0.0

    def test_partially_missing(self, engine: AnalyticsEngine):
        records = [make_record_dict() for _ in range(3)]
        records.append(make_record_dict(behavior=None, domain=None, outcome=None))
        records.append(make_record_dict(behavior=None))
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "missing_data_rate")
        assert kpi.value > 0


class TestTrends:
    def test_prompt_trend_needs_four_records(self, engine: AnalyticsEngine):
        records = [make_record_dict() for _ in range(3)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "prompt_support_trend")
        assert kpi.abstained

    def test_prompt_trend_computed_with_four(self, engine: AnalyticsEngine):
        records = [
            make_record_dict(prompt_level="verbal_prompt", observation_date="2026-06-01"),
            make_record_dict(prompt_level="verbal_prompt", observation_date="2026-06-05"),
            make_record_dict(prompt_level="independent", observation_date="2026-06-15"),
            make_record_dict(prompt_level="independent", observation_date="2026-06-20"),
        ]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "prompt_support_trend")
        assert not kpi.abstained
        assert kpi.value == 1.0

    def test_outcome_trend_needs_four_records(self, engine: AnalyticsEngine):
        records = [make_record_dict() for _ in range(3)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "outcome_trend")
        assert kpi.abstained

    def test_outcome_trend_computed(self, engine: AnalyticsEngine):
        records = [
            make_record_dict(outcome="incorrect", observation_date="2026-06-01"),
            make_record_dict(outcome="incorrect", observation_date="2026-06-05"),
            make_record_dict(outcome="correct", observation_date="2026-06-15"),
            make_record_dict(outcome="correct", observation_date="2026-06-20"),
        ]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "outcome_trend")
        assert not kpi.abstained
        assert kpi.value == 1.0


class TestCrossComparisons:
    def test_cross_setting_abstains_when_partial(self, engine: AnalyticsEngine):
        adequacy = AdequacyResult(
            level=AdequacyLevel.LIMITED,
            eligible=True,
            checks=[],
            partial_abstentions={"cross_setting_comparison": "Single setting only"},
        )
        records = [make_record_dict() for _ in range(5)]
        result = engine.compute("c1", "rp1", records, adequacy)
        kpi = _kpi(result, "cross_setting_comparison")
        assert kpi.abstained

    def test_cross_contributor_abstains_when_partial(self, engine: AnalyticsEngine):
        adequacy = AdequacyResult(
            level=AdequacyLevel.LIMITED,
            eligible=True,
            checks=[],
            partial_abstentions={"cross_contributor_comparison": "Single contributor"},
        )
        records = [make_record_dict() for _ in range(5)]
        result = engine.compute("c1", "rp1", records, adequacy)
        kpi = _kpi(result, "cross_contributor_comparison")
        assert kpi.abstained

    def test_cross_setting_computed_when_diverse(self, engine: AnalyticsEngine):
        records = [make_record_dict(setting="home") for _ in range(3)]
        records += [make_record_dict(setting="school") for _ in range(2)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        kpi = _kpi(result, "cross_setting_comparison")
        assert not kpi.abstained
        assert kpi.value == 2.0


class TestKpiCount:
    def test_adequate_produces_14_kpis(self, engine: AnalyticsEngine):
        records = [make_record_dict() for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        assert len(result.kpis) == 14

    def test_all_kpi_names_unique(self, engine: AnalyticsEngine):
        records = [make_record_dict() for _ in range(5)]
        result = engine.compute("c1", "rp1", records, make_adequate_result())
        names = [k.name for k in result.kpis]
        assert len(names) == len(set(names))
