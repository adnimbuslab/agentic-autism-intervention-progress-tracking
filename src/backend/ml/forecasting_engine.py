"""Goal-Attainment Forecasting -- Phase 1 (deterministic trajectory only).

No ML model. Projects an existing Analytics Engine trend KPI's delta forward
to an interventionist-defined target threshold, expressed as elapsed weeks
using the review period's own date span. Introduces no new statistical
quantity beyond that delta -- see docs/lld/Goal_Attainment_Forecasting.md.

Phase 2 (ML forecasting ladder: linear/logistic regression -> Random Forest ->
XGBoost -> temporal model) is explicitly gated on dataset adequacy in the
owning LLD and is NOT implemented here -- see that document's "Phase 2" and
"Open Questions" sections before adding it.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.backend.ml.schemas import GoalForecastResult, KpiResult

_MIN_REVIEW_PERIOD_WEEKS = 1e-6  # guards against a zero/negative-length period


class ForecastingEngine:
    """Pure, deterministic Phase 1 trajectory projection. No LLM, no ORM
    access -- callers supply already-computed KPIs and the goal's threshold,
    mirroring how AnalyticsEngine/AdequacyRouter take plain data in and
    return a Pydantic result, not reaching into models themselves."""

    # @spec FORECAST-001, FORECAST-002, FORECAST-003, FORECAST-004, FORECAST-005, FORECAST-006, FORECAST-007, FORECAST-008
    def forecast(
        self,
        *,
        goal_id: str | None,
        trend_kpi: KpiResult,
        current_value_kpi: KpiResult,
        target_threshold: float,
        review_period_start: str,
        review_period_end: str,
    ) -> GoalForecastResult:
        """Project ``trend_kpi``'s delta forward to ``target_threshold``.

        ``trend_kpi`` is expected to be ``prompt_support_trend`` or
        ``outcome_trend`` from AnalyticsResult; ``current_value_kpi`` is the
        corresponding rate KPI (``independence_rate`` / ``positive_outcome_rate``)
        those trends are deltas of.
        """
        base = dict(
            goal_id=goal_id,
            kpi_name=trend_kpi.name,
            target_threshold=target_threshold,
        )

        # FORECAST-002: a forecast is never computed for a KPI the Analytics
        # Engine has already abstained on -- this component does not
        # override or second-guess that per-KPI abstention discipline.
        if trend_kpi.abstained or current_value_kpi.abstained:
            reason = trend_kpi.abstention_reason or current_value_kpi.abstention_reason
            return GoalForecastResult(
                **base,
                abstained=True,
                abstention_reason=(
                    "Upstream KPI abstained; no forecast is computed for a "
                    f"KPI the Analytics Engine has already abstained on: {reason}"
                ),
            )

        current_value = current_value_kpi.value
        slope_per_review_period = trend_kpi.value
        if current_value is None or slope_per_review_period is None:
            return GoalForecastResult(
                **base,
                abstained=True,
                abstention_reason="Upstream KPI has no value to project from.",
            )

        # FORECAST-003: express the delta as a per-week slope using the
        # review period's own real date span -- a unit conversion of an
        # already-computed quantity, not a new statistical quantity.
        start = date.fromisoformat(review_period_start)
        end = date.fromisoformat(review_period_end)
        weeks_elapsed = max((end - start).days / 7.0, _MIN_REVIEW_PERIOD_WEEKS)
        slope_per_week = slope_per_review_period / weeks_elapsed

        # FORECAST-004: threshold already met is a factual statement about
        # current standing, not a forward-looking projection.
        gap = target_threshold - current_value
        if gap <= 0:
            return GoalForecastResult(
                **base,
                current_value=current_value,
                slope_per_week=round(slope_per_week, 6),
                already_met=True,
            )

        # FORECAST-005: abstain rather than assert a crossing date when the
        # current trend is flat or moving away from the threshold.
        if slope_per_week <= 0:
            return GoalForecastResult(
                **base,
                current_value=current_value,
                slope_per_week=round(slope_per_week, 6),
                abstained=True,
                abstention_reason=(
                    "Current trend is flat or moving away from the threshold; "
                    "no crossing time is projected."
                ),
            )

        # FORECAST-006: linear crossing-time projection.
        projected_weeks = gap / slope_per_week
        projected_date = end + timedelta(weeks=projected_weeks)

        # FORECAST-007: attainment_window (the chart's uncertainty band) is
        # intentionally left unset -- Open Question #4 in the owning LLD
        # leaves the uncertainty-quantification method undefined. Abstaining
        # on it here rather than fabricating a band follows the same
        # "abstain over assert" discipline applied to the point estimate.
        # (FORECAST-008's caveat string is applied via GoalForecastResult's
        # own field default -- every branch above and below carries it.)
        return GoalForecastResult(
            **base,
            current_value=current_value,
            slope_per_week=round(slope_per_week, 6),
            projected_weeks_to_threshold=round(projected_weeks, 2),
            projected_crossing_date=projected_date.isoformat(),
        )
