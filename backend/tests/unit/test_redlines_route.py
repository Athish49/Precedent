"""Unit tests for S3 Redlines API endpoints (T-051).

All DB and service calls are mocked — no real database or LLM.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.redlines import _get_session
from app.db.models.redline import Redline
from app.main import app

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CONTRACT_ID = uuid.uuid4()
_REDLINE_ID = uuid.uuid4()
_CLAUSE_ID = uuid.uuid4()
_FLAG_ID = uuid.uuid4()


def _make_redline(
    redline_id: uuid.UUID = _REDLINE_ID,
    contract_id: uuid.UUID = _CONTRACT_ID,
    clause_id: uuid.UUID = _CLAUSE_ID,
    flag_id: uuid.UUID = _FLAG_ID,
    stance_mode: str = "balanced",
    position: str = "preferred",
    status: str = "proposed",
) -> MagicMock:
    r = MagicMock(spec=Redline)
    r.id = redline_id
    r.contract_id = contract_id
    r.clause_id = clause_id
    r.flag_id = flag_id
    r.stance_mode = stance_mode
    r.position = position
    r.replacement_text = "Revised clause text."
    r.tracked_changes = [{"op": "equal", "text": "Revised", "old_start": 0, "old_end": 7, "new_start": 0, "new_end": 7}]
    r.alternatives = [{"label": "fallback", "text": "Alternative text."}]
    r.explanation = "The original clause imposed unlimited liability."
    r.counterparty_comment = "This limits our exposure appropriately."
    r.rationale = {"flag_type": "liability", "flag_severity": "high"}
    r.status = status
    r.created_at = _NOW
    return r


mock_session = AsyncMock()
mock_session.commit = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)


# ── GET /api/redlines/{contract_id} ───────────────────────────────────────────


def test_get_redlines_returns_list() -> None:
    redline = _make_redline()
    with patch(
        "app.db.repositories.redline_repo.get_redlines_for_contract",
        new=AsyncMock(return_value=[redline]),
    ):
        response = client.get(f"/api/redlines/{_CONTRACT_ID}")

    assert response.status_code == 200
    body = response.json()
    assert "redlines" in body
    assert len(body["redlines"]) == 1
    assert body["redlines"][0]["status"] == "proposed"
    assert body["redlines"][0]["stance_mode"] == "balanced"


def test_get_redlines_empty() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redlines_for_contract",
        new=AsyncMock(return_value=[]),
    ):
        response = client.get(f"/api/redlines/{_CONTRACT_ID}")

    assert response.status_code == 200
    assert response.json() == {"redlines": []}


# ── POST /api/redlines/{redline_id}/toggle-fallback ───────────────────────────


def test_toggle_fallback_not_found() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redline",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(f"/api/redlines/{_REDLINE_ID}/toggle-fallback")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_toggle_fallback_success() -> None:
    redline = _make_redline(position="fallback")
    mock_clause = MagicMock()
    mock_clause.text = "Original clause text."

    with (
        patch(
            "app.db.repositories.redline_repo.get_redline",
            new=AsyncMock(return_value=redline),
        ),
        patch(
            "app.db.repositories.clause_repo.get_clause",
            new=AsyncMock(return_value=mock_clause),
        ),
        patch(
            "app.services.redline.operations.toggle_fallback",
            new=AsyncMock(return_value=redline),
        ),
    ):
        response = client.post(f"/api/redlines/{_REDLINE_ID}/toggle-fallback")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_REDLINE_ID)
    assert body["position"] == "fallback"


# ── POST /api/redlines/{redline_id}/refine ────────────────────────────────────


def test_refine_not_found() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redline",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/refine",
            json={"instruction": "Make it shorter."},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_refine_success() -> None:
    redline = _make_redline()
    mock_clause = MagicMock()
    mock_clause.text = "Original clause text."

    with (
        patch(
            "app.db.repositories.redline_repo.get_redline",
            new=AsyncMock(return_value=redline),
        ),
        patch(
            "app.db.repositories.clause_repo.get_clause",
            new=AsyncMock(return_value=mock_clause),
        ),
        patch(
            "app.services.redline.operations.refine",
            new=AsyncMock(return_value=redline),
        ),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/refine",
            json={"instruction": "Make it shorter."},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_REDLINE_ID)


# ── POST /api/redlines/{redline_id}/decision ──────────────────────────────────


def test_decision_not_found() -> None:
    with patch(
        "app.db.repositories.redline_repo.get_redline",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/decision",
            json={"outcome": "accepted"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_decision_success() -> None:
    redline = _make_redline(status="accepted")
    redline.contract_id = _CONTRACT_ID

    mock_contract = MagicMock()
    mock_contract.counterparty_id = uuid.uuid4()

    mock_clause = MagicMock()
    mock_clause.clause_type = "liability"

    mock_event = MagicMock()

    with (
        patch(
            "app.db.repositories.redline_repo.get_redline",
            new=AsyncMock(return_value=redline),
        ),
        patch(
            "app.db.repositories.contract_repo.get_contract",
            new=AsyncMock(return_value=mock_contract),
        ),
        patch(
            "app.db.repositories.clause_repo.get_clause",
            new=AsyncMock(return_value=mock_clause),
        ),
        patch(
            "app.services.redline.operations.record_decision",
            new=AsyncMock(return_value=(redline, mock_event)),
        ),
    ):
        response = client.post(
            f"/api/redlines/{_REDLINE_ID}/decision",
            json={"outcome": "accepted"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_REDLINE_ID)
    assert body["status"] == "accepted"


# ── POST /api/redlines/{contract_id}: preferred-language fallback (task 5.5) ──


def _position_response(kind: str, rung: int | None, language: str):
    from app.schemas.playbook import RulePositionResponse

    return RulePositionResponse(
        id=uuid.uuid4(), rule_id=uuid.uuid4(), kind=kind, rung=rung, label=kind,
        language=language, summary=None, zone="green", approver_role_id=None,
        conditions=None, give_get=None, internal_note=None, created_at=_NOW, updated_at=_NOW,
    )


def _generate_with_rule(rule: object | None) -> MagicMock:
    """POST /api/redlines/{id} over one flagged 'indemnification' clause with
    *rule* as its resolved rule; return the generate_redline mock."""
    from types import SimpleNamespace

    from app.schemas.analysis import FlagDTO

    mod = "app.api.routes.redlines"
    contract = MagicMock()
    contract.counterparty_id = None
    contract.contract_type = "nda"
    contract.party_role = "vendor"
    contract.paper_origin = "own"
    contract.context = None
    flag = FlagDTO(
        id=_FLAG_ID, contract_id=_CONTRACT_ID, clause_id=_CLAUSE_ID, flag_type="deviation",
        severity="high", source="deterministic", char_start=0, char_end=10, detail={},
        matched_rule_id=None, created_at=_NOW,
    )
    clause = SimpleNamespace(id=_CLAUSE_ID, clause_type="indemnification", text="Clause text.")
    redline_out = MagicMock(replacement_text="Revised.")
    generate = MagicMock(return_value=redline_out)
    rules = {"indemnification": rule} if rule is not None else {}

    with (
        patch(f"{mod}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{mod}.analysis_repo.get_flags_for_contract", new=AsyncMock(return_value=[flag])),
        patch(f"{mod}.routing.resolve", new=AsyncMock(return_value=MagicMock())),
        patch(f"{mod}.routing.rules_by_clause_type", return_value=rules),
        patch(f"{mod}.stance.queue_clauses", return_value=[flag]),
        patch(f"{mod}.clause_repo.get_clause", new=AsyncMock(return_value=clause)),
        patch(f"{mod}.nms_repo.get_counterparty_pattern", new=AsyncMock(return_value=None)),
        patch(f"{mod}.llm_call.generate_redline", new=generate),
        patch(f"{mod}.render.render", return_value=MagicMock()),
        patch(
            f"{mod}.persist.persist_redline",
            new=AsyncMock(return_value=(_make_redline(), MagicMock())),
        ),
    ):
        response = client.post(f"/api/redlines/{_CONTRACT_ID}", json={"stance_mode": "balanced"})
    assert response.status_code == 200
    return generate


def test_generate_redlines_preferred_language_from_rung_zero_position() -> None:
    """With no kind='preferred' position, the rung-0 position's language
    feeds redline generation. The legacy column fallback is gone."""
    from types import SimpleNamespace

    rule = SimpleNamespace(
        positions=[_position_response("acceptable_variant", 0, "Rung zero text.")],
        objections=[],
    )
    generate = _generate_with_rule(rule)
    assert generate.call_args.args[2] == "Rung zero text."


def test_generate_redlines_preferred_language_none_without_rung_zero() -> None:
    from types import SimpleNamespace

    rule = SimpleNamespace(
        positions=[_position_response("fallback", 1, "Fallback.")], objections=[]
    )
    assert _generate_with_rule(rule).call_args.args[2] is None
    assert _generate_with_rule(None).call_args.args[2] is None


# ── POST /api/redlines/{contract_id}: ladder chosen by the flag's rule_key ────


def _generate_with_family(flag_rule_key: str | None) -> tuple[MagicMock, AsyncMock, list]:
    """Two resolved rules share clause_type 'indemnification'. Uses the REAL
    routing.rules_by_clause_type / rules_by_rule_key / rule_for_flag."""
    from types import SimpleNamespace

    from app.schemas.analysis import FlagDTO

    mod = "app.api.routes.redlines"
    contract = MagicMock()
    contract.counterparty_id = None
    contract.contract_type = "nda"
    contract.party_role = "vendor"
    contract.paper_origin = "own"
    contract.context = None
    flag = FlagDTO(
        id=_FLAG_ID, contract_id=_CONTRACT_ID, clause_id=_CLAUSE_ID, flag_type="deviation",
        severity="high", source="deterministic", char_start=0, char_end=10, detail={},
        matched_rule_id=None, created_at=_NOW, rule_key=flag_rule_key,
    )
    clause = SimpleNamespace(id=_CLAUSE_ID, clause_type="indemnification", text="Clause text.")
    family = [
        SimpleNamespace(
            rule_key="indemnification.a_general", clause_type="indemnification",
            positions=[_position_response("preferred", 0, "GENERAL")], objections=[],
        ),
        SimpleNamespace(
            rule_key="indemnification.b_ip_infringement", clause_type="indemnification",
            positions=[_position_response("preferred", 0, "IP")], objections=[],
        ),
    ]
    resolved = MagicMock()
    resolved.rules = family
    generate = MagicMock(return_value=MagicMock(replacement_text="Revised."))
    persist_mock = AsyncMock(return_value=(_make_redline(), MagicMock()))

    with (
        patch(f"{mod}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{mod}.analysis_repo.get_flags_for_contract", new=AsyncMock(return_value=[flag])),
        patch(f"{mod}.routing.resolve", new=AsyncMock(return_value=resolved)),
        patch(f"{mod}.stance.queue_clauses", return_value=[flag]),
        patch(f"{mod}.clause_repo.get_clause", new=AsyncMock(return_value=clause)),
        patch(f"{mod}.nms_repo.get_counterparty_pattern", new=AsyncMock(return_value=None)),
        patch(f"{mod}.llm_call.generate_redline", new=generate),
        patch(f"{mod}.render.render", return_value=MagicMock()),
        patch(f"{mod}.persist.persist_redline", new=persist_mock),
    ):
        response = client.post(f"/api/redlines/{_CONTRACT_ID}", json={"stance_mode": "balanced"})
    assert response.status_code == 200
    return generate, persist_mock, family


def test_generate_redlines_uses_flag_rule_key_not_first_rule_in_family() -> None:
    generate, persist_mock, family = _generate_with_family("indemnification.b_ip_infringement")
    assert persist_mock.call_args.kwargs["rule"] is family[1]
    assert generate.call_args.args[2] == "IP"


def test_generate_redlines_flag_without_rule_key_uses_clause_type_rule() -> None:
    generate, persist_mock, family = _generate_with_family(None)
    assert persist_mock.call_args.kwargs["rule"] is family[0]
    assert generate.call_args.args[2] == "GENERAL"


def test_generate_redlines_unresolved_rule_key_gets_no_rule() -> None:
    generate, persist_mock, _ = _generate_with_family("indemnification.not_resolved")
    assert persist_mock.call_args.kwargs["rule"] is None
    assert generate.call_args.args[2] is None
