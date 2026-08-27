# Sweep 3: src/backend/models/ and src/backend/schemas/

Scope: 12 files read in full. Cross-checked against `src/backend/database.py` (Base/engine
definition) and `alembic/versions/*` (migration history) to verify RLS claims from CLAUDE.md.

---

```yaml
- path: src/backend/models/__init__.py
  purpose: Central import/re-export point for all SQLAlchemy ORM model classes so Alembic autogenerate can discover them via Base.metadata.
  exports: |
    No classes defined here. Re-exports: ActorAssignment, AuditEvent, Child, ClarificationTurn,
    GeneratedReport, Goal, Observation, OverdueEvent, ReportingExpectation, ReviewPeriod,
    StructuredRecord, User (via __all__, lines 16-29).
  dependencies: |
    src.backend.models.actor.ActorAssignment; src.backend.models.audit.AuditEvent;
    src.backend.models.child.Child; src.backend.models.goal.{Goal, ReviewPeriod};
    src.backend.models.observation.{ClarificationTurn, Observation, StructuredRecord};
    src.backend.models.report.GeneratedReport; src.backend.models.schedule.{OverdueEvent,
    ReportingExpectation}; src.backend.models.user.User
  data_shapes: none (pure import aggregator)
  side_effects: none directly, but importing this module triggers class-body execution of every
    model module, which registers tables on Base.metadata (import-time side effect relied on by Alembic env.py).
  role: Single source of truth for "all tables" used by Alembic's autogenerate and by any code that needs the full model set.
  observations: |
    Docstring (line 1) explicitly ties this file's existence to Alembic autogeneration
    discovery — confirms Alembic is the live migration tool (consistent with CLAUDE.md).
    No model for GoalType/Role/RecordStatus/ObservationStatus enums exported here even though
    they are meaningful shared vocabulary — enums are only reachable by importing the owning
    model module directly (e.g. src.backend.models.user.Role), not via this __init__. Minor
    inconsistency: schemas/api_schemas.py imports Role, GoalType, ObservationStatus, RecordStatus
    directly from their model submodules rather than from this __init__, meaning the __init__'s
    curated __all__ is incomplete relative to what's actually consumed elsewhere.
```

```yaml
- path: src/backend/models/actor.py
  purpose: SQLAlchemy model recording that a given user acts in a given role on a given child's case (an "actor assignment" / invitation).
  exports: |
    class ActorAssignment(Base) — table "actor_assignments".
    Columns: id (UUID pk, server default gen_random_uuid()), user_id (UUID FK -> users.id,
    indexed), child_id (UUID FK -> children.id, indexed), role (Enum Role from user.py),
    invited_by (UUID FK -> users.id), invited_at (timestamptz, server default now()),
    invitation_email (String(320) nullable), revoked_at (timestamptz nullable).
    Table arg: UniqueConstraint(user_id, child_id, name="uq_actor_user_child") (line 17-19).
    Relationships: user -> User.actor_assignments (foreign_keys=[user_id]); child -> Child.actor_assignments.
  dependencies: |
    sqlalchemy (DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint, text);
    sqlalchemy.dialects.postgresql.UUID; sqlalchemy.orm (Mapped, mapped_column, relationship);
    sqlalchemy.sql.func; src.backend.database.Base; src.backend.models.user.Role.
  data_shapes: One row = one (user, child, role) assignment with an audit trail of who invited them and an optional revocation timestamp.
  side_effects: none (declarative model only; DB writes happen elsewhere via SQLAlchemy session)
  role: |
    This is the RBAC join table linking users to children with a role — the mechanism CLAUDE.md
    calls "child-level RBAC enforced at both UI and API layers." It is the only per-child access
    grant table in the schema.
  observations: |
    child_id (line 32-37) has a plain indexed FK column, not a composite/partitioned key and no
    Postgres Row-Level-Security policy anywhere (searched entire repo for "ROW LEVEL"/"POLICY"/
    "row_security" — zero hits, and alembic/versions/*.py contain none either). CLAUDE.md states
    "child-level RLS on every table" as a coding convention; the actual mechanism observed in code
    is a UniqueConstraint + indexed FK used for application-level authorization joins, not
    database-enforced RLS. This is a real gap between stated convention and implemented code —
    flagging per task instructions rather than assuming RLS exists.
    UniqueConstraint means a user can only ever have ONE role per child (revoking then
    re-inviting under a different role would need to update/replace the row, not insert a new
    one) — no soft-delete-then-reinvite pattern is visible in this file alone (unclear how
    revoked_at interacts with the unique constraint from model code alone).
    invited_by has no server default and is NOT nullable (line 42-46) — self-invitation (e.g.,
    system-seeded first actor) would require a real user id to already exist.
```

