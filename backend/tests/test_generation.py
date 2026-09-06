"""Verify Gemini output is accepted only when its citation maps to evidence."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.config import Settings
from app.generation.gemini import generate_grounded_answer
from app.generation.openai import generate_grounded_answer as generate_openai_grounded_answer
from app.retrieval.search import RetrievedPassage


def test_gemini_grounded_answer_requires_supported_excerpt(monkeypatch) -> None:
    passage = RetrievedPassage(
        chunk_id=uuid4(),
        document_id=uuid4(),
        rule_number="4512",
        title="Customer Account Information",
        source_type="rule",
        source_url="https://www.finra.org/rules-guidance/rulebooks/finra-rules/4512",
        retrieved_at=datetime.now(UTC),
        section_path="4512 > (a)",
        subsection="(a)",
        content="Each member shall maintain the following information.",
        score=1.0,
    )

    class FakeModels:
        def generate_content(self, **_kwargs):
            return SimpleNamespace(
                text='{"answer":"A member must maintain the listed account information.",'
                '"citations":[{"rule_number":"4512","subsection":"(a)",'
                '"title":"Customer Account Information",'
                '"source_url":"https://www.finra.org/rules-guidance/rulebooks/finra-rules/4512",'
                '"supporting_excerpt":"Each member shall maintain the following information."}],'
                '"abstained":false}'
            )

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr("app.generation.gemini.genai.Client", lambda **_: FakeClient())
    result = generate_grounded_answer(
        "What account information must a member maintain?",
        [passage],
        settings=Settings(generation_provider="gemini", gemini_api_key="test-key"),
    )

    assert result.abstained is False
    assert result.answer.startswith("A member must maintain")
    assert result.citations[0]["rule_number"] == "4512"


def test_openai_grounded_answer_requires_supported_citation(monkeypatch) -> None:
    passage = RetrievedPassage(
        chunk_id=uuid4(),
        document_id=uuid4(),
        rule_number="4512",
        title="Customer Account Information",
        source_type="rule",
        source_url="https://www.finra.org/rules-guidance/rulebooks/finra-rules/4512",
        retrieved_at=datetime.now(UTC),
        section_path="4512 > (a)",
        subsection="(a)",
        content="Each member shall maintain the following information.",
        score=1.0,
    )

    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"answer":"A member must maintain the listed account '
                                'information.",'
                                '"citations":[{"rule_number":"4512","subsection":"(a)",'
                                '"title":"Customer Account Information",'
                                '"source_url":"https://www.finra.org/rules-guidance/rulebooks/finra-rules/4512",'
                                '"supporting_excerpt":"Each member shall maintain the following '
                                'information."}],'
                                '"abstained":false}'
                            )
                        )
                    )
                ]
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.generation.openai.OpenAI", lambda **_: FakeClient())
    result = generate_openai_grounded_answer(
        "What account information must a member maintain?",
        [passage],
        settings=Settings(
            generation_provider="openai",
            openai_api_key="test-key",
            generation_model="gpt-4.1-mini",
        ),
    )

    assert result.abstained is False
    assert result.citations[0]["subsection"] == "(a)"
