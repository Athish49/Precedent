import app.db.models  # noqa: F401
from app.db.base import Base, get_session_factory, init_db


def test_base_metadata_tables() -> None:
    expected = {
        "party", "contract", "contract_metadata", "clause", "clause_embedding", "contract_version"
    }
    # Table keys carry the project schema (see test_schema_partitioning.py).
    schema = Base.metadata.schema
    assert schema
    assert {f"{schema}.{name}" for name in expected}.issubset(Base.metadata.tables.keys())


def test_init_db_creates_session_factory() -> None:
    init_db("postgresql+psycopg://user:pass@ep-test.us-east-2.aws.neon.tech/testdb?sslmode=require")
    factory = get_session_factory()
    assert factory is not None


def test_get_session_factory_raises_before_init(monkeypatch) -> None:
    import app.db.base as db_base

    original_factory = db_base._session_factory
    db_base._session_factory = None
    try:
        import pytest

        with pytest.raises(RuntimeError, match="DB not initialized"):
            get_session_factory()
    finally:
        db_base._session_factory = original_factory