```yaml
- path: src/backend/models/audit.py
  purpose: SQLAlchemy model for an immutable, append-only audit log of user actions.
  exports: |
    class AuditEvent(Base) — table "audit_events". Columns: id (UUID pk), user_id (UUID FK ->
    users.id, indexed), child_id (UUID FK -> children.id, nullable, indexed), action
    (String(128), indexed), resource_type (String(64)), resource_id (String(64), nullable),
    detail (JSONB, nullable), created_at (timestamptz, server default now()).
  dependencies: |
    sqlalchemy (DateTime, ForeignKey, String, text); sqlalchemy.dialects.postgresql (JSONB, UUID);
    sqlalchemy.orm (Mapped, mapped_column); sqlalchemy.sql.func; src.backend.database.Base.
  data_shapes: One row per audited action; detail is a free-form JSON blob (schema not constrained at DB level).
  side_effects: none in this file (no ORM event listeners / triggers defined here to actually enforce append-only-ness)
  role: |
    Backing store for CLAUDE.md's "Audit Logger" application-layer component and the "Audit
    Trail" data-layer concept. Consumed by schemas.api_schemas.AuditEventResponse and
    presumably an audit service (not in this scope).
  observations: |
    Docstring says "APPEND-ONLY — no UPDATE or DELETE" (line 15), but this is only a comment —
    no SQLAlchemy mechanism (event listener, DB trigger, GRANT restriction, migration-level
    REVOKE UPDATE/DELETE) is present in this file or anywhere found in alembic/versions to
    actually enforce it. Append-only-ness is currently a convention, not a guarantee.
    child_id nullable (line 30-35) — allows audit events unscoped to any child (e.g. login
    events), which is reasonable but means audit rows are NOT uniformly child-scoped, so any
    child-level RLS policy applied uniformly across tables would need to special-case this
    table (further evidence RLS isn't actually wired up per-row here).
    No index on created_at despite this being a log table typically queried by time range —
    only action and the two FK columns are indexed.
```

```yaml
- path: src/backend/models/child.py
  purpose: SQLAlchemy model for a child (the case/subject of intervention tracking) — the root entity that most other tables key off of.
  exports: |
    class Child(Base) — table "children". Columns: id (UUID pk), display_name (String(128)),
    date_of_birth (timestamptz, nullable — see observations), created_by (UUID FK -> users.id,
    indexed), created_at (timestamptz, server default now()), is_active (bool, default True).
    Relationships: actor_assignments -> ActorAssignment.child; goals -> Goal.child;
    observations -> Observation.child; review_periods -> ReviewPeriod.child.
  dependencies: |
    sqlalchemy (DateTime, ForeignKey, String, text); sqlalchemy.dialects.postgresql.UUID;
    sqlalchemy.orm (Mapped, mapped_column, relationship); sqlalchemy.sql.func;
    src.backend.database.Base.
  data_shapes: One row per child; the "tenant" root for goals/observations/review periods/actor assignments.
  side_effects: none (declarative model only)
  role: |
    This IS the tenancy boundary referenced throughout CLAUDE.md as "child-level" — every other
    domain table (goals, observations, structured records indirectly, reports, schedules) FKs
    either directly to children.id or transitively through it.
  observations: |
    date_of_birth is typed as DateTime(timezone=True) (line 23) rather than Date, inconsistent
    with goal.py/schedule.py which correctly use sqlalchemy.Date for date-only fields
    (start_date/target_date/due_date). A birthdate carrying a timezone-aware datetime is an odd
    mismatch (schemas/api_schemas.ChildCreate.date_of_birth is typed `Optional[date]` (Python
    date, not datetime) — line 52 of api_schemas.py — while ChildResponse.date_of_birth is typed
    `Optional[datetime]` (api_schemas.py line 64), matching the DB column but not the input
    schema; this input/output type asymmetry is a minor inconsistency worth flagging).
    No RLS/tenant column beyond the primary key itself — as the root of the tenancy hierarchy,
    Child has no "owner org" or multi-tenant column; every other table's child-scoping is via FK
    to this table's id, confirming (as under actor.py) that "child-level RLS" in the stated
    convention sense is not present as a DB policy — it's implemented (if at all) at the
    application/service layer, outside this scope.
```

