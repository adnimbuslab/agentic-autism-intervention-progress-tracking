# Analytics Engine — EARS Specs

Owning design: [Analytics_Engine.md](./Analytics_Engine.md). Prefix: `ANALYTICS`.

Test citations below reflect an actual `@spec`-annotation pass — all `[x]`, no coverage gaps found for this component.

## Top-Level Gate

- [x] **ANALYTICS-001**: If `AdequacyResult.eligible` is `false`, then the system shall return a single `KpiResult` named `all_analytics` with `abstained=true`, and shall not compute any other KPI. — `tests/phase4/test_analytics_engine.py::test_returns_single_abstained_kpi`
- [x] **ANALYTICS-002**: The system shall compute every KPI using deterministic code only; no KPI value shall be computed or asserted by an LLM. — `tests/phase4/test_safety_validation.py::test_no_llm_imports_in_analytics_engine`

## Per-KPI Abstention (each independent of ANALYTICS-001, evaluated only when eligible)

- [x] **ANALYTICS-010**: If zero records have a `prompt_level` value set, then the system shall abstain the `independence_rate` KPI. — `test_no_prompt_data_abstains`
- [x] **ANALYTICS-011**: When at least one record has `prompt_level` set, the system shall compute `independence_rate` as the count of records with `prompt_level="independent"` divided by the count of records with any `prompt_level` set. — `test_mixed`
- [x] **ANALYTICS-012**: If zero records have a non-`"unknown"` `outcome` value, then the system shall abstain the `positive_outcome_rate` KPI. — `test_no_outcome_data_abstains`, `test_safety_validation.py::test_unknown_outcome_excluded`
- [x] **ANALYTICS-013**: When at least one record has a non-`"unknown"` `outcome`, the system shall compute `positive_outcome_rate` as the fraction of such records whose `outcome` is `correct`, `approximation`, or `partial`. — `test_mixed_outcomes`
- [x] **ANALYTICS-014**: If fewer than 4 dated records carry the field relevant to a trend KPI (`prompt_support_trend` or `outcome_trend`), then the system shall abstain that trend KPI. — `test_prompt_trend_needs_four_records`, `test_outcome_trend_needs_four_records`
- [x] **ANALYTICS-015**: When at least 4 dated records carry the relevant field, the system shall compute the trend KPI value as the second-half rate minus the first-half rate, where the records are split chronologically in half. — `test_prompt_trend_computed_with_four`, `test_outcome_trend_computed`
- [x] **ANALYTICS-020**: If `AdequacyResult.partial_abstentions` contains the key `cross_setting_comparison`, then the system shall abstain the `cross_setting_comparison` KPI (see [Adequacy_Router_Specs.md](./Adequacy_Router_Specs.md) ADEQ-031 for the producing condition). — `test_cross_setting_abstains_when_partial`
- [x] **ANALYTICS-021**: If `AdequacyResult.partial_abstentions` contains the key `cross_contributor_comparison`, then the system shall abstain the `cross_contributor_comparison` KPI (see [Adequacy_Router_Specs.md](./Adequacy_Router_Specs.md) ADEQ-030 for the producing condition). — `test_cross_contributor_abstains_when_partial`
- [x] **ANALYTICS-022**: The system shall compute `missing_data_rate` over the `behavior`, `domain`, `modality`, `prompt_level`, and `outcome` fields, counting a value as missing when it is null or the string `"unknown"`. — `test_complete_data_zero_rate`, `test_partially_missing`

## References

- [Analytics_Engine.md](./Analytics_Engine.md) — full design, decisions, and the open question on `*_distribution` KPIs computing and then discarding per-category proportions (no spec covers exposing those proportions, since that behavior does not exist yet — see the LLD's Open Questions before adding one).
