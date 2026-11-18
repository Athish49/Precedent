"""Unit tests for S4 Drafting API endpoints (T-072).

All DB and service calls are mocked — no real database or LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.routes.drafting import _get_session
from app.main import app
from app.services.drafting.service import DraftResult

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)


# ── POST /api/drafting/clause ─────────────────────────────────────────────────


def test_draft_clause_with_preferred_language() -> None:
    """preferred_language set → 200, source='playbook'."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_clause",
        new=AsyncMock(return_value=DraftResult(text="Preferred text.", source="playbook")),
    ):
        response = client.post(
            "/api/drafting/clause",
            json={
                "clause_type": "limitation_of_liability",
                "preferred_language": "Liability is capped at fees paid.",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "playbook"
    assert body["text"] == "Preferred text."


def test_draft_clause_without_preferred_language() -> None:
    """No preferred_language → 200, source from mock (frequency or llm)."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_clause",
        new=AsyncMock(return_value=DraftResult(text="Frequency clause text.", source="frequency")),
    ):
        response = client.post(
            "/api/drafting/clause",
            json={"clause_type": "indemnification", "context": "SaaS deal context"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "frequency"
    assert body["text"] == "Frequency clause text."


def test_draft_clause_forwards_playbook_resolution_fields() -> None:
    """contract_type/party_role/paper_origin/mode (task 4.7) reach the
    service layer unchanged, alongside the free-text context."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_clause",
        new=AsyncMock(return_value=DraftResult(text="Playbook text.", source="playbook")),
    ) as draft_mock:
        response = client.post(
            "/api/drafting/clause",
            json={
                "clause_type": "limitation_of_liability",
                "context": "Enterprise SaaS deal.",
                "contract_type": "saas_msa",
                "party_role": "vendor",
                "paper_origin": "own",
                "mode": "playbook",
            },
        )

    assert response.status_code == 200
    assert response.json()["source"] == "playbook"
    draft_mock.assert_called_once()
    _, kwargs = draft_mock.call_args
    assert kwargs["context"] == "Enterprise SaaS deal."
    assert kwargs["contract_type"] == "saas_msa"
    assert kwargs["party_role"] == "vendor"
    assert kwargs["paper_origin"] == "own"
    assert kwargs["mode"] == "playbook"
    assert kwargs["deal_context"] is None


def test_draft_clause_forwards_structured_deal_context() -> None:
    """A structured deal_context dict reaches the service layer as-is."""
    deal_context = {"regimes": ["hipaa", "gdpr"], "deal_value_band": "mid"}
    with patch(
        "app.api.routes.drafting.drafting_service.draft_clause",
        new=AsyncMock(return_value=DraftResult(text="Overlay text.", source="playbook")),
    ) as draft_mock:
        response = client.post(
            "/api/drafting/clause",
            json={
                "clause_type": "data_protection",
                "context": "Cover PHI.",
                "contract_type": "saas_msa",
                "party_role": "customer",
                "deal_context": deal_context,
            },
        )

    assert response.status_code == 200
    _, kwargs = draft_mock.call_args
    assert kwargs["deal_context"] == deal_context
    assert kwargs["context"] == "Cover PHI."
    assert kwargs["mode"] is None


def test_draft_clause_rejects_unknown_mode() -> None:
    """mode is validated against the cascade steps it can start from."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_clause",
        new=AsyncMock(return_value=DraftResult(text="x", source="llm")),
    ) as draft_mock:
        response = client.post(
            "/api/drafting/clause",
            json={"clause_type": "indemnification", "mode": "bogus"},
        )

    assert response.status_code == 422
    draft_mock.assert_not_called()


# ── POST /api/drafting/document ───────────────────────────────────────────────


def test_draft_document_no_polish() -> None:
    """polish=False → 200, source='template'."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_document",
        new=AsyncMock(return_value=DraftResult(text="Rendered document.", source="template")),
    ):
        response = client.post(
            "/api/drafting/document",
            json={
                "template": "Agreement between $party_a and $party_b.",
                "variables": {"party_a": "Acme", "party_b": "Beta"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "template"
    assert body["text"] == "Rendered document."


def test_draft_document_with_polish() -> None:
    """polish=True → 200, source='llm'."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_document",
        new=AsyncMock(return_value=DraftResult(text="Polished document.", source="llm")),
    ):
        response = client.post(
            "/api/drafting/document",
            json={
                "template": "Agreement between $party_a and $party_b.",
                "variables": {"party_a": "Acme", "party_b": "Beta"},
                "polish": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "llm"
    assert body["text"] == "Polished document."


# ── POST /api/drafting/precedent ──────────────────────────────────────────────


def test_draft_precedent() -> None:
    """Vector search + LLM → 200, source='llm'."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_precedent",
        new=AsyncMock(return_value=DraftResult(text="Precedent-style clause.", source="llm")),
    ):
        response = client.post(
            "/api/drafting/precedent",
            json={"clause_type": "governing_law", "context": {"contract_type": "SaaS"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "llm"
    assert body["text"] == "Precedent-style clause."


# ── POST /api/drafting/memo ───────────────────────────────────────────────────


def test_draft_memo() -> None:
    """LLM memo → 200, source='llm'."""
    with patch(
        "app.api.routes.drafting.drafting_service.draft_memo",
        new=AsyncMock(return_value=DraftResult(text="Drafted memo.", source="llm")),
    ):
        response = client.post(
            "/api/drafting/memo",
            json={"context": {"subject": "Contract Review", "to": "Client"}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "llm"
    assert body["text"] == "Drafted memo."
