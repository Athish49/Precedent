"""Model-level tests for doc_proc task 5.2 (migration 019's ORM counterparts).

Checks the models directly on ``Base.metadata``, so a model/migration
mismatch (e.g. the column dropped in the migration but still present on the
model, or ``nullable`` disagreeing between the two) would show up here.
"""

from __future__ import annotations

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.clause import Clause
from app.db.models.contract import ContractMetadata

_SCHEMA = Base.metadata.schema

_OLD_COLUMNS = (
    "parties",
    "financial_fields",
    "milestone_dates",
    "liability_cap",
    "notice_period_days",
    "payment_terms",
    "extracted",
)


def _table(name: str):
    return Base.metadata.tables[f"{_SCHEMA}.{name}"]


def test_contract_metadata_has_no_trace_of_the_dropped_columns() -> None:
    """Task 5.1 already removed these Python attributes; confirm it, don't
    just assume it (the implementation doc's own instruction)."""
    table = _table("contract_metadata")
    assert not (set(_OLD_COLUMNS) & set(table.columns.keys()))
    for name in _OLD_COLUMNS:
        assert not hasattr(ContractMetadata, name)


def test_clause_contract_version_id_is_not_null() -> None:
    """Migration 019 tightens this column now that the old pipeline (which
    needed it nullable) is deleted and every orphaned row is gone."""
    table = _table("clause")
    assert table.columns["contract_version_id"].nullable is False
    assert Clause.__table__.columns["contract_version_id"].nullable is False