```yaml
- path: src/backend/models/goal.py
  purpose: SQLAlchemy models for intervention Goals (long/short-term, with parent/child hierarchy) and ReviewPeriods (date windows for reporting).
  exports: |
    enum GoalType(str, Enum): LONG_TERM, SHORT_TERM (lines 16-18).
    class Goal(Base) — table "goals". Columns: id (UUID pk), child_id (UUID FK -> children.id,
    indexed), goal_type (Enum GoalType), domain (Enum Domain, imported from
    schemas.observation_schema), title (String(512)), description (Text), criteria (Text,
    nullable), parent_goal_id (UUID FK -> goals.id, nullable, self-referential), start_date
    (Date, nullable), target_date (Date, nullable), is_active (bool default True), created_by
    (UUID FK -> users.id), created_at (timestamptz), version (int default 1). Relationship:
    child -> Child.goals.
    class ReviewPeriod(Base) — table "review_periods". Columns: id (UUID pk), child_id (UUID FK
    -> children.id, indexed), start_date (Date), end_date (Date), is_active (bool default True),
    created_at (timestamptz). Relationship: child -> Child.review_periods.
  dependencies: |
    sqlalchemy (Date, DateTime, Enum as SAEnum, ForeignKey, String, Text, text);
    sqlalchemy.dialects.postgresql.UUID; sqlalchemy.orm (Mapped, mapped_column, relationship);
    sqlalchemy.sql.func; src.backend.database.Base; src.backend.schemas.observation_schema.Domain
    (cross-layer import: a model importing an enum from the pydantic schemas module).
  data_shapes: Goal = hierarchical treatment target scoped to a child and a Domain; ReviewPeriod = a [start_date, end_date] window used to bucket observations/reports for a child.
  side_effects: none (declarative model only)
  role: |
    Goals are the treatment targets that Observations/StructuredRecords are evaluated against
    and that Reports summarize progress toward; ReviewPeriod is the reporting-cadence window
    consumed by GeneratedReport (see report.py) and the Analytics layer (per CLAUDE.md, Phase 4).
  observations: |
    Line 13: `from src.backend.schemas.observation_schema import Domain` — a models/ file
    depends on a schemas/ file. This is the one cross-directory dependency observed in this
    sweep's scope; Domain is a plain str Enum with no pydantic BaseModel behavior invoked here,
    so it works as a SQLAlchemy Enum column type, but it does create a coupling where models/
    is not self-contained without schemas/ (worth noting for later clustering — Domain may
    conceptually belong closer to "shared enums" than "pydantic-only schema").
    parent_goal_id is self-referential FK to goals.id (line 46-50) with no explicit
    relationship() defined for parent/children traversal in the ORM (no `parent`/`children`
    relationship declared) — the FK exists at the DB level but isn't modeled as an ORM
    relationship in this file, so any parent/child goal tree traversal must be done via raw
    queries elsewhere.
    version column (line 64) suggests optimistic versioning intent similar to StructuredRecord,
    but unlike StructuredRecord there is no previous_version_id / corrected_by /
    correction_reason lineage tracking for Goal edits — CLAUDE.md says "Corrections create new
    record versions — never overwrite originals," but Goal has only a bare int version counter
    with no linkage to prior versions and no versioned-row-per-edit pattern visible; goals.py
    API (out of scope) would need to be checked to see if version is even mutated on update, but
    from the model alone there's no schema support for keeping old goal versions around.
    ReviewPeriod has no UniqueConstraint preventing overlapping periods for the same child, and
    no CHECK constraint that end_date > start_date.
```

```yaml
- path: src/backend/models/observation.py
  purpose: SQLAlchemy models for the core observation-intake and structured-extraction pipeline — raw Observation, its ClarificationTurn Q&A exchanges, and the resulting versioned StructuredRecord.
  exports: |
    enum ObservationStatus(str, Enum): PENDING, EXTRACTING, CLARIFYING, FINALIZED, FAILED (lines 15-20).
    class Observation(Base) — table "observations". Columns: id (UUID pk), child_id (UUID FK ->
    children.id, indexed), submitted_by (UUID FK -> users.id, indexed), raw_text (Text),
    source_type (String(32)), setting (String(32)), status (Enum ObservationStatus, default
    PENDING), conversation_json (JSONB, nullable), submitted_at (timestamptz), finalized_at
    (timestamptz, nullable), extraction_result_json (JSONB, nullable). Relationships: child ->
    Child.observations; structured_records -> StructuredRecord.observation;
    clarification_turns -> ClarificationTurn.observation (ordered by turn_number).
    class ClarificationTurn(Base) — table "clarification_turns". Columns: id (UUID pk),
    observation_id (UUID FK -> observations.id, indexed), turn_number (Integer), question
    (Text), answer (Text, nullable), created_at (timestamptz), answered_at (timestamptz,
    nullable). Relationship: observation -> Observation.clarification_turns.
    enum RecordStatus(str, Enum): PENDING, VALIDATED, CORRECTED, REJECTED, ABSTAINED (lines 109-114).
    class StructuredRecord(Base) — table "structured_records". Columns: id (UUID pk),
    observation_id (UUID FK -> observations.id, indexed), version (int, default 1), status
    (Enum RecordStatus, default PENDING), record_data (JSONB, not null), validation_result
    (JSONB, nullable), corrected_by (UUID FK -> users.id, nullable), correction_reason (Text,
    nullable), previous_version_id (UUID FK -> structured_records.id, nullable,
    self-referential), provider (String(64)), model (String(128)), prompt_version (String(32)),
    created_at (timestamptz). Relationship: observation -> Observation.structured_records.
  dependencies: |
    sqlalchemy (DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, text);
    sqlalchemy.dialects.postgresql (JSONB, UUID); sqlalchemy.orm (Mapped, mapped_column,
    relationship); sqlalchemy.sql.func; src.backend.database.Base.
  data_shapes: |
    Observation.raw_text = contributor's free-text/conversational submission (immutable).
    Observation.conversation_json = presumably the full chat transcript incl. clarification
    exchanges (shape not defined/validated at this layer — plain dict). Observation.extraction_result_json
    = presumably a serialized ExtractionResult (per CLAUDE.md's ExtractionProvider contract) but that contract
    itself lives outside this scope (ml pipeline) — not cross-checked here.
    StructuredRecord.record_data = presumably a serialized StructuredObservation
    (schemas/observation_schema.py) but there is no FK/type constraint tying record_data's JSON
    shape to that pydantic model — it's an untyped JSONB column, so schema drift between the
    pydantic contract and what's actually stored would not be caught by the DB.
  side_effects: none (declarative model only)
  role: |
    This is the heart of the "Observation Store (immutable)" and "Structured Record Store
    (versioned)" data-layer components named in CLAUDE.md's architecture section. Observation
    is fed by the Observation Orchestrator; StructuredRecord is the deterministic-validation
    output store; ClarificationTurn backs the "may ask focused, non-leading clarification
    questions" behavior.
  observations: |
    Docstring "IMMUTABLE once finalized — raw_text is immutable immediately on submission"
    (line 24) is, like audit.py, a comment-only guarantee — no SQLAlchemy-level protection
    (e.g., no read-only column, no trigger, no revoked UPDATE grant) prevents raw_text from
    being updated after the fact; enforcement (if any) must live in the service layer, outside
    this scope.
    ClarificationTurn docstring says "APPEND-ONLY" (line 76) but the table has an `answer` and
    `answered_at` column that are explicitly meant to be filled in AFTER row creation (see
    ClarificationSubmit schema in api_schemas.py, which submits an answer for an existing turn)
    — this is UPDATE-in-place on a table labeled "append-only," a direct contradiction between
    the docstring and the modeled column semantics (lines 76, 93, 99-102).
    StructuredRecord.previous_version_id (line 147-151) is self-referential but, like Goal's
    parent_goal_id, has no ORM relationship() defined for walking version history — only a raw
    FK column.
    StructuredRecord has no UniqueConstraint on (observation_id, version) — two rows could exist
    with the same observation_id and version, allowing accidental duplicate "current" versions.
    Observation.setting and Observation.source_type are stored as plain String(32) (lines 46-47)
    rather than a SQLAlchemy Enum, even though schemas/observation_schema.py defines a Setting
    str-Enum (SCHOOL/HOME/CLINIC/COMMUNITY/OTHER/UNKNOWN) that is used for validation at the API
    layer (ObservationCreate.setting: Setting, in api_schemas.py line 137) — the DB column itself
    does not enforce this enum, so a raw DB write (or a future code path that bypasses the
    Pydantic schema) could store an arbitrary string.
```

