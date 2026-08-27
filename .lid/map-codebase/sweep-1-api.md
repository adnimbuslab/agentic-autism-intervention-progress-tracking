# Sweep 1 — src/backend/api/

Recon sweep for map-codebase. Scope: all files directly under `src/backend/api/`
(12 files). Every file read in full. No clustering/design performed here —
raw per-file facts only.

Cross-cutting note (applies to every router file below): all routers are
registered in `src/backend/main.py` (lines 16-25, 138-147) via
`app.include_router(...)` with **no additional prefix** — so each router's own
`APIRouter(prefix=..., tags=...)` (or lack of prefix) determines the final
route path exactly as written in the file. `children.py` and `auth.py` set an
explicit `prefix`; the other 8 router files set `prefix=None` and instead
hardcode the full path (e.g. `/children/{child_id}/goals`) on every route
decorator — an inconsistent pattern across the same directory (see per-file
observations).

---

```yaml
- path: src/backend/api/__init__.py
  purpose: Package marker for src/backend/api as a Python package.
  exports: none (empty file)
  dependencies: none
  data_shapes: none
  side_effects: none
  role: Makes `src/backend/api` importable as a package; no re-exports, so all consumers import submodules directly (e.g. `src.backend.api.deps`, `src.backend.api.auth`).
  observations: File is completely empty (0 bytes). No `__all__`, no shared router aggregation — main.py imports each router individually rather than through this package's `__init__`. Confirms api/ has no central "router registry" module; that responsibility lives in src/backend/main.py instead.
```

```yaml
- path: src/backend/api/actors.py
  purpose: Endpoints for inviting, listing, and revoking actor (contributor/role) assignments on a child workspace.
  exports:
    - "POST /children/{child_id}/actors -> invite_actor (ActorResponse, 201)"
    - "GET /children/{child_id}/actors -> list_actors (list[ActorResponse])"
    - "DELETE /actors/{assignment_id} -> revoke_actor (ActorResponse)"
    - "router (APIRouter, tags=['actors'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, HTTPException, status"
    - "sqlalchemy.exc.IntegrityError"
    - "src.backend.api.deps: DBSession, RequireInterventionist, authorize_child_access"
    - "src.backend.schemas.api_schemas: ActorInvite, ActorResponse"
    - "src.backend.services: audit_service, auth_service, workspace_service"
    - "src.backend.models.actor.ActorAssignment (imported locally inside revoke_actor, line 84)"
  data_shapes:
    - "Consumes ActorInvite {email, role} on invite"
    - "Produces/consumes ActorResponse (assignment record) on all three endpoints"
    - "Emits audit detail dict {invited_user_id, role} on invite; no detail dict on revoke"
  side_effects:
    - "DB writes via workspace_service.invite_actor / revoke_actor"
    - "DB writes via audit_service.log_event (audit trail row per action)"
    - "db.commit() after each mutating call"
    - "Looks up user by email via auth_service.get_user_by_email (DB read)"
  role: "Presentation/Application boundary for RBAC actor-assignment management — lets an interventionist grant/revoke other users' (contributors', parents', etc.) access to a specific child's workspace."
  observations:
    - "Line 84: `from src.backend.models.actor import ActorAssignment as ActorModel` is a local import inside the function body rather than at module top, unlike every other model/service import in this codebase which is top-level. Inconsistent import style; unclear from code why this one is deferred (no obvious circular-import comment)."
    - "All three routes require RequireInterventionist — contributors/parents cannot see or manage actor assignments themselves, consistent with CLAUDE.md RBAC principle."
    - "invite_actor swallows only IntegrityError into a 409; any other exception from workspace_service.invite_actor propagates unhandled."
    - "No prefix set on the router (line 18) — paths are fully spelled out per route, unlike children.py/auth.py which use a router prefix."
```

