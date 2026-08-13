from __future__ import annotations

from openai import OpenAI

from app.config import Settings, get_settings
from app.db.models import EMBEDDING_DIMENSIONS


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding cannot be produced safely."""


def embed_text(text: str, *, settings: Settings | None = None) -> list[float]:
    active_settings = settings or get_settings()
    if not active_settings.openai_api_key:
        raise EmbeddingProviderError("OPENAI_API_KEY is not configured")
    client = OpenAI(
        api_key=active_settings.openai_api_key,
        timeout=active_settings.request_timeout_seconds,
    )
    response = client.embeddings.create(
        model=active_settings.embedding_model,
        input=text,
    )
    if not response.data or len(response.data[0].embedding) != EMBEDDING_DIMENSIONS:
        raise EmbeddingProviderError(
            f"Embedding provider returned an unexpected dimension; expected {EMBEDDING_DIMENSIONS}"
        )
    return list(response.data[0].embedding)