```yaml
- path: src/backend/models/report.py
  purpose: SQLAlchemy model for a generated (LLM-authored, validated) progress report tied to a child and review period.
  exports: |
    class GeneratedReport(Base) — table "generated_reports". Columns: id (UUID pk), child_id
    (UUID FK -> children.id, indexed), review_period_id (UUID FK -> review_periods.id),
    report_json (JSONB, not null), evidence_packet_json (JSONB, not null), provider
    (String(64)), model (String(128)), prompt_version (String(32), default "1.0"), version (int,
    default 1), validation_passed (bool, default False), validation_errors (JSONB, nullable),
    flagged (bool, default False), flagged_reason (Text, nullable), flagged_by (UUID FK ->
    users.id, nullable), generated_at (timestamptz).
  dependencies: |
    sqlalchemy (DateTime, ForeignKey, String, Text, text); sqlalchemy.dialects.postgresql
    (JSONB, UUID); sqlalchemy.orm (Mapped, mapped_column); sqlalchemy.sql.func;
    src.backend.database.Base.
  data_shapes: |
    report_json presumably mirrors schemas.api_schemas.ReportResponse.sections (list of
    heading/body/evidence_refs/abstention_note) but, as with StructuredRecord.record_data, this
    is an untyped JSONB blob with no DB-level shape enforcement.
    evidence_packet_json presumably mirrors schemas.api_schemas.EvidencePacketResponse — again
    untyped JSONB.
  side_effects: none (declarative model only)
  role: |
    Backing store for the "Reporting LLM" output described in CLAUDE.md — the versioned,
    validated, flaggable report artifact that interventionists/EPA review. review_period_id
    ties it to Goal.py's ReviewPeriod, and the review_period_id has no back-populated
    relationship() declared on either GeneratedReport or ReviewPeriod (one-directional FK only,
    unlike most other tables in this scope which declare relationship() both ways).
  observations: |
    No relationship() attributes at all in this file (only raw FK columns to children,
    review_periods, users) — inconsistent with every other model file in scope, all of which
    declare at least one relationship(). This means GeneratedReport rows can't be reached via
    ORM navigation from Child or ReviewPeriod (e.g., child.reports doesn't exist per child.py's
    relationship list, which only defines actor_assignments/goals/observations/review_periods —
    confirmed by re-reading child.py lines 37-46, no `reports` relationship present).
    No UniqueConstraint on (child_id, review_period_id, goal_id-equivalent) to prevent duplicate
    "current" reports — version column exists but nothing enforces version increments or
    uniqueness of (child_id, review_period_id, version).
    flagged_by allows a report to be flagged by a user with no similar workflow captured for
    *unflagging* (no unflagged_at/unflagged_by columns) — one-way flag state only, from the
    model alone.
```