```yaml
- path: src/backend/api/analytics.py
  purpose: Endpoints for computing deterministic analytics/adequacy for a child and for creating/listing review periods.
  exports:
    - "POST /children/{child_id}/analytics -> get_analytics (AnalyticsResponse)"
    - "GET /children/{child_id}/review-periods -> list_review_periods (list[ReviewPeriodResponse])"
    - "POST /children/{child_id}/review-periods -> create_review_period (ReviewPeriodResponse, 201)"
    - "router (APIRouter, tags=['analytics'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, HTTPException, status"
    - "src.backend.api.deps: DBSession, RequireInterventionist, authorize_child_access"
    - "src.backend.schemas.api_schemas: AdequacyCheckResponse, AdequacyResponse, AnalyticsRequest, AnalyticsResponse, KpiResponse, ReviewPeriodCreate, ReviewPeriodResponse"
    - "src.backend.services: analytics_service, audit_service"
    - "sqlalchemy.select (imported locally as sa_select, lines 97 and inside create_review_period is not re-imported but ReviewPeriod is, line 131)"
    - "src.backend.models.goal.ReviewPeriod (imported locally, lines 99 and 131)"
  data_shapes:
    - "Consumes AnalyticsRequest {review_period_id, goal_id}"
    - "Produces AnalyticsResponse with nested KpiResponse list (name, numerator, denominator, value, abstained, abstention_reason, display_eligible) and AdequacyResponse (level, eligible, checks: list[AdequacyCheckResponse], partial_abstentions, quality_flags)"
    - "Consumes ReviewPeriodCreate {start_date, end_date}; produces ReviewPeriodResponse {id, child_id, start_date, end_date, is_active, created_at}"
  side_effects:
    - "DB read via analytics_service.compute_analytics (join across observations/records presumably; not in scope to trace further)"
    - "DB write: creates ReviewPeriod row directly in this file (lines 133-139) rather than through a service function — the only place in this sweep where a router directly constructs and adds an ORM model"
    - "audit_service.log_event on both compute_analytics and create_review_period"
    - "db.commit() / db.flush() / db.refresh()"
  role: "Application/AI-ML boundary — exposes the deterministic Analytics Engine and Adequacy/Abstention Router outputs described in CLAUDE.md to interventionists, and manages the review-period entities analytics are scoped to."
  observations:
    - "Lines 97-99 and 131: local imports of `select as sa_select` and `ReviewPeriod` inside function bodies instead of module-level imports — same inconsistent-import pattern seen in actors.py line 84. No accompanying comment explaining why."
    - "create_review_period (lines 122-159) builds and persists a ReviewPeriod ORM object directly in the API layer instead of delegating to a workspace/schedule service, breaking the pattern used by every other create-endpoint in this directory (which all call into `*_service.create_*`). This is a notable inconsistency / layering violation relative to children.py, goals.py, schedules.py, actors.py.
    - "get_analytics only catches ValueError -> 404 (line 37-38); unclear from code what triggers ValueError vs. other exceptions in analytics_service.compute_analytics (not in scope)."
    - "adequacy.level and c.check are enums serialized via `.value` (lines 48, 70, 75) — consistent enum-to-string handling."
```

```yaml
- path: src/backend/api/audit.py
  purpose: Single read-only endpoint to fetch a child's audit trail with pagination.
  exports:
    - "GET /children/{child_id}/audit -> get_audit_trail (list[AuditEventResponse])"
    - "router (APIRouter, tags=['audit'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, Query"
    - "src.backend.api.deps: DBSession, RequireInterventionist, authorize_child_access"
    - "src.backend.schemas.api_schemas.AuditEventResponse"
    - "src.backend.services.audit_service"
  data_shapes: "Produces list[AuditEventResponse]; query params limit (1-500, default 100) and offset (>=0, default 0)."
  side_effects: "DB read only via audit_service.get_audit_trail; no writes, no audit-of-the-audit-read logged."
  role: "Presentation/Application boundary exposing the immutable Audit Trail (CLAUDE.md Data layer) to interventionists for compliance/governance review."
  observations:
    - "Smallest router file in scope (30 lines), single endpoint, no anomalies. Restricted to RequireInterventionist only — contributors cannot view audit trail, consistent with CLAUDE.md."
    - "No try/except — relies entirely on authorize_child_access raising 403 and FastAPI's default error handling; no 404 case for nonexistent child_id (would just return empty list)."
```

