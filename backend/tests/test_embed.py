from types import SimpleNamespace

from app.config import Settings
from app.ingestion.embed import embed_text, embedding_model_name, has_embedding_credentials


def test_gemini_embedding_provider_uses_retrieval_configuration(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeModels:
        def embed_content(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                embeddings=[SimpleNamespace(values=[0.0] * 1536)],
            )

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr("app.ingestion.embed.genai.Client", lambda **_: FakeClient())
    settings = Settings(
        embedding_provider="gemini",
        gemini_api_key="test-key",
        gemini_embedding_model="gemini-embedding-001",
    )

    values = embed_text("Rule 2090", purpose="document", settings=settings)

    assert len(values) == 1536
    assert calls["model"] == "gemini-embedding-001"
    assert calls["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert calls["config"].output_dimensionality == 1536
    assert has_embedding_credentials(settings) is True
    assert embedding_model_name(settings) == "gemini-embedding-001"