```yaml
- path: src/backend/models/schedule.py
  purpose: SQLAlchemy models for recurring reporting-cadence expectations per child/goal/actor/setting, and detected overdue events against those expectations.
  exports: |
    class ReportingExpectation(Base) — table "reporting_expectations". Columns: id (UUID pk),
    child_id (UUID FK -> children.id, indexed), goal_id (UUID FK -> goals.id, nullable),
    actor_id (UUID FK -> users.id, nullable), setting (String(32), nullable), cadence_days
    (Integer, not null), description (Text, nullable), is_active (bool, default True),
    created_at (timestamptz).
    class OverdueEvent(Base) — table "overdue_events". Columns: id (UUID pk), expectation_id
    (UUID FK -> reporting_expectations.id, indexed), due_date (Date), detected_at (timestamptz),
    reminder_sent_at (timestamptz, nullable), resolved_at (timestamptz, nullable).
  dependencies: |
    sqlalchemy (Date, DateTime, ForeignKey, Integer, String, Text, text);
    sqlalchemy.dialects.postgresql.UUID; sqlalchemy.orm (Mapped, mapped_column); sqlalchemy.sql.func;
    src.backend.database.Base.
  data_shapes: |
    ReportingExpectation = "someone should submit an observation about this child/goal/actor/
    setting every N days" rule. OverdueEvent = a detected violation of one such rule on a given
    due_date, with reminder/resolution timestamps.
  side_effects: none (declarative model only)
  role: |
    Backing store for CLAUDE.md's "Schedule Engine" (Application layer) — drives the
    Notification Service (email/SMS reminders) referenced in the architecture doc, though the
    actual scheduling/cron/notification-dispatch logic is out of this scope.
  observations: |
    No relationship() attributes declared in this file at all (same pattern as report.py) — no
    ORM navigation from Child/Goal/User to their ReportingExpectations, and no relationship from
    ReportingExpectation to its OverdueEvents (only the reverse raw FK). This is inconsistent
    with actor.py/child.py/goal.py/observation.py which all declare bidirectional
    relationship()s; two of the eight files in this sweep (report.py, schedule.py) skip
    relationship() declarations entirely, suggesting these two areas were built with a more
    query-first/service-layer access pattern rather than ORM graph traversal — but this is
    inferred from the pattern, not stated anywhere in code (worth flagging as an inconsistency
    for later phases, not asserting which is "correct").
    setting column (line 38) is again a plain nullable String(32), not the Setting enum from
    schemas/observation_schema.py — same DB-level enum-enforcement gap noted in observation.py.
    No UniqueConstraint preventing duplicate/overlapping ReportingExpectation rows for the same
    (child_id, goal_id, actor_id, setting) tuple.
    cadence_days has no CHECK constraint (e.g., > 0) at the DB level; the >=1 constraint exists
    only in the Pydantic layer (schemas/api_schemas.py ScheduleCreate.cadence_days: int =
    Field(ge=1), line 222) — again, a DB write that bypasses the API schema would not be
    protected.
```

```yaml
- path: src/backend/models/user.py
  purpose: SQLAlchemy model for application users (all actor types) plus the shared Role enum used across the whole system for RBAC.
  exports: |
    enum Role(str, Enum): INTERVENTIONIST, PARENT, TEACHER, TRAINER, EPA,
    SECONDARY_INTERVENTIONIST (lines 13-19).
    class User(Base) — table "users". Columns: id (UUID pk), email (String(320), unique,
    indexed, not null), hashed_password (String(256), not null), full_name (String(256), not
    null), role (Enum Role, not null), is_active (bool, default True). Relationship:
    actor_assignments -> ActorAssignment.user (foreign_keys="[ActorAssignment.user_id]").
  dependencies: |
    sqlalchemy (Enum as SAEnum, String, text); sqlalchemy.dialects.postgresql.UUID;
    sqlalchemy.orm (Mapped, mapped_column, relationship); src.backend.database.Base.
  data_shapes: One row per authenticated user; role is a single global Role value on the user record itself, separate from the per-child role captured in ActorAssignment.role.
  side_effects: none (declarative model only — password hashing itself happens elsewhere, not in this file)
  role: |
    Root identity table for auth/RBAC (CLAUDE.md's "Auth/RBAC" Application-layer component).
    Notably, User.role is a GLOBAL role (one per user, not per child), while ActorAssignment.role
    is a PER-CHILD role — these are two separate, independently-settable Role values for the
    same user, using the identical Role enum type.
  observations: |
    Potential source of confusion: a User has both a global `role` (user.py line 33-36) and,
    for each child they're assigned to, a separate `role` on ActorAssignment (actor.py line
    38-41) — both drawn from the exact same Role enum. Nothing in either file's code documents
    how these two roles relate (e.g., can a user be a global PARENT but an EPA on a specific
    child's ActorAssignment? Is User.role meant to be a default/registration-time value that
    ActorAssignment overrides per child?). Flagging as unclear-from-code rather than assuming
    intent.
    No email format validation at the DB level (String(320) only) — validation (if any) is
    presumably in the Pydantic UserCreate schema (api_schemas.py uses plain `email: str` with no
    EmailStr type either — see api_schemas.py lines 21, 41 — so email format isn't validated by
    Pydantic here either).
    No relationship declared from User to Child.created_by, Goal.created_by, Observation.submitted_by,
    StructuredRecord.corrected_by, GeneratedReport.flagged_by, or ReportingExpectation.actor_id
    — User only has the one relationship back to ActorAssignment. All those other FKs to
    users.id are one-directional (queryable only by starting from the other table), which is
    consistent with this file alone but means "all observations submitted by user X" requires a
    query starting from Observation, not User.
```

