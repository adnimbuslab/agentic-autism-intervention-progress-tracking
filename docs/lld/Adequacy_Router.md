---
parent: high-level-design
prefix: ADEQ
---

# Adequacy Router (batch)

*Brownfield LLD — reverse-engineered from `src/backend/ml/adequacy_router.py` and `src/backend/config.py`. Decisions marked `[inferred]` were observed in code, not confirmed by the author.*

## Context and Design Philosophy

Module docstring: "deterministic evidence sufficiency checks... All logic is pure Python. No LLM involvement." This component answers a different question from the real-time [Abstention Router](./Abstention_Router.md): not "is this one observation usable?" but "is the accumulated evidence for a child, across a review period, sufficient and representative enough to support analytics at all?" It is the gate at the front of the **batch analytics/reporting pipeline** — `AdequacyRouter → AnalyticsEngine → ReportingClient` — which is architecturally separate from the real-time ingestion pipeline (`ExtractionProvider → ValidationEngine → AbstentionRouter`); it consumes many already-persisted, already-validated records at once rather than one observation at ingestion time. This is the concrete implementation of CLAUDE.md's "Abstention is a first-class output when evidence is inadequate" and "Analytics MUST be withheld when adequacy checks fail — never force a conclusion."

## Interface Contract

```text
AdequacyRouter.assess(
    records: list[dict],
    goals: list[dict],
    review_start: date,
    review_end: date,
    expected_observation_count: int | None = None,
) -> AdequacyResult
```

`AdequacyResult` carries a `level: AdequacyLevel` (`INSUFFICIENT` | `LIMITED` | `ADEQUATE`), an `eligible: bool` gate consumed directly by `AnalyticsEngine`, per-check pass/fail detail, and a `partial_abstentions` dict keyed by named reason strings.

## Checks (all six always run)

`COVERAGE`, `TEMPORAL_DISTRIBUTION`, `CONTRIBUTOR_REPRESENTATION`, `SETTING_REPRESENTATION`, `GOAL_COVERAGE`, `FIELD_COMPLETENESS`.

Two additional `AdequacyCheck` enum values, `CONSISTENCY` and `TIMELINESS`, exist but are never invoked — reserved or dead (see Open Questions).

### Thresholds (`src/backend/config.py`)

| Constant | Value |
|---|---|
| `adequacy_min_observations` | 5 |
| `adequacy_limited_observations` | 3 |
| `adequacy_field_completeness_threshold` | 0.7 |
| `adequacy_temporal_cluster_max_ratio` | 0.8 |

### Per-check logic (exact)

- **Coverage**: `count >= (expected_observation_count or adequacy_min_observations)`.
- **Temporal distribution**: fewer than 2 records passes only if the record count is 0; otherwise passes iff `max_same_day_count / distinct_date_count <= 0.8`.
- **Contributor representation**: passes iff ≥2 distinct `contributor_role` values are present.
- **Setting representation**: passes iff ≥2 distinct `setting` values are present.
- **Goal coverage**: passes automatically if no goals are defined; otherwise `|goal_domains ∩ record_domains| / |goal_domains| >= 0.5`.
- **Field completeness**: over `{behavior, domain, outcome}` × records — a value counts as present only if it is neither `None` nor the literal string `"unknown"` — passes iff `present / total >= 0.7`.

## Level Computation (`_compute_level`, exact order)

1. 0 records → **INSUFFICIENT**.
2. Critical checks = `{COVERAGE, FIELD_COMPLETENESS}`; if either fails: **INSUFFICIENT** if `record_count < 3`, else **LIMITED**.
3. More than 2 failed checks (of any kind) → **LIMITED**.
4. `record_count < 3` → **LIMITED**.
5. `record_count >= 5` and zero failed checks → **ADEQUATE**.
6. Otherwise → **LIMITED**.

`eligible` (consumed by `AnalyticsEngine`) is true for any level except `INSUFFICIENT`.

## Partial Abstentions

When `CONTRIBUTOR_REPRESENTATION` or `SETTING_REPRESENTATION` fails, a keyed reason is recorded in `AdequacyResult.partial_abstentions`: `cross_contributor_comparison`, `cross_setting_comparison`. These exact string keys are read directly by name inside `AnalyticsEngine` — see Decisions below.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Adequacy assessed per review period, over the full accumulated record set | Batch assessment ahead of analytics computation | Assess adequacy incrementally as each observation is ingested | `[inferred]` Sufficiency (temporal spread, contributor/setting diversity) is a property of the *set*, not any single observation — it can only be evaluated once the period's records are assembled |
| Two-tier severity: `INSUFFICIENT` (blocks all analytics) vs. `LIMITED` (analytics run, with named partial abstentions) | Binary eligible/not-eligible plus a finer per-KPI partial-abstention channel | A single pass/fail gate with no partial output | `[inferred]` Matches the HLD tenet "abstain over assert" at KPI granularity rather than an all-or-nothing period-level cutoff — e.g. cross-setting comparison can be withheld while independence rate still displays |
| Partial-abstention reasons as string keys (`cross_setting_comparison`, `cross_contributor_comparison`) | Plain dict keys, consumed by exact string match in `AnalyticsEngine` | A shared enum or constant module between `AdequacyRouter` and `AnalyticsEngine` | `[inferred]` — no rationale evident in code; reads as incidental rather than deliberate. Flagged below as a fragility to address, not treated as a settled decision. |

## Open Questions & Future Decisions

### Deferred
1. **String-key coupling between `AdequacyRouter` and `AnalyticsEngine`.** `partial_abstentions` keys (`cross_setting_comparison`, `cross_contributor_comparison`) are matched by literal string in `AnalyticsEngine` rather than a shared enum. A rename in one file silently breaks the other with no type-checker signal. Consider a shared constant/enum.
2. `AdequacyCheck.CONSISTENCY` and `AdequacyCheck.TIMELINESS` are defined but never invoked. Confirm whether these are planned checks or should be removed.
3. Rename this component (and update the HLD diagram) to disambiguate from the real-time [Abstention_Router.md](./Abstention_Router.md) — both currently read as "the adequacy/abstention thing" from the HLD's single combined box label.

## References

- `src/backend/ml/adequacy_router.py`, `src/backend/config.py`.
- [Abstention_Router.md](./Abstention_Router.md) — the real-time, per-observation sibling this is often conflated with.
- [Analytics_Engine.md](./Analytics_Engine.md) — the consumer gated by `AdequacyResult.eligible`.
- `docs/High_Level_Design.md` § Tenets ("Abstain over assert").
- Tests: `tests/phase4/test_adequacy_router.py`, `tests/phase6/integration/test_adequacy_analytics_e2e.py`, `tests/phase4/test_safety_validation.py`.
