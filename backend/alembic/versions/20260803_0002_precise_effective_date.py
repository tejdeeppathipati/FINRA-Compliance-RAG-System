"""Rename effective date to state its precise semantics.

Revision ID: 20260803_0002
Revises: 20260803_0001
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260803_0002"
down_revision: str | None = "20260803_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("documents", "effective_date", new_column_name="latest_effective_date")


def downgrade() -> None:
    op.alter_column("documents", "latest_effective_date", new_column_name="effective_date")

