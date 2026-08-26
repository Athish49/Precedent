"""Unit tests for T-050 — toggle_fallback, refine, record_decision."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm.schemas.redline import AlternativeProposal, RedlineOut
from app.db.models.nms import DecisionEvent
from app.db.models.redline import Redline
from app.services.redline import operations as ops_module
from app.services.redline.operations import record_decision, refine, toggle_fallback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _redline(
    position: str = "preferred",
    replacement_text: str = "Revised clause text.",
    alternatives: list[dict] | None = None,
    explanation: str = "Changed for protection.",
    counterparty_comment: str = "We propose the following.",
    status: str = "proposed",
    stance_mode: str = "balanced",
) -> Redline:
    if alternatives is None:
        alternatives = [
            {"label": "Option A", "text": "Fallback clause text."},
            {"label": "Option B", "text": "Another alternative."},
        ]
    r = Redline(
        contract_id=uuid.uuid4(),
        stance_mode=stance_mode,
        position=position,
        replacement_text=replacement_text,
        tracked_changes=[],
        alternatives=alternatives,
        explanation=explanation,
        counterparty_comment=counterparty_comment,
        rationale={},
        status=status,
    )
    return r


def _canned_redline_out(replacement: str = "Refined replacement text.") -> RedlineOut:
    return RedlineOut(
        replacement_text=replacement,
        alternatives=[
            AlternativeProposal(label="Option A", text="Alt A text."),
            AlternativeProposal(label="Option B", text="Alt B text."),
        ],
        explanation="Refined explanation.",
        counterparty_comment="Refined comment.",
    )


# ---------------------------------------------------------------------------
# toggle_fallback — preferred → fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_fallback_preferred_to_fallback_swaps_text() -> None:
    session = _mock_session()
    r = _redline(position="preferred", replacement_text="Preferred text.")

    original_fallback_text = r.alternatives[0]["text"]
    await toggle_fallback(session, r, "Original clause.")

    assert r.replacement_text == original_fallback_text


@pytest.mark.asyncio
async def test_toggle_fallback_preferred_to_fallback_flips_position() -> None:
    session = _mock_session()
    r = _redline(position="preferred")
    await toggle_fallback(session, r, "Original clause.")
    assert r.position == "fallback"


@pytest.mark.asyncio
async def test_toggle_fallback_preferred_to_fallback_updates_tracked_changes() -> None:
    session = _mock_session()
    r = _redline(position="preferred", replacement_text="Preferred text.")
    await toggle_fallback(session, r, "Original clause.")
    assert isinstance(r.tracked_changes, list)
    assert len(r.tracked_changes) > 0


@pytest.mark.asyncio
async def test_toggle_fallback_preferred_to_fallback_calls_flush() -> None:
    session = _mock_session()
    r = _redline(position="preferred")
    await toggle_fallback(session, r, "Original clause.")
    session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# toggle_fallback — fallback → preferred (reversible)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_fallback_fallback_to_preferred_swaps_back() -> None:
    session = _mock_session()
    r = _redline(position="preferred", replacement_text="Preferred text.")
    original_preferred = r.replacement_text

    await toggle_fallback(session, r, "Original.")
    assert r.position == "fallback"

    session2 = _mock_session()
    await toggle_fallback(session2, r, "Original.")

    assert r.position == "preferred"
    assert r.replacement_text == original_preferred


@pytest.mark.asyncio
async def test_toggle_fallback_fallback_to_preferred_flips_position() -> None:
    session = _mock_session()
    r = _redline(position="fallback", replacement_text="Fallback text.")
    await toggle_fallback(session, r, "Original clause.")
    assert r.position == "preferred"


# ---------------------------------------------------------------------------
# toggle_fallback — no alternatives raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_fallback_no_alternatives_raises() -> None:
    session = _mock_session()
    r = _redline(position="preferred", alternatives=[])

    with pytest.raises(ValueError, match="No fallback alternative available"):
        await toggle_fallback(session, r, "Original clause.")


# ---------------------------------------------------------------------------
# refine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refine_calls_llm_exactly_once() -> None:
    session = _mock_session()
    r = _redline()
    canned = _canned_redline_out()

    with patch.object(ops_module, "gateway") as mock_gw:
        mock_gw.call_structured.return_value = canned
        await refine(session, r, "Original clause.", "Make it mutual.")

    assert mock_gw.call_structured.call_count == 1


@pytest.mark.asyncio
async def test_refine_uses_correct_task_name() -> None:
    session = _mock_session()
    r = _redline()
    canned = _canned_redline_out()

    with patch.object(ops_module, "gateway") as mock_gw:
        mock_gw.call_structured.return_value = canned
        await refine(session, r, "Original clause.", "Make it mutual.")

    call_args = mock_gw.call_structured.call_args
    assert call_args[0][0] == "redline_refine"


@pytest.mark.asyncio
async def test_refine_updates_replacement_text() -> None:
    session = _mock_session()
    r = _redline(replacement_text="Old proposal.")
    canned = _canned_redline_out(replacement="New refined text.")

    with patch.object(ops_module, "gateway") as mock_gw:
        mock_gw.call_structured.return_value = canned
        await refine(session, r, "Original clause.", "Shorten it.")

    assert r.replacement_text == "New refined text."


@pytest.mark.asyncio
async def test_refine_updates_tracked_changes() -> None:
    session = _mock_session()
    r = _redline(replacement_text="Old proposal.")
    canned = _canned_redline_out(replacement="Completely different text.")

    with patch.object(ops_module, "gateway") as mock_gw:
        mock_gw.call_structured.return_value = canned
        await refine(session, r, "Original clause.", "Rewrite it.")

    assert isinstance(r.tracked_changes, list)
    assert len(r.tracked_changes) > 0


@pytest.mark.asyncio
async def test_refine_updates_explanation_and_comment() -> None:
    session = _mock_session()
    r = _redline()
    canned = _canned_redline_out()

    with patch.object(ops_module, "gateway") as mock_gw:
        mock_gw.call_structured.return_value = canned
        await refine(session, r, "Original.", "Adjust.")

    assert r.explanation == "Refined explanation."
    assert r.counterparty_comment == "Refined comment."


@pytest.mark.asyncio
async def test_refine_calls_flush() -> None:
    session = _mock_session()
    r = _redline()
    canned = _canned_redline_out()

    with patch.object(ops_module, "gateway") as mock_gw:
        mock_gw.call_structured.return_value = canned
        await refine(session, r, "Original.", "Change something.")

    session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# record_decision — accepted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_decision_accepted_sets_status() -> None:
    session = _mock_session()
    session.add = MagicMock()
    r = _redline(status="proposed")

    redline_out, _ = await record_decision(
        session, r, uuid.uuid4(), "indemnification", "accepted", None
    )

    assert redline_out.status == "accepted"


@pytest.mark.asyncio
async def test_record_decision_accepted_creates_decision_event() -> None:
    session = _mock_session()
    session.add = MagicMock()
    r = _redline(status="proposed")

    _, event = await record_decision(
        session, r, uuid.uuid4(), "indemnification", "accepted", "Final accepted text."
    )

    assert isinstance(event, DecisionEvent)
    assert event.outcome == "accepted"
    assert event.final_text == "Final accepted text."


# ---------------------------------------------------------------------------
# record_decision — rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_decision_rejected_sets_status() -> None:
    session = _mock_session()
    session.add = MagicMock()
    r = _redline(status="proposed")

    redline_out, _ = await record_decision(
        session, r, uuid.uuid4(), "termination", "rejected", None
    )

    assert redline_out.status == "rejected"


@pytest.mark.asyncio
async def test_record_decision_rejected_event_outcome() -> None:
    session = _mock_session()
    session.add = MagicMock()
    r = _redline(status="proposed")

    _, event = await record_decision(
        session, r, uuid.uuid4(), "termination", "rejected", None
    )

    assert event.outcome == "rejected"
