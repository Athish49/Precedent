"""Tests for T-046 deterministic stance filter and NMS context builder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.db.repositories.nms_repo import CounterpartyPattern
from app.schemas.analysis import FlagDTO
from app.services.redline.stance import build_nms_context, queue_clauses

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(
    clause_id: uuid.UUID | None = None,
    severity: str = "high",
    flag_type: str = "high_risk",
    source: str = "llm",
) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        clause_id=clause_id,
        flag_type=flag_type,
        severity=severity,
        source=source,
        char_start=None,
        char_end=None,
        detail={},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
    )


def _pattern(
    accept_rate: float | None = 0.75,
    last_closed_text: str | None = "Mutual indemnification.",
    clause_type: str = "indemnification",
) -> CounterpartyPattern:
    return CounterpartyPattern(
        counterparty_id=uuid.uuid4(),
        clause_type=clause_type,
        accept_rate=accept_rate,
        last_closed_text=last_closed_text,
    )


# ---------------------------------------------------------------------------
# queue_clauses — severity filtering by stance
# ---------------------------------------------------------------------------


def test_light_queues_high_severity_only() -> None:
    flags = [
        _flag(clause_id=uuid.uuid4(), severity="low"),
        _flag(clause_id=uuid.uuid4(), severity="medium"),
        _flag(clause_id=uuid.uuid4(), severity="high"),
    ]
    result = queue_clauses(flags, "light")
    assert len(result) == 1
    assert result[0].severity == "high"


def test_balanced_queues_medium_and_high() -> None:
    cid_med = uuid.uuid4()
    cid_high = uuid.uuid4()
    flags = [
        _flag(clause_id=uuid.uuid4(), severity="low"),
        _flag(clause_id=cid_med, severity="medium"),
        _flag(clause_id=cid_high, severity="high"),
    ]
    result = queue_clauses(flags, "balanced")
    clause_ids = {f.clause_id for f in result}
    assert cid_med in clause_ids
    assert cid_high in clause_ids
    assert len(result) == 2


def test_firm_queues_all_severities() -> None:
    flags = [
        _flag(clause_id=uuid.uuid4(), severity="low"),
        _flag(clause_id=uuid.uuid4(), severity="medium"),
        _flag(clause_id=uuid.uuid4(), severity="high"),
    ]
    result = queue_clauses(flags, "firm")
    assert len(result) == 3


def test_queue_clauses_excludes_null_clause_id() -> None:
    """Missing-clause flags (clause_id=None) are excluded — no text to redline."""
    flags = [
        _flag(clause_id=None, severity="high"),
        _flag(clause_id=uuid.uuid4(), severity="high"),
    ]
    result = queue_clauses(flags, "firm")
    assert len(result) == 1
    assert result[0].clause_id is not None


def test_queue_clauses_deduplicates_per_clause() -> None:
    cid = uuid.uuid4()
    flags = [
        _flag(clause_id=cid, severity="medium"),
        _flag(clause_id=cid, severity="high"),
        _flag(clause_id=cid, severity="low"),
    ]
    result = queue_clauses(flags, "firm")
    assert len(result) == 1


def test_queue_clauses_picks_highest_severity_representative() -> None:
    cid = uuid.uuid4()
    flags = [
        _flag(clause_id=cid, severity="medium"),
        _flag(clause_id=cid, severity="high"),
    ]
    result = queue_clauses(flags, "balanced")
    assert result[0].severity == "high"


def test_queue_clauses_preserves_first_appearance_order() -> None:
    cid1, cid2, cid3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    flags = [
        _flag(clause_id=cid1, severity="high"),
        _flag(clause_id=cid2, severity="medium"),
        _flag(clause_id=cid3, severity="high"),
        _flag(clause_id=cid1, severity="low"),
    ]
    result = queue_clauses(flags, "firm")
    assert [f.clause_id for f in result] == [cid1, cid2, cid3]


def test_queue_clauses_returns_empty_when_no_flags_qualify() -> None:
    flags = [_flag(clause_id=uuid.uuid4(), severity="low")]
    assert queue_clauses(flags, "light") == []


def test_queue_clauses_empty_input() -> None:
    assert queue_clauses([], "balanced") == []


def test_queue_clauses_raises_on_unknown_stance_mode() -> None:
    with pytest.raises(ValueError, match="Unknown stance_mode"):
        queue_clauses([], "aggressive")


# ---------------------------------------------------------------------------
# build_nms_context — deterministic NMS stance context
# ---------------------------------------------------------------------------


def test_build_nms_context_no_pattern_light_mentions_light_approach() -> None:
    ctx = build_nms_context(None, "light")
    assert "light" in ctx.lower() or "minimal" in ctx.lower()


def test_build_nms_context_no_pattern_firm_mentions_firm_approach() -> None:
    ctx = build_nms_context(None, "firm")
    assert "firm" in ctx.lower() or "preferred" in ctx.lower()


def test_build_nms_context_includes_accept_rate_as_percentage() -> None:
    ctx = build_nms_context(_pattern(accept_rate=0.8, last_closed_text=None), "balanced")
    assert "80%" in ctx


def test_build_nms_context_includes_zero_accept_rate() -> None:
    ctx = build_nms_context(_pattern(accept_rate=0.0, last_closed_text=None), "firm")
    assert "0%" in ctx


def test_build_nms_context_includes_last_closed_text() -> None:
    ctx = build_nms_context(
        _pattern(accept_rate=None, last_closed_text="Vendor indemnifies for direct damages."),
        "balanced",
    )
    assert "Vendor indemnifies for direct damages." in ctx


def test_build_nms_context_stance_guidance_differs_by_mode() -> None:
    ctx_firm = build_nms_context(_pattern(), "firm")
    ctx_light = build_nms_context(_pattern(), "light")
    assert ctx_firm != ctx_light


def test_build_nms_context_all_null_fields_returns_no_history_string() -> None:
    ctx_none = build_nms_context(None, "balanced")
    ctx_all_null = build_nms_context(_pattern(accept_rate=None, last_closed_text=None), "balanced")
    assert ctx_none == ctx_all_null


def test_build_nms_context_raises_on_unknown_stance_mode() -> None:
    with pytest.raises(ValueError, match="Unknown stance_mode"):
        build_nms_context(None, "nuclear")


def test_build_nms_context_deterministic_same_input_same_output() -> None:
    pattern = _pattern(accept_rate=0.6, last_closed_text="Standard 30-day notice required.")
    ctx1 = build_nms_context(pattern, "balanced")
    ctx2 = build_nms_context(pattern, "balanced")
    assert ctx1 == ctx2


def test_build_nms_context_full_pattern_contains_all_fields() -> None:
    ctx = build_nms_context(
        _pattern(accept_rate=0.5, last_closed_text="Limitation of liability to 2x fees."),
        "firm",
    )
    assert "50%" in ctx
    assert "Limitation of liability to 2x fees." in ctx
