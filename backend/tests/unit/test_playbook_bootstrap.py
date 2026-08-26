"""Tests for S6 playbook bootstrap batch LLM job (T-038)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.playbooks import _get_session
from app.core.llm.schemas.playbook import PlaybookBootstrapOut
from app.db.models.playbook import Playbook, PlaybookRule
from app.main import app
from tests.fake_llm import FakeLLMGateway

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK = "playbook.bootstrap"


def _make_playbook(practice_area: str = "nda") -> MagicMock:
    pb = MagicMock(spec=Playbook)
    pb.id = uuid.uuid4()
    pb.practice_area = practice_area
    pb.name = "Test Playbook"
    pb.precedence = 0
    return pb


def _make_clause(
    contract_id: uuid.UUID,
    clause_type: str,
    text: str = "Standard clause text.",
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.contract_id = contract_id
    c.clause_type = clause_type
    c.text = text
    c.ordinal = 1
    return c


def _make_rule(playbook_id: uuid.UUID, clause_type: str) -> MagicMock:
    r = MagicMock(spec=PlaybookRule)
    r.id = uuid.uuid4()
    r.playbook_id = playbook_id
    r.clause_type = clause_type
    r.preferred_language = "Existing rule"
    r.acceptable_variations = None
    r.prohibited_terms = None
    return r


# ---------------------------------------------------------------------------
# Unit tests for run_bootstrap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_creates_rules_from_corpus() -> None:
    """Bootstrap seeds preferred_language and acceptable_variations per clause_type."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    cid = uuid.uuid4()

    clause_indem = _make_clause(cid, "indemnification", "Party A shall indemnify...")
    clause_term = _make_clause(cid, "termination", "Either party may terminate...")

    preset = PlaybookBootstrapOut(
        clause_type="indemnification",
        preferred_language="Party A shall indemnify Party B.",
        acceptable_variations=["Each party indemnifies the other."],
    )
    fake = FakeLLMGateway(structured_responses={_TASK: preset})

    mock_session = AsyncMock()

    created_rules: list[dict] = []

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        rule = MagicMock(spec=PlaybookRule)
        rule.id = uuid.uuid4()
        rule.playbook_id = playbook_id
        rule.clause_type = clause_type
        rule.preferred_language = kwargs.get("preferred_language", "")
        rule.acceptable_variations = kwargs.get("acceptable_variations")
        rule.prohibited_terms = None
        created_rules.append({"clause_type": clause_type, **kwargs})
        return rule

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause_indem, clause_term],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules",
            return_value=[],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
    ):
        count = await svc.run_bootstrap(mock_session, pb.id, [cid])

    # Two distinct clause_types → two rules created
    assert count == 2
    types_created = {r["clause_type"] for r in created_rules}
    assert types_created == {"indemnification", "termination"}

    # SC-3: prohibited_terms must NOT be seeded
    for r in created_rules:
        assert "prohibited_terms" not in r or r.get("prohibited_terms") is None

    # preferred_language and acceptable_variations must be populated
    for r in created_rules:
        assert r["preferred_language"]
        assert "acceptable_variations" in r


@pytest.mark.asyncio
async def test_bootstrap_skips_existing_clause_types() -> None:
    """Clause types that already have a rule in the playbook are not overwritten."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    cid = uuid.uuid4()

    existing_rule = _make_rule(pb.id, "indemnification")
    clause_indem = _make_clause(cid, "indemnification")
    clause_term = _make_clause(cid, "termination")

    preset = PlaybookBootstrapOut(
        clause_type="termination",
        preferred_language="Either party may terminate.",
        acceptable_variations=[],
    )
    fake = FakeLLMGateway(structured_responses={_TASK: preset})

    created_rules: list[dict] = []

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        created_rules.append({"clause_type": clause_type})
        return _make_rule(playbook_id, clause_type)

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause_indem, clause_term],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules",
            return_value=[existing_rule],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [cid])

    # Only "termination" is new; "indemnification" already exists
    assert count == 1
    assert created_rules[0]["clause_type"] == "termination"


@pytest.mark.asyncio
async def test_bootstrap_empty_corpus_returns_zero() -> None:
    """No contracts in corpus → 0 rules created, no LLM call made."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    fake = FakeLLMGateway()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[],
        ),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [uuid.uuid4()])

    assert count == 0
    assert fake.calls == []


