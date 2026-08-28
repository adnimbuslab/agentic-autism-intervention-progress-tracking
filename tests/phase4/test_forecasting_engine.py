"""Tests for ForecastingEngine -- Phase 1 deterministic trajectory projection.

Phase 2 (ML forecasting ladder) is explicitly out of scope -- see
docs/lld/Goal_Attainment_Forecasting.md and
docs/lld/Goal_Attainment_Forecasting_Specs.md.
"""

from __future__ import annotations

import pytest

from src.backend.ml.forecasting_engine import ForecastingEngine
from src.backend.ml.schemas import KpiResult


@pytest.fixture
def engine() -> ForecastingEngine:
    return ForecastingEngine()


def _trend_kpi(value: float | None = 0.09, abstained: bool = False, reason: str | None = None) -> KpiResult:
    return KpiResult(
        name="outcome_trend",
        numerator=0.0,
        denominator=0.0,
        value=value,
        abstained=abstained,
        abstention_reason=reason,
    )


def _current_value_kpi(value: float | None = 0.62, abstained: bool = False, reason: str | None = None) -> KpiResult:
    return KpiResult(
        name="positive_outcome_rate",
        numerator=0.0,
        denominator=0.0,
        value=value,
        abstained=abstained,
        abstention_reason=reason,
    )


class TestNoLLMInvariant:
    # @spec FORECAST-001
    def test_no_llm_imports_in_forecasting_engine(self):
        import inspect

        from src.backend.ml import forecasting_engine

        source = inspect.getsource(forecasting_engine)
        assert "anthropic" not in source
        assert "openai" not in source
        assert "langchain" not in source

    # @spec FORECAST-001
    def test_deterministic(self, engine: ForecastingEngine):
        kwargs = dict(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.09),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        r1 = engine.forecast(**kwargs)
        r2 = engine.forecast(**kwargs)
        assert r1 == r2


class TestAbstentionPassThrough:
    # @spec FORECAST-002
    def test_abstains_when_trend_kpi_abstained(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(None, abstained=True, reason="Insufficient data for trend"),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.abstained is True
        assert "Insufficient data for trend" in result.abstention_reason
        assert result.projected_weeks_to_threshold is None

    # @spec FORECAST-002
    def test_abstains_when_current_value_kpi_abstained(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.09),
            current_value_kpi=_current_value_kpi(None, abstained=True, reason="No records with outcome data"),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.abstained is True
        assert "No records with outcome data" in result.abstention_reason


class TestUnitConversion:
    # @spec FORECAST-003
    def test_slope_per_week_matches_worked_example(self, engine: ForecastingEngine):
        # LLD worked example: threshold=80%, current=62%, slope=+4.5pp/week -> ~4 weeks.
        # 0.09 delta over a 2-week review period = 0.045/week.
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.09),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.slope_per_week == pytest.approx(0.045)

    # @spec FORECAST-003
    def test_zero_length_period_does_not_divide_by_zero(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.09),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-01",
        )
        assert result.slope_per_week is not None


class TestAlreadyMet:
    # @spec FORECAST-004
    def test_already_met_when_current_value_above_threshold(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.05),
            current_value_kpi=_current_value_kpi(0.85),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.already_met is True
        assert result.abstained is False
        assert result.projected_weeks_to_threshold is None

    # @spec FORECAST-004
    def test_already_met_when_current_value_equals_threshold(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.05),
            current_value_kpi=_current_value_kpi(0.80),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.already_met is True


class TestNonConvergentTrend:
    # @spec FORECAST-005
    def test_abstains_when_slope_flat(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.0),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.abstained is True
        assert "flat or moving away" in result.abstention_reason
        assert result.projected_weeks_to_threshold is None

    # @spec FORECAST-005
    def test_abstains_when_slope_negative(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(-0.05),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.abstained is True
        assert result.projected_weeks_to_threshold is None


class TestCrossingTimeProjection:
    # @spec FORECAST-006
    def test_projected_weeks_matches_worked_example(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.09),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.abstained is False
        assert result.already_met is False
        assert result.projected_weeks_to_threshold == pytest.approx(4.0)
        assert result.projected_crossing_date == "2026-07-13"


class TestUncertaintyBandDeferral:
    # @spec FORECAST-007
    def test_attainment_window_left_unset_on_projection(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.09),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.attainment_window is None

    # @spec FORECAST-007
    def test_attainment_window_left_unset_when_abstained(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(0.0),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.attainment_window is None


class TestCaveat:
    # @spec FORECAST-008
    @pytest.mark.parametrize(
        "trend_value, current_value, threshold",
        [
            (0.09, 0.62, 0.80),  # projected
            (0.05, 0.85, 0.80),  # already met
            (0.0, 0.62, 0.80),  # abstained (flat trend)
        ],
    )
    def test_caveat_present_on_every_branch(
        self, engine: ForecastingEngine, trend_value, current_value, threshold,
    ):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(trend_value),
            current_value_kpi=_current_value_kpi(current_value),
            target_threshold=threshold,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.caveat
        assert "not a committed prediction" in result.caveat

    # @spec FORECAST-008
    def test_caveat_present_when_upstream_abstained(self, engine: ForecastingEngine):
        result = engine.forecast(
            goal_id="g1",
            trend_kpi=_trend_kpi(None, abstained=True, reason="Insufficient data"),
            current_value_kpi=_current_value_kpi(0.62),
            target_threshold=0.80,
            review_period_start="2026-06-01",
            review_period_end="2026-06-15",
        )
        assert result.caveat
