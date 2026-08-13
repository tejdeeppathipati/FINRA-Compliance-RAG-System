from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.ingestion.normalize import NormalizedDocument, NormalizedSection


@dataclass(frozen=True, slots=True)
class ChunkSettings:
    target_tokens: int = 600
    overlap_tokens: int = 50

    def __post_init__(self) -> None:
        if self.target_tokens < 1:
            raise ValueError("target_tokens must be positive")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens cannot be negative")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")


@dataclass(frozen=True, slots=True)
class TextChunk:
    section_path: str
    subsection: str | None
    chunk_index: int
    content: str
    token_count: int
    content_hash: str


def _tokens(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _split_section(section: NormalizedSection, settings: ChunkSettings) -> list[str]:
    tokens = _tokens(section.content)
    if not tokens:
        return []
    if len(tokens) <= settings.target_tokens:
        return [" ".join(tokens)]

    chunks: list[str] = []
    start = 0
    step = settings.target_tokens - settings.overlap_tokens
    while start < len(tokens):
        end = min(start + settings.target_tokens, len(tokens))
        chunks.append(" ".join(tokens[start:end]))
        if end == len(tokens):
            break
        start += step
    return chunks


def chunk_document(
    document: NormalizedDocument,
    settings: ChunkSettings | None = None,
) -> list[TextChunk]:
    active_settings = settings or ChunkSettings()
    chunks: list[TextChunk] = []
    for section in document.sections:
        section_chunks = _split_section(section, active_settings)
        for content in section_chunks:
            chunks.append(
                TextChunk(
                    section_path=section.section_path,
                    subsection=section.label,
                    chunk_index=len(chunks),
                    content=content,
                    token_count=len(_tokens(content)),
                    content_hash=_content_hash(content),
                )
            )
    return chunks
