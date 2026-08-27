# Adequacy Router (batch) — EARS Specs

Owning design: [Adequacy_Router.md](./Adequacy_Router.md). Prefix: `ADEQ`.

Do not confuse with `ABSTAIN` ([Abstention_Router_Specs.md](./Abstention_Router_Specs.md)) — that is the real-time, per-observation sibling.

All specs below are `[x]` — implemented, covered by `tests/phase4/test_adequacy_router.py`, `tests/phase6/integration/test_adequacy_analytics_e2e.py`, `tests/phase4/test_safety_validation.py`.

## Invariant

- [x] **ADEQ-001**: The system shall assess adequacy using six deterministic checks — coverage, temporal distribution, contributor representation, setting representation, goal coverage, and field completeness — without invoking any LLM.

## Adequacy Level (priority order — first match wins)

- [x] **ADEQ-010**: If the record count for the review period is 0, then the system shall set `AdequacyLevel` to `INSUFFICIENT`.
- [x] **ADEQ-011**: If the coverage check or the field-completeness check fails, then the system shall set `AdequacyLevel` to `INSUFFICIENT` when the record count is less than 3, or `LIMITED` when the record count is 3 or more, unless ADEQ-010 already applies.
- [x] **ADEQ-012**: If more than 2 of the six checks fail, then the system shall set `AdequacyLevel` to `LIMITED`, unless ADEQ-010 or ADEQ-011 already applies.
- [x] **ADEQ-013**: If the record count is less than 3, then the system shall set `AdequacyLevel` to `LIMITED`, unless ADEQ-010 or ADEQ-011 already applies.
- [x] **ADEQ-014**: If the record count is 5 or more and zero checks fail, then the system shall set `AdequacyLevel` to `ADEQUATE`.
- [x] **ADEQ-015**: Where none of ADEQ-010 through ADEQ-014 apply, the system shall set `AdequacyLevel` to `LIMITED`.
- [x] **ADEQ-016**: The system shall set `AdequacyResult.eligible` to `false` only when `AdequacyLevel` is `INSUFFICIENT`, and to `true` for `LIMITED` or `ADEQUATE`.

## Per-Check Logic

- [x] **ADEQ-020**: The coverage check shall pass only if the record count is at least `expected_observation_count` when supplied, or `adequacy_min_observations` (5) otherwise.
- [x] **ADEQ-021**: While fewer than 2 records exist, the temporal-distribution check shall pass only if the record count is 0.
- [x] **ADEQ-022**: When 2 or more records exist, the temporal-distribution check shall pass only if the fraction of records sharing the most common single observation date does not exceed `adequacy_temporal_cluster_max_ratio` (0.8).
- [x] **ADEQ-023**: The contributor-representation check shall pass only if at least 2 distinct `contributor_role` values are present among the records.
- [x] **ADEQ-024**: The setting-representation check shall pass only if at least 2 distinct `setting` values are present among the records.
- [x] **ADEQ-025**: Where no goals are supplied, the goal-coverage check shall pass automatically; where goals are supplied, it shall pass only if the fraction of goal domains represented in the records is at least 0.5.
- [x] **ADEQ-026**: The field-completeness check shall pass only if, across the `behavior`, `domain`, and `outcome` fields over all records, the fraction of values that are neither null nor the string `"unknown"` is at least `adequacy_field_completeness_threshold` (0.7).

## Partial Abstentions

- [x] **ADEQ-030**: When the contributor-representation check fails, the system shall record a partial-abstention reason keyed `cross_contributor_comparison` in `AdequacyResult.partial_abstentions`.
- [x] **ADEQ-031**: When the setting-representation check fails, the system shall record a partial-abstention reason keyed `cross_setting_comparison` in `AdequacyResult.partial_abstentions`.

## References

- [Adequacy_Router.md](./Adequacy_Router.md) — full design, decisions, and the string-key coupling open question (ADEQ-030/031's exact key names are load-bearing for [Analytics_Engine_Specs.md](./Analytics_Engine_Specs.md)'s ANALYTICS-020/021 — a rename here breaks those without a type-checker signal).
