# Reporting LLM (ReportingClient) — EARS Specs

Owning design: [Reporting_Llm.md](./Reporting_Llm.md). Prefix: `REPORT`.

Test citations below reflect an actual `@spec`-annotation pass. `[x]` = annotated test exists and passes; `[ ]` = no test currently cites this spec, though the underlying code already implements it.

## Invariant

- [ ] **REPORT-001**: The system shall generate report sections only by summarizing and organizing the deterministic `AnalyticsResult` and `AdequacyResult` contained in the `EvidencePacket`; the reporting LLM shall not compute, invent, or alter any KPI value. — inherently hard to verify with the current test approach: every test mocks `_call_llm`'s return value directly, so none actually exercises whether a *real* model call stays within the evidence packet. Closing this gap needs an eval-tier test against real or recorded LLM output (the same category as `tests/eval/test_extraction_hallucination.py` for the extraction provider), not another mocked unit test.

## Generation and Fallback

- [x] **REPORT-010**: If the LLM call to generate report sections raises an exception, then the system shall fall back to generating sections via the deterministic template builder (`_build_fallback_sections()`), producing no LLM-authored text. — `tests/phase4/test_reporting_client.py::test_fallback_on_llm_failure`
- [x] **REPORT-011**: When the deterministic fallback path is used, the system shall set `provider="deterministic_fallback"`, `model="deterministic_fallback_v1"`, and `prompt_version="N/A"` on the result. — `test_fallback_provenance`
- [x] **REPORT-012**: The system shall run `validate_report()` against the generated sections regardless of whether they were produced by the LLM path or the deterministic fallback path. — `test_validation_errors_recorded`, `test_validation_runs_on_fallback`

## Post-Hoc Validation

- [x] **REPORT-020**: If any report section's body matches one of the six prohibited-language patterns (diagnosis language; recommend/should/must combined with therapy, treatment, or medication; causal autism/ASD/condition language; prognosis/outlook language; normal/abnormal/delayed/deficit language; or change/modify/adjust combined with goal/objective/target), then the system shall record a validation error for that match and set `validation_passed` to `false`. This spec documents current *detect-and-flag* behavior only — see the open question below on whether delivery should also be blocked. — `test_validation_errors_recorded`, `test_safety_validation.py::test_prohibited_text_detected` (parametrized across all 6 patterns), `test_safe_text_passes`
- [x] **REPORT-021**: If `AdequacyResult.level` is `"insufficient"`, then the system shall require at least one report section's body to state that evidence is insufficient or limited, or else record a validation error. — `test_insufficient_evidence_must_be_acknowledged`, `test_insufficient_acknowledged_passes`
- [ ] **REPORT-022**: If any KPI in `AnalyticsResult` is abstained with a reason, then the system shall require some report section to reference that KPI's abstention (by its de-underscored name, or the words "withheld"/"insufficient"), or else record a validation error naming the unacknowledged KPI. — `test_fallback_handles_abstained_kpis` checks the fallback section text only, not `validate_report()`'s acknowledgment logic itself; no test builds an evidence packet with an abstained KPI and calls `validate_report()` directly to check the error path.

## Open Question Carried Forward

REPORT-020 currently describes detect-and-flag only: a report that fails this check is still returned, with `validation_passed=false` and the errors attached. Whether the caller (`report_service.py` and above) gates on `validation_passed` before showing a report to an interventionist is unconfirmed — see [Reporting_Llm.md](./Reporting_Llm.md) Open Questions #1. If that gate does not exist, a new `[ ]` spec (e.g. `REPORT-023`: "If `validation_passed` is `false`, then the system shall not deliver the report to the interventionist without explicit override") should be added once the intended behavior is confirmed — not assumed here.

## References

- [Reporting_Llm.md](./Reporting_Llm.md) — full design, decisions, and the detect-and-flag vs. detect-and-block open question.
