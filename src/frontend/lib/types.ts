/**
 * TypeScript mirrors of the backend API contracts
 * (src/backend/schemas/api_schemas.py and the model enums). UUIDs, dates and
 * datetimes arrive as strings.
 */

// ─── Enums ──────────────────────────────────────────────────────

export type Role =
  | "interventionist"
  | "parent"
  | "teacher"
  | "trainer"
  | "epa"
  | "secondary_interventionist";

export type Domain =
  | "social_communication"
  | "language"
  | "play"
  | "behavior"
  | "motor"
  | "cognitive"
  | "adaptive"
  | "sensory";

export type Setting =
  | "home"
  | "school"
  | "clinic"
  | "community"
  | "other"
  | "unknown";

export type GoalType = "long_term" | "short_term";

export type ObservationStatus =
  | "pending"
  | "extracting"
  | "clarifying"
  | "finalized"
  | "failed";

/**
 * `validated` is schema-conformant but unseen by a human; only `verified`
 * and `corrected` records are admitted to longitudinal analytics.
 */
export type RecordStatus =
  | "pending"
  | "validated"
  | "verified"
  | "corrected"
  | "rejected"
  | "abstained";

// ─── Users and children ─────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type?: string;
}

export interface Child {
  id: string;
  display_name: string;
  date_of_birth: string | null;
  created_by: string;
  created_at: string;
  is_active: boolean;
}

// ─── Goals ──────────────────────────────────────────────────────

export interface Goal {
  id: string;
  child_id: string;
  goal_type: GoalType;
  domain: Domain;
  title: string;
  description: string;
  criteria: string | null;
  parent_goal_id: string | null;
  start_date: string | null;
  target_date: string | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at?: string;
}

export interface GoalCreateRequest {
  goal_type: GoalType;
  domain: Domain;
  title: string;
  description: string;
  criteria?: string | null;
  parent_goal_id?: string | null;
  start_date?: string | null;
  target_date?: string | null;
}

// ─── Actors ─────────────────────────────────────────────────────

export interface ActorAssignment {
  id: string;
  user_id: string;
  child_id: string;
  role: Role;
  invited_by: string;
  invited_at: string;
  invitation_email: string | null;
  revoked_at: string | null;
}

export interface ActorInviteRequest {
  email: string;
  role: Role;
}

// ─── Observations ───────────────────────────────────────────────

export interface Observation {
  id: string;
  child_id: string;
  submitted_by: string;
  raw_text: string;
  source_type: string;
  setting: string;
  status: ObservationStatus;
  submitted_at: string;
  finalized_at: string | null;
}

export interface ClarificationTurn {
  turn_number: number;
  question: string;
  answer: string | null;
  created_at: string;
  answered_at: string | null;
}

export interface ObservationDetail extends Observation {
  clarification_turns: ClarificationTurn[];
  structured_record: StructuredRecord | null;
}

export interface ObservationCreateRequest {
  raw_text: string;
  setting: Setting;
  source_type?: string;
  goal_id?: string | null;
}

export interface ClarificationRequest {
  answer: string | null;
  declined: boolean;
}

export interface ObservationSubmitResponse {
  observation: Observation;
  routing_decision: string;
  clarification_question: string | null;
}

// ─── Structured records ─────────────────────────────────────────

export interface StructuredRecord {
  id: string;
  observation_id: string;
  version: number;
  status: RecordStatus;
  record_data: Record<string, unknown>;
  validation_result: Record<string, unknown> | null;
  corrected_by: string | null;
  correction_reason: string | null;
  verified_by?: string | null;
  verified_at?: string | null;
  provider: string;
  model: string;
  prompt_version: string;
  created_at: string;
}

export interface RecordCorrectionRequest {
  record_data: Record<string, unknown>;
  correction_reason: string;
}

// ─── Schedules ──────────────────────────────────────────────────

export interface OverdueInfo {
  is_overdue: boolean;
  due_date: string | null;
  days_overdue: number;
}

export interface Schedule {
  id: string;
  child_id: string;
  goal_id: string | null;
  actor_id: string | null;
  setting: string | null;
  cadence_days: number;
  description: string | null;
  is_active: boolean;
  created_at: string;
  overdue: OverdueInfo | null;
}

export interface ScheduleCreateRequest {
  goal_id?: string | null;
  actor_id?: string | null;
  setting?: Setting | null;
  cadence_days: number;
  description?: string | null;
}

// ─── Audit ──────────────────────────────────────────────────────

export interface AuditEvent {
  id: string;
  user_id: string;
  child_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

// ─── Analytics ──────────────────────────────────────────────────

export interface ReviewPeriod {
  id: string;
  child_id: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
  created_at: string;
}

export interface ReviewPeriodCreateRequest {
  start_date: string;
  end_date: string;
}

export interface KpiResult {
  name: string;
  numerator: number;
  denominator: number;
  value: number | null;
  abstained: boolean;
  abstention_reason: string | null;
  display_eligible: boolean;
}

export interface AdequacyCheck {
  check: string;
  passed: boolean;
  detail: string;
  value: number | null;
  threshold: number | null;
}

export interface AdequacyResponse {
  level: string;
  eligible: boolean;
  checks: AdequacyCheck[];
  partial_abstentions: Record<string, string>;
  quality_flags: string[];
}

export interface AnalyticsResponse {
  child_id: string;
  review_period_id: string;
  goal_id: string | null;
  kpis: KpiResult[];
  adequacy: AdequacyResponse;
  computed_at: string;
}

// ─── Reports ────────────────────────────────────────────────────

export interface ReportSection {
  heading: string;
  body: string;
  evidence_refs: string[];
  abstention_note: string | null;
}

export interface ReportResponse {
  id: string;
  child_id: string;
  review_period_id: string;
  sections: ReportSection[];
  provider: string;
  model: string;
  prompt_version: string;
  version: number;
  validation_passed: boolean;
  validation_errors: Record<string, unknown> | null;
  flagged: boolean;
  flagged_reason: string | null;
  flagged_by: string | null;
  generated_at: string;
  is_experimental?: boolean;
}

export interface ReportListItem {
  id: string;
  child_id: string;
  review_period_id: string;
  version: number;
  validation_passed: boolean;
  flagged: boolean;
  generated_at: string;
}

export interface ReportGenerateRequest {
  review_period_id: string;
  goal_id?: string | null;
}

export interface ReportFlagRequest {
  reason: string;
}

export interface EvidencePacket {
  child_id: string;
  review_period_id: string;
  review_period_start: string;
  review_period_end: string;
  goals: Record<string, unknown>[];
  record_ids: string[];
  record_versions: Record<string, number>;
  contributor_summary: Record<string, number>;
  setting_summary: Record<string, number>;
  observation_count: number;
  abstained_count: number;
  review_count: number;
  quality_flags: string[];
}