```yaml
- path: src/backend/api/auth.py
  purpose: Authentication routes — login (OAuth2 password flow, dual content-type support), registration, and current-user lookup.
  exports:
    - "POST /auth/login -> login (TokenResponse)"
    - "POST /auth/register -> register (UserResponse, 201)"
    - "GET /auth/me -> me (UserResponse)"
    - "router (APIRouter, prefix='/auth', tags=['auth'])"
  dependencies:
    - "fastapi: APIRouter, HTTPException, Request, status"
    - "src.backend.api.deps: CurrentUser, DBSession"
    - "src.backend.config.settings (imported but not referenced anywhere in the file body)"
    - "src.backend.schemas.api_schemas: LoginRequest, TokenResponse, UserCreate, UserResponse"
    - "src.backend.services.auth_service"
  data_shapes:
    - "login: accepts either form-encoded (username/password, OAuth2-style) or JSON body validated against LoginRequest {email, password}; produces TokenResponse {access_token}"
    - "register: consumes UserCreate {email, password, full_name, role}; produces UserResponse"
    - "me: produces UserResponse from CurrentUser dependency"
  side_effects:
    - "auth_service.authenticate_user does a DB read + password check"
    - "auth_service.create_access_token presumably signs a JWT (no DB access)"
    - "auth_service.create_user writes a new User row; db.commit() after register"
    - "No audit_service.log_event calls anywhere in this file — login/register/me are not written to the audit trail, unlike almost every other mutating endpoint in the api/ directory."
  role: "Presentation/Application boundary for identity — the only unauthenticated-entry-point router (login/register need no CurrentUser dependency); everything else in api/ requires a valid bearer token via CurrentUser/RequireInterventionist."
  observations:
    - "Line 8: `from src.backend.config import settings` is imported but never used in the file — dead import."
    - "login() (lines 20-47) manually branches on Content-Type to support both form-encoded OAuth2PasswordRequestForm-style submission and raw JSON, rather than using FastAPI's `OAuth2PasswordRequestForm` dependency directly. Bespoke/hand-rolled parsing (lines 22-37) — works but diverges from the more common FastAPI idiom, and swallows all JSON-parsing exceptions into a generic 422 (line 31-35) without distinguishing malformed JSON from schema-validation failures."
    - "No audit logging on register/login despite CLAUDE.md stating 'All model invocations logged' and other routers logging nearly every state change; unclear from code whether auth events are intentionally excluded from the audit trail or an oversight — flagging as inconsistency, not asserting intent."
    - "register() does not check role restrictions — any caller can self-register as any Role (including INTERVENTIONIST) per UserCreate.role; no invite-only or admin-approval gate visible in this file (may exist elsewhere, out of scope)."
```

```yaml
- path: src/backend/api/children.py
  purpose: CRUD-ish endpoints for child workspaces (create, list-for-user, get-by-id, patch/update).
  exports:
    - "POST /children/ -> create_child (ChildResponse, 201)"
    - "GET /children/ -> list_children (list[ChildResponse])"
    - "GET /children/{child_id} -> get_child (ChildResponse)"
    - "PATCH /children/{child_id} -> update_child (ChildResponse)"
    - "router (APIRouter, prefix='/children', tags=['children'])"
  dependencies:
    - "fastapi: APIRouter, HTTPException, status"
    - "src.backend.api.deps: CurrentUser, DBSession, RequireInterventionist, authorize_child_access, get_authorized_children"
    - "src.backend.schemas.api_schemas: ChildCreate, ChildResponse, ChildUpdate"
    - "src.backend.services: audit_service, workspace_service"
  data_shapes:
    - "ChildCreate {display_name, date_of_birth} in; ChildResponse out"
    - "ChildUpdate {display_name?, date_of_birth?, is_active?} in (uses `model_fields_set` to distinguish 'not provided' from 'explicitly set to None' for date_of_birth, line 76)"
  side_effects: "DB writes via workspace_service.create_child/update_child; DB reads via list_children/get_child; audit_service.log_event on create and update; db.commit() after mutations."
  role: "Application layer — Child Workspace Manager surface (CLAUDE.md Application layer) enforcing RLS-like child-level RBAC via authorize_child_access / get_authorized_children."
  observations:
    - "create_child is RequireInterventionist-only (line 25) — only interventionists can create a child workspace; consistent with CLAUDE.md.
    - "list_children (line 47) uses CurrentUser (any authenticated role) and filters by get_authorized_children — contributors only see children they're assigned to, interventionists see owned+assigned; logic actually lives in deps.py (see deps.py entry)."
    - "update_child (lines 62-90) has a slightly asymmetric null-handling pattern: display_name and is_active use straightforward `is not None` checks, but date_of_birth uses `model_fields_set` to allow explicitly clearing it to None — a deliberate but non-obvious PATCH semantics distinction worth noting for anyone extending ChildUpdate with new optional fields (they'd need to decide which pattern applies)."
    - "No DELETE endpoint for children — deactivation is presumably done via PATCH is_active=false (soft delete), consistent with CLAUDE.md's 'never UPDATE or DELETE' philosophy, though that phrasing in CLAUDE.md is specifically about the observation store, not children — unclear from code whether children can ever be hard-deleted (no code path for it here)."
```

