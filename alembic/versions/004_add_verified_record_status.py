"""Add VERIFIED record status and verification provenance.

Separates "passed deterministic validation" from "a human accepted it".
Before this change, analytics admitted records with status VALIDATED, which is
set automatically on four routing paths and means only that the record was
schema-conformant. A semantically wrong but schema-valid value therefore
reached longitudinal analytics unreviewed.

Existing VALIDATED rows are deliberately **not** migrated to VERIFIED: nobody
verified them, and relabelling them would assert a human review that never
happened. They stop being analytics-eligible, which is the intended effect.

Revision ID: 004
Revises: 003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "recordstatus"


def upgrade() -> None:
    # Postgres cannot add an enum value inside a transaction block on older
    # versions; ALTER TYPE ... ADD VALUE IF NOT EXISTS is safe and idempotent.
    op.execute(f"ALTER TYPE {_ENUM_NAME} ADD VALUE IF NOT EXISTS 'verified'")

    op.add_column(
        "structured_records",
        sa.Column("verified_by", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "structured_records",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_structured_records_verified_by_users",
        "structured_records",
        "users",
        ["verified_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_structured_records_verified_by_users",
        "structured_records",
        type_="foreignkey",
    )
    op.drop_column("structured_records", "verified_at")
    op.drop_column("structured_records", "verified_by")
    # The enum value is intentionally left in place. Removing a value from a
    # Postgres enum requires recreating the type and rewriting every dependent
    # column, and any row already carrying 'verified' would be destroyed.
