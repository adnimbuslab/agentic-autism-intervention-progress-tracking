---
name: backend-api
description: Implements the FastAPI backend — database models, auth/RBAC, child workspace management, observation orchestration, schedule engine, audit logging, and all API endpoints with child-level authorization.
model: sonnet
tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Backend API Agent

You are building the FastAPI backend for a governance-aware autism intervention monitoring system. The backend enforces strict role-based access control, manages child workspaces, orchestrates the observation pipeline, and provides APIs for the frontend dashboard.

## Core Principles
- Child-level authorization on EVERY endpoint and database query
- Immutable observation store — original text is never modified
- Corrections create new versioned records, not updates
- All actions audit-logged with actor, timestamp, and event type
- Contributors cannot access professional analytics or reports
- The API never returns data for unauthorized children

## Extraction Provider Boundary

During the current application-development phase, observation extraction
uses `TemporaryLLMExtractionProvider`.

Backend services MUST NOT call a specific LLM vendor directly.

`observation_service.py` must call the common `ExtractionProvider`
interface.

Current implementation:
- `TemporaryLLMExtractionProvider`

Future implementation:
- `FineTunedExtractionProvider`

Both providers must return the same `ExtractionResult` contract.

Provider selection must be configuration-driven:

EXTRACTION_PROVIDER=temporary_llm

Later:

EXTRACTION_PROVIDER=finetuned_model

Replacing the extraction provider must NOT require changes to:
- API endpoints
- database models
- deterministic validation
- abstention/clarification routing
- analytics
- reporting
- frontend contracts

## Project Setup

### Directory Structure
```
src/backend/
  main.py                    # FastAPI app entry point
  config.py                  # Settings, env vars
  database.py                # SQLAlchemy engine, session
  api/
    __init__.py
    auth.py                  # OAuth2/OIDC, token validation
    children.py              # Child workspace CRUD
    goals.py                 # Goal definition, indicators
    actors.py                # Actor invitation, enrollment, revocation
    observations.py          # Observation submission, retrieval
    schedules.py             # Schedule configuration, overdue tracking
    structured_records.py    # Structured record review, correction
    analytics.py             # KPI retrieval (computed by analytics engine)
    reports.py               # Report generation trigger, retrieval
    audit.py                 # Audit trail queries (interventionist only)
  models/
    __init__.py
    user.py                  # User, Role enum
    child.py                 # Child workspace
    goal.py                  # Goal, Indicator, ReviewPeriod
    observation.py           # Observation (immutable), StructuredRecord (versioned)
    schedule.py              # ReportingExpectation, OverdueEvent
    actor.py                 # ActorAssignment, InvitationEvent
    report.py                # GeneratedReport, ReportFlag
    audit.py                 # AuditEvent
  services/
    __init__.py
    auth_service.py          # RBAC logic, permission checks
    workspace_service.py     # Child workspace operations
    observation_service.py   # Observation intake pipeline
    schedule_service.py      # Due date tracking, overdue detection
    notification_service.py  # Email/SMS sending
    audit_service.py         # Audit event creation
  ml/
    extraction/
      __init__.py
      base.py                # ExtractionProvider interface
      temporary_llm.py       # Current temporary LLM provider
      finetuned_model.py     # Future foundation-model provider stub
      prompts.py             # Structured extraction prompts
      schemas.py             # ExtractionRequest / ExtractionResult
    validation_engine.py     # Deterministic schema validation
    abstention_router.py     # Clarification and abstention routing
    adequacy_router.py       # Adequacy/representation checks
    analytics_engine.py      # Deterministic KPI computation
    reporting_client.py      # Call grounded reporting LLM
  schemas/
    __init__.py
    observation_schema.py    # Pydantic models for structured records
    api_schemas.py           # Request/response models
```

### Tech Stack
- Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic
- PostgreSQL with Row-Level Security (RLS)
- Pydantic v2 for all data models
- OAuth 2.0 / OIDC for auth (python-jose for JWT)
- Celery or asyncio tasks for pipeline orchestration

## Database Models

### Key Tables (implement with SQLAlchemy)

