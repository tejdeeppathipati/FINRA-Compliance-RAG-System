"""Define PostgreSQL tables for documents, chunks, traces, and evaluations."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.ingestion.manifest import SourceType

SHA256_PATTERN = "^[a-f0-9]{64}$"
EMBEDDING_DIMENSIONS = 1536


class Base(DeclarativeBase):
    pass


source_type_enum = Enum(
    SourceType,
    name="source_type",
    values_callable=lambda enum: [member.value for member in enum],
)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            f"raw_content_hash ~ '{SHA256_PATTERN}'",
            name="documents_raw_content_hash_sha256",
        ),
        CheckConstraint(
            f"normalized_content_hash ~ '{SHA256_PATTERN}'",
            name="documents_normalized_content_hash_sha256",
        ),
        UniqueConstraint(
            "source_id",
            "normalized_content_hash",
            "chunk_target_tokens",
            "chunk_overlap_tokens",
            name="uq_documents_source_normalized_hash",
        ),
        Index("ix_documents_source_retrieved", "source_id", "retrieved_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_number: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(source_type_enum, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    latest_effective_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    chunk_target_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    chunk_overlap_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="chunks_chunk_index_nonnegative"),
        CheckConstraint("token_count > 0", name="chunks_token_count_positive"),
        CheckConstraint(
            f"content_hash ~ '{SHA256_PATTERN}'",
            name="chunks_content_hash_sha256",
        ),
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    subsection: Mapped[str | None] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(section_path, '') || ' ' || content)",
            persisted=True,
        ),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class QueryLog(Base):
    __tablename__ = "query_logs"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="query_logs_latency_nonnegative"),
        Index("ix_query_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retrieved_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), nullable=False)
    retrieval_configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_rule_numbers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expected_subsections: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expected_answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reference_notes: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)

    results: Mapped[list[EvaluationResult]] = relationship(back_populates="evaluation_case")


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        CheckConstraint(
            "reciprocal_rank >= 0 AND reciprocal_rank <= 1",
            name="evaluation_results_reciprocal_rank_range",
        ),
        CheckConstraint(
            "unsupported_claim_count >= 0",
            name="evaluation_results_unsupported_claims_nonnegative",
        ),
        Index("ix_evaluation_results_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_case_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("evaluation_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    retrieved_rule_numbers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    retrieved_subsections: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    reciprocal_rank: Mapped[float] = mapped_column(Double, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    passed_grounding: Mapped[bool | None] = mapped_column(Boolean)
    passed_abstention: Mapped[bool | None] = mapped_column(Boolean)
    unsupported_claim_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    evaluation_case: Mapped[EvaluationCase] = relationship(back_populates="results")
