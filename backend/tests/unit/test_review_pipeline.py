"""Tests for T-060 Review Pipeline orchestration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.schemas.analysis import AnalysisResult, FlagDTO, RiskDTO
from app.schemas.redline import RedlineDTO
from app.workflows.review_pipeline import PipelineResult, run_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE = "app.workflows.review_pipeline"


def _make_contract(
    contract_type: str = "nda",
    counterparty_id: uuid.UUID | None = None,
    party_role: str = "vendor",
    paper_origin: str = "own",
    context: dict | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.contract_type = contract_type
    c.counterparty_id = counterparty_id or uuid.uuid4()
    c.party_role = party_role
    c.paper_origin = paper_origin
    c.context = context
    return c


def _make_flag(
    contract_id: uuid.UUID | None = None,
    clause_id: uuid.UUID | None = None,
    severity: str = "high",
) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=contract_id or uuid.uuid4(),
        clause_id=clause_id,
        flag_type="missing_clause",
        severity=severity,
        source="deterministic",
        char_start=0,
        char_end=10,
        detail={},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
    )


def _make_clause(contract_id: uuid.UUID, clause_id: uuid.UUID | None = None) -> MagicMock:
    c = MagicMock()
    c.id = clause_id or uuid.uuid4()
    c.contract_id = contract_id
    c.clause_type = "indemnification"
    c.text = "Indemnification clause text."
    return c


def _make_redline_row(contract_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=uuid.uuid4(),
        flag_id=uuid.uuid4(),
        stance_mode="balanced",
        position="preferred",
        replacement_text="Revised text.",
        tracked_changes=[],
        alternatives=[],
        explanation="Explanation.",
        counterparty_comment="Comment.",
        rationale={},
        status="proposed",
        created_at=datetime.now(UTC),
    )


def _make_resolved(rules: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.rules = rules or {}
    return r


def _make_redline_out(replacement: str = "Revised text.") -> MagicMock:
    out = MagicMock()
    out.replacement_text = replacement
    out.explanation = "Explanation."
    out.counterparty_comment = "Comment."
    out.alternatives = []
    return out


def _make_render_result() -> MagicMock:
    rr = MagicMock()
    rr.tracked_changes = []
    rr.interference_detected = False
    return rr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_pipeline_result():
    """run_pipeline returns PipelineResult with correct contract_id and stance_mode."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    flag = _make_flag(contract_id=contract_id, clause_id=clause_id, severity="high")
    analysis = AnalysisResult(
        flags=[flag],
        risk=RiskDTO(score=7.5, max_clause_severity="high", weights_version="v1"),
    )
    clause = _make_clause(contract_id, clause_id)
    redline_row = _make_redline_row(contract_id)
    redline_out = _make_redline_out()
    render_result = _make_render_result()

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=_make_resolved())),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[clause]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(
            f"{_MODULE}.nms_repo.get_counterparty_pattern",
            new=AsyncMock(return_value=None),
        ),
        patch(f"{_MODULE}.llm_call.generate_redline", return_value=redline_out),
        patch(f"{_MODULE}.render.render", return_value=render_result),
        patch(
            f"{_MODULE}.persist.persist_redline",
            new=AsyncMock(return_value=(redline_row, MagicMock())),
        ),
    ):
        result = await run_pipeline(session, contract_id, stance_mode="balanced")

    assert isinstance(result, PipelineResult)
    assert result.contract_id == contract_id
    assert result.stance_mode == "balanced"
    assert isinstance(result.analysis, AnalysisResult)
    assert len(result.redlines) == 1
    assert isinstance(result.redlines[0], RedlineDTO)


