"""Unit tests for the version comparison workflow (T-090)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.errors import AppError
from app.api.routes.versions import _get_session
from app.main import app
from app.workflows.version_comparison import VersionDiffResult, compare_versions

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_contract(contract_id: uuid.UUID) -> MagicMock:
    m = MagicMock()
    m.id = contract_id
    return m


def _make_version(version_id: uuid.UUID, contract_id: uuid.UUID, number: int, text: str) -> MagicMock:
    m = MagicMock()
    m.id = version_id
    m.contract_id = contract_id
    m.version_number = number
    m.canonical_text = text
    return m


def _make_clause(contract_id: uuid.UUID, *, char_start: int = 0, char_end: int = 50) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.contract_id = contract_id
    m.clause_type = "indemnification"
    m.heading_text = "Indemnification"
    m.ordinal = 1
    m.char_start = char_start
    m.char_end = char_end
    return m


def _execute_side_effects(*versions: MagicMock | None) -> list[MagicMock]:
    results = []
    for v in versions:
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        results.append(r)
    return results


# ── Async workflow tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_identical_versions_all_unchanged() -> None:
    """Identical canonical texts → all clauses unchanged, no delete/insert in global_changes."""
    contract_id = uuid.uuid4()
    v_a_id = uuid.uuid4()
    v_b_id = uuid.uuid4()
    text = "This is clause one text here. " * 3

    mock_contract = _make_contract(contract_id)
    version_a = _make_version(v_a_id, contract_id, 1, text)
    version_b = _make_version(v_b_id, contract_id, 2, text)
    clause = _make_clause(contract_id, char_start=0, char_end=len(text))

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_execute_side_effects(version_a, version_b))

    with (
        patch(
            "app.workflows.version_comparison.contract_repo.get_contract",
            new_callable=AsyncMock,
            return_value=mock_contract,
        ),
        patch(
            "app.workflows.version_comparison.clause_repo.get_clauses_for_contract",
            new_callable=AsyncMock,
            return_value=[clause],
        ),
    ):
        result = await compare_versions(mock_session, contract_id, v_a_id, v_b_id)

    assert result.contract_id == contract_id
    assert result.v_a == v_a_id
    assert result.v_b == v_b_id
    assert all(cd.change_type == "unchanged" for cd in result.clause_diffs)
    ops = {ch["op"] for ch in result.global_changes}
    assert "delete" not in ops
    assert "insert" not in ops


@pytest.mark.asyncio
async def test_modified_version_produces_modified_clause() -> None:
    """Version B with modified text → at least one modified clause and non-equal ops in global_changes."""
    contract_id = uuid.uuid4()
    v_a_id = uuid.uuid4()
    v_b_id = uuid.uuid4()
    text_a = "The vendor shall indemnify the client against all claims."
    text_b = "The vendor shall indemnify and hold harmless the client against all claims."

    mock_contract = _make_contract(contract_id)
    version_a = _make_version(v_a_id, contract_id, 1, text_a)
    version_b = _make_version(v_b_id, contract_id, 2, text_b)
    clause = _make_clause(contract_id, char_start=0, char_end=len(text_a))

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_execute_side_effects(version_a, version_b))

    with (
        patch(
            "app.workflows.version_comparison.contract_repo.get_contract",
            new_callable=AsyncMock,
            return_value=mock_contract,
        ),
        patch(
            "app.workflows.version_comparison.clause_repo.get_clauses_for_contract",
            new_callable=AsyncMock,
            return_value=[clause],
        ),
    ):
        result = await compare_versions(mock_session, contract_id, v_a_id, v_b_id)

    modified = [cd for cd in result.clause_diffs if cd.change_type == "modified"]
    assert len(modified) >= 1

    ops = {ch["op"] for ch in result.global_changes}
    assert "equal" in ops or "insert" in ops or "delete" in ops
    non_equal = [ch for ch in result.global_changes if ch["op"] != "equal"]
    assert len(non_equal) >= 1


@pytest.mark.asyncio
async def test_unknown_contract_raises_404() -> None:
    """Unknown contract_id raises AppError(404, 'contract_not_found', ...)."""
    mock_session = AsyncMock()

    with (
        patch(
            "app.workflows.version_comparison.contract_repo.get_contract",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.workflows.version_comparison.clause_repo.get_clauses_for_contract",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        with pytest.raises(AppError) as exc_info:
            await compare_versions(mock_session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "contract_not_found"


@pytest.mark.asyncio
async def test_unknown_version_a_raises_404() -> None:
    """Unknown v_a raises AppError(404, 'version_not_found', ...)."""
    contract_id = uuid.uuid4()
    mock_contract = _make_contract(contract_id)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_execute_side_effects(None))

    with (
        patch(
            "app.workflows.version_comparison.contract_repo.get_contract",
            new_callable=AsyncMock,
            return_value=mock_contract,
        ),
        patch(
            "app.workflows.version_comparison.clause_repo.get_clauses_for_contract",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        with pytest.raises(AppError) as exc_info:
            await compare_versions(mock_session, contract_id, uuid.uuid4(), uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "version_not_found"


# ── HTTP route test ───────────────────────────────────────────────────────────

_mock_http_session = AsyncMock()


async def _override_session():
    yield _mock_http_session


app.dependency_overrides[_get_session] = _override_session

client = TestClient(app, raise_server_exceptions=False)


def test_diff_endpoint_200() -> None:
    """GET /api/versions/diff returns 200 with the correct response shape."""
    contract_id = uuid.uuid4()
    v_a_id = uuid.uuid4()
    v_b_id = uuid.uuid4()

    fake_result = VersionDiffResult(
        contract_id=contract_id,
        v_a=v_a_id,
        v_b=v_b_id,
        v_a_number=1,
        v_b_number=2,
        clause_diffs=[],
        global_changes=[],
    )

    with patch(
        "app.api.routes.versions.version_comparison.compare_versions",
        new_callable=AsyncMock,
        return_value=fake_result,
    ):
        response = client.get(
            "/api/versions/diff",
            params={
                "contract_id": str(contract_id),
                "v_a": str(v_a_id),
                "v_b": str(v_b_id),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["contract_id"] == str(contract_id)
    assert body["v_a"] == str(v_a_id)
    assert body["v_b"] == str(v_b_id)
    assert body["v_a_number"] == 1
    assert body["v_b_number"] == 2
    assert body["clause_diffs"] == []
    assert body["global_changes"] == []