@pytest.mark.asyncio
async def test_bootstrap_empty_contract_ids_returns_zero() -> None:
    """Empty contract_ids list short-circuits before any DB or LLM call."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    fake = FakeLLMGateway()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [])

    assert count == 0
    assert fake.calls == []


@pytest.mark.asyncio
async def test_bootstrap_404_on_missing_playbook() -> None:
    """Missing playbook raises AppError 404."""
    from app.api.errors import AppError

    from app.services.playbook import bootstrap as svc

    with patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=None):
        mock_session = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await svc.run_bootstrap(mock_session, uuid.uuid4(), [uuid.uuid4()])

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_bootstrap_all_types_already_exist_returns_zero() -> None:
    """All clause types already have rules → no LLM call, 0 created."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    cid = uuid.uuid4()
    clause = _make_clause(cid, "indemnification")
    existing = _make_rule(pb.id, "indemnification")

    fake = FakeLLMGateway()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules",
            return_value=[existing],
        ),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [cid])

    assert count == 0
    assert fake.calls == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

mock_session = AsyncMock()


async def _bootstrap_mock_session():
    yield mock_session


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _patch_bootstrap_session():
    prev = app.dependency_overrides.get(_get_session)
    app.dependency_overrides[_get_session] = _bootstrap_mock_session
    yield
    if prev is None:
        app.dependency_overrides.pop(_get_session, None)
    else:
        app.dependency_overrides[_get_session] = prev


def test_bootstrap_api_with_contract_ids() -> None:
    """POST /playbooks/bootstrap with explicit contract_ids returns created count."""
    playbook_id = uuid.uuid4()
    contract_id = uuid.uuid4()

    with patch(
        "app.api.routes.playbooks.bootstrap_service.run_bootstrap",
        new_callable=AsyncMock,
        return_value=3,
    ):
        response = client.post(
            "/api/playbooks/bootstrap",
            json={
                "playbook_id": str(playbook_id),
                "contract_ids": [str(contract_id)],
            },
        )

    assert response.status_code == 200
    assert response.json()["created_rule_count"] == 3


def test_bootstrap_api_with_contract_type() -> None:
    """POST /playbooks/bootstrap with contract_type loads contracts then bootstraps."""
    from app.db.models.contract import Contract

    playbook_id = uuid.uuid4()
    contract_id = uuid.uuid4()

    fake_contract = MagicMock(spec=Contract)
    fake_contract.id = contract_id

    with (
        patch(
            "app.api.routes.playbooks.contract_repo.list_contracts",
            new_callable=AsyncMock,
            return_value=([fake_contract], 1),
        ),
        patch(
            "app.api.routes.playbooks.bootstrap_service.run_bootstrap",
            new_callable=AsyncMock,
            return_value=2,
        ) as mock_run,
    ):
        response = client.post(
            "/api/playbooks/bootstrap",
            json={"playbook_id": str(playbook_id), "contract_type": "nda"},
        )

    assert response.status_code == 200
    assert response.json()["created_rule_count"] == 2
    # Verify contract IDs were resolved and passed through
    call_args = mock_run.call_args
    assert contract_id in call_args.args[2]


def test_bootstrap_api_missing_corpus_returns_422() -> None:
    """Neither contract_ids nor contract_type → 422 validation error."""
    response = client.post(
        "/api/playbooks/bootstrap",
        json={"playbook_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


def test_bootstrap_api_missing_playbook_id_returns_422() -> None:
    """Missing playbook_id → 422 validation error."""
    response = client.post(
        "/api/playbooks/bootstrap",
        json={"contract_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 422


def test_bootstrap_api_propagates_404() -> None:
    """AppError 404 from bootstrap service is surfaced as HTTP 404."""
    from app.api.errors import AppError

    with patch(
        "app.api.routes.playbooks.bootstrap_service.run_bootstrap",
        new_callable=AsyncMock,
        side_effect=AppError(404, "not_found", "Playbook not found"),
    ):
        response = client.post(
            "/api/playbooks/bootstrap",
            json={
                "playbook_id": str(uuid.uuid4()),
                "contract_ids": [str(uuid.uuid4())],
            },
        )

    assert response.status_code == 404
