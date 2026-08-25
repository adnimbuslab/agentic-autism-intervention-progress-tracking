"""Initial schema — all 12 tables.

Revision ID: 001
Revises: None
Create Date: 2026-08-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

role_enum = postgresql.ENUM(
    "interventionist", "parent", "teacher", "trainer", "epa", "secondary_interventionist",
    name="role",
    create_type=False,
)
goal_type_enum = postgresql.ENUM("long_term", "short_term", name="goaltype", create_type=False)
domain_enum = postgresql.ENUM(
    "social_communication", "language", "play", "behavior", "motor", "cognitive",
    "adaptive", "sensory",
    name="domain",
    create_type=False,
)
observation_status_enum = postgresql.ENUM(
    "pending", "extracting", "clarifying", "finalized", "failed",
    name="observationstatus",
    create_type=False,
)
record_status_enum = postgresql.ENUM(
    "pending", "validated", "corrected", "rejected", "abstained",
    name="recordstatus",
    create_type=False,
)


def upgrade() -> None:
    # Create enum types
    role_enum.create(op.get_bind(), checkfirst=True)
    goal_type_enum.create(op.get_bind(), checkfirst=True)
    domain_enum.create(op.get_bind(), checkfirst=True)
    observation_status_enum.create(op.get_bind(), checkfirst=True)
    record_status_enum.create(op.get_bind(), checkfirst=True)

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(256), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # 2. children
    op.create_table(
        "children",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("date_of_birth", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # 3. actor_assignments
    op.create_table(
        "actor_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("children.id"), nullable=False, index=True),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("invitation_email", sa.String(320), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "child_id", name="uq_actor_user_child"),
    )

    # 4. goals
    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("children.id"), nullable=False, index=True),
        sa.Column("goal_type", goal_type_enum, nullable=False),
        sa.Column("domain", domain_enum, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column("parent_goal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("goals.id"), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    # 5. review_periods
    op.create_table(
        "review_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("children.id"), nullable=False, index=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 6. observations (IMMUTABLE once finalized)
    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("children.id"), nullable=False, index=True),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("setting", sa.String(32), nullable=False),
        sa.Column("status", observation_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("conversation_json", postgresql.JSONB(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extraction_result_json", postgresql.JSONB(), nullable=True),
    )

    # 7. clarification_turns (APPEND-ONLY)
    op.create_table(
        "clarification_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("observations.id"), nullable=False, index=True),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 8. structured_records (versioned)
    op.create_table(
        "structured_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("observations.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", record_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("record_data", postgresql.JSONB(), nullable=False),
        sa.Column("validation_result", postgresql.JSONB(), nullable=True),
        sa.Column("corrected_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("previous_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("structured_records.id"), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 9. reporting_expectations
    op.create_table(
        "reporting_expectations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("children.id"), nullable=False, index=True),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("goals.id"), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("setting", sa.String(32), nullable=True),
        sa.Column("cadence_days", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 10. overdue_events
    op.create_table(
        "overdue_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("expectation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reporting_expectations.id"), nullable=False, index=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 11. generated_reports
    op.create_table(
        "generated_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("children.id"), nullable=False, index=True),
        sa.Column("review_period_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("review_periods.id"), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_packet_json", postgresql.JSONB(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("validation_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("flagged_reason", sa.Text(), nullable=True),
        sa.Column("flagged_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 12. audit_events (APPEND-ONLY)
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("children.id"), nullable=True, index=True),
        sa.Column("action", sa.String(128), nullable=False, index=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("generated_reports")
    op.drop_table("overdue_events")
    op.drop_table("reporting_expectations")
    op.drop_table("structured_records")
    op.drop_table("clarification_turns")
    op.drop_table("observations")
    op.drop_table("review_periods")
    op.drop_table("goals")
    op.drop_table("actor_assignments")
    op.drop_table("children")
    op.drop_table("users")

    record_status_enum.drop(op.get_bind(), checkfirst=True)
    observation_status_enum.drop(op.get_bind(), checkfirst=True)
    domain_enum.drop(op.get_bind(), checkfirst=True)
    goal_type_enum.drop(op.get_bind(), checkfirst=True)
    role_enum.drop(op.get_bind(), checkfirst=True)
