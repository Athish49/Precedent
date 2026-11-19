import re
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SCHEMA_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_RESERVED_SCHEMAS = frozenset({"public"})


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

    # ── Project partitioning ──────────────────────────────────────────────────
    # The database and the storage account are shared with other projects.
    # Everything this project creates lives in its own namespace: a Postgres
    # schema and an object-key prefix. This is the only place the default
    # name is written; all other code reads it from these settings.
    project_namespace: str = Field(
        default="precedent",
        description="Namespace for everything this project owns on shared infrastructure.",
    )
    db_schema: str = Field(
        default="",
        description="Postgres schema for all tables and views. Defaults to project_namespace. "
        "Must match ^[a-z][a-z0-9_]*$ and must not be 'public'.",
    )
    object_storage_prefix: str = Field(
        default="",
        description="Key prefix applied inside the storage backend. "
        "Defaults to project_namespace.",
    )

    # ── Object storage (required; there is no local fallback) ─────────────────
    object_storage_endpoint: str = Field(
        description="S3-compatible endpoint URL (e.g. Cloudflare R2).",
    )
    object_storage_bucket: str = Field(description="Bucket name")
    object_storage_access_key: str = Field(description="Access key ID")
    object_storage_secret_key: str = Field(description="Secret access key")

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

    # ── TEMPORARY DEV BYPASS ──────────────────────────────────────────────────
    # TEMPORARY: routes LLM calls through a local file queue
    # (backend/.llm_bypass_queue/) instead of the real Anthropic API, so a
    # human-run Claude Code agent can answer them for free during cost-
    # sensitive testing. Must be False/unset in any real deployment.
    # Delete this setting (and app/core/llm/dev_bypass.py, and the bypass
    # blocks in app/core/llm/gateway.py) once testing is done.
    # See backend/.llm_bypass_queue/README.md.
    llm_file_queue_bypass: bool = Field(
        default=False,
        description="TEMPORARY DEV-ONLY: bypass the real Anthropic API with a local file "
        "queue. Never set True in production. Delete alongside dev_bypass.py.",
    )

    # ── Runtime ───────────────────────────────────────────────────────────────
    env: str = Field(
        default="dev",
        description="Runtime environment: 'dev' or 'prod'. Controls log level and dev shortcuts.",
    )

    # ── Analysis (task 4.4) ─────────────────────────────────────────────────
    layer2_max_prompt_chars: int = Field(
        default=60_000,
        description="Max characters in the Layer 2 content-analysis user prompt "
        "(one call per contract) before clauses are split into multiple "
        "batched LLM calls.",
    )

    # ── Document processing: Extend (task 0.1 / plan section 5) ───────────────
    extend_api_key: str | None = Field(
        default=None,
        description="Extend API key. Optional so other settings keep working "
        "without it; document ingest fails with a clear, retryable error "
        "when unset rather than at import time.",
    )
    extend_base_url: str = Field(
        default="",
        description="Extend API base URL. Blank defers to ExtendClient's own "
        "default (app/core/extend/client.py) — the literal URL lives there "
        "only, per the CI guard that confines it to that package.",
    )
    extend_extract_processor: str = Field(
        default="extraction_light",
        description="Extend Extract processor name (pinned, per plan section 3).",
    )
    extend_extract_version: str = Field(
        default="3.8.0",
        description="Pinned Extend Extract processor version.",
    )
    extend_parse_engine: str = Field(
        default="parse_light",
        description="Extend Parse engine name (pinned, per plan section 3).",
    )
    extend_parse_version: str = Field(
        default="1.0.0",
        description="Pinned Extend Parse engine version.",
    )
    extend_poll_interval_seconds: float = Field(
        default=3,
        description="Seconds between polls while waiting for an Extend run to finish.",
    )
    extend_timeout_seconds: float = Field(
        default=300,
        description="Seconds to wait for an Extend run before raising ExtendTimeout.",
    )
    own_org_names: list[str] = Field(
        default_factory=list,
        description="Our own organisation's name(s), for party role assignment "
        "(plan section 5.6). Parsed from a comma-separated OWN_ORG_NAMES.",
    )
    max_upload_mb: int = Field(
        default=25,
        description="Maximum accepted upload size in megabytes.",
    )

    # ── Validation ────────────────────────────────────────────────────────────
    @field_validator("own_org_names", mode="before")
    @classmethod
    def _parse_own_org_names(cls, value: object) -> object:
        if isinstance(value, str):
            return [name.strip() for name in value.split(",") if name.strip()]
        return value

    @field_validator("project_namespace", "db_schema", "object_storage_prefix", mode="before")
    @classmethod
    def _strip_namespace_values(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "object_storage_endpoint",
        "object_storage_bucket",
        "object_storage_access_key",
        "object_storage_secret_key",
    )
    @classmethod
    def _storage_setting_not_blank(cls, value: str) -> str:
        # A blank line such as ``OBJECT_STORAGE_BUCKET=`` counts as missing.
        if not value.strip():
            raise ValueError(
                "must not be empty: cloud object storage is required and there is no "
                "local storage fallback"
            )
        return value.strip()

    @field_validator("anthropic_api_key")
    @classmethod
    def _anthropic_api_key_not_blank(cls, value: str) -> str:
        # A blank line such as ``ANTHROPIC_API_KEY=`` would otherwise pass
        # settings validation and only fail on the first model call.
        if not value.strip():
            raise ValueError("must not be empty: an Anthropic API key is required")
        return value.strip()

    @model_validator(mode="after")
    def _resolve_namespace(self) -> "Settings":
        _check_identifier("project_namespace", self.project_namespace)

        if not self.db_schema:
            self.db_schema = self.project_namespace
        _check_identifier("db_schema", self.db_schema)

        prefix = self.object_storage_prefix.strip("/") or self.project_namespace
        segments = prefix.split("/")
        if "\\" in prefix or any(seg in ("", ".", "..") for seg in segments):
            raise ValueError(
                f"object_storage_prefix {self.object_storage_prefix!r} is not a valid key prefix"
            )
        self.object_storage_prefix = prefix
        return self


def _check_identifier(name: str, value: str) -> None:
    """Raise unless *value* is a safe, non-shared Postgres schema name."""
    if not _SCHEMA_PATTERN.fullmatch(value):
        raise ValueError(f"{name} {value!r} must match {_SCHEMA_PATTERN.pattern}")
    if value in _RESERVED_SCHEMAS:
        raise ValueError(
            f"{name} must not be {value!r}: that schema is shared with other projects"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