```yaml
- path: src/backend/api/deps.py
  purpose: Shared FastAPI dependencies for authentication (JWT decode), role-based access control, and child-level authorization used by every other router in this directory.
  exports:
    - "oauth2_scheme (OAuth2PasswordBearer, tokenUrl='/auth/login')"
    - "DBSession (Annotated[AsyncSession, Depends(get_session)])"
    - "get_current_user(token, db) -> User  (async)"
    - "CurrentUser (Annotated[User, Depends(get_current_user)])"
    - "require_role(*roles) -> dependency factory returning an async checker"
    - "RequireInterventionist (Annotated[User, Depends(require_role(Role.INTERVENTIONIST))])"
    - "get_authorized_children(user, db) -> list[uuid.UUID]  (async)"
    - "authorize_child_access(user, child_id, db) -> None  (async, raises 403)"
  dependencies:
    - "fastapi: Depends, HTTPException, status"
    - "fastapi.security.OAuth2PasswordBearer"
    - "jose: JWTError, jwt"
    - "sqlalchemy.select"
    - "sqlalchemy.ext.asyncio.AsyncSession"
    - "src.backend.config.settings (jwt_secret_key, jwt_algorithm)"
    - "src.backend.database.get_session"
    - "src.backend.models.actor.ActorAssignment"
    - "src.backend.models.user.Role, User"
    - "src.backend.models.child.Child (imported locally inside get_authorized_children, line 83)"
  data_shapes:
    - "Decodes JWT payload expecting a 'sub' claim = user UUID string (line 39)"
    - "get_authorized_children returns a deduplicated list of child UUIDs: for INTERVENTIONIST role, union of children they created (Child.created_by) and children they have a non-revoked ActorAssignment for; for any other role, just their non-revoked ActorAssignment child_ids."
  side_effects: "DB reads: db.get(User, ...), db.get(Child...) indirectly, select() queries against Child and ActorAssignment tables. No writes."
  role: "This is the RBAC/auth backbone for the entire api/ package — every other file in this sweep imports DBSession, CurrentUser, and/or RequireInterventionist, and 9 of the other 11 files also call authorize_child_access directly. This is the single most depended-upon file in the scope."
  observations:
    - "Line 83: local import of `Child` model inside get_authorized_children, same deferred-import pattern flagged in actors.py:84 and analytics.py:99/131 — a recurring inconsistency across the api/ directory (4 occurrences total in this sweep) that's worth resolving as a convention (either always top-level or document why deferred, e.g. circular import avoidance — not stated anywhere in comments)."
    - "require_role only supports role-in-allowlist; there's exactly one instantiated variant, RequireInterventionist (line 74). No RequireContributor or similar despite CLAUDE.md describing multiple roles (interventionist, contributor, parent, admin) — role differentiation for non-interventionist users is instead handled ad hoc inside route bodies (e.g. observations.py line 187: `user.role == Role.INTERVENTIONIST` checks) rather than via a dependency. Inconsistent enforcement mechanism: some authorization is declarative (dependency-based), some is imperative (inline if-checks in handlers)."
    - "authorize_child_access (lines 109-121) always calls get_authorized_children fresh — no caching — meaning every single authorized route in the app does at least 1-2 extra DB queries (Child select + ActorAssignment select) per request purely for authorization, on top of whatever the handler itself queries. Not necessarily wrong, just a potential N+1-per-request cost worth flagging."
    - "get_current_user raises 403 for inactive user accounts (lines 49-53) but this happens *after* successful JWT decode; unclear from code whether a deactivated user's already-issued token is otherwise still considered 'valid' until expiry (no token revocation/blacklist visible)."
]
```

