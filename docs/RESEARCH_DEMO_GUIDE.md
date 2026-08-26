# Research Demo Guide

## Overview

This system is a governance-aware, human-in-the-loop AI platform for
structuring longitudinal autism intervention observations and generating
evidence-linked progress reports. It is built for the JMIR AI research paper
(V3 draft).

**This is a research demonstration — not a clinically validated or
production-ready system.** All outputs are provisional and require expert
review.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                   Presentation Layer                        │
│  Interventionist Dashboard  │  Contributor Observation UI   │
└──────────────┬──────────────┴──────────────┬────────────────┘
               │                             │
┌──────────────▼─────────────────────────────▼────────────────┐
│                   Application Layer                         │
│  Auth/RBAC │ Child Workspace │ Schedule │ Audit Logger      │
│  Observation Orchestrator (LangGraph state machine)         │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                     AI/ML Layer                             │
│  ExtractionProvider (Temporary LLM ↔ Future Fine-Tuned)     │
│  ValidationEngine │ AbstentionRouter │ AdequacyRouter       │
│  AnalyticsEngine │ ReportingClient (grounded reporting)     │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                      Data Layer                             │
│  Observations (immutable) │ StructuredRecords (versioned)   │
│  Goals/Schedules │ Audit Trail │ Model Version Registry     │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Node.js 20+
- PostgreSQL 16 (provided via Docker)
- Git

---

## Quick Start

### 1. Clone and Configure

```bash
git clone <repository-url>
cd agentic-autism-intervention-progress-tracking
cp .env.example .env
# Edit .env with a real ANTHROPIC_API_KEY or use mock mode
```

### 2. Start the Stack

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

This starts:
- **PostgreSQL** on port 5433 (host) → 5432 (container)
- **FastAPI backend** on port 8000
- **Next.js frontend** on port 3000

### 3. Apply Database Migrations

```bash
docker compose -f docker/docker-compose.yml exec backend alembic upgrade head
```

### 4. Seed Demo Data

```bash
docker compose -f docker/docker-compose.yml exec backend python -m scripts.seed_demo
```

### 5. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API docs**: http://localhost:8000/docs

---

## Demo Credentials

| Role             | Email                              | Password      |
|------------------|------------------------------------|---------------|
| Interventionist  | demo-interventionist@example.com   | DemoPass123!  |
| Parent           | demo-parent@example.com            | DemoPass123!  |
| Teacher          | demo-teacher@example.com           | DemoPass123!  |

---

## Demo Walkthrough

### Interventionist Flow

1. **Login** as `demo-interventionist@example.com`
2. **Dashboard** → see assigned children (Alex, Sam)
3. **Child workspace** → click on Alex
4. **Goals** → view/create intervention goals
5. **Observations** → see submitted observations from contributors
6. **Records** → inspect structured extraction records
7. **Record detail** → view validation, confidence, fields
8. **Correction** → correct a structured record; verify new version
9. **Analytics** → view deterministic KPIs (adequacy-gated)
10. **Reports** → generate a progress report (mocked LLM for demo)
11. **Report detail** → view report sections and evidence provenance
12. **Audit trail** → see all system events

### Contributor Flow

1. **Login** as `demo-parent@example.com`
2. **Contribute** → see assigned children
3. **Observe** → submit a conversational observation
4. **Clarification** → if prompted, answer a focused question
5. **History** → view own submission history

### Key Behaviors to Observe

- **Immutability**: original observation text never changes
- **Versioning**: corrections create new record versions
- **RBAC**: contributors cannot access analytics, reports, or audit
- **Adequacy gating**: analytics are withheld when evidence is insufficient
- **Abstention**: fields without adequate evidence show "unknown"
- **Prohibited content validation**: reports are validated against 6 safety patterns
- **Evidence provenance**: every report statement traces to source records

---

## Demo Data Summary

| Entity             | Count | Notes                                      |
|--------------------|-------|--------------------------------------------|
| Users              | 3     | Interventionist, Parent, Teacher           |
| Children           | 2     | Alex (adequate data), Sam (limited data)   |
| Actor Assignments  | 3     | Parent→Alex, Teacher→Alex, Teacher→Sam     |
| Goals              | 3     | 2 for Alex, 1 for Sam                      |
| Review Periods     | 2     | 1 per child                                |
| Observations       | 10    | 8 for Alex (multi-setting), 2 for Sam      |
| Clarification Turn | 1     | Demonstrates clarification flow            |
| Corrected Record   | 1     | Demonstrates version history               |
| Schedules          | 2     | Weekly observation reminders                |
| Audit Events       | 2+    | System events for demo actions             |

