"""Create the FINRA document, retrieval trace, and evaluation schema.

Revision ID: 20260803_0001
Revises:
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260803_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

source_type = postgresql.ENUM("rule", "guidance", name="source_type", create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    source_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("rule_number", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_content_hash", sa.Text(), nullable=False),
        sa.Column("normalized_content_hash", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("normalized_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "normalized_content_hash ~ '^[a-f0-9]{64}$'",
            name="documents_normalized_content_hash_sha256",
        ),
        sa.CheckConstraint(
            "raw_content_hash ~ '^[a-f0-9]{64}$'",
            name="documents_raw_content_hash_sha256",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "normalized_content_hash",
            name="uq_documents_source_normalized_hash",
        ),
    )
    op.create_index(
        "ix_documents_source_retrieved",
        "documents",
        ["source_id", "retrieved_at"],
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False),
        sa.Column("subsection", sa.Text(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(section_path, '') || ' ' || content)",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.CheckConstraint("chunk_index >= 0", name="chunks_chunk_index_nonnegative"),
        sa.CheckConstraint(
            "content_hash ~ '^[a-f0-9]{64}$'",
            name="chunks_content_hash_sha256",
        ),
        sa.CheckConstraint("token_count > 0", name="chunks_token_count_positive"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("embedding IS NOT NULL"),
    )
    op.create_index(
        "ix_chunks_search_vector",
        "chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.create_table(
        "query_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("abstained", sa.Boolean(), nullable=False),
        sa.Column("retrieved_chunk_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column(
            "retrieval_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.CheckConstraint("latency_ms >= 0", name="query_logs_latency_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_logs_created_at", "query_logs", ["created_at"])

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_rule_numbers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("expected_subsections", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("expected_answerable", sa.Boolean(), nullable=False),
        sa.Column("reference_notes", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_case_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieved_rule_numbers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("retrieved_subsections", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("reciprocal_rank", sa.Double(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("passed_grounding", sa.Boolean(), nullable=True),
        sa.Column("passed_abstention", sa.Boolean(), nullable=True),
        sa.Column("unsupported_claim_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reciprocal_rank >= 0 AND reciprocal_rank <= 1",
            name="evaluation_results_reciprocal_rank_range",
        ),
        sa.CheckConstraint(
            "unsupported_claim_count >= 0",
            name="evaluation_results_unsupported_claims_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"],
            ["evaluation_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_run_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_cases")
    op.drop_index("ix_query_logs_created_at", table_name="query_logs")
    op.drop_table("query_logs")
    op.drop_index("ix_chunks_search_vector", table_name="chunks", postgresql_using="gin")
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks", postgresql_using="hnsw")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_documents_source_retrieved", table_name="documents")
    op.drop_table("documents")
    source_type.drop(op.get_bind(), checkfirst=True)
