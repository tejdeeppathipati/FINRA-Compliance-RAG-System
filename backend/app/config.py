from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://finra:finra@localhost:5432/finra_rag"
    database_direct_url: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    embedding_provider: Literal["openai", "gemini"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    gemini_embedding_model: str = "gemini-embedding-001"
    generation_model: str = "gpt-4.1-mini"
    prompt_version: str = "finra-grounded-v1"
    default_retrieval_mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    default_top_k: int = Field(default=5, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1)
    request_timeout_seconds: float = Field(default=30, gt=0)

    @property
    def migration_database_url(self) -> str:
        return self.database_direct_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
