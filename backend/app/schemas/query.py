from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)
    retrieval_mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=20)


class Citation(BaseModel):
    rule_number: str | None = None
    subsection: str | None = None
    title: str
    source_url: HttpUrl
    supporting_excerpt: str


class RetrievedChunk(BaseModel):
    chunk_id: str
    rule_number: str | None = None
    section_path: str
    subsection: str | None = None
    source_type: Literal["rule", "guidance"]
    source_url: HttpUrl
    retrieved_at: datetime
    content: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    abstained: bool
    retrieved_chunks: list[RetrievedChunk]
    retrieval_configuration: str
    prompt_version: str
    disclaimer: str = "Informational only; not legal, compliance, or investment advice."

