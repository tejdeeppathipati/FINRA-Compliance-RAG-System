"""Persist normalized rule snapshots and configurable chunk variants."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.ingestion.chunk import ChunkSettings, chunk_document
from app.ingestion.manifest import Source
from app.ingestion.normalize import (
    latest_snapshot_paths,
    normalize_guidance_snapshot,
    normalize_rule_snapshot,
)


def ingest_source_snapshot(
    session: Session,
    *,
    source: Source,
    raw_dir: Path,
    chunk_settings: ChunkSettings | None = None,
    embedding_provider: Callable[[str], list[float]] | None = None,
    embedding_model: str | None = None,
) -> tuple[Document, bool]:
    html_path, metadata_path = latest_snapshot_paths(raw_dir, source)
    normalizer = (
        normalize_rule_snapshot
        if source.source_type.value == "rule"
        else normalize_guidance_snapshot
    )
    normalized = normalizer(html_path=html_path, metadata_path=metadata_path, source=source)
    active_chunk_settings = chunk_settings or ChunkSettings()
    existing = session.scalar(
        select(Document).where(
            Document.source_id == source.source_id,
            Document.normalized_content_hash == normalized.normalized_content_hash,
            Document.chunk_target_tokens == active_chunk_settings.target_tokens,
            Document.chunk_overlap_tokens == active_chunk_settings.overlap_tokens,
        )
    )
    if existing is not None:
        # Re-running ingestion is idempotent, but --embed can backfill vectors on
        # documents that were initially loaded for keyword-only retrieval.
        if embedding_provider is not None:
            existing_chunks = session.scalars(
                select(Chunk)
                .where(Chunk.document_id == existing.id)
                .order_by(Chunk.chunk_index)
            ).all()
            for existing_chunk in existing_chunks:
                if existing_chunk.embedding is None:
                    existing_chunk.embedding = embedding_provider(existing_chunk.content)
                    existing_chunk.embedding_model = embedding_model
            session.flush()
        return existing, False

    document = Document(
        source_id=normalized.source_id,
        rule_number=normalized.rule_number,
        title=normalized.title,
        source_type=source.source_type,
        source_url=normalized.source_url,
        latest_effective_date=(
            date.fromisoformat(normalized.latest_effective_date)
            if normalized.latest_effective_date
            else None
        ),
        retrieved_at=datetime.fromisoformat(normalized.retrieved_at),
        raw_content_hash=normalized.raw_content_hash,
        normalized_content_hash=normalized.normalized_content_hash,
        parser_version=normalized.parser_version,
        normalized_content=normalized.to_dict(),
        chunk_target_tokens=active_chunk_settings.target_tokens,
        chunk_overlap_tokens=active_chunk_settings.overlap_tokens,
    )
    session.add(document)
    session.flush()

    # Flush the document first so every chunk receives its foreign-key identity.
    for chunk in chunk_document(normalized, active_chunk_settings):
        embedding = embedding_provider(chunk.content) if embedding_provider else None
        session.add(
            Chunk(
                document_id=document.id,
                section_path=chunk.section_path,
                subsection=chunk.subsection,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                token_count=chunk.token_count,
                embedding=embedding,
                embedding_model=embedding_model if embedding is not None else None,
            )
        )
    session.flush()
    return document, True


# Backward-compatible name for callers that only ingest rule sources.
ingest_rule_snapshot = ingest_source_snapshot