```yaml
- path: src/backend/api/goals.py
  purpose: Endpoints for creating, listing, and updating intervention goals for a child.
  exports:
    - "POST /children/{child_id}/goals -> create_goal (GoalResponse, 201)"
    - "GET /children/{child_id}/goals -> list_goals (list[GoalResponse])"
    - "PATCH /goals/{goal_id} -> update_goal (GoalResponse)"
    - "router (APIRouter, tags=['goals'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, HTTPException, status"
    - "src.backend.api.deps: CurrentUser, DBSession, RequireInterventionist, authorize_child_access"
    - "src.backend.schemas.api_schemas: GoalCreate, GoalResponse, GoalUpdate"
    - "src.backend.services: audit_service, workspace_service"
  data_shapes:
    - "GoalCreate {goal_type, domain, title, description, criteria, parent_goal_id, start_date, target_date} in"
    - "GoalUpdate {title, description, criteria, is_active} in (all passed through unconditionally, no None-filtering unlike children.py's update_child)"
    - "GoalResponse out for all three endpoints"
  side_effects: "DB writes via workspace_service.create_goal/update_goal; DB read via list_goals/get_goal; audit_service.log_event on create/update; db.commit()."
  role: "Application layer — Goal/Schedule Registry surface (CLAUDE.md Data layer) allowing interventionists to define and revise goals that the AI 'never modifies' per CLAUDE.md safety rules; goal mutation is explicitly human-only (RequireInterventionist on both mutating routes)."
  observations:
    - "list_goals (line 58) uses CurrentUser (any authenticated role incl. contributors) — contributors can read goals for children they're authorized on, but per CLAUDE.md 'Contributors do not see structured extraction fields...' goals themselves are presumably fine to expose; no field-level filtering visible in GoalResponse for contributor vs interventionist (unclear from this file whether GoalResponse itself hides sensitive fields — schema not in scope)."
    - "update_goal (lines 69-97) passes body.title, body.description, body.criteria, body.is_active straight into workspace_service.update_goal without None-checks, unlike children.py's update_child which explicitly builds a partial update_kwargs dict only for provided fields (lines 73-79 there). Suggests update_goal's underlying service function may have different partial-update semantics than update_child's — worth confirming when goals.py's counterpart service is examined, since as written here a PATCH with only `title` set would seemingly send description=None, criteria=None, is_active=None too, potentially clobbering existing values unless workspace_service.update_goal itself filters Nones (not in scope to verify)."
    - "parent_goal_id support in GoalCreate (line 42) implies hierarchical/sub-goal structure, but there's no endpoint here to list a goal's children/sub-goals or to fetch a single goal by ID directly (only list-all-for-child and patch-by-id) — a GET /goals/{goal_id} single-fetch endpoint is notably absent."
```

```yaml
- path: src/backend/api/observations.py
  purpose: Core conversational-observation lifecycle endpoints — submit, answer clarification, view conversation, finalize, list, and get-detail (including any resulting structured record for interventionists).
  exports:
    - "POST /children/{child_id}/observations -> submit_observation (ObservationSubmitResponse, 201)"
    - "POST /observations/{observation_id}/clarifications -> submit_clarification (ObservationSubmitResponse)"
    - "GET /observations/{observation_id}/conversation -> get_conversation (ConversationResponse)"
    - "POST /observations/{observation_id}/finalize -> finalize_observation (ObservationResponse)"
    - "GET /children/{child_id}/observations -> list_observations (list[ObservationResponse])"
    - "GET /observations/{observation_id} -> get_observation (ObservationDetail)"
    - "router (APIRouter, tags=['observations'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, HTTPException, status"
    - "src.backend.api.deps: CurrentUser, DBSession, RequireInterventionist (imported but unused — see observations below), authorize_child_access"
    - "src.backend.models.user.Role"
    - "src.backend.schemas.api_schemas: ClarificationSubmit, ClarificationTurnResponse, ConversationResponse, ObservationCreate, ObservationDetail, ObservationResponse, ObservationSubmitResponse, RecordResponse"
    - "src.backend.services: audit_service, observation_service"
  data_shapes:
    - "ObservationCreate {raw_text, setting (enum, uses .value), source_type, goal_id} in"
    - "ObservationSubmitResponse {observation, routing_decision, clarification_question} out from both submit_observation and submit_clarification — routing_decision and clarification_question types come from observation_service, not from api_schemas import list here (implies observation_service returns pre-shaped values matching the response model's field types directly)"
    - "ClarificationSubmit {answer, declined} in"
    - "ConversationResponse {observation_id, raw_text, status, clarification_turns, pending_question} — built from a dict returned by observation_service.get_conversation (`conversation.get(...)`, lines 133-141) rather than a typed object"
    - "ObservationDetail includes structured_record: RecordResponse | None, populated only for INTERVENTIONIST role (lines 213-216) — contributors never see the extracted structured record, consistent with CLAUDE.md"
  side_effects: "DB writes via observation_service.submit_observation/submit_clarification/finalize_observation; audit_service.log_event on submit/clarification/finalize (3 of 6 endpoints are read-only and not audited: get_conversation, list_observations, get_observation); db.commit() after each mutation."
  role: "Presentation/Application boundary implementing the Observation Orchestrator + conversational clarification loop described in CLAUDE.md (Application layer) and the human-in-the-loop routing between temporary LLM extraction and clarification questions."
  observations:
    - "Line 12: RequireInterventionist is imported but never referenced anywhere in the file body — dead import (all six routes actually gate on CurrentUser + inline role checks or ownership checks, not the RequireInterventionist dependency)."
    - "Authorization-by-ownership pattern used twice: submit_clarification (line 86-90) and finalize_observation (lines 159-163) both check `observation.submitted_by != user.id` and raise 403 if the caller isn't the original submitter — this is imperative, handler-local authorization logic, distinct from the declarative RequireInterventionist pattern used elsewhere (e.g. actors.py, goals.py mutations). Another instance of the declarative-vs-imperative RBAC inconsistency flagged in deps.py."
    - "list_observations (lines 187-191): `user_id_filter = None if user.role == Role.INTERVENTIONIST else user.id` — interventionists see all observations for a child, everyone else (contributors) only see their own submissions. This role-branching logic lives inline in the route handler rather than in a shared dependency, same pattern as get_observation (line 214) checking `user.role == Role.INTERVENTIONIST` to decide whether to attach structured_record."
    - "get_observation (lines 198-229): picks the latest structured record via `max(observation.structured_records, key=lambda r: r.version)` (line 215) — assumes observation.structured_records is already eagerly loaded (no explicit query here), and assumes version numbers are monotonically comparable ints; no tie-break or handling if the list is empty (guarded by `if ... and observation.structured_records` before entering, so fine) but no explicit ordering/DB-level guarantee is visible from this file alone."
    - "No PATCH/PUT/DELETE for observations anywhere — consistent with CLAUDE.md 'Immutable observation store: never UPDATE or DELETE original text'; corrections instead happen at the structured-record level (see structured_records.py) not the observation level."
```

