"""Tests for review API routes (T-062)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisResult, FlagDTO, RiskDTO

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC)
_CONTRACT_ID = uuid.uuid4()
_RUN_ID = uuid.uuid4()


def _make_redline_dto(contract_id: uuid.UUID) -> dict:
    return dict(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=None,
        flag_id=None,
        stance_mode="balanced",
        position="preferred",
        replacement_text="revised clause text",
        tracked_changes=[],
        alternatives=[],
        explanation="explanation",
        counterparty_comment="",
        rationale={},
        status="proposed",
        created_at=_NOW,
    )


def _make_flag_dto(contract_id: uuid.UUID) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=None,
        flag_type="missing",
        severity="high",
        source="deterministic",
        char_start=None,
        char_end=None,
        detail={},
        matched_rule_id=None,
        created_at=_NOW,
    )


def _make_review_run(contract_id: uuid.UUID, run_id: uuid.UUID, trigger: str = "manual") -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id,
        contract_id=contract_id,
        trigger=trigger,
        gate_decision="auto_applied",
        gate_reason={"hard_stop": None, "aggregate_score": 0.2},
        status="completed",
        started_at=_NOW,
        completed_at=_NOW,
    )


def _make_pipeline(contract_id: uuid.UUID, redlines: list | None = None):
    from app.schemas.redline import RedlineDTO
    from app.workflows.review_pipeline import PipelineResult

    flag = _make_flag_dto(contract_id)
    risk = RiskDTO(score=0.2, max_clause_severity="low", weights_version="v1")
    analysis = AnalysisResult(flags=[flag], risk=risk)
    rdto_list = redlines or [RedlineDTO(**_make_redline_dto(contract_id))]
    return PipelineResult(
        contract_id=contract_id,
        analysis=analysis,
        redlines=rdto_list,
        stance_mode="balanced",
    )


def _make_gate(contract_id: uuid.UUID, run_id: uuid.UUID, pipeline, trigger: str = "manual"):
    from app.workflows.gate import GateResult

    return GateResult(
        review_run_id=run_id,
        contract_id=contract_id,
        gate_decision="auto_applied",
        gate_reason={"hard_stop": None, "aggregate_score": 0.2},
        pipeline=pipeline,
    )


def _mock_session() -> AsyncMock:
    return AsyncMock()


def _override_session(session):
    """Return a dependency override that injects the given session."""
    async def _dep():
        yield session
    return _dep


# ---------------------------------------------------------------------------
# Test: POST /api/review/run
# ---------------------------------------------------------------------------


def test_run_review_returns_200_with_gate_decision() -> None:
    contract_id = _CONTRACT_ID
    run_id = _RUN_ID
    session = _mock_session()
    pipeline = _make_pipeline(contract_id)
    gate = _make_gate(contract_id, run_id, pipeline)
    run_row = _make_review_run(contract_id, run_id)

    with (
        patch("app.api.routes.review.run_pipeline", AsyncMock(return_value=pipeline)),
        patch("app.api.routes.review.evaluate_gate", AsyncMock(return_value=gate)),
        patch("app.api.routes.review.review_run_repo.get_review_run", AsyncMock(return_value=run_row)),
    ):
        from app.api.routes import review as review_module
        app.dependency_overrides[review_module._get_session] = _override_session(session)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/review/run", json={"contract_id": str(contract_id)})
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["gate_decision"] == "auto_applied"
    assert "redlines" in body
    assert "run" in body
    assert body["run"]["id"] == str(run_id)
    assert body["flags_count"] == 1


# ---------------------------------------------------------------------------
# Test: GET /api/review/runs/{run_id}
# ---------------------------------------------------------------------------


def test_get_review_run_returns_200_with_run_data() -> None:
    contract_id = _CONTRACT_ID
    run_id = _RUN_ID
    session = _mock_session()
    run_row = _make_review_run(contract_id, run_id)

    flag = _make_flag_dto(contract_id)
    risk = RiskDTO(score=0.3, max_clause_severity="medium", weights_version="v1")
    analysis = AnalysisResult(flags=[flag], risk=risk)

    from app.db.models.redline import Redline
    redline_ns = SimpleNamespace(**_make_redline_dto(contract_id))

    with (
        patch("app.api.routes.review.review_run_repo.get_review_run", AsyncMock(return_value=run_row)),
        patch("app.api.routes.review.redline_repo.get_redlines_for_contract", AsyncMock(return_value=[redline_ns])),
        patch("app.api.routes.review.contract_analysis_service.get_analysis", AsyncMock(return_value=analysis)),
    ):
        from app.api.routes import review as review_module
        app.dependency_overrides[review_module._get_session] = _override_session(session)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(f"/api/review/runs/{run_id}")
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["id"] == str(run_id)
    assert body["gate_decision"] == "auto_applied"
    assert body["flags_count"] == 1
    assert body["risk_score"] == pytest.approx(0.3)


def test_get_review_run_returns_404_when_not_found() -> None:
    session = _mock_session()

    with (
        patch("app.api.routes.review.review_run_repo.get_review_run", AsyncMock(return_value=None)),
    ):
        from app.api.routes import review as review_module
        app.dependency_overrides[review_module._get_session] = _override_session(session)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/review/runs/{uuid.uuid4()}")
        app.dependency_overrides.clear()

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "run_not_found"


# ---------------------------------------------------------------------------
# Test: POST /api/review/webhook
# ---------------------------------------------------------------------------


def test_webhook_returns_200_with_upload_event_trigger() -> None:
    contract_id = _CONTRACT_ID
    run_id = _RUN_ID
    session = _mock_session()
    pipeline = _make_pipeline(contract_id)
    gate = _make_gate(contract_id, run_id, pipeline, trigger="upload_event")
    run_row = _make_review_run(contract_id, run_id, trigger="upload_event")

    captured_trigger: list[str] = []

    async def _mock_evaluate_gate(sess, pip, trigger="manual", **kwargs):
        captured_trigger.append(trigger)
        return gate

    with (
        patch("app.api.routes.review.run_pipeline", AsyncMock(return_value=pipeline)),
        patch("app.api.routes.review.evaluate_gate", _mock_evaluate_gate),
        patch("app.api.routes.review.review_run_repo.get_review_run", AsyncMock(return_value=run_row)),
    ):
        from app.api.routes import review as review_module
        app.dependency_overrides[review_module._get_session] = _override_session(session)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/review/webhook", json={"contract_id": str(contract_id)})
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert captured_trigger == ["upload_event"]
    body = resp.json()
    assert body["run"]["trigger"] == "upload_event"
    assert body["gate_decision"] == "auto_applied"
