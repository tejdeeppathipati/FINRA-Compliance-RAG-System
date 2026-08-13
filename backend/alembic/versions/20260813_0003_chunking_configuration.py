"""Record chunking configuration per indexed document variant.

Revision ID: 20260813_0003
Revises: 20260803_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260813_0003"
down_revision: str | None = "20260803_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("chunk_target_tokens", sa.Integer(), nullable=False, server_default="600"),
    )
    op.add_column(
        "documents",
        sa.Column("chunk_overlap_tokens", sa.Integer(), nullable=False, server_default="50"),
    )
    op.drop_constraint("uq_documents_source_normalized_hash", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_source_normalized_hash",
        "documents",
        [
            "source_id",
            "normalized_content_hash",
            "chunk_target_tokens",
            "chunk_overlap_tokens",
        ],
    )
    op.alter_column("documents", "chunk_target_tokens", server_default=None)
    op.alter_column("documents", "chunk_overlap_tokens", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_documents_source_normalized_hash", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_source_normalized_hash",
        "documents",
        ["source_id", "normalized_content_hash"],
    )
    op.drop_column("documents", "chunk_overlap_tokens")
    op.drop_column("documents", "chunk_target_tokens")
