"""Unit tests for taxonomy_repo — all DB access is mocked (task 1.4)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.taxonomy import AgreementType, ClauseFamily, ClauseIssue, ContextDimension
from app.db.repositories import taxonomy_repo


def _make_session() -> AsyncMock:
    return AsyncMock()


def _scalar_result(value: object) -> MagicMock:
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = value
    return mock


def _scalars_all_result(items: list) -> MagicMock:
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


def _rowcount_result(rowcount: int) -> MagicMock:
    mock = MagicMock()
    mock.rowcount = rowcount
    return mock


# ---------------------------------------------------------------------------
# AgreementType
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agreement_type() -> None:
    session = _make_session()
    session.add = MagicMock()

    result = await taxonomy_repo.create_agreement_type(session, "saas_msa", "SaaS MSA", "agreement")

    added = session.add.call_args[0][0]
    assert isinstance(added, AgreementType)
    assert added.key == "saas_msa"
    assert added.kind == "agreement"
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_get_agreement_type_found_and_not_found() -> None:
    agreement_type = MagicMock(spec=AgreementType)
    session = _make_session()

    session.execute.return_value = _scalar_result(agreement_type)
    assert await taxonomy_repo.get_agreement_type(session, "saas_msa") is agreement_type

    session.execute.return_value = _scalar_result(None)
    assert await taxonomy_repo.get_agreement_type(session, "unknown") is None


@pytest.mark.asyncio
async def test_list_agreement_types() -> None:
    a = MagicMock(spec=AgreementType)
    b = MagicMock(spec=AgreementType)
    session = _make_session()
    session.execute.return_value = _scalars_all_result([a, b])

    assert await taxonomy_repo.list_agreement_types(session) == [a, b]


@pytest.mark.asyncio
async def test_update_agreement_type() -> None:
    agreement_type = MagicMock(spec=AgreementType)
    session = _make_session()
    session.execute.return_value = _scalar_result(agreement_type)

    updated = await taxonomy_repo.update_agreement_type(session, "saas_msa", name="New Name")

    assert updated is agreement_type
    assert agreement_type.name == "New Name"
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_update_agreement_type_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    assert await taxonomy_repo.update_agreement_type(session, "unknown", name="x") is None
    session.flush.assert_not_called()


@pytest.mark.asyncio
async def test_delete_agreement_type() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(1)
    assert await taxonomy_repo.delete_agreement_type(session, "saas_msa") is True

    session.execute.return_value = _rowcount_result(0)
    assert await taxonomy_repo.delete_agreement_type(session, "unknown") is False


# ---------------------------------------------------------------------------
# ClauseFamily
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_clause_family() -> None:
    session = _make_session()
    session.add = MagicMock()

    result = await taxonomy_repo.create_clause_family(
        session, "service_levels", "Service Levels", "commercial", "Uptime and credits.",
        synonyms=["SLA", "uptime"],
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, ClauseFamily)
    assert added.key == "service_levels"
    assert added.synonyms == ["SLA", "uptime"]
    assert result is added


@pytest.mark.asyncio
async def test_get_list_update_delete_clause_family() -> None:
    family = MagicMock(spec=ClauseFamily)
    session = _make_session()

    session.execute.return_value = _scalar_result(family)
    assert await taxonomy_repo.get_clause_family(session, "service_levels") is family

    session.execute.return_value = _scalars_all_result([family])
    assert await taxonomy_repo.list_clause_families(session) == [family]

    session.execute.return_value = _scalar_result(family)
    updated = await taxonomy_repo.update_clause_family(session, "service_levels", sort_order=5)
    assert updated is family
    assert family.sort_order == 5

    session.execute.return_value = _rowcount_result(1)
    assert await taxonomy_repo.delete_clause_family(session, "service_levels") is True


# ---------------------------------------------------------------------------
# ClauseIssue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_clause_issue() -> None:
    session = _make_session()
    session.add = MagicMock()

    result = await taxonomy_repo.create_clause_issue(
        session, "limitation_of_liability", "cap_amount", "Cap amount", "The liability cap.",
        detection_hints="Look for aggregate liability.",
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, ClauseIssue)
    assert added.family_key == "limitation_of_liability"
    assert added.key == "cap_amount"
    assert result is added


@pytest.mark.asyncio
async def test_get_clause_issue_by_key() -> None:
    issue = MagicMock(spec=ClauseIssue)
    session = _make_session()
    session.execute.return_value = _scalar_result(issue)

    result = await taxonomy_repo.get_clause_issue_by_key(
        session, "limitation_of_liability", "cap_amount"
    )

    assert result is issue


@pytest.mark.asyncio
async def test_list_clause_issues_filtered_and_unfiltered() -> None:
    issue = MagicMock(spec=ClauseIssue)
    session = _make_session()
    session.execute.return_value = _scalars_all_result([issue])

    assert await taxonomy_repo.list_clause_issues(session) == [issue]
    assert await taxonomy_repo.list_clause_issues(session, family_key="payment") == [issue]


@pytest.mark.asyncio
async def test_update_delete_clause_issue() -> None:
    issue = MagicMock(spec=ClauseIssue)
    issue.id = uuid.uuid4()
    session = _make_session()

    session.execute.return_value = _scalar_result(issue)
    updated = await taxonomy_repo.update_clause_issue(session, issue.id, name="Renamed")
    assert updated is issue
    assert issue.name == "Renamed"

    session.execute.return_value = _rowcount_result(1)
    assert await taxonomy_repo.delete_clause_issue(session, issue.id) is True


# ---------------------------------------------------------------------------
# ContextDimension
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_context_dimension() -> None:
    session = _make_session()
    session.add = MagicMock()

    result = await taxonomy_repo.create_context_dimension(
        session, "deal_value_band", "Deal value band", "enum", "metadata",
        values={"standard": "Under $100k a year"},
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, ContextDimension)
    assert added.key == "deal_value_band"
    assert result is added


@pytest.mark.asyncio
async def test_get_list_update_delete_context_dimension() -> None:
    dimension = MagicMock(spec=ContextDimension)
    session = _make_session()

    session.execute.return_value = _scalar_result(dimension)
    assert await taxonomy_repo.get_context_dimension(session, "deal_value_band") is dimension

    session.execute.return_value = _scalars_all_result([dimension])
    assert await taxonomy_repo.list_context_dimensions(session) == [dimension]

    session.execute.return_value = _scalar_result(dimension)
    updated = await taxonomy_repo.update_context_dimension(
        session, "deal_value_band", source="upload"
    )
    assert updated is dimension
    assert dimension.source == "upload"

    session.execute.return_value = _rowcount_result(1)
    assert await taxonomy_repo.delete_context_dimension(session, "deal_value_band") is True
