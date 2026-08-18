"""Generate optional grounded JSON answers using Gemini with citation validation."""

from __future__ import annotations

import json
from dataclasses import dataclass

from google import genai
from google.genai import types

from app.config import Settings, get_settings
from app.generation.prompts import ABSTENTION_TEXT, SYSTEM_PROMPT
from app.retrieval.search import RetrievedPassage


class GenerationProviderError(RuntimeError):
    """Raised when Gemini cannot produce a safely validated answer."""


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    answer: str
    citations: list[dict[str, str | None]]
    abstained: bool


def has_generation_credentials(settings: Settings | None = None) -> bool:
    active_settings = settings or get_settings()
    return active_settings.generation_provider == "gemini" and bool(active_settings.gemini_api_key)


def _prompt(question: str, passages: list[RetrievedPassage]) -> str:
    evidence = "\n\n".join(
        "SOURCE CHUNK {index}\n"
        "rule_number={rule}\n"
        "subsection={subsection}\n"
        "title={title}\n"
        "source_url={url}\n"
        "content={content}"
        .format(
            index=index,
            rule=passage.rule_number or "",
            subsection=passage.subsection or "",
            title=passage.title,
            url=passage.source_url,
            content=passage.content,
        )
        for index, passage in enumerate(passages, start=1)
    )
    return f"""Question:
{question}

Retrieved source passages:
{evidence}

Return only valid JSON with this shape:
{{
  "answer": "grounded answer or the exact abstention text",
  "citations": [
    {{
      "rule_number": "rule number or null",
      "subsection": "subsection or null",
      "title": "source title",
      "source_url": "source URL",
      "supporting_excerpt": "exact short excerpt from a source chunk"
    }}
  ],
  "abstained": false
}}

Every citation must refer to one of the supplied chunks. If the chunks do not support
the answer, use the exact abstention text and return an empty citations array.
"""


def generate_grounded_answer(
    question: str,
    passages: list[RetrievedPassage],
    *,
    settings: Settings | None = None,
) -> GeneratedAnswer:
    active_settings = settings or get_settings()
    if not has_generation_credentials(active_settings):
        raise GenerationProviderError("Gemini generation is not configured")
    client = genai.Client(api_key=active_settings.gemini_api_key)
    response = client.models.generate_content(
        model=active_settings.generation_model,
        contents=_prompt(question, passages),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    try:
        payload = json.loads(response.text or "")
    except (TypeError, json.JSONDecodeError) as error:
        raise GenerationProviderError("Gemini did not return valid JSON") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
        raise GenerationProviderError("Gemini response is missing an answer")
    abstained = bool(payload.get("abstained"))
    raw_citations = payload.get("citations", [])
    if not isinstance(raw_citations, list):
        raise GenerationProviderError("Gemini citations are not a list")
    if abstained:
        return GeneratedAnswer(ABSTENTION_TEXT, [], True)

    citations: list[dict[str, str | None]] = []
    for raw in raw_citations:
        if not isinstance(raw, dict):
            raise GenerationProviderError("Gemini returned an invalid citation")
        rule_number = raw.get("rule_number")
        subsection = raw.get("subsection")
        source_url = raw.get("source_url")
        excerpt = raw.get("supporting_excerpt")
        matches = [
            passage
            for passage in passages
            if passage.rule_number == rule_number
            and passage.subsection == subsection
            and passage.source_url == source_url
        ]
        if not matches or not isinstance(excerpt, str) or excerpt not in matches[0].content:
            raise GenerationProviderError("Gemini returned a citation not supported by evidence")
        citations.append(
            {
                "rule_number": rule_number,
                "subsection": subsection,
                "title": (
                    raw.get("title")
                    if isinstance(raw.get("title"), str)
                    else matches[0].title
                ),
                "source_url": source_url,
                "supporting_excerpt": excerpt,
            }
        )
    if not citations:
        raise GenerationProviderError("Gemini returned no citations for a non-abstained answer")
    return GeneratedAnswer(payload["answer"], citations, False)
