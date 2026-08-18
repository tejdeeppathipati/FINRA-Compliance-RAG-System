"""Provide interchangeable OpenAI/Gemini embedding adapters for retrieval."""

from __future__ import annotations

from typing import Literal

from google import genai
from google.genai import types
from openai import OpenAI

from app.config import Settings, get_settings
from app.db.models import EMBEDDING_DIMENSIONS


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding cannot be produced safely."""


def embedding_model_name(settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    if active_settings.embedding_provider == "gemini":
        return active_settings.gemini_embedding_model
    return active_settings.embedding_model


def has_embedding_credentials(settings: Settings | None = None) -> bool:
    active_settings = settings or get_settings()
    if active_settings.embedding_provider == "gemini":
        return bool(active_settings.gemini_api_key)
    return bool(active_settings.openai_api_key)


def embed_text(
    text: str,
    *,
    purpose: Literal["document", "query"] = "query",
    settings: Settings | None = None,
) -> list[float]:
    active_settings = settings or get_settings()
    if active_settings.embedding_provider == "gemini":
        # Gemini distinguishes stored-document and live-query embeddings; using the
        # matching task type improves semantic retrieval quality.
        if not active_settings.gemini_api_key:
            raise EmbeddingProviderError("GEMINI_API_KEY is not configured")
        client = genai.Client(api_key=active_settings.gemini_api_key)
        task_type = "RETRIEVAL_DOCUMENT" if purpose == "document" else "RETRIEVAL_QUERY"
        response = client.models.embed_content(
            model=active_settings.gemini_embedding_model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBEDDING_DIMENSIONS,
            ),
        )
        values = response.embeddings[0].values if response.embeddings else None
    else:
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
        values = response.data[0].embedding if response.data else None
    if not values or len(values) != EMBEDDING_DIMENSIONS:
        raise EmbeddingProviderError(
            f"Embedding provider returned an unexpected dimension; expected {EMBEDDING_DIMENSIONS}"
        )
    return list(values)