```
users (id, email, name, role, created_at, is_active)
  - role: ENUM('interventionist', 'parent', 'teacher', 'trainer', 'epa', 'secondary_interventionist')

children (id, created_by, name_pseudonym, background_context, created_at)
  - created_by → users.id (must be interventionist)

actor_assignments (id, user_id, child_id, role, assigned_by, active, assigned_at, revoked_at)
  - Enforces who can see/submit for which child

goals (id, child_id, type, domain, description, observable_indicators, created_by, version, active, created_at)
  - type: ENUM('long_term', 'short_term')
  - domain: ENUM('functional_communication', 'social_interaction', 'play', 'behavior_regulation', ...)

review_periods (id, child_id, goal_id, start_date, end_date, status, created_by)

observations (id, child_id, submitted_by, goal_id, setting, raw_text, conversation_json, submitted_at)
  - IMMUTABLE: no UPDATE or DELETE allowed
  - raw_text is the canonical source evidence

structured_records (id, observation_id, version, fields_json, confidence, status, created_by_model, model_version, corrected_by, correction_reason, created_at)
  - status: ENUM('pending', 'validated', 'corrected', 'rejected', 'abstained')
  - version increments on correction; observation_id links to immutable source

reporting_expectations (id, child_id, goal_id, actor_id, setting, cadence, time_window, grace_period, active, created_by)

overdue_events (id, expectation_id, due_date, status, reminder_sent_at, resolved_at)

generated_reports (id, child_id, review_period_id, evidence_packet_json, report_text, model_version, generated_at, reviewed_by, review_status)

audit_events (id, actor_id, event_type, target_type, target_id, details_json, timestamp)
  - APPEND-ONLY: no UPDATE or DELETE
```

### Row-Level Security
Every query must filter by child_id based on the authenticated user's actor_assignments. Implement as:
1. A `get_authorized_children(user_id)` function
2. A SQLAlchemy query filter applied to every child-related query
3. API-level checks before any data access

## API Endpoints

### Auth
- `POST /auth/login` — OAuth2 token exchange
- `GET /auth/me` — Current user profile and roles

### Children (Interventionist only)
- `POST /children` — Create child workspace
- `GET /children` — List authorized children
- `GET /children/{id}` — Get child detail
- `PATCH /children/{id}` — Update background context

### Goals (Interventionist only)
- `POST /children/{id}/goals` — Create goal
- `GET /children/{id}/goals` — List goals
- `PATCH /goals/{id}` — Update goal (creates new version)

### Actors (Interventionist only)
- `POST /children/{id}/actors` — Invite actor (sends email)
- `GET /children/{id}/actors` — List assigned actors
- `DELETE /actors/{id}` — Revoke access (preserves history)

### Observations (Authorized actors)

- `POST /children/{id}/observations` — Submit initial free-text observation
- `POST /observations/{id}/clarifications` — Submit contributor response to a focused clarification question
- `GET /observations/{id}/conversation` — Retrieve the contributor's observation/clarification conversation
- `POST /observations/{id}/finalize` — Finalize the observation after clarification is complete or the contributor declines/does not know
- `GET /children/{id}/observations` — List observations (scoped by role)
- `GET /observations/{id}` — Get observation with structured record, subject to role permissions

### Structured Records (Interventionist)
- `GET /children/{id}/records` — List structured records
- `POST /records/{id}/correct` — Submit correction (creates new version)
- `GET /records/{id}/history` — Version history

### Schedules (Interventionist)
- `POST /children/{id}/schedules` — Configure reporting expectation
- `GET /children/{id}/schedules` — List schedules with overdue status

### Analytics (Interventionist)
- `GET /children/{id}/analytics?goal_id=&period_id=` — Get KPIs (or abstention reason)

### Reports (Interventionist)
- `POST /children/{id}/reports/generate` — Trigger report generation
- `GET /reports/{id}` — Get report with evidence drill-down
- `POST /reports/{id}/flag` — Flag inaccurate statement

### Audit (Interventionist)
- `GET /children/{id}/audit` — Audit trail for a child

## Security Requirements
- All endpoints require valid JWT
- Child-level authorization checked on every request
- Rate limiting on observation submission
- Input validation on all user-provided text
- No raw SQL — use parameterized queries via SQLAlchemy
- Secrets in environment variables, never in code
- CORS configured for frontend origin only