```yaml
- path: src/backend/api/reports.py
  purpose: Endpoints for generating, listing, retrieving, viewing evidence for, and flagging progress reports.
  exports:
    - "POST /children/{child_id}/reports/generate -> generate_report (ReportResponse, 201)"
    - "GET /children/{child_id}/reports -> list_reports (list[ReportListItem])"
    - "GET /reports/{report_id} -> get_report (ReportResponse)"
    - "GET /reports/{report_id}/evidence -> get_evidence (EvidencePacketResponse)"
    - "POST /reports/{report_id}/flag -> flag_report (ReportResponse)"
    - "router (APIRouter, tags=['reports'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, HTTPException, status"
    - "src.backend.api.deps: DBSession, RequireInterventionist, authorize_child_access"
    - "src.backend.schemas.api_schemas: EvidencePacketResponse, ReportFlagRequest, ReportGenerateRequest, ReportListItem, ReportResponse, ReportSectionResponse"
    - "src.backend.services.report_service"
  data_shapes:
    - "ReportGenerateRequest {review_period_id, goal_id} in"
    - "ReportResponse {id, child_id, review_period_id, sections: list[ReportSectionResponse], provider, model, prompt_version, version, validation_passed, validation_errors, flagged, flagged_reason, flagged_by, generated_at} — this exact shape is manually reconstructed three separate times (generate_report lines 48-63, get_report lines 107-122, flag_report lines 175-190) rather than factored into a shared mapper function"
    - "sections built from report.report_json.get('sections', []) — raw JSON dict unpacked into ReportSectionResponse(**s) in three places (lines 43-46, 102-105, 170-173) — duplicated logic"
    - "EvidencePacketResponse built field-by-field from report.evidence_packet_json.get(...) with defaults (lines 138-152) — mirrors the CLAUDE.md principle 'every report statement traces back to source observation'"
    - "ReportFlagRequest {reason} in"
  side_effects: "DB writes via report_service.generate_report and report_service.flag_report; DB reads via list_reports/get_report; NO audit_service calls anywhere in this file (unlike goals/children/actors/schedules/observations/structured_records, which all call audit_service.log_event on mutations) — report generation and flagging are not written to the audit trail from this router."
  role: "Presentation/Application boundary for the Reporting LLM output (CLAUDE.md AI/ML layer) — the human-facing surface for grounded, evidence-linked reports; flag_report implements human override/QA of AI-generated report content."
  observations:
    - "No audit_service import or calls at all in this file — every other mutating router in scope (actors, analytics, children, goals, observations, schedules, structured_records) logs to the audit trail on create/update actions, but generate_report and flag_report do not. Given CLAUDE.md's emphasis on governance/audit for AI-generated content specifically, this stands out as a likely gap rather than an intentional omission (unclear from code which it is)."
    - "Three near-identical ReportResponse construction blocks (lines 48-63, 107-122, 175-190) are exact duplicates of the same 12-field mapping — classic candidate for a shared `_to_report_response(report)` helper; not present."
    - "get_analytics-style pattern of catching ValueError -> 404 appears only in generate_report (lines 40-41); get_report/get_evidence/flag_report instead check `if report is None` directly against the service return value (lines 97-98, 132-133, 163-164) — two different 'not found' idioms (raised ValueError vs. None sentinel) used across sibling functions calling into the same report_service module."
    - "flag_report has no apparent restriction preventing flagging an already-flagged report multiple times, or unflagging — only a one-way flag action is exposed here (service-layer behavior not in scope)."
  ]
```

