from app.config import Settings


def test_safe_retrieval_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.default_retrieval_mode == "hybrid"
    assert settings.default_top_k == 5
    assert settings.rrf_k == 60
    assert settings.migration_database_url == settings.database_url


def test_direct_database_url_is_used_for_migrations() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://pooled/database",
        database_direct_url="postgresql+psycopg://direct/database",
    )

    assert settings.migration_database_url == "postgresql+psycopg://direct/database"
