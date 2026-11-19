"""Model-level tests for doc_proc task 1.2 (migration 017's ORM counterparts).

These check the models directly on ``Base.metadata`` rather than the
migration module, so they also catch a model/migration mismatch (a column
added to one but not the other).
"""

from __future__ import annotations

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.contract import ContractMetadata, Party
from app.db.models.field import ContractField
from app.db.models.ingest_run import IngestRun
from app.db.models.party_link import ContractParty, ContractSignatory
from app.db.models.clause import ClauseEmbedding

_SCHEMA = Base.metadata.schema


def _table(name: str):
    return Base.metadata.tables[f"{_SCHEMA}.{name}"]


def test_new_tables_registered_on_metadata() -> None:
    for name in ("contract_field", "contract_party", "contract_signatory", "ingest_run"):
        assert f"{_SCHEMA}.{name}" in Base.metadata.tables


def test_model_classes_import_and_map_to_expected_table() -> None:
    assert ContractField.__tablename__ == "contract_field"
    assert ContractParty.__tablename__ == "contract_party"
    assert ContractSignatory.__tablename__ == "contract_signatory"
    assert IngestRun.__tablename__ == "ingest_run"
    for cls in (ContractField, ContractParty, ContractSignatory, IngestRun):
        assert cls.__table__.schema == _SCHEMA


def test_contract_field_unique_and_index() -> None:
    table = _table("contract_field")
    unique_names = {c.name for c in table.constraints if c.name}
    assert "uq_contract_field_version_key_source" in unique_names
    index_names = {ix.name for ix in table.indexes}
    assert "ix_contract_field_key_contract" in index_names
    check_names = {
        c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
    }
    assert {"ck_contract_field_source", "ck_contract_field_confidence"} <= check_names


def test_contract_field_clause_and_ingest_run_fk_are_set_null() -> None:
    table = _table("contract_field")
    fks = {fk.target_fullname: fk for fk in table.foreign_keys}
    clause_fk = next(fk for fk in table.foreign_keys if fk.column.table.name == "clause")
    assert clause_fk.ondelete == "SET NULL"
    ingest_fk = next(fk for fk in table.foreign_keys if fk.column.table.name == "ingest_run")
    assert ingest_fk.ondelete == "SET NULL"
    version_fk = next(
        fk for fk in table.foreign_keys if fk.column.table.name == "contract_version"
    )
    assert version_fk.ondelete == "CASCADE"
    assert fks  # keep reference alive for lint


def test_contract_party_unique_and_role_check() -> None:
    table = _table("contract_party")
    unique_names = {c.name for c in table.constraints if c.name}
    assert "uq_contract_party_contract_party" in unique_names
    check_names = {
        c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_contract_party_role" in check_names


def test_contract_signatory_fk_to_contract_party_is_set_null() -> None:
    table = _table("contract_signatory")
    fk = next(fk for fk in table.foreign_keys if fk.column.table.name == "contract_party")
    assert fk.ondelete == "SET NULL"
    version_fk = next(
        fk for fk in table.foreign_keys if fk.column.table.name == "contract_version"
    )
    assert version_fk.ondelete == "CASCADE"


def test_ingest_run_status_check_and_cascade() -> None:
    table = _table("ingest_run")
    check_names = {
        c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_ingest_run_status" in check_names
    version_fk = next(
        fk for fk in table.foreign_keys if fk.column.table.name == "contract_version"
    )
    assert version_fk.ondelete == "CASCADE"


def test_party_has_is_own_org_not_null_default_false() -> None:
    table = _table("party")
    column = table.columns["is_own_org"]
    assert column.nullable is False
    assert Party.__table__.columns["is_own_org"].default.arg is False


def test_clause_embedding_unique_on_clause_id_and_model_column() -> None:
    table = _table("clause_embedding")
    unique_names = {c.name for c in table.constraints if c.name}
    assert "uq_clause_embedding_clause_id" in unique_names
    assert "model" in table.columns
    assert table.columns["model"].nullable is True
    assert ClauseEmbedding.__table__.columns["model"].nullable is True


def test_contract_metadata_has_projection_columns() -> None:
    table = _table("contract_metadata")
    expected = {
        "contract_version_id",
        "expiry_is_derived",
        "initial_term_months",
        "renewal_term_months",
        "renewal_notice_days",
        "dispute_resolution",
        "total_value_amount",
        "currency",
        "liability_cap_amount",
        "liability_cap_basis",
        "payment_terms_days",
        "termination_for_convenience",
        "termination_notice_days",
    }
    assert expected <= set(table.columns.keys())
    # The old untyped columns (parties, financial_fields, milestone_dates,
    # liability_cap, notice_period_days, payment_terms, extracted) were
    # removed from this ORM model in doc_proc task 5.1. The underlying
    # database columns are dropped later, by task 5.2's migration.
    legacy = {
        "parties",
        "financial_fields",
        "milestone_dates",
        "liability_cap",
        "notice_period_days",
        "payment_terms",
        "extracted",
    }
    assert not (legacy & set(table.columns.keys()))


def test_contract_metadata_version_fk_is_cascade() -> None:
    table = _table("contract_metadata")
    fk = next(fk for fk in table.foreign_keys if fk.column.table.name == "contract_version")
    assert fk.ondelete == "CASCADE"


def test_contract_metadata_model_matches_table() -> None:
    assert "contract_version_id" in ContractMetadata.__table__.columns
