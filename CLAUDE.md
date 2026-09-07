# Interventionist AI System

## Project Overview
A governance-aware, human-in-the-loop AI system for structuring longitudinal autism intervention observations and generating evidence-linked progress reports. Based on the JMIR AI research paper (V3 draft).

## Current Development Phase

The current phase builds the complete working application and CHAT
processing pipeline using a temporary general-purpose LLM.

Do NOT train or fine-tune the final foundation model during this phase.

Current extraction architecture:

ExtractionProvider
    ├── TemporaryLLMExtractionProvider   [CURRENT]
    └── FineTunedExtractionProvider      [FUTURE]

Both providers must return the same `ExtractionResult` contract.

The temporary LLM is used for:
- conversational observations submitted by contributors
- selected behavioral segments produced from CHAT transcripts

CHAT processing IS part of the current phase:
- parsing
- unified dataset generation
- deidentification
- episode segmentation
- behavioral segment selection
- provisional LLM structured extraction

LLM-generated CHAT structured records are provisional and are NOT
expert gold-standard research labels.

Deferred until later:
- expert adjudicated gold-standard dataset finalization
- foundation-model fine-tuning
- LoRA/QLoRA training
- final baseline comparison
- frozen held-out research-model evaluation

The future fine-tuned model must replace the temporary extraction
provider without requiring changes to backend APIs, persistence,
validation, abstention, analytics, reporting, or frontend behavior.

## Architecture (4 Layers)
1. **Presentation**: Interventionist Dashboard, Contributor Observation UI, Admin/Role Management, Notification Service
2. **Application**: Auth/RBAC, Child Workspace Manager, Schedule Engine, Observation Orchestrator, Audit Logger
3. **AI/ML**: Pluggable Extraction Provider (temporary general-purpose LLM now; fine-tuned foundation model later), Deterministic Validation Engine, Adequacy/Abstention Router, Analytics Engine, Reporting LLM
4. **Data**: Observation Store (immutable), Structured Record Store (versioned), Goal/Schedule Registry, Audit Trail, Model Version Registry

## Key Design Principles
- AI extracts/communicates; it never diagnoses, prescribes, or modifies goals
- LLM outputs pass through deterministic validation before persistence
- All analytics computed by code, never by LLM
- Abstention is a first-class output when evidence is inadequate
- Every report statement traces back to source observation
- Child-level RBAC enforced at both UI and API layers
- Contributors submit observations through a conversational/chat-style interface
- The system may ask focused, non-leading clarification questions when important information is ambiguous
- Contributors do not see structured extraction fields, model confidence scores, professional analytics, or cross-setting reports
- The complete observation and clarification conversation is preserved as source evidence

## Data Sources
- **Rollins Corpus**: 5 children, 21 sessions, 11,020 utterances (child-investigator, ASDBank)
- **Flusberg Corpus**: 6 children, 65 sessions, ~57,000 utterances (child-parent, ASDBank)
- **Combined**: 11 children, 85 sessions, 75,003 utterances in CHAT format
- Source data in `exp-data/`

## Tech Stack (Planned)
- **Frontend**: React / Next.js + TypeScript
- **Backend**: Python (FastAPI)
- **Database**: PostgreSQL with row-level security
- **Auth**: OAuth 2.0 / OpenID Connect
- **ML Serving**: vLLM or Cloud LLM API
- **Agentic Framework**: LangChain + LangGraph (pipeline orchestration, stateful agent graph with conditional routing, clarification loops, and checkpointing for async human-in-the-loop)
- **Notifications**: SendGrid (email), Twilio (SMS)
- **Deployment**: Docker / Kubernetes

## Project Structure
```
interventionist/
  .claude/agents/          # Sub-agent definitions
  src/
    backend/               # FastAPI backend
      api/                 # API routes
      models/              # SQLAlchemy models
      services/            # Business logic
      ml/                  # ML pipeline (extraction, validation, reporting)
    frontend/              # Next.js frontend
      components/          # React components
      pages/               # Next.js pages
    shared/                # Shared types/schemas
  data/
    pipeline/              # CHAT parsing, preprocessing scripts
    annotation/            # Annotation tools and schema
    training/              # Reserved for later foundation-model fine-tuning phase
  tests/
  docker/
  docs/
```

## Coding Conventions
- Python: type hints everywhere, pydantic models for all data contracts
- API: RESTful with OpenAPI docs, all endpoints require auth
- Database: migrations via Alembic, child-level RLS on every table
- Tests: pytest, child-level split must be tested for leakage
- Frontend: TypeScript strict mode, server components by default
- Never store raw LLM output directly — always validate through deterministic layer first
- Immutable observation store: never UPDATE or DELETE original text
- All model invocations logged with version, config hash, and timestamp

## Safety Rules
- The extraction provider MUST NOT generate field values not supported by the source text
- Backend business logic MUST NOT call a specific LLM vendor directly; all extraction must go through `ExtractionProvider`
- The reporting LLM MUST NOT produce diagnostic statements, treatment recommendations, or causal claims
- Analytics MUST be withheld when adequacy checks fail — never force a conclusion
- Corrections create new record versions — never overwrite originals
- Contributor roles cannot access professional analytics or cross-setting reports
- All API endpoints enforce child-level authorization; negative tests required

## Key Documents
- `JMIR_AI_Autism_Longitudinal_Intervention_Draft_V3_Operational_Workflow.docx` — Research paper
- `Technical_Specification_Autism_AI_System.docx` — Technical spec with diagrams
- `exp-data/Rollins/` — Rollins CHAT transcripts
- `exp-data/Flusberg.zip` — Flusberg CHAT transcripts
- `exp-data/data repos.docx` — Data source notes

## Sub-Agents

Use the specialized agents in `.claude/agents/` for implementation:

- `data-pipeline` — CHAT parsing, deidentification, episode segmentation, segment selection, and temporary LLM provisional structured extraction
- `backend-api` — FastAPI backend, database models, auth/RBAC, conversational observation orchestration, schedules, notifications, and extraction-provider integration
- `ml-pipeline` — Temporary LLM extraction provider, deterministic validation, clarification/abstention, adequacy checks, deterministic analytics, and grounded reporting LLM; final foundation-model fine-tuning is deferred
- `frontend` — React/Next.js interventionist dashboard and contributor conversational observation interface
- `eval-harness` — Application, safety, robustness, temporary-LLM, validation, analytics, reporting, and integration testing; final foundation-model research evaluation is deferred
