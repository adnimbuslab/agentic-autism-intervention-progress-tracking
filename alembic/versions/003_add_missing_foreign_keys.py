"""Add missing foreign key constraints.

Revision ID: 003
Revises: 002
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_children_created_by_users",
        "children",
        "users",
        ["created_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_children_created_by_users", "children", type_="foreignkey")
