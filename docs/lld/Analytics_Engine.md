---
parent: high-level-design
prefix: ANALYTICS
---

# Analytics Engine

*Brownfield LLD — reverse-engineered from `src/backend/ml/analytics_engine.py`. Decisions marked `[inferred]` were observed in code, not confirmed by the author.*

## Context and Design Philosophy

Module docstring: "all KPIs computed by code, never by LLM... deterministic and reproducible for identical inputs." This is the concrete implementation of CLAUDE.md's "All analytics computed by code, never by LLM." It sits after the [Adequacy Router](./Adequacy_Router.md) in the batch pipeline and runs only when the period's evidence has been judged eligible; its output (`AnalyticsResult`) is the sole numeric input the [Reporting LLM](./Reporting_Llm.md) is permitted to narrate — the reporting layer may describe these numbers but must never compute or invent its own.

## Interface Contract

```text
AnalyticsEngine.compute(
    child_id, review_period_id,
    records: list[dict],
    adequacy: AdequacyResult,
    goal_id: str | None = None,
) -> AnalyticsResult
```

`KpiResult`: `name`, `numerator`, `denominator`, `value`, `prerequisites_met`, `display_eligible`, `abstained`, `abstention_reason`.

`AnalyticsResult`: `child_id`, `review_period_id`, `goal_id`, `kpis: list[KpiResult]`, `adequacy`, `computed_at`.

## Top-Level Gate

If `adequacy.eligible` is false (i.e. `AdequacyLevel.INSUFFICIENT`), `compute()` returns a single `KpiResult(name="all_analytics", abstained=True, abstention_reason=f"Evidence level: {level}", prerequisites_met=False, display_eligible=False)` and computes nothing else. This is a total short-circuit — no partial KPI computation is attempted below the insufficiency floor.

## KPIs (computed in this order when eligible)

`observation_count`, `domain_distribution`, `modality_distribution`, `prompt_level_distribution`, `outcome_distribution`, `independence_rate`, `contributor_distribution`, `setting_distribution`, `missing_data_rate`, `positive_outcome_rate`, `prompt_support_trend`, `outcome_trend`, `cross_setting_comparison`, `cross_contributor_comparison`.

Each KPI carries its **own** abstention condition independent of the top-level gate — a period can be `eligible` overall while individual KPIs still abstain:

- **`independence_rate`** — abstains if zero records have `prompt_level` set; else `count(prompt_level == "independent") / count(has prompt_level)`.
- **`positive_outcome_rate`** — abstains if zero records have a non-`"unknown"` `outcome`; else positive = `outcome in {correct, approximation, partial}`.
- **`prompt_support_trend`** / **`outcome_trend`** — abstain if fewer than 4 dated records carry the relevant field; else the record set is split chronologically in half and `value = second_half_rate - first_half_rate` for the relevant rate. This first-half-vs-second-half delta is the entire "trend" the Reporting LLM is permitted to narrate as increased/decreased/unchanged — there is no regression or smoothing.
- **`cross_setting_comparison`** / **`cross_contributor_comparison`** — abstain by checking for the presence of `"cross_setting_comparison"` / `"cross_contributor_comparison"` keys in `adequacy.partial_abstentions`, rather than recomputing their own sufficiency condition. This couples this engine to the Adequacy Router's exact key strings — see [Adequacy_Router.md](./Adequacy_Router.md) Open Questions.
- **`missing_data_rate`** — over 5 key fields (`behavior, domain, modality, prompt_level, outcome`); a value counts as missing if it is `None` **or** the string `"unknown"`.
- **`*_distribution` KPIs** (`domain`, `modality`, `prompt_level`, `outcome`, `contributor`, `setting`) — internally compute a proportion dict per category, but this dict is discarded; `KpiResult` for these only carries `numerator` = count of distinct categories, `denominator` = total, `value` = count of distinct categories. **The per-category proportions are computed and then thrown away** — see Open Questions; this looks unfinished rather than intentional.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Per-KPI abstention, not just a period-level gate | Every KPI independently checks its own data sufficiency in addition to the top-level `adequacy.eligible` gate | A single period-level eligible/not-eligible flag governing all KPIs uniformly | `[inferred]` A period can have enough overall evidence (`ADEQUATE`) while still lacking, say, enough dated records for a trend — per-KPI abstention avoids either over-suppressing (hiding a computable KPI because of an unrelated shortfall) or over-asserting (showing a trend from 2 data points) |
| Trend = simple first-half vs. second-half rate delta | No regression, no smoothing, no confidence interval | Linear regression slope; rolling mean; a formal statistical trend test | `[inferred]` Matches the HLD's Non-Goal against overselling this as a validated prediction — a plain split-half delta is legible and defensible as "association," not a fitted model presented as more rigorous than the data supports |
| Trend abstention floor of 4 dated records | Hard-coded threshold | A period-length-relative threshold, or a statistical minimum-sample test | `[inferred]` — no stated rationale in code; a round, conservative floor rather than a derived one |
| Cross-setting/cross-contributor abstention delegated to `AdequacyRouter`'s output rather than recomputed here | Read `adequacy.partial_abstentions` dict keys | Recompute the ≥2-distinct-values check independently in this engine | `[inferred]` Avoids duplicating the representation check, but does so via fragile string-key coupling rather than a shared type — flagged in [Adequacy_Router.md](./Adequacy_Router.md) |

## Open Questions & Future Decisions

### Deferred
1. **Discarded distribution proportions.** Every `*_distribution` KPI computes a per-category proportion dict internally and then exposes only cardinality (`numerator`/`value` = distinct category count) in `KpiResult`. Confirm whether `KpiResult` should be extended to carry the proportion breakdown (needed for the Reporting LLM to narrate, e.g., "60% verbal, 40% gestural") or whether proportions are intentionally deferred to a later reporting-side computation.
2. Trend abstention floor (4 dated records) and completeness/temporal thresholds inherited from `AdequacyRouter` are not derived from any documented statistical justification — worth revisiting once real longitudinal data volume is known (handoff §14, §17).

## References

- `src/backend/ml/analytics_engine.py`.
- [Adequacy_Router.md](./Adequacy_Router.md) — upstream eligibility gate and `partial_abstentions` source.
- [Reporting_Llm.md](./Reporting_Llm.md) — sole consumer of `AnalyticsResult`.
- `docs/High_Level_Design.md` § Non-Goals (no clinical prediction claims), § Key Design Decisions (analytics computed in deterministic code only).
- Tests: `tests/phase4/test_analytics_engine.py`, `tests/phase6/integration/test_adequacy_analytics_e2e.py`.