```yaml
- path: src/backend/schemas/__init__.py
  purpose: Package marker for src/backend/schemas/.
  exports: none (file is completely empty — 0 bytes)
  dependencies: none
  data_shapes: none
  side_effects: none
  role: Makes src/backend/schemas a Python package; no re-exports, so all consumers import directly from src.backend.schemas.api_schemas or src.backend.schemas.observation_schema (confirmed by grep — every import in src/backend/api/* targets api_schemas directly, never `from src.backend.schemas import X`).
  observations: |
    Empty — unlike models/__init__.py, this package does not aggregate/re-export its two
    submodules. This is an inconsistent pattern between the two sibling packages (models/
    curates an __all__; schemas/ does not) but not necessarily a bug, since nothing appears to
    rely on `from src.backend.schemas import ...` (verified via grep across src/backend).
```

```yaml
- path: src/backend/schemas/api_schemas.py
  purpose: All Pydantic request/response DTOs for the FastAPI HTTP layer, covering auth, children, goals, actors, observations, structured records, schedules, audit, analytics, and reports.
  exports: |
    Auth: LoginRequest{email,password}, TokenResponse{access_token,token_type}, UserResponse{id,
    email,full_name,role,is_active}, UserCreate{email,password(min 8),full_name(min 1),role}.
    Children: ChildCreate{display_name,date_of_birth?}, ChildUpdate{display_name?,date_of_birth?,
    is_active?}, ChildResponse{id,display_name,date_of_birth?,created_by,created_at,is_active}.
    Goals: GoalCreate{goal_type,domain,title,description,criteria?,parent_goal_id?,start_date?,
    target_date?}, GoalUpdate{title?,description?,criteria?,is_active?}, GoalResponse{id,
    child_id,goal_type,domain,title,description,criteria,parent_goal_id,start_date,target_date,
    is_active,version,created_at}.
    Actors: ActorInvite{email,role}, ActorResponse{id,user_id,child_id,role,invited_by,
    invited_at,invitation_email,revoked_at}.
    Observations: ObservationCreate{raw_text,setting,source_type="conversational",goal_id?},
    ClarificationSubmit{answer?,declined=False}, ClarificationTurnResponse{turn_number,question,
    answer,created_at,answered_at}, ObservationResponse{id,child_id,submitted_by,raw_text,
    source_type,setting,status,submitted_at,finalized_at}, ObservationDetail(ObservationResponse
    + clarification_turns, structured_record?), ConversationResponse{observation_id,raw_text,
    status,clarification_turns,pending_question?}, ObservationSubmitResponse{observation,
    routing_decision,clarification_question?}.
    Structured Records: RecordResponse{id,observation_id,version,status,record_data,
    validation_result,corrected_by,correction_reason,provider,model,prompt_version,created_at},
    RecordCorrection{record_data,correction_reason(min 1)}.
    Schedules: ScheduleCreate{goal_id?,actor_id?,setting?,cadence_days(ge=1),description?},
    ScheduleUpdate{cadence_days?,description?,is_active?}, OverdueInfo{is_overdue,due_date?,
    days_overdue=0}, ScheduleResponse{id,child_id,goal_id,actor_id,setting,cadence_days,
    description,is_active,created_at,overdue?}.
    Audit: AuditEventResponse{id,user_id,child_id,action,resource_type,resource_id,detail,created_at}.
    Generic: MessageResponse{message}, PaginatedResponse{items,total,page=1,page_size=50}.
    Analytics: AnalyticsRequest{review_period_id,goal_id?}, KpiResponse{name,numerator,
    denominator,value?,abstained=False,abstention_reason?,display_eligible=True},
    AdequacyCheckResponse{check,passed,detail,value?,threshold?}, AdequacyResponse{level,
    eligible,checks,partial_abstentions,quality_flags}, AnalyticsResponse{child_id,
    review_period_id,goal_id?,kpis,adequacy,computed_at}.
    Reports: ReportGenerateRequest{review_period_id,goal_id?}, ReportSectionResponse{heading,
    body,evidence_refs,abstention_note?}, ReportResponse{id,child_id,review_period_id,sections,
    provider,model,prompt_version,version,validation_passed,validation_errors?,flagged,
    flagged_reason?,flagged_by?,generated_at}, ReportListItem{id,child_id,review_period_id,
    version,validation_passed,flagged,generated_at}, ReportFlagRequest{reason(min 1)},
    EvidencePacketResponse{child_id,review_period_id,review_period_start,review_period_end,
    goals,record_ids,record_versions,contributor_summary,setting_summary,observation_count,
    abstained_count,review_count,quality_flags}.
    Review Periods: ReviewPeriodCreate{start_date,end_date}, ReviewPeriodResponse{id,child_id,
    start_date,end_date,is_active,created_at}.
  dependencies: |
    pydantic (BaseModel, Field); src.backend.models.goal.GoalType;
    src.backend.models.observation.{ObservationStatus, RecordStatus};
    src.backend.models.user.Role; src.backend.schemas.observation_schema.{Domain, Setting}.
    (Notable: a schemas/ file imports enums from models/ — the reverse direction of goal.py's
    models-importing-from-schemas dependency — so the two directories are mutually coupled via
    shared enums rather than one cleanly layered on the other.)
  data_shapes: |
    Pure request/response DTOs; every *Response model with `model_config = {"from_attributes":
    True}` is meant to be constructed directly from a SQLAlchemy ORM instance
    (Pydantic v2 ORM-mode equivalent).
  side_effects: none (pure data contracts, no I/O)
  role: |
    This is the API contract layer between the FastAPI routers (src/backend/api/*, out of
    scope) and both the ORM models (this sweep) and the ML/analytics layer (out of scope). It's
    the single place all HTTP-facing shapes are defined.
  observations: |
    Line 173: `structured_record: Optional[RecordResponse] = None` inside `ObservationDetail`,
    but `RecordResponse` is not defined until line 193 — a genuine forward reference within the
    same module. The file has `from __future__ import annotations` (line 3), which stores
    annotations as strings so this doesn't raise a NameError at class-definition time; Pydantic
    v2 auto-attempts schema-building and will complete it once the module finishes loading
    (standard working pattern), but it is fragile ordering — if `ObservationDetail` were ever
    *used* (instantiated/validated) before the module finished executing (e.g., some
    import-cycle edge case), it could fail. Flagging as an ordering fragility, not a confirmed
    bug.
    `email: str` used for LoginRequest, UserCreate, ActorInvite, and UserResponse (lines 21, 41,
    115) rather than pydantic's `EmailStr` — no format validation at the schema layer; combined
    with User.email being unbounded to a validated format at the DB layer too, email correctness
    is currently unenforced anywhere in this scope.
    `PaginatedResponse.items: list` (line 277) is untyped (`list`, not `list[T]`) — loses type
    information for consumers/OpenAPI docs; every concrete use of pagination would presumably
    need to subclass or re-declare this, but no such subclass exists in this file.
    `ScheduleResponse.setting: Optional[str]` (line 243) and `ObservationResponse.setting: str`
    (line 163) both use plain `str` rather than the `Setting` enum already imported and used
    for `ObservationCreate.setting` (line 137) — inconsistent enum usage for the same
    conceptual field within the same file (input schema is strongly typed as `Setting`, output
    schemas degrade to plain `str`), which matches the DB-level String(32) columns noted in
    observation.py/schedule.py.
    `EvidencePacketResponse` and several Analytics/Reports schemas (marked "Phase 4" in comments
    at lines 283 and 326) use raw `dict`/`list[dict]` fields (goals: list[dict], record_versions:
    dict[str, int], etc.) rather than nested Pydantic models — less type safety for a
    fairly important governance artifact (the evidence packet is the traceability mechanism
    CLAUDE.md calls out: "every report statement traces back to source observation").
    RecordResponse.record_data and validation_result are typed as plain `dict` (lines 198-199)
    — no reference to the StructuredObservation pydantic model in observation_schema.py, so the
    API contract doesn't statically guarantee that record_data conforms to the canonical
    structured-observation shape; this mirrors the untyped JSONB column noted in
    models/observation.py.
```

