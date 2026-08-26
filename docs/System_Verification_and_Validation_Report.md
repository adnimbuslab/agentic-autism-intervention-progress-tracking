# System Verification and Validation Report

## Interventionist AI System — Autism Intervention Progress Tracking

---

## Table of Contents

1. [Document Control](#1-document-control)
2. [System Under Test](#2-system-under-test)
3. [Test Strategy](#3-test-strategy)
4. [Requirements Traceability Matrix](#4-requirements-traceability-matrix)
5. [Detailed Automated Test Cases](#5-detailed-automated-test-cases)
6. [Manual Verification Test Cases](#6-manual-verification-test-cases)
7. [Defect Register](#7-defect-register)
8. [Current Analytics Limitations](#8-current-analytics-limitations)
9. [Live Extraction Limitation](#9-live-extraction-limitation)
10. [Build / Deployment Verification](#10-build--deployment-verification)
11. [Test Execution Summary](#11-test-execution-summary)
12. [Verification Conclusion](#12-verification-conclusion)

---

## 1. Document Control

| Field | Value |
|---|---|
| **Document Title** | System Verification and Validation Report |
| **System Name** | Interventionist AI System — Autism Intervention Progress Tracking |
| **Repository** | agentic-autism-intervention-progress-tracking |
| **Branch** | main |
| **Git Revision** | 43e8eb7 |
| **Document Version** | 1.0 |
| **Date Generated** | 2026-08-26 |
| **Purpose** | Formal engineering verification artifact for a governance-aware, human-in-the-loop AI research prototype |
| **Scope** | Software system verification only. Model scientific evaluation is out of scope. |
| **Intended Audience** | Research collaborators, technical reviewers, manuscript reviewers, future handoff engineers |
| **Test Environment** | Docker Compose (PostgreSQL 16-alpine, Python 3.11, Node.js 20-alpine); local development on Windows 11 |

### Important Limitations

- This document verifies the **software system** — API, database, RBAC, workflows, deterministic validation, analytics, reporting, provenance, and audit.
- This document does **NOT** constitute clinical validation, regulatory submission, or production readiness certification.
- This document does **NOT** validate the future fine-tuned extraction model. Extraction accuracy, precision/recall/F1, hallucination rate, expert adjudication, fine-tuned model comparison, and model calibration are all **FUTURE/PENDING** work.
- The system is a **controlled research prototype**, not production clinical software or clinical decision support.
- Seeded demo data bypasses the live extraction pipeline and must not be treated as evidence of live extraction performance.

---

## 2. System Under Test

### 2.1 Architecture Overview

The system implements a four-layer architecture:

1. **Presentation Layer** — React/Next.js 14 frontend with TypeScript (strict mode), interventionist dashboard, contributor observation UI, analytics views, report viewer
2. **Application Layer** — FastAPI backend (Python 3.11), JWT authentication, role-based access control, observation orchestration, schedule engine, audit logging
3. **AI/ML Layer** — Pluggable ExtractionProvider (currently TemporaryLLMExtractionProvider using Claude API), deterministic ValidationEngine, AbstentionRouter, AdequacyRouter, deterministic AnalyticsEngine, grounded ReportingClient
4. **Data Layer** — PostgreSQL 16 with SQLAlchemy async ORM, Alembic migrations, immutable observation store, versioned structured records, audit trail

### 2.2 Observation-to-Report Pipeline

```
Contributor natural-language observation (ConversationalCapture UI)
  → POST /children/{child_id}/observations
  → Immutable raw observation persistence (Observation row, status=PENDING)
  → ExtractionProvider.extract() [TemporaryLLMExtractionProvider]
  → ExtractionResult (SUCCESS / PARTIAL / ABSTAINED / FAILED)
  → Deterministic ValidationEngine.validate()
  → AbstentionRouter.route()
  → Routing decision:
      ACCEPT → StructuredRecord (VALIDATED), observation finalized
      CLARIFY → ClarificationTurn created, observation status=CLARIFYING
      RETAIN_WITH_UNKNOWN → StructuredRecord (VALIDATED) with unknowns, observation finalized
      INTERVENTIONIST_REVIEW → StructuredRecord (PENDING), observation finalized
      REJECT → No StructuredRecord, observation status=FAILED
  → [On finalization] conversation_json preserved with full clarification history
  → AdequacyRouter.assess() [per review period]
  → Deterministic AnalyticsEngine.compute() [14 KPIs]
  → EvidencePacket assembly (analytics + structured records + adequacy + goals)
  → ReportingClient.generate_report()
      → LLM path (Anthropic API) OR deterministic fallback
      → validate_report() [prohibited content scan on BOTH paths]
  → GeneratedReportData with provenance (provider, model, prompt_version)
  → Interventionist review / flag / version
```

### 2.3 Role Boundaries

| Role | Capabilities | Restrictions |
|---|---|---|
| **Interventionist** | Owns child workspaces; manages goals, actors, schedules; views observations with structured records; corrects records; runs analytics/reports; views audit trail | — |
| **Contributor** (Parent, Teacher, etc.) | Submits natural-language observations; answers clarification questions; views own observation history for assigned children | Cannot access: other children, structured extraction internals, analytics, reports, audit trail, record correction, goal management, actor management |

### 2.4 AI Safety Boundaries

The system enforces that AI:

- **Does NOT diagnose** autism or any other condition
- **Does NOT prescribe** treatment, therapy, or medication
- **Does NOT make causal claims** (e.g., "improvement was caused by…")
- **Does NOT autonomously modify** intervention goals or strategies
- **Does NOT generate** statistics not present in the evidence packet

The **interventionist remains the highest-authority reviewer**. All AI outputs (extraction, reporting) require interventionist review before use. Deterministic validation (`validate_report`) scans both LLM and fallback report output for prohibited patterns including diagnostic language, treatment recommendations, causal claims, prognostic statements, and deficit terminology.

---

## 3. Test Strategy

### 3.1 Testing Levels

| Level | Framework | Location | Description |
|---|---|---|---|
| Unit tests | pytest | `tests/unit/` | CHAT parser, schemas, deidentification, episode segmentation, segment selection, validation engine, abstention router |
| Eval tests | pytest | `tests/eval/` | Extraction behavior (schema conformance, unsupported fields, abstention, clarification), validation (schema, cross-field, routing), robustness (prompt injection, hallucination detection) |
| Phase 3 API/service tests | pytest + httpx | `tests/phase3/` | Authentication, children CRUD, goals, actors, observations, structured records, schedules, audit, workspace service, observation service, observation workflow, immutability, RBAC, auth service |
| Phase 4 analytics/reporting tests | pytest + httpx | `tests/phase4/` | Analytics engine, evidence packet, reports API, safety validation, adequacy router, analytics API, reporting client (fallback content, provenance, validation) |
| Phase 6 security/hardening tests | pytest + httpx | `tests/phase6/` | Prompt injection (validation + reporting), security RBAC (unauthenticated, invalid tokens, role escalation, IDOR, deactivated users), input hardening (malformed payloads, boundary conditions) |
| Phase 6 integration tests | pytest + httpx | `tests/phase6/integration/` | End-to-end workflows: CHAT pipeline, audit provenance, extraction pipeline, adequacy/analytics, contributor flow, interventionist flow, reporting provenance |
| Frontend component tests | Vitest + Testing Library | `src/frontend/__tests__/` | Auth, roles, API client, formatters, analytics UI, records UI, observation UI, goals UI, contributor isolation, resilience, components, analytics page, reports page, report viewer |
| Browser E2E tests | Playwright | `tests/phase6/e2e/browser.spec.ts` | Login flows, dashboard navigation, child workspace, page loads (goals, observations, records, reports, audit), contributor isolation, login failure |
| Manual verification | Browser | Documented in Section 6 | Interventionist and contributor workflows in live Docker environment |

### 3.2 Test Count by Suite

Counts are derived by counting `def test_` / `async def test_` in Python files and `it(` in TypeScript files.

| Suite | Test Files | Test Functions |
|---|---|---|
| `tests/unit/` | 7 | 90 |
| `tests/eval/` | 10 | 64 |
| `tests/phase3/` | 15 | 142 |
| `tests/phase4/` | 7 | 108 |
| `tests/phase6/` (non-integration) | 3 | 93 |
| `tests/phase6/integration/` | 7 | 77 |
| **Backend total** | **49** | **574** |
| `src/frontend/__tests__/` | 14 | 109 |
| `tests/phase6/e2e/browser.spec.ts` | 1 | 16 |
| **Frontend total** | **15** | **125** |
| **Grand total** | **64** | **699** |

Note: Each suite is counted independently. Running `pytest tests/` invokes backend tests; running `npx vitest` invokes frontend tests; running `npx playwright test` invokes browser E2E tests. There is no overlap between these three runners.

---

## 4. Requirements Traceability Matrix

| Req ID | Requirement | Implementation | Automated Test(s) | Manual Test | Status | Evidence / Notes |
|---|---|---|---|---|---|---|
| **REQ-AUTH-001** | Interventionist authentication | `POST /auth/login` → JWT token; `src/backend/api/auth.py`, `services/auth_service.py` | `test_auth.py` (5 tests), `test_auth_service.py` (13 tests), integration `test_interventionist_e2e.py::test_interventionist_login` | MAN-001 | VERIFIED | Bcrypt password hashing, JWT HS256 |
| **REQ-AUTH-002** | Contributor authentication | Same `/auth/login` endpoint, JWT with role claim | `test_auth.py`, integration `test_contributor_e2e.py::test_contributor_login` | MAN-023 | VERIFIED | Role returned in token; frontend routes by role |
| **REQ-RBAC-001** | Child-level authorization | `authorize_child_access()` in `api/deps.py`; interventionist sees own children, contributors see assigned children | `test_rbac.py` (23 tests), `test_security_rbac.py` (22 tests), `test_input_hardening.py` (46 tests) | MAN-002, MAN-025 | VERIFIED | IDOR tests (cross-child access) return 403 |
| **REQ-RBAC-002** | Contributor cannot access interventionist functionality | `RequireInterventionist` dependency on all interventionist-only endpoints | `test_rbac.py::TestContributorDeniedEndpoints` (11 tests), `test_security_rbac.py::TestContributorCannotAccessInterventionistEndpoints` (10 tests) | MAN-027 | VERIFIED | 403 on: create child, goals, records, analytics, reports, audit, actors, schedules |
| **REQ-OBS-001** | Raw observation persistence | `Observation` model created with `status=PENDING` before extraction; `observation_service.py:236-245` | `test_observation_service.py` (14 tests), `test_immutability.py` (11 tests) | MAN-005 | VERIFIED | Row flushed to DB before pipeline runs |
| **REQ-OBS-002** | Raw text immutability | `raw_text` set once at submission; `build_conversation_json` preserves original | `test_immutability.py::TestRawTextImmutability` (3 tests) | MAN-006 | VERIFIED | No UPDATE/DELETE on raw_text in any service |
| **REQ-OBS-003** | Contributor natural-language capture | `ConversationalCapture` component → `POST /children/{child_id}/observations` | `test_observations.py` (11 tests), `observation-ui.test.tsx` (6 tests), integration `test_contributor_e2e.py` (12 tests), browser `spec:14` | MAN-005 | VERIFIED | Free-text input with setting selector |
| **REQ-OBS-004** | Extraction-provider abstraction | `ExtractionProvider` protocol; `get_extraction_provider()` factory; `TemporaryLLMExtractionProvider` implements it | `test_extraction.py` (7 tests), `test_extraction_pipeline_e2e.py` (9 tests) | — | AUTOMATED-TEST VERIFIED | Provider type configurable via `EXTRACTION_PROVIDER` env var |
| **REQ-OBS-005** | Extraction failure handling | `_run_pipeline` try/except → `status=FAILED`, `routing=REJECT`, raw observation preserved | `test_observation_service.py::test_extraction_failure`, `test_observation_workflow.py` (22 tests) | — | AUTOMATED-TEST VERIFIED | No StructuredRecord created on failure |
| **REQ-VAL-001** | Deterministic field validation | `ValidationEngine.validate()` checks field presence, cross-field consistency, enum validity | `test_validation_engine.py` (19 tests), `test_schema_validation.py` (6 tests), `test_cross_field_logic.py` (8 tests) | — | AUTOMATED-TEST VERIFIED | Deterministic; no LLM involvement |
| **REQ-VAL-002** | Clarification routing | `AbstentionRouter.route()` → `CLARIFY` when extraction is PARTIAL or low confidence | `test_abstention_router.py` (13 tests), `test_clarification.py` (6 tests), `test_routing_decisions.py` (5 tests), `test_observation_workflow.py` (22 tests) | MAN-007 | VERIFIED | Max turns enforced; clarification turns persisted |
| **REQ-VAL-003** | Abstention/rejection | `AbstentionRouter` abstains on low confidence or excessive null fields; `ValidationEngine` rejects on missing critical fields | `test_abstention.py` (5 tests), `test_abstention_router.py` (13 tests) | — | AUTOMATED-TEST VERIFIED | Abstention is first-class output |
| **REQ-VAL-004** | Prompt-injection handling | `ValidationEngine` processes adversarial input deterministically without crash; `validate_report` catches prohibited patterns | `test_prompt_injection.py` (25 Phase 6 + 6 eval robustness), `test_extraction_hallucination.py` (6 tests), Phase 6 `test_prompt_injection.py::TestValidationEngineAdversarial` (13 tests) | — | AUTOMATED-TEST VERIFIED | JSON injection, XSS, extreme-length, unicode, null-field injection tested |
| **REQ-REC-001** | Structured evidence creation | `StructuredRecord` model with `record_data`, `validation_result`, provenance fields | `test_structured_records.py` (7 tests), `test_observation_service.py` | — | AUTOMATED-TEST VERIFIED | Created only on ACCEPT/CLARIFY/RETAIN/REVIEW routing |
| **REQ-REC-002** | Source observation traceability | `StructuredRecord.observation_id` FK → `Observation.id` | `test_structured_records.py`, `test_evidence_packet.py` (11 tests) | MAN-020 | VERIFIED | Every record traces to source observation |
| **REQ-REC-003** | Correction creates new version | `correct_record()` creates new `StructuredRecord` with `version=original.version+1`, `previous_version_id=original.id` | `test_immutability.py::TestCorrectionVersioning` (5 tests), `test_structured_records.py` | MAN-010, MAN-012 | VERIFIED | Version chain preserved |
| **REQ-REC-004** | Original version preserved | Original record unchanged after correction; `previous_version_id` links versions | `test_immutability.py::TestCorrectionVersioning` | MAN-011 | VERIFIED | Append-only semantics |
| **REQ-REC-005** | Corrected version used downstream | Analytics use latest version per observation | `test_analytics_engine.py` | MAN-014 | VERIFIED | Version-aware record selection |
| **REQ-GOAL-001** | Interventionist goal access | `GET/POST /children/{child_id}/goals`; contributor 403 | `test_goals.py` (4 tests), `test_rbac.py` | MAN-004 | VERIFIED | CRUD with domain/type classification |
| **REQ-ACTOR-001** | Contributor assignment | `POST /children/{child_id}/actors` → `ActorAssignment` | `test_actors.py` (4 tests), `test_security_rbac.py` | MAN-025, MAN-029 | VERIFIED | Interventionist invites; contributor sees assigned children |
| **REQ-SCHED-001** | Schedules / expected observations | `ReportingExpectation` model; `GET/POST /children/{child_id}/schedules` | `test_schedules.py` (4 tests) | MAN-028 | PENDING MANUAL VERIFICATION | Cadence_days and goal association |
| **REQ-ANA-001** | Review-period creation | `POST /children/{child_id}/review-periods` | `test_analytics_api.py` (8 tests) | MAN-013 | FIXED AND RETESTED | Defect DEF-013 fixed: listing integration |
| **REQ-ANA-002** | Existing review-period retrieval | `GET /children/{child_id}/review-periods` | `test_analytics_api.py` | MAN-013 | FIXED AND RETESTED | Was missing; added in Phase 6 |
| **REQ-ANA-003** | Deterministic adequacy | `AdequacyRouter.assess()` → ADEQUATE/LIMITED/INSUFFICIENT with checks and quality flags | `test_adequacy_router.py` (16 tests), `test_adequacy_analytics_e2e.py` (11 tests) | MAN-015 | VERIFIED | Deterministic; no LLM |
| **REQ-ANA-004** | Deterministic analytics | `AnalyticsEngine.compute()` → 14 KPIs; all computed by code, never by LLM | `test_analytics_engine.py` (20 tests) | MAN-014 | VERIFIED | See Section 8 for semantic limitations |
| **REQ-ANA-005** | Insufficient-evidence gating | When adequacy=INSUFFICIENT, analytics abstain; report must acknowledge | `test_adequacy_router.py`, `test_safety_validation.py` (14 tests), `test_adequacy_analytics_e2e.py` | — | AUTOMATED-TEST VERIFIED | Abstained KPIs cannot be silently presented |
| **REQ-ANA-006** | Current-version records only | Analytics engine uses latest version per observation, not superseded versions | `test_analytics_engine.py` | — | AUTOMATED-TEST VERIFIED | Version filtering in record retrieval |
| **REQ-REP-001** | EvidencePacket grounding | Report generated from EvidencePacket containing analytics, records, adequacy, goals | `test_evidence_packet.py` (11 tests), `test_reporting_client.py` (27 tests) | MAN-020 | VERIFIED | All report content must trace to evidence |
| **REQ-REP-002** | Deterministic fallback reporting | When LLM call fails, fallback generates 7 sections from EvidencePacket analytics | `test_reporting_client.py::TestFallbackSections` (13 tests), `test_reporting_provenance_e2e.py` (9 tests) | MAN-019 | FIXED AND RETESTED | Originally produced shallow 2–3 sections; expanded to 7 |
| **REQ-REP-003** | Real LLM reporting path | When Anthropic API key is valid, `_call_llm()` generates report sections | `test_reporting_client.py::TestReportGeneration::test_generate_calls_llm` | — | AUTOMATED-TEST VERIFIED | LLM boundary mocked in tests; live requires API key |
| **REQ-REP-004** | Prohibited-language validation | `validate_report()` scans both LLM and fallback output for 6 prohibited regex patterns | `test_safety_validation.py` (14 tests), Phase 6 `test_prompt_injection.py::TestReportingProhibitedContent` (7 tests) | — | AUTOMATED-TEST VERIFIED | Diagnosis, recommendation, causal, prognostic, deficit, goal-modification |
| **REQ-REP-005** | Report provenance | `GeneratedReportData` stores provider, model, prompt_version; fallback uses "deterministic_fallback" | `test_reporting_client.py::TestReportProvenance` (3 tests), `report-ui.test.tsx` (12 tests) | MAN-018 | FIXED AND RETESTED | Defect DEF-014: was hardcoded "anthropic" |
| **REQ-REP-006** | Report versioning | `Report.version` field; multiple versions per child/review-period | `test_reports_api.py` (12 tests) | MAN-022 | VERIFIED | Version badge displayed in UI |
| **REQ-REP-007** | Interventionist flagging/review | `PATCH /reports/{report_id}/flag` with reason | `test_reports_api.py` | MAN-022 | VERIFIED | Flagged badge and reason displayed |
| **REQ-AUD-001** | Audit logging | `AuditEvent` model; `audit_service.log_event()` on all mutating operations | `test_audit.py` (3 tests), `test_audit_provenance_e2e.py` (9 tests) | MAN-030 | PENDING MANUAL VERIFICATION | Action, resource_type, resource_id, child_id, user_id, timestamp |
| **REQ-AUD-002** | Child-scoped audit visibility | `GET /children/{child_id}/audit` filtered by child_id; interventionist only | `test_audit.py`, `test_rbac.py`, `test_security_rbac.py` | MAN-030 | PENDING MANUAL VERIFICATION | Contributor returns 403 |
| **REQ-DEPLOY-001** | Docker backend | `docker/Dockerfile.backend` — Python 3.11-slim, uvicorn | Build verification | — | VERIFIED | Health check: `GET /health` |
| **REQ-DEPLOY-002** | Docker frontend | `docker/Dockerfile.frontend` — Node 20-alpine, multi-stage standalone build | Build verification | — | VERIFIED | Output mode: standalone |
| **REQ-DEPLOY-003** | PostgreSQL | PostgreSQL 16-alpine in Docker Compose; port 5433:5432 | Build verification | — | VERIFIED | Health check: `pg_isready` |
| **REQ-DEPLOY-004** | Alembic migrations | 3 migration files (001, 002, 003) | Build verification | — | VERIFIED | Run via `alembic upgrade head` |
| **REQ-DEPLOY-005** | Idempotent demo seed | `scripts/seed_demo.py` checks for existing data before insert | Code review | — | VERIFIED | Re-runnable without duplication |

---

## 5. Detailed Automated Test Cases

### 5.1 Critical Governance and Safety Tests

#### 5.1.1 Prohibited Content Detection (Phase 6)

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| PI-001 | `test_diagnosis_language_detected` | REQ-REP-004 | "diagnosed with autism" triggers prohibited-content error | `tests/phase6/test_prompt_injection.py::TestReportingProhibitedContent` |
| PI-002 | `test_treatment_recommendation_detected` | REQ-REP-004 | "recommend…therapy" triggers error | Same |
| PI-003 | `test_causal_claim_detected` | REQ-REP-004 | "caused by…ASD" triggers error | Same |
| PI-004 | `test_prognostic_statement_detected` | REQ-REP-004 | "will likely reach…milestones" triggers error | Same |
| PI-005 | `test_deficit_language_detected` | REQ-REP-004 | "deficit in language" triggers error | Same |
| PI-006 | `test_goal_modification_language_detected` | REQ-REP-004 | "change the intervention goal" triggers error | Same |
| PI-007 | `test_clean_report_passes_validation` | REQ-REP-004 | Evidence-based language produces zero errors | Same |

All: **PASS** (automated)

#### 5.1.2 Abstention Preservation in Reports

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| AP-001 | `test_abstained_kpi_not_mentioned_flagged` | REQ-ANA-005 | Unacknowledged abstained KPI triggers validation error | `tests/phase6/test_prompt_injection.py::TestAbstentionPreservation` |
| AP-002 | `test_abstained_kpi_acknowledged_passes` | REQ-ANA-005 | "withheld" acknowledgment clears error | Same |
| AP-003 | `test_insufficient_not_mentioned_flagged` | REQ-ANA-005 | INSUFFICIENT evidence not mentioned triggers error | `TestInsufficientEvidenceAcknowledgment` |
| AP-004 | `test_insufficient_mentioned_passes` | REQ-ANA-005 | "insufficient" mention clears error | Same |

All: **PASS** (automated)

#### 5.1.3 Validation Engine Adversarial Input

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| VA-001 | `test_injection_in_behavior_field` | REQ-VAL-004 | JSON injection in behavior does not crash or force ACCEPT | `tests/phase6/test_prompt_injection.py::TestValidationEngineAdversarial` |
| VA-002 | `test_extremely_long_behavior` | REQ-VAL-004 | 50,000 character behavior processes without crash | Same |
| VA-003 | `test_html_script_in_behavior` | REQ-VAL-004 | XSS payload in behavior does not crash | Same |
| VA-004 | `test_null_behavior_and_domain` | REQ-VAL-004 | Null critical fields → REJECT/CLARIFY/REVIEW (not ACCEPT) | Same |
| VA-005 | `test_all_fields_none` | REQ-VAL-004 | All-null observation → REJECT | Same |
| VA-006 | `test_confidence_exactly_zero` | REQ-VAL-003 | Confidence=0 → INTERVENTIONIST_REVIEW | Same |
| VA-007 | `test_unicode_in_behavior` | REQ-VAL-004 | Unicode/emoji in behavior does not crash | Same |
| VA-008 | `test_empty_string_behavior` | REQ-VAL-004 | Empty-string behavior does not crash | Same |

All: **PASS** (automated)

#### 5.1.4 RBAC — Unauthenticated Access

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| UA-001 | `test_endpoint_requires_auth` (10 endpoints) | REQ-AUTH-001 | All critical endpoints return 401 without token | `tests/phase6/test_security_rbac.py::TestUnauthenticatedAccess` |
| UA-002 | `test_invalid_token_rejected` (3 token types) | REQ-AUTH-001 | Garbage/malformed/empty tokens return 401 | `TestInvalidToken` |
| UA-003 | `test_deactivated_user_rejected` | REQ-AUTH-001 | Deactivated user's valid JWT returns 403 | `TestDeactivatedUser` |

All: **PASS** (automated)

#### 5.1.5 RBAC — Role Escalation Prevention

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| RE-001 | Contributor cannot create child | REQ-RBAC-002 | 403 | `tests/phase6/test_security_rbac.py::TestContributorCannotAccessInterventionistEndpoints` (10 tests) |
| RE-002 | Contributor cannot list/correct records | REQ-RBAC-002 | 403 | Same |
| RE-003 | Contributor cannot run analytics/reports | REQ-RBAC-002 | 403 | Same |
| RE-004 | Contributor cannot view audit trail | REQ-RBAC-002 | 403 | Same |
| RE-005 | Contributor cannot manage actors | REQ-RBAC-002 | 403 | Same |

All: **PASS** (automated)

#### 5.1.6 IDOR (Cross-Child Access)

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| IDOR-001 | `test_cross_child_goals` | REQ-RBAC-001 | 403 | `tests/phase6/test_security_rbac.py::TestCrossChildAccess` |
| IDOR-002 | `test_cross_child_observations` | REQ-RBAC-001 | 403 | Same |
| IDOR-003 | `test_cross_child_audit` | REQ-RBAC-001 | 403 | Same |

All: **PASS** (automated)

#### 5.1.7 Raw Text Immutability

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| IM-001 | `test_raw_text_preserved_in_conversation_json` | REQ-OBS-002 | raw_text unchanged in conversation JSON | `tests/phase3/test_immutability.py::TestRawTextImmutability` |
| IM-002 | `test_raw_text_unchanged_after_clarification_turns` | REQ-OBS-002 | raw_text unchanged after 2 clarification turns | Same |
| IM-003 | `test_conversation_json_does_not_modify_raw_text_field` | REQ-OBS-002 | build_conversation_json does not mutate observation | Same |

All: **PASS** (automated)

#### 5.1.8 Report Provenance

| Test Case ID | Test Name | Requirement | Expected | Source |
|---|---|---|---|---|
| RP-001 | `test_llm_success_provenance` | REQ-REP-005 | LLM path: provider="anthropic", model="claude-sonnet-4-20250514", prompt_version="1.0" | `tests/phase4/test_reporting_client.py::TestReportProvenance` |
| RP-002 | `test_fallback_provenance` | REQ-REP-005 | Fallback path: provider="deterministic_fallback", model="deterministic_fallback_v1", prompt_version="N/A" | Same |
| RP-003 | `test_llm_and_fallback_provenance_differ` | REQ-REP-005 | LLM and fallback provenance are distinct | Same |

All: **PASS** (automated)

### 5.2 Grouped Test Summaries

#### 5.2.1 Unit Tests (90 tests)

| File | Count | Coverage Area |
|---|---|---|
| `test_chat_parser.py` | 25 | CHAT transcript parsing: headers, utterances, tiers, edge cases |
| `test_schemas.py` | 15 | Pydantic model serialization, enum validation, field constraints |
| `test_deidentify.py` | 7 | Name/date/location replacement, pattern matching |
| `test_segment_episodes.py` | 6 | Episode boundary detection, temporal segmentation |
| `test_select_segments.py` | 5 | Behavioral segment selection criteria |
| `test_validation_engine.py` | 19 | Field validation rules, cross-field consistency, routing decisions |
| `test_abstention_router.py` | 13 | Confidence routing, null-field thresholds, extraction-status handling |

#### 5.2.2 Eval Tests (64 tests)

| File | Count | Coverage Area |
|---|---|---|
| `test_extraction.py` | 7 | Extraction result structure, provider metadata |
| `test_schema_conformance.py` | 10 | Output schema compliance, field types |
| `test_unsupported_fields.py` | 5 | Unsupported field rejection |
| `test_abstention.py` | 5 | Abstention behavior on ambiguous input |
| `test_clarification.py` | 6 | Clarification question generation |
| `test_schema_validation.py` | 6 | Schema-level validation rules |
| `test_cross_field_logic.py` | 8 | Cross-field consistency checks (verbal modality with non-speech behavior, etc.) |
| `test_routing_decisions.py` | 5 | Routing decision logic |
| `test_prompt_injection.py` (eval) | 6 | Prompt injection in extraction context |
| `test_extraction_hallucination.py` | 6 | Hallucination detection heuristics |

#### 5.2.3 Phase 3 API/Service Tests (142 tests)

| File | Count | Coverage Area |
|---|---|---|
| `test_auth.py` | 5 | Login, token issuance, invalid credentials |
| `test_children.py` | 6 | CRUD, ownership, listing |
| `test_goals.py` | 4 | Goal creation, retrieval, domain/type |
| `test_actors.py` | 4 | Actor assignment, listing, revocation |
| `test_observations.py` | 11 | Submission, listing, detail, conversation |
| `test_structured_records.py` | 7 | Record creation, versioning, history |
| `test_schedules.py` | 4 | Schedule creation, listing |
| `test_audit.py` | 3 | Audit event logging, child-scoped retrieval |
| `test_workspace_service.py` | 11 | Child workspace operations |
| `test_observation_service.py` | 14 | Pipeline orchestration, failure handling |
| `test_observation_workflow.py` | 22 | All 5 routing paths, clarification loop, error recovery |
| `test_immutability.py` | 11 | Raw text immutability, correction versioning, audit append-only |
| `test_stubs.py` | 4 | Endpoint stub validation |
| `test_rbac.py` | 23 | Comprehensive role enforcement across endpoint groups |
| `test_auth_service.py` | 13 | Password hashing, token creation/validation, user lookup |

#### 5.2.4 Phase 4 Analytics/Reporting Tests (108 tests)

| File | Count | Coverage Area |
|---|---|---|
| `test_analytics_engine.py` | 20 | All 14 KPIs, edge cases, empty data |
| `test_evidence_packet.py` | 11 | Packet assembly, record inclusion, version filtering |
| `test_reports_api.py` | 12 | Report CRUD, generation, flagging |
| `test_safety_validation.py` | 14 | Prohibited patterns, insufficient evidence acknowledgment |
| `test_adequacy_router.py` | 16 | Adequacy level determination, quality flags |
| `test_analytics_api.py` | 8 | Analytics API endpoints, review period management |
| `test_reporting_client.py` | 27 | Fallback sections (13), generation (4), provenance (3), validation (7) |

#### 5.2.5 Phase 6 Security/Hardening Tests (93 tests)

| File | Count | Coverage Area |
|---|---|---|
| `test_prompt_injection.py` | 25 | Adversarial validation (13), reporting prohibited content (7), abstention preservation (2), insufficient evidence (2), pattern coverage (1) |
| `test_security_rbac.py` | 22 | Unauthenticated (10+3), role escalation (10), IDOR (3), nonexistent resources (3), malformed UUIDs (3), deactivated user (1) |
| `test_input_hardening.py` | 46 | Malformed payloads, missing fields, invalid enums, oversized input, boundary conditions |

#### 5.2.6 Phase 6 Integration Tests (77 tests)

| File | Count | Coverage Area |
|---|---|---|
| `test_chat_pipeline_e2e.py` | 8 | CHAT parse → segment → select → extract (mocked LLM) |
| `test_audit_provenance_e2e.py` | 9 | Audit trail creation and retrieval across operations |
| `test_extraction_pipeline_e2e.py` | 9 | Raw observation → extraction → validation → routing → record |
| `test_adequacy_analytics_e2e.py` | 11 | Adequacy assessment → analytics computation → KPI verification |
| `test_contributor_e2e.py` | 12 | Login → observe → clarify → finalize → history |
| `test_interventionist_e2e.py` | 9 | Login → create child → goals → observe → records → report |
| `test_reporting_provenance_e2e.py` | 9 | Evidence packet → report → provenance → validation chain |

#### 5.2.7 Frontend Vitest Tests (109 tests)

| File | Count | Coverage Area |
|---|---|---|
| `auth.test.tsx` | 4 | Login form, token storage, redirect |
| `roles.test.tsx` | 6 | Role-based routing, UI differentiation |
| `api-client.test.ts` | 8 | API client configuration, error handling |
| `formatters.test.ts` | 5 | Date/number formatting utilities |
| `analytics-ui.test.tsx` | 8 | KPI card rendering, abstention display |
| `records-ui.test.tsx` | 8 | Record detail, version history display |
| `observation-ui.test.tsx` | 6 | Observation list, detail display |
| `goals-ui.test.tsx` | 8 | Goal list, domain badges |
| `contributor-isolation.test.tsx` | 4 | Contributor restricted views |
| `resilience.test.tsx` | 13 | Error states, loading states, empty states |
| `components.test.tsx` | 16 | Shared UI components |
| `analytics-page.test.tsx` | 6 | Analytics page integration |
| `reports-page.test.tsx` | 5 | Reports page with period selector |
| `report-ui.test.tsx` | 12 | Report viewer banners, provenance, sections |

#### 5.2.8 Browser E2E Tests (16 tests)

| Test | Description |
|---|---|
| Spec 1 | Login page renders with title |
| Spec 2 | Interventionist login redirects to dashboard |
| Spec 3 | Dashboard shows child list |
| Spec 4 | Navigate to child workspace |
| Spec 5 | Child workspace shows navigation tabs/links |
| Spec 6 | Goals page loads |
| Spec 7 | Observations page loads |
| Spec 8 | Records page loads |
| Spec 9 | Reports page loads |
| Spec 10 | Audit page loads |
| Spec 11 | Login failure shows error |
| Spec 12 | Contributor login redirects to /contribute |
| Spec 13 | Contributor sees assigned children |
| Spec 14 | Observation submission page loads |
| Spec 15 | Contributor cannot navigate to interventionist pages |
| Spec 16 | Contributor history page loads |

---

## 6. Manual Verification Test Cases

### Legend

| Status | Meaning |
|---|---|
| PASSED | Manually verified in browser against live Docker environment |
| FIXED AND RETESTED | Defect discovered, fixed, regression test added, manually re-verified |
| PENDING MANUAL VERIFICATION | Test case defined but not yet executed in browser |

### 6.1 Interventionist Workflow

| Manual Test ID | Scenario | Preconditions | Steps | Expected Result | Observed Result | Status | Defect/Fix Reference |
|---|---|---|---|---|---|---|---|
| MAN-001 | Interventionist login | Docker running, seed data loaded | Navigate to localhost:3000; enter demo-interventionist@example.com / DemoPass123!; click Sign In | Dashboard loads showing authorized children | Dashboard loads with Demo Child Alex and Demo Child Sam | PASSED | — |
| MAN-002 | Dashboard displays authorized children | Logged in as interventionist | View dashboard | Two child cards: Alex (ADEQUATE data), Sam (LIMITED data) | Both children visible with Active badges | PASSED | — |
| MAN-003 | Child workspace navigation | Logged in as interventionist | Click Demo Child Alex card | Child workspace opens with navigation tabs | Workspace opens with Goals, Observations, Records, Analytics, Reports, Schedules, Contributors, Audit tabs | PASSED | — |
| MAN-004 | Goal list | In Alex's workspace | Click Goals tab | Active goals displayed with domain, type | "Functional requesting" (social_communication, long_term) and "Cooperative play" (play, short_term) visible | PASSED | — |
| MAN-005 | Observation list | In Alex's workspace | Click Observations tab | 8 observations listed with dates, settings, status | 8 observations with home/school settings, all FINALIZED | PASSED | — |
| MAN-006 | Original source observation display | In observation detail | Click an observation row | Raw text displayed under "Source Evidence — Original Observation" | Original natural-language text displayed, unmodified | PASSED | — |
| MAN-007 | Clarification conversation visibility | In last Alex observation detail | Click observation with clarification | Clarification Q&A visible: question and answer preserved | "Could you describe the type of prompt…" / "It was a gestural prompt…" visible | PASSED | — |
| MAN-008 | AI-derived structured record visibility | In observation detail (interventionist only) | View structured information section | Structured fields (domain, behavior, modality, prompt_level, outcome) displayed | Fields displayed with values from demo_seed extraction | PASSED | — |
| MAN-009 | Validation/provenance visibility | In observation detail | View provenance section | Provider, model, prompt_version visible; validation status shown | provider=demo_seed, model=demo_seed_v1, prompt_version=demo | PASSED | — |
| MAN-010 | Record correction interface | In Records tab, interventionist | Select a record; click Correct/Edit; enter corrected data and reason | New version created; correction reason preserved | Submit Correction creates v2 with correction_reason | PASSED | — |
| MAN-011 | v1 preserved after correction | After MAN-010 | View version history | v1 still visible and unchanged | Original version preserved in history | PASSED | — |
| MAN-012 | v2 corrected record/version history | After MAN-010 | View record version history | Both v1 and v2 visible; v2 marked CORRECTED; v1 remains VALIDATED | Version chain displayed correctly | PASSED | — |

### 6.2 Analytics and Reports

| Manual Test ID | Scenario | Preconditions | Steps | Expected Result | Observed Result | Status | Defect/Fix Reference |
|---|---|---|---|---|---|---|---|
| MAN-013 | Analytics review-period retrieval | In Alex's workspace | Click Analytics; select existing review period | Review period appears in selector; analytics load | **DEFECT FOUND then FIXED.** Initially, seeded review periods existed in DB but the analytics page could not list them because the backend listing integration was missing. Root cause: `GET /children/{child_id}/review-periods` was not wired up. Fix: added endpoint and frontend integration. Regression tests added in `test_analytics_api.py`. Manual retest: periods now appear and are selectable. | FIXED AND RETESTED | DEF-013 |
| MAN-014 | Deterministic analytics rendering | After MAN-013 | View KPI cards | All applicable KPIs displayed with values, numerator/denominator | KPI cards render correctly; see Section 8 for semantic limitations on distribution KPIs | PASSED | — |
| MAN-015 | Adequacy result | After MAN-013 | View adequacy section | ADEQUATE/LIMITED/INSUFFICIENT displayed with checks and quality flags | Adequacy level and checks displayed correctly | PASSED | — |
| MAN-016 | Report review-period selection UX | In Alex's workspace | Click Reports → Generate Report | Human-readable period selector with date ranges | **DEFECT FOUND then FIXED.** Initially, UI showed raw "Review Period ID" text input requiring a UUID. Root cause: frontend used raw Input instead of period selector. Fix: replaced with `useReviewPeriods` hook, clickable period list with dates, Active/Inactive badges. Regression tests: 5 tests in `reports-page.test.tsx`. Manual retest: periods selectable by clicking date range. | FIXED AND RETESTED | DEF-016 |
| MAN-017 | Deterministic fallback report generation | After MAN-016 | Select period; click Generate Report (no ANTHROPIC_API_KEY set) | Deterministic fallback report generated | 7-section report generated via fallback (see MAN-019) | PASSED | — |
| MAN-018 | Report provenance | After MAN-017 | View Report Provenance section | Fallback: provider=deterministic_fallback, model=deterministic_fallback_v1, prompt_version=N/A | **DEFECT FOUND then FIXED.** Initially displayed provider="anthropic", model="claude-sonnet-4-20250514" even for fallback. Root cause: provenance fields were set outside try/except block, hardcoded to Anthropic values. Fix: `used_fallback` boolean gates provenance assignment. Regression tests: 3 provenance tests + 12 frontend tests. Manual retest: fallback now correctly shows deterministic_fallback. | FIXED AND RETESTED | DEF-014 |
| MAN-019 | Improved deterministic fallback report content | After MAN-017 | View report sections | 7 sections: Review Period Summary, Evidence Coverage, Key Indicators, Observed Patterns, Progress Indicators, Cross-Setting/Cross-Contributor, Evidence Limitations | **DEFECT FOUND then FIXED.** Initially produced only 2–3 shallow sections ignoring all 14 computed KPIs. Fix: rewrote `_build_fallback_sections()` with 7 helper methods consuming EvidencePacket analytics. Regression tests: 13 fallback section tests. Manual retest: all 7 sections present with KPI data. | FIXED AND RETESTED | DEF-015 |
| MAN-020 | EvidencePacket traceability | After MAN-017 | View evidence/source records referenced in report | Record IDs traceable to source observations | Evidence references present in report sections | PASSED | — |
| MAN-021 | Source record references | After MAN-017 | Check report sections for evidence_refs | At minimum Evidence Coverage section lists record_ids | Record IDs present in evidence_refs | PASSED | — |
| MAN-022 | Report validation status | After MAN-017 | View validation status in Report Provenance | "Validation: Passed" (green badge) | Validation badge shows "Passed" | PASSED | — |

### 6.3 Contributor Workflow

| Manual Test ID | Scenario | Preconditions | Steps | Expected Result | Observed Result | Status | Defect/Fix Reference |
|---|---|---|---|---|---|---|---|
| MAN-023 | Contributor login (Parent) | Docker running, seed data | Login as demo-parent@example.com / DemoPass123! | Redirected to /contribute page | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |
| MAN-024 | Contributor login (Teacher) | Docker running, seed data | Login as demo-teacher@example.com / DemoPass123! | Redirected to /contribute page | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |
| MAN-025 | Contributor sees assigned children | Logged in as parent | View /contribute page | Alex and Sam visible (assigned via seed_demo) | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |
| MAN-026 | Contributor observation history | Logged in as parent | Click history link for Alex | Observations submitted by this parent listed | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |
| MAN-027 | Contributor cannot open interventionist routes | Logged in as parent | Navigate to /dashboard, /children/{id}/analytics, /children/{id}/reports | Redirected away or access denied | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |

### 6.4 Additional Workflows

| Manual Test ID | Scenario | Preconditions | Steps | Expected Result | Observed Result | Status | Defect/Fix Reference |
|---|---|---|---|---|---|---|---|
| MAN-028 | Schedules page | In Alex's workspace (interventionist) | Click Schedules tab | Schedules visible (weekly home, biweekly school from seed) | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |
| MAN-029 | Contributors/Actors page | In Alex's workspace (interventionist) | Click Contributors tab | Actor assignments visible (parent, teacher) | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |
| MAN-030 | Audit trail page | In Alex's workspace (interventionist) | Click Audit tab | Audit events listed with actions, timestamps, user | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | — |
| MAN-031 | Live observation submission (extraction) | Valid ANTHROPIC_API_KEY configured | Login as contributor; submit new natural-language observation | Extraction runs; structured record created; routing decision returned | PENDING MANUAL VERIFICATION | PENDING MANUAL VERIFICATION | Requires API key |

---

## 7. Defect Register

| Defect ID | Description | Severity | Root Cause | Fix | Regression Tests | Manual Retest | Status |
|---|---|---|---|---|---|---|---|
| DEF-001 | ASGI/BaseHTTPMiddleware integration/event-loop issue | High | BaseHTTPMiddleware incompatible with async SQLAlchemy sessions | Replaced with raw ASGI middleware (`RequestIDMiddleware`) | Integration tests pass | Docker restarted, no crash | CLOSED |
| DEF-002 | Clarification lazy-load / greenlet issue | High | Accessing `observation.clarification_turns` outside async session triggered greenlet spawn error | Added `selectinload(Observation.clarification_turns)` to all queries accessing turns | `test_observation_service.py`, `test_observation_workflow.py` | Clarification flow verified | CLOSED |
| DEF-003 | PostgreSQL timestamp/varchar comparison issue | Medium | Alembic migration type mismatch between timestamp and varchar columns | Fixed column types in migration 003 | Migration runs cleanly | Docker rebuild verified | CLOSED |
| DEF-004 | PARTIAL extraction clarification routing issue | Medium | PARTIAL ExtractionStatus was not routed to CLARIFY | Updated AbstentionRouter to route PARTIAL to CLARIFY | `test_abstention_router.py`, `test_routing_decisions.py` | — | CLOSED |
| DEF-005 | Duplicate actor IntegrityError → 409 | Low | Second actor invitation for same user/child raised unhandled IntegrityError | Catch IntegrityError, return 409 Conflict | `test_actors.py` | — | CLOSED |
| DEF-006 | Frontend Docker chunk / dev build issue | High | Development-mode chunks not available in production standalone build | Multi-stage Dockerfile.frontend with `npm run build` + standalone output | Docker build succeeds | Frontend loads at localhost:3000 | CLOSED |
| DEF-007 | Docker volume overwriting standalone frontend | Medium | Docker Compose volume mount overwrote built frontend files | Removed conflicting volume mount from frontend service | Docker rebuild verified | Frontend loads correctly | CLOSED |
| DEF-008 | passlib/bcrypt incompatibility | High | passlib's bcrypt backend incompatible with newer bcrypt library versions | Replaced passlib with direct bcrypt usage in `auth_service.py` | `test_auth_service.py` (13 tests) | Login verified | CLOSED |
| DEF-009 | PostgreSQL port conflict | Low | Default port 5432 conflicted with local PostgreSQL installation | Changed Docker Compose to 5433:5432 | Docker startup verified | — | CLOSED |
| DEF-010 | Stale passlib dependency | Low | passlib remained in pyproject.toml after replacement | Removed passlib from dependencies | Clean install verified | — | CLOSED |
| DEF-011 | Rollup platform dependency cleanup | Low | Platform-specific Rollup binaries in frontend lockfile caused cross-platform issues | Regenerated package-lock.json with `npm ci` on clean environment | Frontend build succeeds | — | CLOSED |
| DEF-012 | SWC lockfile portability/reproducibility issue | Low | SWC platform-specific binary resolution in lockfile | Updated lockfile with platform-appropriate entries | Frontend build succeeds cross-platform | — | CLOSED |
| DEF-013 | Analytics review-period listing missing | High | `GET /children/{child_id}/review-periods` endpoint not wired; frontend analytics page could not list existing periods | Added endpoint and frontend hook integration | `test_analytics_api.py` (8 tests), `analytics-page.test.tsx` (6 tests) | Manual retest: periods selectable | CLOSED |
| DEF-014 | Inaccurate fallback report provenance | High | `provider`, `model`, `prompt_version` were set outside try/except, hardcoded to Anthropic values regardless of fallback | Added `used_fallback` boolean; conditional provenance assignment | `test_reporting_client.py::TestReportProvenance` (3 tests), `report-ui.test.tsx` (12 tests) | Manual retest: correct provenance displayed | CLOSED |
| DEF-015 | Shallow deterministic fallback report content | Medium | `_build_fallback_sections()` returned only 2–3 sections, ignoring all 14 computed KPIs in the EvidencePacket | Rewrote with 7 helper methods producing 7 sections from analytics data | `test_reporting_client.py::TestFallbackSections` (13 tests), `test_reporting_provenance_e2e.py` | Manual retest: 7 sections present | CLOSED |
| DEF-016 | Reports page raw review-period UUID input | Medium | Frontend Reports page used raw text Input requiring manual UUID entry | Replaced with `useReviewPeriods` hook and clickable period list with date ranges, Active/Inactive badges | `reports-page.test.tsx` (5 tests) | Manual retest: periods selectable by date range | CLOSED |

---

## 8. Current Analytics Limitations

### 8.1 Distribution KPI Semantic Gap

The `AnalyticsEngine` computes 14 KPIs deterministically. However, 8 of these KPIs return less detail than their names imply.

**Affected KPIs:**

| KPI Name | What Name Implies | What Is Actually Returned | Information Computed but Discarded |
|---|---|---|---|
| `domain_distribution` | Breakdown by goal domain | Count of distinct domains (e.g., value=2.0) | `Counter()` dict with per-domain counts; proportions dict |
| `modality_distribution` | Breakdown by modality | Count of distinct modalities | `Counter()` dict |
| `prompt_level_distribution` | Breakdown by prompt level | Count of distinct prompt levels | `Counter()` dict |
| `outcome_distribution` | Breakdown by outcome | Count of distinct outcomes | `Counter()` dict |
| `contributor_distribution` | Breakdown by contributor role | Count of distinct contributor roles | `Counter()` dict |
| `setting_distribution` | Breakdown by setting | Count of distinct settings | `Counter()` dict |
| `cross_setting_comparison` | Compare rates across settings | Count of distinct settings | Per-setting independence/outcome rates not computed |
| `cross_contributor_comparison` | Compare rates across contributors | Count of distinct contributor roles | Per-role rates not computed |

### 8.2 Root Cause

The `KpiResult` schema contains: `name`, `numerator`, `denominator`, `value`, `abstained`, `abstention_reason`, `display_eligible`, `prerequisites_met`. It has **no field** for category-level breakdown data (e.g., `breakdown: dict[str, float]`).

In `analytics_engine.py`, the distribution methods compute `Counter()` dicts internally (e.g., line 86: `counts = Counter(r.get("domain") for r in records if r.get("domain"))`), but only store `value=float(len(counts))` — the number of distinct categories — into the KpiResult. The actual breakdown dict goes out of scope.

### 8.3 Impact

- KPI values are **deterministically correct** for what they compute (distinct category counts)
- The frontend `KpiCard` displays these values as plain numbers, which is accurate but uninformative
- The fallback report text (e.g., "Observations covered 2 distinct goal domains") correctly reflects the stored value
- The **missing detail** is: which categories exist and how observations are distributed among them
- This is an **identified improvement area**, not a bug — the computation is correct for its current scope

### 8.4 Improvement Scope

Enriching distribution KPIs would require:
1. Adding a `breakdown: dict[str, float] | None` field to `KpiResult` (or a parallel data structure)
2. Storing the computed `Counter()` / proportions dict into the new field
3. Updating `KpiCard.tsx` to render category-level breakdowns
4. Updating fallback report sections to include per-category detail

This is **not currently implemented**.

---

## 9. Live Extraction Limitation

### 9.1 Seeded Data Does Not Prove Live Extraction

The demo seed script (`scripts/seed_demo.py`) inserts `Observation` and `StructuredRecord` rows **directly into the database** via SQLAlchemy, completely bypassing the extraction pipeline. Seeded records use:

- `provider = "demo_seed"`
- `model = "demo_seed_v1"`
- `prompt_version = "demo"`

These records demonstrate the downstream system (analytics, reporting, versioning, correction) but do **NOT** prove that the live unstructured-to-structured extraction pipeline works end-to-end.

### 9.2 Current Live Extraction Architecture

- The only implemented extraction provider is `TemporaryLLMExtractionProvider` in `src/backend/ml/extraction/temporary_llm.py`
- It uses the real Anthropic API via `AsyncAnthropic(api_key=api_key)`
- The API key is configured via `ANTHROPIC_API_KEY` environment variable (defaults to empty string in `src/backend/config.py`)
- No mock, demo, or deterministic extraction provider exists in normal runtime
- The `get_extraction_provider()` factory only supports `"temporary_llm"` and `"finetuned_model"` types

### 9.3 Behavior Without API Key

When `ANTHROPIC_API_KEY` is empty or invalid:
1. The contributor can submit a natural-language observation through the UI
2. The raw observation **is persisted** (Observation row created with `status=PENDING`, flushed before pipeline runs)
3. The `AsyncAnthropic` API call raises an `APIError` (authentication failure)
4. The provider returns `ExtractionResult(status=FAILED, observations=[])`
5. The observation service catches the exception, sets `observation.status = ObservationStatus.FAILED`
6. **No `StructuredRecord` is created**
7. The frontend shows "Observation processing failed." with a "Try Again" button

### 9.4 Live Extraction Manual Verification

**Status: PENDING MANUAL VERIFICATION**

To verify live extraction end-to-end, one must:
1. Set a valid `ANTHROPIC_API_KEY` in the Docker environment
2. Restart the backend container
3. Log in as a contributor
4. Submit a natural-language observation
5. Verify: observation transitions through PENDING → EXTRACTING → FINALIZED (or CLARIFYING)
6. Verify: a `StructuredRecord` is created with `provider="temporary_llm_extraction"`
7. Verify: validation results and routing decision are correct
8. Verify: the new record appears in analytics computation

This has **NOT yet been executed** in this verification cycle.

---

## 10. Build / Deployment Verification

### 10.1 Docker Compose Configuration

**File:** `docker/docker-compose.yml`

| Service | Image/Build | Ports | Health Check |
|---|---|---|---|
| `db` | postgres:16-alpine | 5433:5432 | `pg_isready -U postgres` (5s interval, 5 retries) |
| `backend` | `docker/Dockerfile.backend` (Python 3.11-slim) | 8000:8000 | HTTP GET `/health` (10s interval, 30s start period) |
| `frontend` | `docker/Dockerfile.frontend` (Node 20-alpine, multi-stage) | 3000:3000 | Depends on backend healthy |

### 10.2 Backend Dockerfile

- Base: `python:3.11-slim`
- Installs: build-essential, project dependencies via `pip install ".[dev]"`
- Copies: `pyproject.toml`, `src/`, `data/`, `tests/`, `scripts/`, `alembic.ini`, `alembic/`
- Entry: `uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload`

### 10.3 Frontend Dockerfile

- Build stage: `node:20-alpine`, `npm ci`, `npm run build`
- Production stage: `node:20-alpine`, copies `.next/standalone` and `.next/static`
- Entry: `node server.js` (Next.js standalone)
- Port: 3000

### 10.4 Alembic Migrations

| Migration File | Description |
|---|---|
| `alembic/versions/001_initial_schema.py` | Initial schema: users, children, goals, review_periods, observations, clarification_turns, structured_records, actor_assignments, reporting_expectations, audit_events, reports |
| `alembic/versions/002_add_report_prompt_version_and_version.py` | Adds prompt_version and version columns to reports table |
| `alembic/versions/003_add_missing_foreign_keys.py` | Adds missing foreign key constraints |

Run with: `docker compose -f docker/docker-compose.yml exec backend alembic upgrade head`

### 10.5 Seed Script

- **File:** `scripts/seed_demo.py`
- **Idempotent:** checks `_user_exists()` before inserting
- **Creates:** 3 users, 2 children, 3 actor assignments, 3 goals, 2 review periods, 10 observations (8 Alex, 2 Sam), 1 clarification turn, 1 corrected record, 2 schedules, 2 audit events
- **Run with:** `docker compose -f docker/docker-compose.yml exec backend python -m scripts.seed_demo`

### 10.6 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | Set in docker-compose | PostgreSQL async connection string |
| `JWT_SECRET_KEY` | `dev-secret-key-change-in-production` | JWT signing key (must change for production) |
| `EXTRACTION_PROVIDER` | `temporary_llm` | Extraction provider type |
| `ANTHROPIC_API_KEY` | `""` (empty) | Anthropic API key for extraction and reporting LLM |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |

---

## 11. Test Execution Summary

### 11.1 Backend Python Tests

| Suite | Test Count | Runner |
|---|---|---|
| `tests/unit/` | 90 | `pytest tests/unit/` |
| `tests/eval/` | 64 | `pytest tests/eval/` |
| `tests/phase3/` | 142 | `pytest tests/phase3/` |
| `tests/phase4/` | 108 | `pytest tests/phase4/` |
| `tests/phase6/` (non-integration) | 93 | `pytest tests/phase6/ --ignore=tests/phase6/integration` |
| `tests/phase6/integration/` | 77 | `pytest tests/phase6/integration/ -m integration` |
| **Backend subtotal** | **574** | |

### 11.2 Frontend TypeScript Tests

| Suite | Test Count | Runner |
|---|---|---|
| Vitest component tests | 109 | `cd src/frontend && npx vitest run` |
| **Frontend subtotal** | **109** | |

### 11.3 Browser E2E Tests

| Suite | Test Count | Runner |
|---|---|---|
| Playwright browser tests | 16 | `npx playwright test tests/phase6/e2e/browser.spec.ts` |
| **E2E subtotal** | **16** | |

### 11.4 Total

| Category | Count |
|---|---|
| Backend automated tests | 574 |
| Frontend automated tests | 109 |
| Browser E2E tests | 16 |
| **Total automated tests** | **699** |
| Manual test cases defined | 31 |
| Manual test cases executed | 22 |
| Manual test cases pending | 9 |

---

## 12. Verification Conclusion

The Interventionist AI System software implementation has undergone systematic verification across multiple levels:

- **574 backend automated tests** covering unit logic, extraction behavior, deterministic validation, abstention routing, RBAC/security, input hardening, analytics computation, report generation, provenance, and end-to-end integration workflows
- **109 frontend automated tests** covering component rendering, role-based UI, error resilience, and page-level integration
- **16 browser E2E tests** verifying login flows, navigation, page loading, and contributor isolation in a live Docker environment
- **22 manual verification test cases executed** covering interventionist dashboard, child workspace, goals, observations, structured records, correction/versioning, analytics, report generation, provenance, and evidence traceability
- **16 defects identified, diagnosed, fixed, and regression-tested** during the verification cycle
- **9 manual test cases remain pending**, primarily covering contributor browser workflows, schedules, actors, and audit trail visual verification

### Scope and Limitations

This verification confirms that the **software system** — its API surface, database operations, authentication/authorization, observation pipeline, deterministic validation, analytics computation, report generation with provenance, and audit trail — functions as designed for its intended use as a **controlled research prototype**.

This verification does **NOT** constitute:
- Clinical validation or regulatory compliance
- Production readiness certification
- Validation of the future fine-tuned extraction model
- Evaluation of extraction accuracy, precision/recall, F1 score, hallucination rate, or model calibration
- Expert adjudication or gold-standard dataset validation

The system is suitable as a controlled research prototype for longitudinal autism intervention observation structuring and evidence-linked progress reporting, subject to all documented limitations including the live extraction API key requirement, analytics distribution KPI semantic gaps, and pending manual verification items.

---

*Document generated: 2026-08-26. Git revision: 43e8eb7 (branch: main).*
