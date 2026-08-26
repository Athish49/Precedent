from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Required ──────────────────────────────────────────────────────────────
    database_url: str = Field(description="Neon Postgres DSN (psycopg or asyncpg format)")
    anthropic_api_key: str = Field(description="Anthropic API key")

    # ── Object storage ────────────────────────────────────────────────────────
    object_storage_endpoint: str | None = Field(
        default=None,
        description="S3-compatible endpoint URL (e.g. Cloudflare R2). Omit for local dev.",
    )
    object_storage_bucket: str | None = Field(default=None, description="Bucket name")
    object_storage_access_key: str | None = Field(default=None, description="Access key ID")
    object_storage_secret_key: str | None = Field(default=None, description="Secret access key")

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="sentence-transformers model name. Dimension must stay 384.",
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_tier_override: str | None = Field(
        default=None,
        description="Force all LLM tasks to one model ID (e.g. claude-haiku-4-5-20251001). "
        "Useful for cost control during development.",
    )

    # ── Runtime ───────────────────────────────────────────────────────────────
    env: str = Field(
        default="dev",
        description="Runtime environment: 'dev' or 'prod'. Controls log level and dev shortcuts.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
