from app.config import Settings


def test_safe_retrieval_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.default_retrieval_mode == "hybrid"
    assert settings.default_top_k == 5
    assert settings.rrf_k == 60

