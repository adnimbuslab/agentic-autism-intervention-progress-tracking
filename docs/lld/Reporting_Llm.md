---
parent: high-level-design
---

# Reporting LLM (ReportingClient)

*Brownfield LLD — reverse-engineered from `src/backend/ml/reporting_client.py`. Decisions marked `[inferred]` were observed in code, not confirmed by the author.*

## Context and Design Philosophy

Module docstring: the reporting client "may only summarize and organize deterministic findings... must NOT diagnose, prescribe, make causal claims, invent statistics, or calculate KPIs." This is the last stage of the batch pipeline — [Adequacy Router](./Adequacy_Router.md) → [Analytics Engine](./Analytics_Engine.md) → Reporting LLM — and the only component in the entire system whose job is to produce prose an interventionist reads directly. Everything numeric it narrates must already exist in the `EvidencePacket` it's handed; it has no path to compute a figure itself.

## Interface Contract

```text
ReportingClient(api_key: str | None = None, model: str | None = None)
async generate_report(evidence_packet: EvidencePacket) -> GeneratedReportData
```

`EvidencePacket`: `child_id`, `review_period_id`, period start/end, `goals`, `structured_records`, `record_ids`, `record_versions` (tracked per record — see `docs/High_Level_Design.md` § Key Design Decisions on record versioning), `analytics: AnalyticsResult`, `adequacy: AdequacyResult`, `quality_flags`, contributor/setting summaries, observation/abstained/review counts.

`ReportSection`: `heading`, `body`, `evidence_refs`, `abstention_note`.

`GeneratedReportData`: sections, `provider`, `model`, `prompt_version`, `validation_passed`, `validation_errors`.

Config: `settings.reporting_model = "claude-sonnet-4-20250514"`, `settings.reporting_prompt_version = "1.0"`.

## Generation Flow

1. Call Claude with `REPORTING_SYSTEM_PROMPT` plus the JSON-dumped `EvidencePacket` as the user message.
2. Parse the response as a JSON array of sections.
3. **On any exception during the LLM call**, fall back to `_build_fallback_sections()` — a fully deterministic, template-based section builder that reconstructs the required sections (`Review Period Summary`, `Evidence Coverage`, `Evidence Limitations`, plus conditional `Key Indicators` / `Observed Patterns` / `Progress Indicators` / cross-setting sections) directly from `EvidencePacket` fields and KPIs, with no LLM involvement at all. In this path, `provider="deterministic_fallback"`, `model="deterministic_fallback_v1"`, `prompt_version="N/A"`.
4. **Regardless of which path produced the sections**, `validate_report()` always runs against them before the result is returned.

The fallback path is a real safety mechanism, not incidental error handling: it guarantees a report is always producible from already-validated deterministic data even if the LLM call fails entirely.

## Post-Hoc Validation (`validate_report`)

**Prohibited-pattern check** — 6 regexes applied case-insensitively over the joined body of all sections via `re.findall`:

1. Diagnosis language.
2. Recommend/should/must combined with therapy/treatment/medication.
3. Causal language tied to autism/ASD/condition.
4. Prognosis/outlook/"will likely" language.
5. Normal/abnormal/delayed/deficit language.
6. Change/modify/adjust combined with goal/objective/target.

Matches are appended to `validation_errors`; **the report is still returned** with `validation_passed=False` — nothing in this code path blocks persistence or delivery of a report that fails the regex check (see Decisions).

**Adequacy-acknowledgment check** — if `adequacy.level == "insufficient"`, at least one section's body must mention "insufficient" or "limited"; for every abstained KPI carrying a reason, some section must reference it (by its de-underscored name, or the words "withheld"/"insufficient") — otherwise a specific validation error is appended per unacknowledged KPI.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Deterministic fallback on any LLM failure | Full template-based section reconstruction from `EvidencePacket`, no retry-then-fail | Retry with backoff then surface an error to the interventionist; return no report | `[inferred]` A report can always be produced from data that already passed validation/adequacy checks — the LLM only adds narrative polish, so its unavailability shouldn't block delivery of the underlying evidence |
| Prohibited-pattern check is detect-and-flag, not detect-and-block | Violations are recorded in `validation_errors` and `validation_passed=False`, but the report is still returned | Refuse to return a report (or auto-redact/regenerate) when a prohibited pattern is found | `[inferred]` — no rationale evident in code. Given CLAUDE.md's explicit rule that "the reporting LLM MUST NOT produce diagnostic statements, treatment recommendations, or causal claims," a detect-and-flag-only posture is a real gap between the stated safety rule and the enforcement mechanism. Flagged as an open question below rather than treated as settled. |
| Validation always runs, on both the LLM path and the deterministic-fallback path | Single `validate_report()` call after either path produces sections | Skip validation on the fallback path, trusting it by construction | `[inferred]` Even fully deterministic templated text could in principle fail the adequacy-acknowledgment check if a template branch is missing for a given `AdequacyLevel` — running validation unconditionally catches that regardless of source |

## Open Questions & Future Decisions

### Deferred
1. **Prohibited-pattern violations do not block report delivery.** CLAUDE.md states the reporting LLM "MUST NOT" produce diagnostic/prescriptive/causal statements as a safety rule, but the current implementation only flags such violations via `validation_errors`/`validation_passed=False` — the caller (`report_service.py` and above) must be confirmed to actually gate on `validation_passed` before showing a report to an interventionist. If no caller currently enforces that gate, this is a live safety gap, not just a documentation nuance.
2. Whether a report that fails validation should trigger the deterministic fallback (i.e., retry via the safe path) rather than being returned as-is with errors attached.

## References

- `src/backend/ml/reporting_client.py`.
- [Analytics_Engine.md](./Analytics_Engine.md), [Adequacy_Router.md](./Adequacy_Router.md) — sole upstream data sources; this component computes nothing itself.
- `docs/High_Level_Design.md` § Safety Rules ("The reporting LLM MUST NOT produce diagnostic statements, treatment recommendations, or causal claims").
- Tests: `tests/phase4/test_reporting_client.py`, `tests/phase4/test_safety_validation.py`, `tests/phase6/integration/test_reporting_provenance_e2e.py`.
