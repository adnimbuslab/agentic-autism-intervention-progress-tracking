# Goal-Attainment Forecasting (Phase 1) — EARS Specs

Owning design: [Goal_Attainment_Forecasting.md](./Goal_Attainment_Forecasting.md). Prefix: `FORECAST`.

Scope note: these specs cover **Phase 1 only** — the deterministic, no-ML trajectory
projection in `src/backend/ml/forecasting_engine.py`. Phase 2 (the ML model
comparison ladder) is explicitly gated on dataset adequacy in the owning LLD
and has no specs here; do not add `FORECAST` IDs for it until that gate is
cleared by an explicit decision, not by default.

All specs below are `[x]` — implemented and covered by `tests/phase4/test_forecasting_engine.py`.

## Invariant

- [x] **FORECAST-001**: The system shall compute the Phase 1 trajectory projection using deterministic arithmetic only; no ML model and no LLM shall be invoked by this component.

## Abstention Pass-Through

- [x] **FORECAST-002**: If either the supplied trend KPI or the supplied current-value KPI is `abstained`, then the system shall abstain the forecast, citing the upstream abstention reason, rather than forcing a projection. This component does not recompute or override the Analytics Engine's per-KPI abstention discipline (see [Analytics_Engine_Specs.md](./Analytics_Engine_Specs.md) ANALYTICS-010 through ANALYTICS-015).

## Unit Conversion

- [x] **FORECAST-003**: The system shall express the trend KPI's delta as a per-week slope by dividing it by the elapsed weeks between the review period's `start` and `end` dates. This is a unit conversion of an already-computed quantity, not a new statistical quantity, per the owning LLD's "no additional modeling machinery" constraint.

## Already-Met State

- [x] **FORECAST-004**: If the current-value KPI's value is already at or above `target_threshold`, then the system shall report `already_met=true` and shall not compute a forward projection, unless FORECAST-002 already applies.

## Abstention on Non-Convergent Trend

- [x] **FORECAST-005**: If the per-week slope is zero or negative while the threshold has not yet been met, then the system shall abstain rather than assert a crossing date, unless FORECAST-002 or FORECAST-004 already applies.

## Crossing-Time Projection

- [x] **FORECAST-006**: Where none of FORECAST-002, FORECAST-004, or FORECAST-005 apply, the system shall compute `projected_weeks_to_threshold` as `(target_threshold - current_value) / slope_per_week` and `projected_crossing_date` as the review period's `end` date plus that many weeks.

## Uncertainty Band Deferral

- [x] **FORECAST-007**: The system shall leave `attainment_window` unset (`None`) in Phase 1 rather than fabricate an uncertainty-quantification method, since that method is an explicitly undefined open question in the owning LLD (Open Question #4). This spec documents a deliberate abstention on that field, not a missing feature to silently fill in later without a decision.

## Caveat

- [x] **FORECAST-008**: Every `GoalForecastResult`, regardless of outcome branch (already-met, abstained, or projected), shall carry a fixed caveat string stating the result is a trajectory estimate conditional on the recent trend, not a committed prediction or clinical outcome.

## Deferred (not in scope here — see owning LLD)

- Phase 2 ML model ladder (linear/logistic regression → Random Forest → XGBoost → temporal model): gated on a dataset-size threshold the owning LLD's Open Questions leaves undefined. Not to be built speculatively ahead of that decision.
- `target_threshold` is accepted as an explicit caller-supplied parameter rather than sourced from the `Goal` ORM model — `Goal` currently has no numeric threshold field (only free-text `criteria` and a `target_date`). Wiring a real threshold into the Goal Registry (schema + migration + API + frontend) is a separate, larger change outside this component's boundary; see the owning LLD's Decisions & Alternatives table.
- No API endpoint or report-service wiring is specced here. `ForecastingEngine.forecast()` sits at the same boundary as `AnalyticsEngine.compute()` and `AdequacyRouter.assess()` — a pure function callers assemble inputs for — and its integration into `report_service.py`/an API route is a follow-on, separately specced change.

## References

- [Goal_Attainment_Forecasting.md](./Goal_Attainment_Forecasting.md) — full design, Phase 1/Phase 2 split, required graph elements, and open questions.
- [Analytics_Engine_Specs.md](./Analytics_Engine_Specs.md) — upstream KPI/abstention source (ANALYTICS-014/015 produce the trend KPIs this component projects).
- `src/backend/ml/forecasting_engine.py`, `src/backend/ml/schemas.py` (`GoalForecastResult`).
- Tests: `tests/phase4/test_forecasting_engine.py`.