@pytest.mark.asyncio
async def test_contract_not_found_raises_app_error():
    """run_pipeline raises AppError(404) when contract is missing."""
    session = AsyncMock()
    contract_id = uuid.uuid4()

    with patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=None)):
        with pytest.raises(AppError) as exc_info:
            await run_pipeline(session, contract_id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "contract_not_found"


@pytest.mark.asyncio
async def test_concurrent_fetch_calls_both_gather_dependencies():
    """Both routing.resolve and clause_repo.get_clauses_for_contract are called."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    resolve_mock = AsyncMock(return_value=_make_resolved())
    clauses_mock = AsyncMock(return_value=[])
    analysis = AnalysisResult(flags=[], risk=None)

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=resolve_mock),
        patch(f"{_MODULE}.clause_repo.get_clauses_for_contract", new=clauses_mock),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
    ):
        result = await run_pipeline(session, contract_id)

    resolve_mock.assert_called_once_with(
        session,
        contract.contract_type,
        contract.party_role,
        contract.paper_origin,
        contract.context,
    )
    clauses_mock.assert_called_once_with(session, contract_id)
    assert result.redlines == []


@pytest.mark.asyncio
async def test_empty_flags_produces_no_redlines_and_no_llm_call():
    """When analysis returns no flags, redlines is empty and LLM is never called."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    analysis = AnalysisResult(flags=[], risk=None)
    llm_mock = MagicMock()

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=_make_resolved())),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(f"{_MODULE}.llm_call.generate_redline", new=llm_mock),
    ):
        result = await run_pipeline(session, contract_id)

    assert result.redlines == []
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_stance_filter_light_skips_low_severity_flags():
    """With stance_mode='light', only high-severity flags pass; low flags produce no redlines."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id

    # Only low-severity flag — should be filtered by stance "light"
    low_flag = _make_flag(contract_id=contract_id, clause_id=clause_id, severity="low")
    analysis = AnalysisResult(flags=[low_flag], risk=None)
    clause = _make_clause(contract_id, clause_id)
    llm_mock = MagicMock()

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=_make_resolved())),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[clause]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(f"{_MODULE}.llm_call.generate_redline", new=llm_mock),
    ):
        result = await run_pipeline(session, contract_id, stance_mode="light")

    assert result.redlines == []
    llm_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Task 5.5: preferred-language fallback comes from rule positions only.
# ---------------------------------------------------------------------------


def _position_response(kind: str, rung: int | None, language: str):
    from app.schemas.playbook import RulePositionResponse

    now = datetime.now(UTC)
    return RulePositionResponse(
        id=uuid.uuid4(), rule_id=uuid.uuid4(), kind=kind, rung=rung, label=kind,
        language=language, summary=None, zone="green", approver_role_id=None,
        conditions=None, give_get=None, internal_note=None, created_at=now, updated_at=now,
    )


async def _run_with_rule(rule: SimpleNamespace | None) -> tuple[MagicMock, AsyncMock]:
    """Run the pipeline over one flagged 'indemnification' clause with *rule*
    as its resolved rule; return the generate_redline and persist mocks."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id
    flag = _make_flag(contract_id=contract_id, clause_id=clause_id, severity="high")
    analysis = AnalysisResult(
        flags=[flag],
        risk=RiskDTO(score=7.5, max_clause_severity="high", weights_version="v1"),
    )
    rules = {"indemnification": rule} if rule is not None else {}
    generate = MagicMock(return_value=_make_redline_out())
    persist_mock = AsyncMock(return_value=(_make_redline_row(contract_id), MagicMock()))

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=_make_resolved())),
        patch(f"{_MODULE}.routing.rules_by_clause_type", return_value=rules),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[_make_clause(contract_id, clause_id)]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(f"{_MODULE}.nms_repo.get_counterparty_pattern", new=AsyncMock(return_value=None)),
        patch(f"{_MODULE}.llm_call.generate_redline", new=generate),
        patch(f"{_MODULE}.render.render", return_value=_make_render_result()),
        patch(f"{_MODULE}.persist.persist_redline", new=persist_mock),
    ):
        await run_pipeline(session, contract_id, stance_mode="balanced")
    return generate, persist_mock


@pytest.mark.asyncio
async def test_preferred_language_from_preferred_position():
    rule = SimpleNamespace(
        positions=[_position_response("preferred", 0, "Preferred text.")], objections=[]
    )
    generate, persist_mock = await _run_with_rule(rule)
    assert generate.call_args.args[2] == "Preferred text."
    assert persist_mock.call_args.args[8] == "Preferred text."


