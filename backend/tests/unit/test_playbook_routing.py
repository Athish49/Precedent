"""Tests for S6 routing — deterministic multi-playbook resolve (T-037)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.routes.playbooks import _get_session
from app.db.models.playbook import Playbook, PlaybookRule
from app.main import app
from app.services.playbook.routing import _applicable_areas, _merge_rules

# ---------------------------------------------------------------------------
# Unit tests for _applicable_areas
# ---------------------------------------------------------------------------


def test_applicable_areas_known() -> None:
    for area in ("hipaa", "gdpr", "saas_msa", "nda", "dpa"):
        assert _applicable_areas(area) == [area]


def test_applicable_areas_unknown() -> None:
    assert _applicable_areas("unknown_type") == []


def test_applicable_areas_empty() -> None:
    assert _applicable_areas("") == []


# ---------------------------------------------------------------------------
# Unit tests for _merge_rules
# ---------------------------------------------------------------------------


def _make_rule_resp(
    clause_type: str,
    playbook_id: uuid.UUID | None = None,
    preferred_language: str = "",
    required: bool = False,
    risk_weight: float = 1.0,
) -> MagicMock:
    from app.schemas.playbook import RuleResponse

    return RuleResponse(
        id=uuid.uuid4(),
        playbook_id=playbook_id or uuid.uuid4(),
        clause_type=clause_type,
        preferred_language=preferred_language,
        acceptable_variations=None,
        prohibited_terms=None,
        fallback_language=None,
        required=required,
        risk_weight=risk_weight,
        escalation_threshold=None,
    )


def test_merge_rules_empty() -> None:
    assert _merge_rules([]) == {}


def test_merge_rules_single_playbook() -> None:
    r1 = _make_rule_resp("indemnification", preferred_language="A")
    r2 = _make_rule_resp("limitation", preferred_language="B")
    merged = _merge_rules([("nda", [r1, r2])])
    assert set(merged.keys()) == {"indemnification", "limitation"}
    assert merged["indemnification"].preferred_language == "A"


def test_merge_rules_higher_precedence_wins() -> None:
    """Rule from first (higher-precedence) playbook wins for shared clause_type."""
    high = _make_rule_resp("indemnification", preferred_language="HIGH")
    low = _make_rule_resp("indemnification", preferred_language="LOW")
    # First entry = higher precedence
    merged = _merge_rules([("saas_msa", [high]), ("gdpr", [low])])
    assert merged["indemnification"].preferred_language == "HIGH"


def test_merge_rules_lower_precedence_fills_gaps() -> None:
    """Lower-precedence playbook covers clause_types the higher one lacks."""
    high = _make_rule_resp("indemnification", preferred_language="HIGH")
    low_unique = _make_rule_resp("data_privacy", preferred_language="GDP")
    merged = _merge_rules([("saas_msa", [high]), ("gdpr", [low_unique])])
    assert merged["indemnification"].preferred_language == "HIGH"
    assert merged["data_privacy"].preferred_language == "GDP"


def test_merge_rules_deterministic_tie_break() -> None:
    """Equal-precedence playbooks — alphabetically first practice_area wins."""
    rule_a = _make_rule_resp("termination", preferred_language="ALPHA")
    rule_b = _make_rule_resp("termination", preferred_language="BETA")
    # "gdpr" < "hipaa" alphabetically → gdpr rule wins
    merged = _merge_rules([("gdpr", [rule_a]), ("hipaa", [rule_b])])
    assert merged["termination"].preferred_language == "ALPHA"


# ---------------------------------------------------------------------------
# API-level resolve endpoint tests
# ---------------------------------------------------------------------------

# The module-level mock session — tests mutate .execute on this object.
mock_session = AsyncMock()


async def _routing_mock_session():
    yield mock_session


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _patch_resolve_session():
    """Own the dependency override for the duration of each test in this file.

    Without this, test_playbooks_api.py's module-level override (same key,
    loaded later alphabetically) would shadow this file's mock_session.
    """
    prev = app.dependency_overrides.get(_get_session)
    app.dependency_overrides[_get_session] = _routing_mock_session
    yield
    if prev is None:
        app.dependency_overrides.pop(_get_session, None)
    else:
        app.dependency_overrides[_get_session] = prev


def _scalar(value: object) -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


def _scalars_all(items: list) -> MagicMock:
    m = MagicMock()
    m.scalars.return_value.all.return_value = items
    return m


def _make_pb(
    practice_area: str = "nda",
    precedence: int = 0,
) -> MagicMock:
    pb = MagicMock(spec=Playbook)
    pb.id = uuid.uuid4()
    pb.practice_area = practice_area
    pb.precedence = precedence
    return pb


def _make_rule_orm(
    playbook_id: uuid.UUID,
    clause_type: str = "indemnification",
    preferred_language: str = "Standard",
    required: bool = False,
    risk_weight: float = 1.0,
) -> MagicMock:
    rule = MagicMock(spec=PlaybookRule)
    rule.id = uuid.uuid4()
    rule.playbook_id = playbook_id
    rule.clause_type = clause_type
    rule.preferred_language = preferred_language
    rule.acceptable_variations = None
    rule.prohibited_terms = None
    rule.fallback_language = None
    rule.required = required
    rule.risk_weight = risk_weight
    rule.escalation_threshold = None
    return rule


def test_resolve_no_playbooks() -> None:
    """Known contract_type with no matching playbooks returns empty rule set."""
    mock_session.execute = AsyncMock(return_value=_scalars_all([]))
    response = client.get("/api/playbooks/resolve?contract_type=nda")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_type"] == "nda"
    assert body["rules"] == {}
    assert body["applied_practice_areas"] == []


def test_resolve_single_playbook_with_rules() -> None:
    pb = _make_pb(practice_area="nda", precedence=10)
    rule = _make_rule_orm(pb.id, clause_type="termination", preferred_language="T-lang")

    call_count = 0

    async def _side_effect(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # list_playbooks_by_areas
            return _scalars_all([pb])
        # list_rules for the playbook
        return _scalars_all([rule])

    mock_session.execute = _side_effect

    response = client.get("/api/playbooks/resolve?contract_type=nda")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_type"] == "nda"
    assert "termination" in body["rules"]
    assert body["rules"]["termination"]["preferred_language"] == "T-lang"
    assert body["applied_practice_areas"] == ["nda"]


def test_resolve_two_playbooks_precedence_merge() -> None:
    """Higher-precedence playbook rule wins on shared clause_type."""
    pb_high = _make_pb(practice_area="saas_msa", precedence=20)
    pb_low = _make_pb(practice_area="saas_msa", precedence=5)

    rule_high = _make_rule_orm(pb_high.id, clause_type="indemnification", preferred_language="HI")
    rule_low = _make_rule_orm(pb_low.id, clause_type="indemnification", preferred_language="LO")
    rule_unique = _make_rule_orm(pb_low.id, clause_type="payment", preferred_language="PAY")

    call_count = 0

    async def _side_effect(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalars_all([pb_high, pb_low])
        if call_count == 2:
            return _scalars_all([rule_high])
        return _scalars_all([rule_low, rule_unique])

    mock_session.execute = _side_effect

    response = client.get("/api/playbooks/resolve?contract_type=saas_msa")
    assert response.status_code == 200
    body = response.json()
    assert body["rules"]["indemnification"]["preferred_language"] == "HI"
    assert body["rules"]["payment"]["preferred_language"] == "PAY"


def test_resolve_unknown_contract_type_returns_empty() -> None:
    """Unknown contract_type → empty rules (identity expansion returns [])."""
    mock_session.execute = AsyncMock(return_value=_scalars_all([]))
    response = client.get("/api/playbooks/resolve?contract_type=unknown")
    assert response.status_code == 200
    body = response.json()
    assert body["rules"] == {}
    assert body["applied_practice_areas"] == []


def test_resolve_missing_contract_type_param() -> None:
    """Missing required query param returns 422."""
    response = client.get("/api/playbooks/resolve")
    assert response.status_code == 422
