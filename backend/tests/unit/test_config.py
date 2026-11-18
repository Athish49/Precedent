import pytest
from pydantic import ValidationError

from app.core.config import Settings

_STORAGE_ENV = {
    "OBJECT_STORAGE_ENDPOINT": "https://storage.invalid",
    "OBJECT_STORAGE_BUCKET": "test-bucket",
    "OBJECT_STORAGE_ACCESS_KEY": "test-access-key",
    "OBJECT_STORAGE_SECRET_KEY": "test-secret-key",
}

_NAMESPACE_ENV = ("PROJECT_NAMESPACE", "DB_SCHEMA", "OBJECT_STORAGE_PREFIX")


def _base_env() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql+psycopg://user:pass@ep-test.us-east-2.aws.neon.tech/testdb?sslmode=require",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        **_STORAGE_ENV,
    }


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://user:pass@ep-test.us-east-2.aws.neon.tech/testdb?sslmode=require"
    assert s.anthropic_api_key == "sk-ant-test"


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.env == "dev"
    assert s.llm_tier_override is None
    assert s.object_storage_endpoint == "https://storage.invalid"
    assert s.object_storage_bucket == "test-bucket"


def test_missing_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "database_url" in str(exc_info.value).lower()


def test_missing_anthropic_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@ep-test.us-east-2.aws.neon.tech/testdb?sslmode=require")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "anthropic_api_key" in str(exc_info.value).lower()


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_anthropic_api_key_raises(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ANTHROPIC_API_KEY", blank)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "anthropic_api_key" in str(exc_info.value).lower()


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("LLM_TIER_OVERRIDE", "claude-haiku-4-5-20251001")
    s = Settings(_env_file=None)
    assert s.env == "prod"
    assert s.llm_tier_override == "claude-haiku-4-5-20251001"


# ── Project namespace ─────────────────────────────────────────────────────────


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Base env set, namespace variables unset."""
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    for name in _NAMESPACE_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_namespace_defaults(clean_env: pytest.MonkeyPatch) -> None:
    s = Settings(_env_file=None)
    assert s.project_namespace == "precedent"
    assert s.db_schema == "precedent"
    assert s.object_storage_prefix == "precedent"


def test_schema_and_prefix_follow_namespace(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("PROJECT_NAMESPACE", "other_project")
    s = Settings(_env_file=None)
    assert s.db_schema == "other_project"
    assert s.object_storage_prefix == "other_project"


def test_blank_schema_and_prefix_fall_back_to_namespace(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DB_SCHEMA", "")
    clean_env.setenv("OBJECT_STORAGE_PREFIX", "")
    s = Settings(_env_file=None)
    assert s.db_schema == "precedent"
    assert s.object_storage_prefix == "precedent"


def test_schema_and_prefix_can_be_overridden(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DB_SCHEMA", "precedent_staging")
    clean_env.setenv("OBJECT_STORAGE_PREFIX", "/shared/precedent/")
    s = Settings(_env_file=None)
    assert s.project_namespace == "precedent"
    assert s.db_schema == "precedent_staging"
    assert s.object_storage_prefix == "shared/precedent"


def test_db_schema_public_is_rejected(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DB_SCHEMA", "public")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "db_schema" in str(exc_info.value)
    assert "public" in str(exc_info.value)


def test_namespace_public_is_rejected(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("PROJECT_NAMESPACE", "public")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "value",
    ["Precedent", "1precedent", "pre-cedent", "pre cedent", "precedent;drop", '"precedent"', "a.b"],
)
def test_db_schema_must_match_pattern(clean_env: pytest.MonkeyPatch, value: str) -> None:
    clean_env.setenv("DB_SCHEMA", value)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "db_schema" in str(exc_info.value)


@pytest.mark.parametrize("value", ["a/../b", "..", "a//b", "a\\b"])
def test_object_storage_prefix_must_be_a_clean_path(
    clean_env: pytest.MonkeyPatch, value: str
) -> None:
    clean_env.setenv("OBJECT_STORAGE_PREFIX", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# ── Object storage is required ────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(_STORAGE_ENV))
def test_missing_storage_setting_raises(clean_env: pytest.MonkeyPatch, name: str) -> None:
    clean_env.delenv(name)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert name.lower() in str(exc_info.value).lower()


@pytest.mark.parametrize("name", sorted(_STORAGE_ENV))
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_storage_setting_raises(
    clean_env: pytest.MonkeyPatch, name: str, blank: str
) -> None:
    clean_env.setenv(name, blank)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert name.lower() in str(exc_info.value).lower()


@pytest.mark.parametrize("name", sorted(_STORAGE_ENV))
def test_application_startup_fails_without_storage_setting(
    clean_env: pytest.MonkeyPatch, name: str
) -> None:
    """Starting the app (lifespan) raises when a storage setting is missing."""
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import app

    # Ignore any developer .env so only the variables set here count.
    clean_env.setitem(Settings.model_config, "env_file", None)
    clean_env.delenv(name)
    get_settings.cache_clear()

    with pytest.raises(ValidationError) as exc_info:
        with TestClient(app):
            pass  # pragma: no cover - startup must fail before this point
    assert name.lower() in str(exc_info.value).lower()