@pytest.mark.asyncio
async def test_preferred_language_falls_back_to_rung_zero_position():
    """No kind='preferred' position, but a rung-0 position exists: its
    language is used. Before migration 015 this case read the legacy
    rule.preferred_language column instead."""
    rule = SimpleNamespace(
        positions=[_position_response("acceptable_variant", 0, "Rung zero text.")],
        objections=[],
    )
    generate, persist_mock = await _run_with_rule(rule)
    assert generate.call_args.args[2] == "Rung zero text."
    assert persist_mock.call_args.args[8] == "Rung zero text."


@pytest.mark.asyncio
async def test_preferred_language_none_without_rung_zero_or_rule():
    rule = SimpleNamespace(
        positions=[_position_response("fallback", 1, "Fallback text.")], objections=[]
    )
    generate, _ = await _run_with_rule(rule)
    assert generate.call_args.args[2] is None

    generate, _ = await _run_with_rule(None)
    assert generate.call_args.args[2] is None


# ---------------------------------------------------------------------------
# Audit fix: a flag's ladder comes from the rule identified by the flag's own
# rule_key, not whichever rule in the clause family sorts first.
# ---------------------------------------------------------------------------


def _family_rule(rule_key: str, language: str) -> SimpleNamespace:
    return SimpleNamespace(
        rule_key=rule_key,
        clause_type="indemnification",
        positions=[_position_response("preferred", 0, language)],
        objections=[],
    )


async def _run_with_family(flag_rule_key: str | None) -> tuple[MagicMock, AsyncMock, list]:
    """Two resolved rules share clause_type 'indemnification'; the one that
    sorts first by rule_key is 'indemnification.a_general'. Uses the REAL
    rules_by_clause_type / rules_by_rule_key / rule_for_flag."""
    session = AsyncMock()
    contract_id = uuid.uuid4()
    clause_id = uuid.uuid4()
    contract = _make_contract()
    contract.id = contract_id
    flag = _make_flag(contract_id=contract_id, clause_id=clause_id, severity="high")
    flag.rule_key = flag_rule_key
    analysis = AnalysisResult(
        flags=[flag],
        risk=RiskDTO(score=7.5, max_clause_severity="high", weights_version="v1"),
    )
    family = [
        _family_rule("indemnification.a_general", "GENERAL"),
        _family_rule("indemnification.b_ip_infringement", "IP"),
    ]
    resolved = MagicMock()
    resolved.rules = family
    resolved.pinned_version_ids = []
    generate = MagicMock(return_value=_make_redline_out())
    persist_mock = AsyncMock(return_value=(_make_redline_row(contract_id), MagicMock()))

    with (
        patch(f"{_MODULE}.contract_repo.get_contract", new=AsyncMock(return_value=contract)),
        patch(f"{_MODULE}.routing.resolve", new=AsyncMock(return_value=resolved)),
        patch(
            f"{_MODULE}.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[_make_clause(contract_id, clause_id)]),
        ),
        patch(
            f"{_MODULE}.contract_analysis_service.analyze",
            new=AsyncMock(return_value=analysis),
        ),
        patch(f"{_MODULE}.nms_repo.get_counterparty_pattern", new=AsyncMock(return_value=None)),
        patch(f"{_MODULE}.llm_call.generate_redline", new=generate),
        patch(f"{_MODULE}.render.render", return_value=_make_render_result()),
        patch(f"{_MODULE}.persist.persist_redline", new=persist_mock),
    ):
        await run_pipeline(session, contract_id, stance_mode="balanced")
    return generate, persist_mock, family


@pytest.mark.asyncio
async def test_flag_rule_key_selects_its_own_rule_not_first_in_clause_family():
    generate, persist_mock, family = await _run_with_family("indemnification.b_ip_infringement")
    assert persist_mock.call_args.kwargs["rule"] is family[1]
    assert generate.call_args.args[2] == "IP"


@pytest.mark.asyncio
async def test_flag_without_rule_key_falls_back_to_clause_type_rule():
    generate, persist_mock, family = await _run_with_family(None)
    assert persist_mock.call_args.kwargs["rule"] is family[0]
    assert generate.call_args.args[2] == "GENERAL"


@pytest.mark.asyncio
async def test_flag_with_unresolved_rule_key_gets_no_rule_not_a_clause_type_guess():
    generate, persist_mock, _ = await _run_with_family("indemnification.dropped_by_applies_when")
    assert persist_mock.call_args.kwargs["rule"] is None
    assert generate.call_args.args[2] is None
