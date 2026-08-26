"""Tests for S2 analysis service — orchestration and persistence (T-044)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.schemas.analysis import AnalysisResult, RiskDTO
from app.services.contract_analysis.models import AnalysisFlag
from app.services.contract_analysis.scoring import WEIGHTS_VERSION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _contract(paper_origin: str = "own", contract_type: str = "nda") -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.paper_origin = paper_origin
    c.contract_type = contract_type
    c.status = "processing"
    return c


def _flag_orm(contract_id: uuid.UUID, flag_type: str = "missing") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=None,
        flag_type=flag_type,
        severity="high",
        source="deterministic",
        char_start=None,
        char_end=None,
        detail={"clause_type": "indemnification"},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
    )


def _risk_orm(contract_id: uuid.UUID, score: float = 9.0) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        contract_id=contract_id,
        score=score,
        max_clause_severity="high",
        weights_version=WEIGHTS_VERSION,
    )


def _analysis_flag(contract_id: uuid.UUID, clause_type: str = "indemnification") -> AnalysisFlag:
    return AnalysisFlag(
        contract_id=contract_id,
        flag_type="missing",
        severity="high",
        source="deterministic",
        clause_type=clause_type,
    )


def _mock_resolve(rules: dict | None = None):
    """Return a coroutine mock for resolve() that yields a ResolveResponse-like object."""
    response = MagicMock()
    response.rules = rules or {}
    return AsyncMock(return_value=response)


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# analyze() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_returns_analysis_result() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    flag_row = _flag_orm(contract_id)
    risk_row = _risk_orm(contract_id)

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = AsyncMock(return_value=[flag_row])
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=9.0,
            max_clause_severity="high",
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        result = await service.analyze(_mock_session(), contract_id)

    assert isinstance(result, AnalysisResult)
    assert isinstance(result.risk, RiskDTO)
    assert result.risk.score == 9.0


@pytest.mark.asyncio
async def test_analyze_flags_appear_in_result() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    flag_row = _flag_orm(contract_id, flag_type="missing")
    risk_row = _risk_orm(contract_id, score=0.0)

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = AsyncMock(return_value=[flag_row])
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=0.0,
            max_clause_severity=None,
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        result = await service.analyze(_mock_session(), contract_id)

    assert len(result.flags) == 1
    assert result.flags[0].flag_type == "missing"


@pytest.mark.asyncio
async def test_analyze_contract_not_found_raises_404() -> None:
    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
    ):
        mock_cr.get_contract = AsyncMock(return_value=None)

        from app.services.contract_analysis import service
        with pytest.raises(AppError) as exc_info:
            await service.analyze(_mock_session(), uuid.uuid4())

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# clause_type preserved in detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_clause_type_folded_into_detail() -> None:
    """clause_type must appear in flag.detail — the DB row has no clause_type column."""
    contract_id = uuid.uuid4()
    contract = _contract()
    layer1_flag = _analysis_flag(contract_id, clause_type="termination")
    risk_row = _risk_orm(contract_id, score=9.0)

    captured_flags: list = []

    async def _capture_bulk_create(_session, flags):
        captured_flags.extend(flags)
        # Return SimpleNamespace rows that FlagDTO.model_validate can read
        rows = [
            SimpleNamespace(
                id=uuid.uuid4(),
                contract_id=f.contract_id,
                clause_id=f.clause_id,
                flag_type=f.flag_type,
                severity=f.severity,
                source=f.source,
                char_start=f.char_start,
                char_end=f.char_end,
                detail=f.detail,
                matched_rule_id=f.matched_rule_id,
                created_at=datetime.now(UTC),
            )
            for f in flags
        ]
        return rows

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[layer1_flag]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = _capture_bulk_create
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=9.0,
            max_clause_severity="high",
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        await service.analyze(_mock_session(), contract_id)

    assert len(captured_flags) == 1
    assert captured_flags[0].detail.get("clause_type") == "termination"


# ---------------------------------------------------------------------------
# Re-run semantics — replace prior results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_deletes_prior_flags_before_persisting() -> None:
    """Re-running analysis must clear prior flags first."""
    contract_id = uuid.uuid4()
    contract = _contract()
    risk_row = _risk_orm(contract_id, score=0.0)

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = AsyncMock(return_value=[])
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=0.0,
            max_clause_severity=None,
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        await service.analyze(_mock_session(), contract_id)

    mock_ar.delete_flags_for_contract.assert_awaited_once()
    mock_ar.delete_risk_score_for_contract.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_commits_after_persist() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    risk_row = _risk_orm(contract_id)
    session = _mock_session()

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = AsyncMock(return_value=[])
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=0.0,
            max_clause_severity=None,
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        await service.analyze(session, contract_id)

    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_sets_contract_status_to_analyzed() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    risk_row = _risk_orm(contract_id)

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = AsyncMock(return_value=[])
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=0.0,
            max_clause_severity=None,
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        await service.analyze(_mock_session(), contract_id)

    assert contract.status == "analyzed"


# ---------------------------------------------------------------------------
# get_analysis() — stored results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_analysis_returns_empty_before_any_run() -> None:
    """Contract exists but unanalyzed → flags=[], risk=None (not 404)."""
    contract_id = uuid.uuid4()
    contract = _contract()

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_ar.get_flags_for_contract = AsyncMock(return_value=[])
        mock_ar.get_risk_score_for_contract = AsyncMock(return_value=None)

        from app.services.contract_analysis import service
        result = await service.get_analysis(_mock_session(), contract_id)

    assert result.flags == []
    assert result.risk is None


@pytest.mark.asyncio
async def test_get_analysis_contract_not_found_raises_404() -> None:
    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
    ):
        mock_cr.get_contract = AsyncMock(return_value=None)

        from app.services.contract_analysis import service
        with pytest.raises(AppError) as exc_info:
            await service.get_analysis(_mock_session(), uuid.uuid4())

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_analysis_returns_stored_flags_and_risk() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    stored_flag = _flag_orm(contract_id, flag_type="high_risk")
    stored_risk = _risk_orm(contract_id, score=9.0)

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_ar.get_flags_for_contract = AsyncMock(return_value=[stored_flag])
        mock_ar.get_risk_score_for_contract = AsyncMock(return_value=stored_risk)

        from app.services.contract_analysis import service
        result = await service.get_analysis(_mock_session(), contract_id)

    assert len(result.flags) == 1
    assert result.flags[0].flag_type == "high_risk"
    assert result.risk is not None
    assert result.risk.score == 9.0


# ---------------------------------------------------------------------------
# Layer 1 + Layer 2 flags combined
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_combines_layer1_and_layer2_flags() -> None:
    """Both deterministic and LLM flags are persisted."""
    contract_id = uuid.uuid4()
    contract = _contract()
    l1_flag = _analysis_flag(contract_id, clause_type="indemnification")
    l2_flag = AnalysisFlag(
        contract_id=contract_id,
        flag_type="high_risk",
        severity="medium",
        source="llm",
        clause_type="limitation_of_liability",
    )
    risk_row = _risk_orm(contract_id, score=12.0)

    captured: list = []

    async def _capture(session, flags):
        captured.extend(flags)
        return [
            SimpleNamespace(
                id=uuid.uuid4(),
                contract_id=f.contract_id,
                clause_id=f.clause_id,
                flag_type=f.flag_type,
                severity=f.severity,
                source=f.source,
                char_start=f.char_start,
                char_end=f.char_end,
                detail=f.detail,
                matched_rule_id=f.matched_rule_id,
                created_at=datetime.now(UTC),
            )
            for f in flags
        ]

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[l1_flag]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[l2_flag]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = _capture
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=12.0,
            max_clause_severity="high",
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        result = await service.analyze(_mock_session(), contract_id)

    assert len(captured) == 2
    flag_types = {f.flag_type for f in captured}
    assert "missing" in flag_types
    assert "high_risk" in flag_types
    assert result.risk.score == 12.0


# ---------------------------------------------------------------------------
# RiskDTO shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_risk_dto_has_expected_fields() -> None:
    contract_id = uuid.uuid4()
    contract = _contract()
    risk_row = _risk_orm(contract_id, score=27.0)
    risk_row.max_clause_severity = "high"
    risk_row.weights_version = WEIGHTS_VERSION

    with (
        patch("app.services.contract_analysis.service.contract_repo") as mock_cr,
        patch("app.services.contract_analysis.service.clause_repo") as mock_cl,
        patch("app.services.contract_analysis.service.analysis_repo") as mock_ar,
        patch("app.services.contract_analysis.service.resolve", _mock_resolve()),
        patch("app.services.contract_analysis.service.run_layer1", return_value=[]),
        patch("app.services.contract_analysis.service.match_clauses_to_rules", return_value=[]),
        patch("app.services.contract_analysis.service.run_layer2", return_value=[]),
        patch("app.services.contract_analysis.service.score_flags") as mock_score,
    ):
        mock_cr.get_contract = AsyncMock(return_value=contract)
        mock_cl.get_clauses_for_contract = AsyncMock(return_value=[])
        mock_ar.delete_flags_for_contract = AsyncMock()
        mock_ar.delete_risk_score_for_contract = AsyncMock()
        mock_ar.bulk_create_flags = AsyncMock(return_value=[])
        mock_ar.create_risk_score = AsyncMock(return_value=risk_row)

        from app.services.contract_analysis.scoring import ContractScore
        mock_score.return_value = ContractScore(
            score=27.0,
            max_clause_severity="high",
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

        from app.services.contract_analysis import service
        result = await service.analyze(_mock_session(), contract_id)

    assert result.risk.score == 27.0
    assert result.risk.max_clause_severity == "high"
    assert result.risk.weights_version == WEIGHTS_VERSION
