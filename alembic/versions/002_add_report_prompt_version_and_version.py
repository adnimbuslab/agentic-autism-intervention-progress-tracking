"""Add prompt_version and version to generated_reports.

Revision ID: 002
Revises: 001
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generated_reports",
        sa.Column(
            "prompt_version",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'1.0'"),
        ),
    )
    op.add_column(
        "generated_reports",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("generated_reports", "version")
    op.drop_column("generated_reports", "prompt_version")