```yaml
- path: src/backend/api/schedules.py
  purpose: Endpoints to create and list observation-reporting schedules (cadence-based expectations) for a child.
  exports:
    - "POST /children/{child_id}/schedules -> create_schedule (ScheduleResponse, 201)"
    - "GET /children/{child_id}/schedules -> list_schedules (list[ScheduleResponse])"
    - "router (APIRouter, tags=['schedules'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, status (note: HTTPException not imported/used, unlike most sibling files)"
    - "src.backend.api.deps: DBSession, RequireInterventionist, authorize_child_access"
    - "src.backend.schemas.api_schemas: ScheduleCreate, ScheduleResponse"
    - "src.backend.services: audit_service, schedule_service"
  data_shapes:
    - "ScheduleCreate {cadence_days, goal_id, actor_id, setting, description} in"
    - "ScheduleResponse out"
  side_effects: "DB write via schedule_service.create_schedule; DB read via schedule_service.list_schedules; audit_service.log_event on create (resource_type='reporting_expectation', line 45 — note the mismatch between the Python/URL naming 'schedule' and the audit resource_type string 'reporting_expectation'); db.commit()."
  role: "Application layer — Schedule Engine surface (CLAUDE.md Application layer) defining expected observation cadence per child/goal/actor/setting, presumably feeding notification/reminder logic elsewhere in the system (not in this scope)."
  observations:
    - "Smallest CRUD-style router in scope (61 lines) — only create + list, no get-by-id, no update, no delete/deactivate for schedules, unlike goals.py (which has update) and children.py (which has update). Unclear from code whether schedules are meant to be immutable-once-created or whether update/delete support simply hasn't been built yet."
    - "Line 45: audit resource_type is 'reporting_expectation' while everywhere else in the codebase (router name, service module name, schema names, URL path) uses 'schedule' — naming inconsistency between the audit-trail vocabulary and the rest of the code's vocabulary for the same concept. This suggests 'reporting expectation' may be the original domain term (possibly from the JMIR paper / tech spec) and 'schedule' is a later renaming that wasn't fully propagated to the audit log string."
```

```yaml
- path: src/backend/api/structured_records.py
  purpose: Endpoints for listing structured (LLM-extracted, validated) records for a child, fetching a single record, submitting a human correction (creating a new version), and viewing a record's version history.
  exports:
    - "GET /children/{child_id}/records -> list_records (list[RecordResponse])"
    - "GET /records/{record_id} -> get_record (RecordResponse)"
    - "POST /records/{record_id}/correct -> correct_record (RecordResponse)"
    - "GET /records/{record_id}/history -> get_record_history (list[RecordResponse])"
    - "router (APIRouter, tags=['records'], no prefix)"
  dependencies:
    - "fastapi: APIRouter, HTTPException, status"
    - "src.backend.api.deps: DBSession, RequireInterventionist, authorize_child_access"
    - "src.backend.schemas.api_schemas: RecordCorrection, RecordResponse"
    - "src.backend.services: audit_service, observation_service"
  data_shapes:
    - "RecordCorrection {record_data, correction_reason} in"
    - "RecordResponse out on all four endpoints"
  side_effects: "DB reads via observation_service.get_record/get_observation/list_records/get_record_history; DB write via observation_service.correct_record (creates a new versioned record rather than mutating); audit_service.log_event on correct only; db.commit() after correction."
  role: "AI/ML + Data layer boundary — the human correction/versioning interface for LLM-extracted structured records (CLAUDE.md 'Corrections create new record versions — never overwrite originals' and 'Structured Record Store (versioned)'); this file is the concrete API implementation of that safety rule."
  observations:
    - "Repeated three-step lookup pattern duplicated across get_record, correct_record, and get_record_history (lines 32-47, 58-68, 95-105): fetch record -> 404 if None -> fetch parent observation via observation.observation_id -> 404 if None -> authorize_child_access(user, observation.child_id, db). This exact sequence appears verbatim three times; a shared helper (e.g. `_get_authorized_record_and_observation`) would remove the duplication but doesn't exist here."
    - "All four endpoints require RequireInterventionist — contributors cannot view or correct structured records at all, consistent with CLAUDE.md ('Contributors do not see structured extraction fields...') and correction being a human-in-the-loop interventionist responsibility."
    - "correct_record audit detail includes `previous_record_id` and `reason` (line 83) — good traceability, linking the new record version back to what it superseded, consistent with the versioning safety rule."
    - "get_record_history's ordering is entirely delegated to observation_service.get_record_history (not in scope) — no explicit sort visible in this file, so chronological/version ordering guarantee can't be confirmed from this file alone."
```

