"""Unit tests for doc_proc task 1.3: clause_repo, field_repo, ingest_repo and
the new contract_repo functions. All DB access is mocked, following the
pattern in tests/unit/test_repositories.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.clause import Clause
from app.db.models.contract import ContractMetadata, ContractVersion
from app.db.models.field import ContractField
from app.db.models.ingest_run import IngestRun
from app.db.models.party_link import ContractParty, ContractSignatory
from app.db.repositories import clause_repo, contract_repo, field_repo, ingest_repo
from app.services.document_processing.types import ClauseDraft, FieldValue, PartyDraft, SignatoryDraft


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _scalar_result(value) -> MagicMock:
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = value
    mock.scalar_one.return_value = value
    return mock


def _scalars_result(items: list) -> MagicMock:
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    mock.scalars.return_value.first.return_value = items[0] if items else None
    return mock


# ---------------------------------------------------------------------------
# clause_repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_clauses_for_contract_default_level_top() -> None:
    clause_a = MagicMock(spec=Clause)
    session = _make_session()
    session.execute.return_value = _scalars_result([clause_a])

    contract_id = uuid.uuid4()
    result = await clause_repo.get_clauses_for_contract(session, contract_id)

    assert result == [clause_a]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_clauses_for_contract_level_all() -> None:
    clause_a = MagicMock(spec=Clause)
    clause_b = MagicMock(spec=Clause)
    session = _make_session()
    session.execute.return_value = _scalars_result([clause_a, clause_b])

    result = await clause_repo.get_clauses_for_contract(session, uuid.uuid4(), level="all")

    assert result == [clause_a, clause_b]


@pytest.mark.asyncio
async def test_get_clauses_for_contract_explicit_version_id() -> None:
    clause_a = MagicMock(spec=Clause)
    session = _make_session()
    session.execute.return_value = _scalars_result([clause_a])

    version_id = uuid.uuid4()
    result = await clause_repo.get_clauses_for_contract(
        session, uuid.uuid4(), version_id=version_id
    )

    assert result == [clause_a]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_clauses_for_contracts_empty_list_short_circuits() -> None:
    session = _make_session()
    result = await clause_repo.get_clauses_for_contracts(session, [])
    assert result == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_clauses_for_contracts_calls_execute_once() -> None:
    clause_a = MagicMock(spec=Clause)
    session = _make_session()
    session.execute.return_value = _scalars_result([clause_a])

    result = await clause_repo.get_clauses_for_contracts(session, [uuid.uuid4(), uuid.uuid4()])

    assert result == [clause_a]
    session.execute.assert_called_once()


def _draft(
    ordinal: int,
    *,
    level: int = 1,
    parent_ordinal: int | None = None,
    clause_type: str = "other",
) -> ClauseDraft:
    return ClauseDraft(
        ordinal=ordinal,
        level=level,
        parent_ordinal=parent_ordinal,
        section_number=str(ordinal),
        title=f"Title {ordinal}",
        heading_text=f"{ordinal}. Title {ordinal}",
        text=f"text of clause {ordinal}",
        char_start=ordinal * 10,
        char_end=ordinal * 10 + 5,
        page_start=1,
        page_end=1,
        clause_type=clause_type,
        type_source="dictionary",
    )


@pytest.mark.asyncio
async def test_replace_clauses_deletes_then_inserts() -> None:
    session = _make_session()
    session.execute.return_value = MagicMock()  # the delete() result

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    drafts = [_draft(0), _draft(1, level=2, parent_ordinal=0)]

    result = await clause_repo.replace_clauses(session, contract_id, version_id, drafts)

    # One execute() for the delete, plus two flush()es (insert pass, then
    # the parent-id back-fill pass).
    assert session.execute.call_count == 1
    assert session.add.call_count == 2
    assert session.flush.await_count == 2
    assert len(result) == 2
    for row in result:
        assert isinstance(row, Clause)
        assert row.contract_id == contract_id
        assert row.contract_version_id == version_id
        assert row.text_sha256


@pytest.mark.asyncio
async def test_replace_clauses_resolves_parent_ordinal_to_parent_id() -> None:
    session = _make_session()
    session.execute.return_value = MagicMock()

    drafts = [_draft(0), _draft(1, level=2, parent_ordinal=0), _draft(2, level=1)]
    result = await clause_repo.replace_clauses(session, uuid.uuid4(), uuid.uuid4(), drafts)

    by_ordinal = {row.ordinal: row for row in result}
    assert by_ordinal[0].parent_id is None
    assert by_ordinal[1].parent_id == by_ordinal[0].id
    assert by_ordinal[2].parent_id is None


@pytest.mark.asyncio
async def test_replace_clauses_empty_drafts_still_deletes() -> None:
    session = _make_session()
    session.execute.return_value = MagicMock()

    result = await clause_repo.replace_clauses(session, uuid.uuid4(), uuid.uuid4(), [])

    assert result == []
    session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# field_repo
# ---------------------------------------------------------------------------


def _field_value(
    key: str, value: object, *, source: str = "extract", clause_ordinal: int | None = None
) -> FieldValue:
    return FieldValue(
        field_key=key,
        value=value,
        source=source,
        confidence="high" if source == "extract" else None,
        quote="some quote" if source == "extract" else None,
        page=1 if source == "extract" else None,
        char_start=0 if source == "extract" else None,
        char_end=10 if source == "extract" else None,
        clause_ordinal=clause_ordinal,
    )


@pytest.mark.asyncio
async def test_replace_extracted_deletes_extract_and_derived_rows() -> None:
    session = _make_session()
    session.execute.return_value = MagicMock()

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    run_id = uuid.uuid4()
    values = [
        _field_value("governing_law", "Delaware", source="extract", clause_ordinal=3),
        _field_value("expiry_date", "2028-03-03", source="derived"),
    ]
    clause_id = uuid.uuid4()

    rows = await field_repo.replace_extracted(
        session,
        contract_id,
        version_id,
        run_id,
        values,
        clause_ids_by_ordinal={3: clause_id},
    )

    delete_call = session.execute.call_args_list[0]
    assert "contract_field" in str(delete_call.args[0]).lower()
    assert len(rows) == 2
    assert rows[0].clause_id == clause_id
    assert rows[1].clause_id is None
    assert rows[0].ingest_run_id == run_id
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_replace_extracted_coerces_date_values_to_iso_strings() -> None:
    """Regression test: fields.validate_value returns a real datetime.date
    for a date-kind field, which psycopg cannot JSON-encode into the
    contract_field.value JSONB column. Found live: this crashed the whole
    ingest transaction for every real contract (virtually all have a date
    field), silently, since the generic except in ingest.py swallowed it."""
    import datetime

    session = _make_session()
    session.execute.return_value = MagicMock()

    values = [_field_value("effective_date", datetime.date(2026, 1, 12), source="extract")]
    rows = await field_repo.replace_extracted(
        session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), values
    )

    assert rows[0].value == "2026-01-12"
    assert isinstance(rows[0].value, str)


@pytest.mark.asyncio
async def test_set_user_value_coerces_date_values_to_iso_strings() -> None:
    import datetime

    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    row = await field_repo.set_user_value(
        session, uuid.uuid4(), uuid.uuid4(), "effective_date", datetime.date(2026, 1, 12)
    )

    assert row.value == "2026-01-12"


@pytest.mark.asyncio
async def test_replace_extracted_never_deletes_user_rows() -> None:
    session = _make_session()
    session.execute.return_value = MagicMock()

    await field_repo.replace_extracted(session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), [])

    delete_stmt = session.execute.call_args_list[0].args[0]
    compiled = str(delete_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "'user'" not in compiled
    assert "'extract'" in compiled
    assert "'derived'" in compiled


@pytest.mark.asyncio
async def test_values_in_force_user_wins_over_extract_and_derived() -> None:
    user_row = MagicMock(spec=ContractField)
    user_row.field_key = "governing_law"
    user_row.source = "user"
    extract_row = MagicMock(spec=ContractField)
    extract_row.field_key = "governing_law"
    extract_row.source = "extract"
    other_row = MagicMock(spec=ContractField)
    other_row.field_key = "expiry_date"
    other_row.source = "derived"

    session = _make_session()
    session.execute.return_value = _scalars_result([extract_row, user_row, other_row])

    result = await field_repo.values_in_force(session, uuid.uuid4())

    assert result["governing_law"] is user_row
    assert result["expiry_date"] is other_row


@pytest.mark.asyncio
async def test_values_in_force_extract_wins_over_derived_when_no_user() -> None:
    extract_row = MagicMock(spec=ContractField)
    extract_row.field_key = "expiry_date"
    extract_row.source = "extract"
    derived_row = MagicMock(spec=ContractField)
    derived_row.field_key = "expiry_date"
    derived_row.source = "derived"

    session = _make_session()
    session.execute.return_value = _scalars_result([derived_row, extract_row])

    result = await field_repo.values_in_force(session, uuid.uuid4())

    assert result["expiry_date"] is extract_row


@pytest.mark.asyncio
async def test_set_user_value_inserts_when_absent() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    row = await field_repo.set_user_value(
        session, uuid.uuid4(), uuid.uuid4(), "governing_law", "New York"
    )

    session.add.assert_called_once()
    assert row.source == "user"
    assert row.value == "New York"
    assert row.confidence is None


@pytest.mark.asyncio
async def test_set_user_value_updates_existing_user_row_in_place() -> None:
    existing = MagicMock(spec=ContractField)
    existing.source = "user"
    session = _make_session()
    session.execute.return_value = _scalar_result(existing)

    row = await field_repo.set_user_value(
        session, uuid.uuid4(), uuid.uuid4(), "governing_law", "Texas"
    )

    session.add.assert_not_called()
    assert row is existing
    assert existing.value == "Texas"
    assert existing.confidence is None


# ---------------------------------------------------------------------------
# contract_repo: new functions
# ---------------------------------------------------------------------------


def _party_draft(role: str = "counterparty") -> PartyDraft:
    return PartyDraft(
        name="Acme, Inc.",
        role_label="Customer",
        entity_type="corporation",
        jurisdiction="Delaware",
        address="1 Main St",
        role=role,
    )


@pytest.mark.asyncio
async def test_replace_contract_parties_deletes_then_inserts_in_order() -> None:
    session = _make_session()
    session.execute.return_value = MagicMock()

    contract_id = uuid.uuid4()
    party_id_1, party_id_2 = uuid.uuid4(), uuid.uuid4()
    entries = [(party_id_1, _party_draft("own")), (party_id_2, _party_draft("counterparty"))]

    rows = await contract_repo.replace_contract_parties(session, contract_id, entries)

    assert len(rows) == 2
    assert rows[0].ordinal == 0
    assert rows[1].ordinal == 1
    assert rows[0].party_id == party_id_1
    assert rows[0].role == "own"
    assert rows[1].role == "counterparty"
    session.execute.assert_called_once()  # the delete
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_replace_signatories_links_contract_party_id() -> None:
    session = _make_session()
    session.execute.return_value = MagicMock()

    version_id = uuid.uuid4()
    contract_party_id = uuid.uuid4()
    draft = SignatoryDraft(
        printed_name="Jane Doe",
        title="VP",
        party_name="Acme, Inc.",
        is_signed=True,
        signed_date=None,
    )

    rows = await contract_repo.replace_signatories(
        session, version_id, [(draft, contract_party_id), (draft, None)]
    )

    assert len(rows) == 2
    assert rows[0].contract_party_id == contract_party_id
    assert rows[1].contract_party_id is None
    assert all(isinstance(r, ContractSignatory) for r in rows)
    assert all(r.contract_version_id == version_id for r in rows)


@pytest.mark.asyncio
async def test_write_metadata_projection_creates_row_when_absent() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    field_row = MagicMock(spec=ContractField)
    field_row.value = "Delaware"
    values_in_force = {"governing_law": field_row}
    registry_projection = {"governing_law": "governing_law", "expiry_date": "expiry_date"}

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    metadata = await contract_repo.write_metadata_projection(
        session, contract_id, version_id, values_in_force, registry_projection
    )

    session.add.assert_called_once()
    assert isinstance(metadata, ContractMetadata)
    assert metadata.contract_id == contract_id
    assert metadata.contract_version_id == version_id
    assert metadata.governing_law == "Delaware"
    assert metadata.expiry_date is None


@pytest.mark.asyncio
async def test_write_metadata_projection_updates_existing_row() -> None:
    existing = MagicMock(spec=ContractMetadata)
    session = _make_session()
    session.execute.return_value = _scalar_result(existing)

    field_row = MagicMock(spec=ContractField)
    field_row.value = 12
    values_in_force = {"initial_term_months": field_row}
    registry_projection = {"initial_term_months": "initial_term_months"}

    version_id = uuid.uuid4()
    metadata = await contract_repo.write_metadata_projection(
        session, uuid.uuid4(), version_id, values_in_force, registry_projection
    )

    session.add.assert_not_called()
    assert metadata is existing
    assert existing.initial_term_months == 12
    assert existing.contract_version_id == version_id


@pytest.mark.asyncio
async def test_find_by_sha256_found() -> None:
    version = MagicMock(spec=ContractVersion)
    session = _make_session()
    session.execute.return_value = _scalars_result([version])

    result = await contract_repo.find_by_sha256(session, "abc123")

    assert result is version


@pytest.mark.asyncio
async def test_find_by_sha256_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalars_result([])

    result = await contract_repo.find_by_sha256(session, "abc123")

    assert result is None


# ---------------------------------------------------------------------------
# ingest_repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_run_inserts_running_row() -> None:
    session = _make_session()

    version_id = uuid.uuid4()
    run = await ingest_repo.start_run(
        session, version_id, provider="extend", processor="extraction_light"
    )

    session.add.assert_called_once()
    assert run.contract_version_id == version_id
    assert run.status == "running"
    assert run.provider == "extend"


@pytest.mark.asyncio
async def test_finish_run_marks_succeeded_and_sets_finished_at() -> None:
    run = MagicMock(spec=IngestRun)
    session = _make_session()
    session.execute.return_value = _scalar_result(run)

    result = await ingest_repo.finish_run(
        session, uuid.uuid4(), warnings=["low_anchor_rate"], credits_used=3.6
    )

    assert result is run
    assert run.status == "succeeded"
    assert run.finished_at is not None
    assert run.warnings == ["low_anchor_rate"]
    assert run.credits_used == 3.6


@pytest.mark.asyncio
async def test_finish_run_returns_none_when_missing() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await ingest_repo.finish_run(session, uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_fail_run_marks_failed_with_reason() -> None:
    run = MagicMock(spec=IngestRun)
    session = _make_session()
    session.execute.return_value = _scalar_result(run)

    result = await ingest_repo.fail_run(session, uuid.uuid4(), "no_text")

    assert result is run
    assert run.status == "failed"
    assert run.failure_reason == "no_text"
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_latest_run_returns_most_recent() -> None:
    run = MagicMock(spec=IngestRun)
    session = _make_session()
    session.execute.return_value = _scalars_result([run])

    result = await ingest_repo.latest_run(session, uuid.uuid4())

    assert result is run


@pytest.mark.asyncio
async def test_latest_run_returns_none_when_no_runs() -> None:
    session = _make_session()
    session.execute.return_value = _scalars_result([])

    result = await ingest_repo.latest_run(session, uuid.uuid4())

    assert result is None