All demo data is synthetic. No real children, participants, or protected
health information is used.

---

## CHAT Data Pipeline

The system also processes CHAT-format transcripts (.cha files) from the
ASDBank corpora:

```
.cha file → chat_parser → build_dataset → deidentify → segment_episodes
    → select_segments → ExtractionRequest → LLM extraction (provisional)
```

- **Rollins corpus**: 5 children, 21 sessions, ~11,000 utterances
- **Flusberg corpus**: 6 children, 65 sessions, ~57,000 utterances
- All names and PII are replaced during deidentification
- LLM-generated CHAT extractions are labeled "provisional" — not gold-standard

---

## Extraction Provider Architecture

```
ExtractionProvider (Protocol)
    ├── TemporaryLLMExtractionProvider   ← current (Claude API, tool_use)
    └── FineTunedExtractionProvider      ← future (deferred)
```

Both providers return the same `ExtractionResult` contract. The temporary
provider can be replaced without changing any backend API, validation,
analytics, reporting, or frontend behavior.

---

## Safety and Governance

### What the AI Does
- Extracts structured fields from conversational observations
- Summarizes deterministic findings in professional prose

### What the AI Does NOT Do
- Diagnose autism or any condition
- Prescribe or recommend treatments
- Make causal claims
- Calculate KPIs (all analytics are deterministic code)
- Modify intervention goals

### Validation Pipeline
1. **Extraction** → LLM extracts structured fields via tool_use
2. **Validation** → 8 deterministic checks (enums, critical fields, cross-field, confidence)
3. **Routing** → ACCEPT / CLARIFY / RETAIN / REVIEW / REJECT
4. **Abstention** → per-field and per-record abstention when evidence is inadequate
5. **Adequacy** → 6 checks (coverage, temporal, contributor, setting, goal, completeness)
6. **Analytics** → 14 deterministic KPIs (only when adequacy allows)
7. **Reporting** → grounded LLM prose validated against 6 prohibited patterns

---

## Test Suite

### Running Tests

```bash
# Backend unit tests
cd . && python -m pytest tests/ -v --ignore=tests/phase6/integration --ignore=tests/phase6/e2e

# Integration tests (requires PostgreSQL on port 5433)
TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/autism_tracker_integration_test" \
  python -m pytest tests/phase6/integration/ -v

# Frontend tests
cd src/frontend && npm test

# Browser E2E (requires running Docker stack + demo seed + Playwright)
npx playwright test tests/phase6/e2e/browser.spec.ts --config tests/phase6/e2e/playwright.config.ts
```

### Test Coverage Areas
- Extraction provider contract conformance
- Validation engine routing decisions
- Abstention and clarification flows
- Adequacy assessment (ADEQUATE/LIMITED/INSUFFICIENT)
- Deterministic analytics repeatability
- Report validation (prohibited content, evidence tracing)
- Child-level RBAC enforcement
- Observation immutability
- Record versioning and correction
- Audit trail completeness
- CHAT pipeline end-to-end (synthetic data only)
- Security hardening (prompt injection, boundary inputs)

---

## Limitations and Disclaimers

1. **Not clinically validated** — this is a research prototype
2. **Temporary extraction provider** — uses a general-purpose LLM, not a
   fine-tuned model; extraction quality is provisional
3. **No real patient data in demo** — all demo data is synthetic
4. **CHAT extractions are provisional** — not expert-adjudicated gold-standard
5. **Report validation is rule-based** — not guaranteed to catch all
   prohibited content in novel phrasings
6. **Single-instance deployment** — not designed for production scale

---

## Key Documents

| Document | Location |
|----------|----------|
| Research paper | `JMIR_AI_Autism_Longitudinal_Intervention_Draft_V3_Operational_Workflow.docx` |
| Technical spec | `docs/Technical_Specification_Autism_AI_System.docx` |
| Project instructions | `CLAUDE.md` |
| API documentation | http://localhost:8000/docs (when running) |
