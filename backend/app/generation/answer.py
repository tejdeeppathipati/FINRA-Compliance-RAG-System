"""Turn retrieved passages into a citation-bearing, evidence-only response."""

from __future__ import annotations

from collections.abc import Sequence

from app.config import get_settings
from app.generation.gemini import GenerationProviderError, generate_grounded_answer
from app.generation.openai import generate_grounded_answer as generate_openai_answer
from app.generation.prompts import ABSTENTION_TEXT, PROMPT_VERSION
from app.retrieval.search import RetrievedPassage
from app.schemas.query import Citation, QueryResponse, RetrievedChunk


def build_grounded_response(
    passages: Sequence[RetrievedPassage],
    *,
    question: str | None = None,
    retrieval_configuration: str,
    top_k: int,
) -> QueryResponse:
    selected = list(passages[:top_k])
    if not selected:
        return QueryResponse(
            answer=ABSTENTION_TEXT,
            citations=[],
            abstained=True,
            retrieved_chunks=[],
            retrieval_configuration=retrieval_configuration,
            prompt_version=PROMPT_VERSION,
        )

    citations = [
        Citation(
            rule_number=passage.rule_number,
            subsection=passage.subsection,
            title=passage.title,
            source_url=passage.source_url,
            supporting_excerpt=passage.content[:500],
        )
        for passage in selected
    ]
    chunks = [
        RetrievedChunk(
            chunk_id=str(passage.chunk_id),
            rule_number=passage.rule_number,
            section_path=passage.section_path,
            subsection=passage.subsection,
            source_type=passage.source_type,
            source_url=passage.source_url,
            retrieved_at=passage.retrieved_at,
            content=passage.content,
            score=passage.score,
        )
        for passage in selected
    ]
    # The deterministic evidence response is the safety fallback. A configured model
    # can replace only the prose/citation fields after its citations are checked.
    if question and get_settings().generation_provider in {"gemini", "openai"}:
        try:
            generated = (
                generate_grounded_answer(question, selected)
                if get_settings().generation_provider == "gemini"
                else generate_openai_answer(question, selected)
            )
            if generated.abstained:
                return QueryResponse(
                    answer=ABSTENTION_TEXT,
                    citations=[],
                    abstained=True,
                    retrieved_chunks=chunks,
                    retrieval_configuration=retrieval_configuration,
                    prompt_version=PROMPT_VERSION,
                )
            return QueryResponse(
                answer=generated.answer,
                citations=generated.citations,
                abstained=False,
                retrieved_chunks=chunks,
                retrieval_configuration=retrieval_configuration,
                prompt_version=PROMPT_VERSION,
            )
        except GenerationProviderError:
            pass

    evidence = "\n\n".join(
        f"[{index}] {passage.content}" for index, passage in enumerate(selected, start=1)
    )
    return QueryResponse(
        answer=(
            "The indexed FINRA evidence relevant to this question is below. "
            "Review the cited rule text and subsection before relying on it.\n\n"
            + evidence
        ),
        citations=citations,
        abstained=False,
        retrieved_chunks=chunks,
        retrieval_configuration=retrieval_configuration,
        prompt_version=PROMPT_VERSION,
    )
