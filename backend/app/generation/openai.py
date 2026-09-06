"""Generate grounded JSON answers with OpenAI and validate citations locally."""

from __future__ import annotations

from openai import OpenAI

from app.config import Settings, get_settings
from app.generation.gemini import (
    GeneratedAnswer,
    GenerationProviderError,
    _prompt,
    parse_generated_payload,
)
from app.generation.prompts import SYSTEM_PROMPT
from app.retrieval.search import RetrievedPassage


def has_generation_credentials(settings: Settings | None = None) -> bool:
    """Return whether OpenAI generation is selected and has a key."""
    active_settings = settings or get_settings()
    return active_settings.generation_provider == "openai" and bool(active_settings.openai_api_key)


def generate_grounded_answer(
    question: str,
    passages: list[RetrievedPassage],
    *,
    settings: Settings | None = None,
) -> GeneratedAnswer:
    """Generate JSON prose, then require every citation to match retrieved evidence."""
    active_settings = settings or get_settings()
    if not has_generation_credentials(active_settings):
        raise GenerationProviderError("OpenAI generation is not configured")
    client = OpenAI(
        api_key=active_settings.openai_api_key,
        timeout=active_settings.request_timeout_seconds,
    )
    response = client.chat.completions.create(
        model=active_settings.generation_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(question, passages)},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content if response.choices else None
    return parse_generated_payload(content, passages)