## Scope / cross-file observations

- **Router registration is not prefixed in main.py.** `app.include_router(...)` calls in `src/backend/main.py` add no prefix, so the effective route path is entirely determined per-router. Only `children.py` (`prefix="/children"`) and `auth.py` (`prefix="/auth"`) declare a router prefix; the other 8 routers (`actors`, `analytics`, `audit`, `goals`, `observations`, `reports`, `schedules`, `structured_records`) hardcode the full path string on every `@router.<verb>(...)` decorator. This is a real inconsistency worth resolving in a later phase, not a scope-boundary issue.
- **Recurring deferred/local-import pattern**: `actors.py:84`, `analytics.py:97-99,131`, `deps.py:83` all import a model or `select` locally inside a function body rather than at module top, while every other import in these files is top-level. No comment anywhere explains this (e.g. circular-import avoidance). Flagging as a cross-file convention gap.
- **Declarative vs. imperative authorization split**: `deps.py` provides one declarative role-gate (`RequireInterventionist`), used by the majority of mutating routes. But `observations.py` implements two additional authorization patterns inline in handler bodies: ownership checks (`observation.submitted_by != user.id`) and role branching (`user.role == Role.INTERVENTIONIST`) that has no corresponding dependency. This means "who can do what" is not answerable by reading `deps.py` alone — a later phase should decide whether to consolidate these into declarative dependencies.
- **Audit logging coverage is inconsistent**: every mutating endpoint in `actors.py`, `analytics.py`, `children.py`, `goals.py`, `observations.py`, `schedules.py`, and `structured_records.py` calls `audit_service.log_event`. `auth.py` (login/register) and `reports.py` (generate/flag) do not call `audit_service` at all. Given CLAUDE.md's governance emphasis, this is likely worth flagging to the user rather than treated as intentional.
- **Naming drift**: `schedules.py` uses `resource_type="reporting_expectation"` in its audit log call (line 45) even though the router, service, schema, and URL path all say "schedule" — suggests a renaming that didn't fully propagate.
- **Response-shape duplication**: `reports.py` reconstructs the same 12-field `ReportResponse` object from a `Report` ORM/service object three separate times (in `generate_report`, `get_report`, `flag_report`) instead of a shared mapper — the most significant code-duplication instance found in this sweep.
- **Dependency on out-of-scope modules**: every file in this sweep depends heavily on `src.backend.services.*` (audit_service, auth_service, workspace_service, analytics_service, observation_service, report_service, schedule_service) and `src.backend.schemas.api_schemas` and `src.backend.models.*` — none of which are in this sweep's scope. The actual extraction/validation/analytics logic, and the full shape of every Pydantic schema referenced here, lives entirely in those out-of-scope modules; this sweep can only describe the API surface's *contract* with them, not their internals.
- **`__init__.py` is empty** — there is no package-level router aggregation; `main.py` is the sole place where all 10 routers are wired together, and it does so with 10 individual `include_router` calls plus 10 individual import lines (`main.py` lines 16-25, 138-147), matching 1:1 with the 10 files in this scope that define a `router` (all files except `__init__.py` and `deps.py`).
```

No files were unreadable and no unexpected file types were found — all 12 are plain `.py` modules matching their expected role (10 FastAPI routers + 1 shared-dependencies module + 1 empty package marker).
