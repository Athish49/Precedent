"""Unit tests for app.services.redline.persist (T-049)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm.schemas.redline import AlternativeProposal, RedlineOut
from app.core.diff.differ import Change
from app.db.models.nms import DecisionEvent
from app.db.models.redline import Redline
from app.schemas.analysis import FlagDTO
from app.services.redline.render import RenderResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def contract_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def counterparty_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def flag(contract_id: uuid.UUID) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=contract_id,
        clause_id=uuid.uuid4(),
        flag_type="missing",
        severity="high",
        source="deterministic",
        char_start=10,
        char_end=50,
        detail={},
        matched_rule_id=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def redline_out() -> RedlineOut:
    return RedlineOut(
        replacement_text="Replacement clause text.",
        alternatives=[
            AlternativeProposal(label="Option A", text="Alt text A"),
            AlternativeProposal(label="Option B", text="Alt text B"),
        ],
        explanation="This clause was missing a limitation of liability cap.",
        counterparty_comment="We propose adding a liability cap of 2x fees.",
    )


@pytest.fixture
def render_result() -> RenderResult:
    change = Change(op="insert", text=" new text", old_start=-1, old_end=-1, new_start=10, new_end=19)
    return RenderResult(tracked_changes=[change], interference_detected=False)


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_redline_returns_tuple(
    mock_session, contract_id, counterparty_id, flag, redline_out, render_result
):
    """persist_redline returns a (Redline, DecisionEvent) tuple."""
    from app.services.redline.persist import persist_redline

    result = await persist_redline(
        session=mock_session,
        contract_id=contract_id,
        counterparty_id=counterparty_id,
        clause_type="limitation_of_liability",
        flag=flag,
        redline_out=redline_out,
        render_result=render_result,
        stance_mode="balanced",
        preferred_language="Liability shall not exceed 2x annual fees.",
    )

    assert isinstance(result, tuple)
    assert len(result) == 2
    redline, event = result
    assert isinstance(redline, Redline)
    assert isinstance(event, DecisionEvent)


@pytest.mark.asyncio
async def test_rationale_dict_keys(
    mock_session, contract_id, counterparty_id, flag, redline_out, render_result
):
    """rationale dict contains all expected keys with correct values."""
    from app.services.redline.persist import persist_redline

    preferred_language = "Liability shall not exceed 2x annual fees."
    redline, _ = await persist_redline(
        session=mock_session,
        contract_id=contract_id,
        counterparty_id=counterparty_id,
        clause_type="limitation_of_liability",
        flag=flag,
        redline_out=redline_out,
        render_result=render_result,
        stance_mode="firm",
        preferred_language=preferred_language,
    )

    rationale = redline.rationale
    assert "playbook_position" in rationale
    assert "flag_type" in rationale
    assert "flag_severity" in rationale
    assert "explanation" in rationale
    assert "stance_mode" in rationale
    assert "interference_detected" in rationale

    assert rationale["playbook_position"] == preferred_language
    assert rationale["flag_type"] == flag.flag_type
    assert rationale["flag_severity"] == flag.severity
    assert rationale["explanation"] == redline_out.explanation
    assert rationale["stance_mode"] == "firm"
    assert rationale["interference_detected"] is False


@pytest.mark.asyncio
async def test_tracked_changes_serialised_to_dicts(
    mock_session, contract_id, counterparty_id, flag, redline_out, render_result
):
    """tracked_changes is stored as a list of dicts (not Change objects)."""
    from app.services.redline.persist import persist_redline

    redline, _ = await persist_redline(
        session=mock_session,
        contract_id=contract_id,
        counterparty_id=counterparty_id,
        clause_type="limitation_of_liability",
        flag=flag,
        redline_out=redline_out,
        render_result=render_result,
        stance_mode="light",
        preferred_language=None,
    )

    assert isinstance(redline.tracked_changes, list)
    assert len(redline.tracked_changes) == 1
    change_dict = redline.tracked_changes[0]
    assert isinstance(change_dict, dict)
    assert "op" in change_dict
    assert "text" in change_dict
    assert change_dict["op"] == "insert"


@pytest.mark.asyncio
async def test_decision_event_outcome_pending(
    mock_session, contract_id, counterparty_id, flag, redline_out, render_result
):
    """DecisionEvent is created with outcome='pending'."""
    from app.services.redline.persist import persist_redline

    _, event = await persist_redline(
        session=mock_session,
        contract_id=contract_id,
        counterparty_id=counterparty_id,
        clause_type="indemnification",
        flag=flag,
        redline_out=redline_out,
        render_result=render_result,
        stance_mode="balanced",
        preferred_language=None,
    )

    assert event.outcome == "pending"
    assert event.position_offered == "preferred"
    assert event.recommended_stance == "balanced"


@pytest.mark.asyncio
async def test_session_add_called_twice(
    mock_session, contract_id, counterparty_id, flag, redline_out, render_result
):
    """Both Redline and DecisionEvent cause session.add to be called."""
    from app.services.redline.persist import persist_redline

    await persist_redline(
        session=mock_session,
        contract_id=contract_id,
        counterparty_id=counterparty_id,
        clause_type="indemnification",
        flag=flag,
        redline_out=redline_out,
        render_result=render_result,
        stance_mode="balanced",
        preferred_language=None,
    )

    assert mock_session.add.call_count == 2
    added_objects = [call.args[0] for call in mock_session.add.call_args_list]
    types = {type(o) for o in added_objects}
    assert Redline in types
    assert DecisionEvent in types
