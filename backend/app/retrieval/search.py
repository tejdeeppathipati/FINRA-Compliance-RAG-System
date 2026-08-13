from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.retrieval.rank_fusion import RankedItem, reciprocal_rank_fusion


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    chunk_id: UUID
    document_id: UUID
    rule_number: str | None
    title: str
    source_type: str
    source_url: str
    retrieved_at: Any
    section_path: str
    subsection: str | None
    content: str
    score: float


def _latest_documents_subquery():
    return (
        select(
            Document.id.label("latest_document_id"),
            Document.source_id,
        )
        .distinct(Document.source_id)
        .order_by(Document.source_id, Document.retrieved_at.desc(), Document.id.desc())
        .subquery()
    )


def _base_query() -> Select[tuple[Chunk, Document]]:
    latest_documents = _latest_documents_subquery()
    return (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .join(
            latest_documents,
            latest_documents.c.latest_document_id == Document.id,
        )
    )


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "by",
    "can",
    "does",
    "for",
    "how",
    "in",
    "is",
    "it",
    "must",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "which",
    "with",
}


def _keyword_tsquery(question: str) -> str:
    terms = [
        term
        for term in re.findall(r"[A-Za-z0-9]+", question.lower())
        if len(term) > 2 and term not in STOP_WORDS
    ]
    return " | ".join(dict.fromkeys(terms)) or question


def keyword_search(session: Session, question: str, *, limit: int = 15) -> list[RetrievedPassage]:
    query = func.to_tsquery("english", _keyword_tsquery(question))
    rank = func.ts_rank_cd(Chunk.search_vector, query)
    statement = (
        _base_query()
        .where(Chunk.search_vector.op("@@")(query))
        .order_by(rank.desc(), Chunk.id)
        .add_columns(rank.label("rank"))
        .limit(limit)
    )
    rows = session.execute(statement).all()
    return [
        _passage(chunk, document, score=float(rank_value))
        for chunk, document, rank_value in rows
    ]


def vector_search(
    session: Session,
    embedding: list[float],
    *,
    limit: int = 15,
) -> list[RetrievedPassage]:
    distance = Chunk.embedding.cosine_distance(embedding)
    latest_documents = _latest_documents_subquery()
    statement = (
        select(Chunk, Document, distance.label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .join(
            latest_documents,
            latest_documents.c.latest_document_id == Document.id,
        )
        .where(Chunk.embedding.is_not(None))
        .order_by(distance, Chunk.id)
        .limit(limit)
    )
    rows = session.execute(statement).all()
    return [
        _passage(chunk, document, score=1.0 - float(distance))
        for chunk, document, distance in rows
    ]


def hybrid_search(
    session: Session,
    question: str,
    *,
    limit: int = 5,
    vector_embedding: list[float] | None = None,
    rrf_k: int = 60,
) -> list[RetrievedPassage]:
    keyword = keyword_search(session, question, limit=15)
    rankings: list[list[RankedItem[RetrievedPassage]]] = [
        [RankedItem(passage.chunk_id, passage) for passage in keyword]
    ]
    if vector_embedding is not None:
        vector = vector_search(session, vector_embedding, limit=15)
        rankings.append([RankedItem(passage.chunk_id, passage) for passage in vector])
    fused = reciprocal_rank_fusion(rankings, rrf_k=rrf_k)
    return [
        RetrievedPassage(
            chunk_id=passage.chunk_id,
            document_id=passage.document_id,
            rule_number=passage.rule_number,
            title=passage.title,
            source_type=passage.source_type,
            source_url=passage.source_url,
            retrieved_at=passage.retrieved_at,
            section_path=passage.section_path,
            subsection=passage.subsection,
            content=passage.content,
            score=score,
        )
        for passage, score in fused[:limit]
    ]


def _passage(chunk: Chunk, document: Document, *, score: float) -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id=chunk.id,
        document_id=document.id,
        rule_number=document.rule_number,
        title=document.title,
        source_type=document.source_type.value,
        source_url=document.source_url,
        retrieved_at=document.retrieved_at,
        section_path=chunk.section_path,
        subsection=chunk.subsection,
        content=chunk.content,
        score=score,
    )