```yaml
- path: src/backend/schemas/observation_schema.py
  purpose: Canonical Pydantic definition of a single structured observation record and its field-provenance categorization (app-known vs. LLM-extracted vs. provider-generated), explicitly sourced from "Technical Specification Section 4.1" per the module docstring.
  exports: |
    Enums: Domain(SOCIAL_COMMUNICATION, LANGUAGE, PLAY, BEHAVIOR, MOTOR, COGNITIVE, ADAPTIVE,
    SENSORY); Modality(VERBAL, GESTURAL, SIGN, AAC, WRITTEN, MULTIMODAL, UNKNOWN);
    PromptLevel(INDEPENDENT, GESTURAL, VERBAL, MODEL, PARTIAL_PHYSICAL, FULL_PHYSICAL, UNKNOWN);
    Outcome(CORRECT, INCORRECT, APPROXIMATION, NO_RESPONSE, PARTIAL, UNKNOWN);
    Setting(HOME, SCHOOL, CLINIC, COMMUNITY, OTHER, UNKNOWN);
    ContributorRole(INTERVENTIONIST, PARENT, TEACHER, TRAINER, EPA, SECONDARY_INTERVENTIONIST).
    class StructuredObservation(BaseModel): child_id: str, session_id: str, contributor_role:
    ContributorRole, observation_date: date, setting: Setting (app-known/passed-through fields);
    domain?, goal_context?, behavior?, modality?, prompt_context?, prompt_level?, outcome?,
    duration_seconds?(ge=0) (LLM-extracted fields); confidence?(0.0-1.0), abstention_reason?
    (provider-generated fields).
    frozenset constants: LLM_EXTRACTED_FIELDS, APP_KNOWN_FIELDS, PROVIDER_GENERATED_FIELDS
    (lines 106-130) — machine-readable partition of StructuredObservation's field names by
    provenance.
  dependencies: pydantic (BaseModel, Field); enum; datetime.date; typing.Optional. No dependency on any other project module (this file is a leaf).
  data_shapes: |
    StructuredObservation is the canonical shape that (per its docstring) an ExtractionProvider
    implementation should produce and that presumably backs
    models.observation.StructuredRecord.record_data's JSON content — though, as noted above,
    that link is not type-enforced anywhere in this scope, only implied by naming/comments.
  side_effects: none (pure data definitions)
  role: |
    This is the shared contract referenced by CLAUDE.md's "Both providers must return the same
    ExtractionResult contract" requirement — StructuredObservation looks like the field-level
    piece of that contract (an ExtractionResult wrapper, if one exists, would be in the ml/
    layer, out of this scope, and was not found by name in this scope's files). Also the source
    of the Domain and Setting enums reused by models/goal.py, models/observation.py's API
    schema (indirectly), and schemas/api_schemas.py.
  observations: |
    ContributorRole (lines 61-67) duplicates models.user.Role's exact value set
    (INTERVENTIONIST, PARENT, TEACHER, TRAINER, EPA, SECONDARY_INTERVENTIONIST) as a second,
    independently-defined enum with different identity — the two are not the same Python type,
    so code that receives one can't be typed-checked against the other without an explicit
    conversion. This is duplication of the same vocabulary across two modules
    (models/user.py:Role and schemas/observation_schema.py:ContributorRole) with no shared
    base/import between them; api_schemas.py resolves this by using models.user.Role everywhere
    for its own API contracts and only observation_schema's ContributorRole is used inside
    StructuredObservation. Whether this duplication is deliberate (decoupling the ML/extraction
    contract from the auth/RBAC enum on purpose) or accidental drift is unclear from code —
    flagging rather than assuming either way.
    Comment block above the class (lines 71-81) documents field provenance in prose, and the
    three frozensets below re-document the same partition in code — this is good self-documentation,
    but there is no runtime assertion/test *in this file* that the three frozensets are disjoint or
    that their union equals StructuredObservation's actual field set; a future field addition to
    the model without updating the frozensets would silently desync (not verifiable from this
    file alone; would need eval-harness/tests scope to check for such a test).
    `Modality.GESTURAL` and `PromptLevel.GESTURAL` both exist as separate enum members with the
    same string value "gestural" in two different enums (lines 25, 35) — not a bug (they're
    different enums for different concepts: response modality vs. prompt level) but worth
    noting as a naming collision that could cause confusion if ever conflated in code that
    handles both.
```

---

## Cross-cutting observation: Row-Level Security (RLS) claim vs. code

CLAUDE.md states: "Database: migrations via Alembic, child-level RLS on every table" and "Child-level
RBAC enforced at both UI and API layers."

What was actually found in this scope plus a direct check of `alembic/versions/*.py` and
`src/backend/database.py`:

- Alembic **is** in real use (`alembic.ini`, `alembic/env.py`, three versioned migration files:
  `001_initial_schema.py`, `002_add_report_prompt_version_and_version.py`,
  `003_add_missing_foreign_keys.py`) — this part of the CLAUDE.md claim is confirmed.
- No SQL `CREATE POLICY`, `ENABLE ROW LEVEL SECURITY`, `row_security`, or any Postgres RLS
  construct appears anywhere in the three migration files or in any model file in this scope.
  Grepped the whole repo for "ROW LEVEL" / "POLICY" / "row_security" / "RLS" — zero hits outside
  this report and CLAUDE.md itself.
- What actually exists is: every domain table has a plain indexed `child_id` (or a FK chain that
  reaches one) `ForeignKey("children.id")` column, and a separate `ActorAssignment` join table
  (`src/backend/models/actor.py`) maps `(user_id, child_id) -> role`. This is the raw material
  RLS *policies* would be written against, but the policies themselves are not present in this
  scope. Enforcement, if it exists, would have to live in the FastAPI service/dependency layer
  (`src/backend/api/*`, `src/backend/services/*` — out of this sweep's scope) rather than the
  database.
- Conclusion for later phases: "child-level RLS" as literally stated in CLAUDE.md is **not
  observed** in the models/migrations layer; what's observed is child-scoped foreign keys plus
  an app-level actor/role join table. This should be treated as a documentation-vs-implementation
  gap to resolve, not assumed to be implemented elsewhere without checking the api/services scope.

## Other cross-file patterns worth carrying into later phases

- Two enum vocabularies for the same concept exist in parallel: `models.user.Role` (used for
  auth/RBAC/ActorAssignment) and `schemas.observation_schema.ContributorRole` (used inside the
  extraction contract) — identical value sets, different types, no conversion helper found in
  this scope.
- Several JSONB columns (`Observation.conversation_json`, `Observation.extraction_result_json`,
  `StructuredRecord.record_data`, `StructuredRecord.validation_result`,
  `GeneratedReport.report_json`, `GeneratedReport.evidence_packet_json`) carry semantically
  important, presumably-structured data but are untyped at both the DB (JSONB) and Pydantic
  (`dict`) layers — the only place strong typing for "a structured observation" exists is
  `schemas/observation_schema.py:StructuredObservation`, and nothing in this scope binds it to
  where it's actually persisted.
- `report.py` and `schedule.py` are the only two model files with zero `relationship()`
  declarations, breaking from the bidirectional-relationship pattern used everywhere else in
  this scope (`actor.py`, `child.py`, `goal.py`, `observation.py`, `user.py`).
- "Append-only" / "immutable" claims are asserted only in docstrings (`audit.py:15`,
  `observation.py:24`, `observation.py:76`) with no enforcing code in this scope; one of them
  (`ClarificationTurn`, `observation.py:76`) is actually contradicted by its own schema, since
  `answer`/`answered_at` are designed to be filled in after row creation.
```
