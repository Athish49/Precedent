"""Unit tests for T-050 / task 4.6 — toggle_fallback, refine, record_decision."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm.schemas.redline import AlternativeProposal, RedlineOut
from app.db.models.exception import PlaybookException
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
    position_id: uuid.UUID | None = None,
) -> Redline:
    if alternatives is None:
        # Task 4.6: alternatives always carry a "rung" (and, when generated
        # from a real playbook position, a "position_id") so toggle_fallback
        # can step through them in order and write "fallback_<rung>" —
        # reconcile_alternatives stamps these at generation time.
        alternatives = [
            {"label": "Option A", "text": "Fallback clause text.", "position_id": None, "rung": 1},
            {"label": "Option B", "text": "Another alternative.", "position_id": None, "rung": 2},
        ]
    r = Redline(
        contract_id=uuid.uuid4(),
        position_id=position_id,
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
# toggle_fallback — preferred → fallback_1 (task 4.6 item 3: rung-stepping,
# never the bare literal "fallback" the widened CHECK constraint rejects)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_fallback_preferred_to_fallback_swaps_text() -> None:
    session = _mock_session()
    r = _redline(position="preferred", replacement_text="Preferred text.")

    original_fallback_text = r.alternatives[0]["text"]
    await toggle_fallback(session, r, "Original clause.")

    assert r.replacement_text == original_fallback_text


@pytest.mark.asyncio
async def test_toggle_fallback_preferred_to_fallback_sets_fallback_1() -> None:
    """The exact bug task 1.3's agent flagged: position must become
    'fallback_1', not the bare literal 'fallback' (which the widened
    ck_redline_position check from migration 012 rejects)."""
    session = _mock_session()
    r = _redline(position="preferred")
    await toggle_fallback(session, r, "Original clause.")
    assert r.position == "fallback_1"


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


@pytest.mark.asyncio
async def test_toggle_fallback_sets_position_id_from_alternative() -> None:
    """toggling moves to the alternative's own position_id, not the vacated one."""
    session = _mock_session()
    next_position_id = uuid.uuid4()
    r = _redline(
        position="preferred",
        position_id=uuid.uuid4(),
        alternatives=[
            {"label": "Fallback 1", "text": "Fallback text.", "position_id": str(next_position_id), "rung": 1},
        ],
    )
    await toggle_fallback(session, r, "Original clause.")
    assert r.position_id == next_position_id


# ---------------------------------------------------------------------------
# toggle_fallback — steps one rung at a time; twice reaches fallback_2
# (task 4.6 "Done when": toggling twice reaches fallback_2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_fallback_twice_reaches_fallback_2() -> None:
    session = _mock_session()
    r = _redline(position="preferred", replacement_text="Preferred text.")

    await toggle_fallback(session, r, "Original.")
    assert r.position == "fallback_1"

    await toggle_fallback(session, r, "Original.")
    assert r.position == "fallback_2"


@pytest.mark.asyncio
async def test_toggle_fallback_twice_moves_to_second_alternative_text() -> None:
    session = _mock_session()
    second_alt_text = "Another alternative."
    r = _redline(position="preferred")

    await toggle_fallback(session, r, "Original.")
    await toggle_fallback(session, r, "Original.")

    assert r.replacement_text == second_alt_text


@pytest.mark.asyncio
async def test_toggle_fallback_cycles_back_to_preferred() -> None:
    """With exactly one alternative, repeated toggles degenerate to the old
    reversible two-state swap: preferred -> fallback_1 -> preferred -> ..."""
    session = _mock_session()
    r = _redline(
        position="preferred",
        replacement_text="Preferred text.",
        alternatives=[
            {"label": "Fallback 1", "text": "Fallback text.", "position_id": None, "rung": 1},
        ],
    )
    original_preferred = r.replacement_text

    await toggle_fallback(session, r, "Original.")
    assert r.position == "fallback_1"

    await toggle_fallback(session, r, "Original.")
    assert r.position == "preferred"
    assert r.replacement_text == original_preferred


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
# refine keeps the ladder intact (audit: refine used to store raw model
# alternatives with position_id/rung = None, so a later toggle wrote a
# mislabeled "preferred" over fallback text)
# ---------------------------------------------------------------------------


def _rule_position(rung: int, language: str, label: str) -> MagicMock:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    pos = MagicMock()
    pos.id = uuid.uuid4()
    pos.rule_id = uuid.uuid4()
    pos.kind = "fallback"
    pos.rung = rung
    pos.label = label
    pos.language = language
    pos.summary = None
    pos.zone = "yellow"
    pos.approver_role_id = None
    pos.conditions = None
    pos.give_get = None
    pos.internal_note = None
    pos.created_at = now
    pos.updated_at = now
    return pos


def _laddered_redline() -> tuple[Redline, MagicMock, MagicMock, AsyncMock]:
    """A preferred-rung redline with two position-backed fallback rungs, as
    persist.py stores it, plus a get_rule_position mock resolving them."""
    fb1 = _rule_position(1, "Canonical fallback 1.", "Fallback 1")
    fb2 = _rule_position(2, "Canonical fallback 2.", "Fallback 2")
    r = _redline(
        position="preferred",
        position_id=uuid.uuid4(),
        replacement_text="Preferred text.",
        alternatives=[
            {"label": "Fallback 1", "text": "FB1 text.", "position_id": str(fb1.id), "rung": 1},
            {"label": "Fallback 2", "text": "FB2 text.", "position_id": str(fb2.id), "rung": 2},
        ],
    )
    by_id = {fb1.id: fb1, fb2.id: fb2}
    lookup = AsyncMock(side_effect=lambda _s, pid: by_id.get(pid))
    return r, fb1, fb2, lookup


@pytest.mark.asyncio
async def test_refine_preserves_position_id_and_rung_on_alternatives() -> None:
    session = _mock_session()
    r, fb1, fb2, lookup = _laddered_redline()
    original_position_id = r.position_id

    with (
        patch.object(ops_module, "gateway") as mock_gw,
        patch.object(ops_module.playbook_repo, "get_rule_position", new=lookup),
    ):
        mock_gw.call_structured.return_value = _canned_redline_out()
        await refine(session, r, "Original.", "Tighten it.")

    assert [a["rung"] for a in r.alternatives] == [1, 2]
    assert [a["position_id"] for a in r.alternatives] == [str(fb1.id), str(fb2.id)]
    # Model wording survives.
    assert [a["text"] for a in r.alternatives] == ["Alt A text.", "Alt B text."]
    # Refined text stays on the current rung.
    assert r.position == "preferred"
    assert r.position_id == original_position_id


@pytest.mark.asyncio
async def test_refine_then_toggle_reaches_fallback_1_not_mislabeled_preferred() -> None:
    """The exact audit scenario: refine, then toggle. Before the fix the
    toggle wrote position='preferred' / position_id=None over fallback text."""
    session = _mock_session()
    r, fb1, _fb2, lookup = _laddered_redline()

    with (
        patch.object(ops_module, "gateway") as mock_gw,
        patch.object(ops_module.playbook_repo, "get_rule_position", new=lookup),
    ):
        mock_gw.call_structured.return_value = _canned_redline_out()
        await refine(session, r, "Original.", "Tighten it.")

    await toggle_fallback(session, r, "Original.")

    assert r.position == "fallback_1"
    assert r.position_id == fb1.id
    assert r.replacement_text == "Alt A text."


@pytest.mark.asyncio
async def test_refine_with_short_model_response_keeps_canonical_rung_text() -> None:
    session = _mock_session()
    r, _fb1, fb2, lookup = _laddered_redline()
    thin = RedlineOut(
        replacement_text="Refined.",
        alternatives=[AlternativeProposal(label="Only one", text="Only alt.")],
        explanation="x",
        counterparty_comment="y",
    )

    with (
        patch.object(ops_module, "gateway") as mock_gw,
        patch.object(ops_module.playbook_repo, "get_rule_position", new=lookup),
    ):
        mock_gw.call_structured.return_value = thin
        await refine(session, r, "Original.", "Tighten it.")

    assert len(r.alternatives) == 2
    assert r.alternatives[1]["position_id"] == str(fb2.id)
    assert r.alternatives[1]["text"] == "Canonical fallback 2."


@pytest.mark.asyncio
async def test_toggle_refine_toggle_reaches_fallback_2() -> None:
    """Refining mid-ladder (queue rotated to [fallback_2, preferred]) keeps
    the queue's order and slots: the next toggle reaches fallback_2, and the
    one after returns to a correctly-labelled preferred rung."""
    session = _mock_session()
    r, fb1, fb2, lookup = _laddered_redline()
    preferred_id = r.position_id

    await toggle_fallback(session, r, "Original.")
    assert r.position == "fallback_1"

    with (
        patch.object(ops_module, "gateway") as mock_gw,
        patch.object(ops_module.playbook_repo, "get_rule_position", new=lookup),
    ):
        mock_gw.call_structured.return_value = _canned_redline_out(replacement="Refined FB1.")
        await refine(session, r, "Original.", "Tighten it.")

    assert r.position == "fallback_1"
    assert r.position_id == fb1.id
    assert [a["rung"] for a in r.alternatives] == [2, 0]

    await toggle_fallback(session, r, "Original.")
    assert r.position == "fallback_2"
    assert r.position_id == fb2.id

    await toggle_fallback(session, r, "Original.")
    assert r.position == "preferred"
    assert r.position_id == preferred_id


@pytest.mark.asyncio
async def test_refine_free_form_path_stamps_sequential_rungs() -> None:
    """No position-backed alternatives (no rule matched): no DB lookups, and
    the reconciled alternatives get rungs 1..n so toggling still works."""
    session = _mock_session()
    r = _redline(position="preferred")
    lookup = AsyncMock()

    with (
        patch.object(ops_module, "gateway") as mock_gw,
        patch.object(ops_module.playbook_repo, "get_rule_position", new=lookup),
    ):
        mock_gw.call_structured.return_value = _canned_redline_out()
        await refine(session, r, "Original.", "Tighten it.")

    lookup.assert_not_awaited()
    assert [a["rung"] for a in r.alternatives] == [1, 2]
    assert all(a["position_id"] is None for a in r.alternatives)

    await toggle_fallback(session, r, "Original.")
    assert r.position == "fallback_1"


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


@pytest.mark.asyncio
async def test_record_decision_accepts_none_counterparty() -> None:
    """Task 4.6 item 6: counterparty_id may be None (unknown counterparty) —
    no zero/nil UUID placeholder."""
    session = _mock_session()
    session.add = MagicMock()
    r = _redline(status="proposed")

    _, event = await record_decision(session, r, None, "indemnification", "accepted", None)

    assert event.counterparty_id is None


# ---------------------------------------------------------------------------
# record_decision — rule/position provenance on the DecisionEvent
# (task 4.6 item 4: rule_id, rule_key, position_id, playbook_version_id)
# ---------------------------------------------------------------------------


def _mock_rule_position(
    rule_id: uuid.UUID,
    position_id: uuid.UUID,
    zone: str = "green",
    approver_role_id: uuid.UUID | None = None,
    label: str = "Fallback 1: 18-month cap",
) -> MagicMock:
    position = MagicMock()
    position.id = position_id
    position.rule_id = rule_id
    position.zone = zone
    position.approver_role_id = approver_role_id
    position.label = label
    return position


def _mock_playbook_rule(
    rule_id: uuid.UUID,
    rule_key: str = "liability_cap",
    playbook_version_id: uuid.UUID | None = None,
) -> MagicMock:
    rule = MagicMock()
    rule.id = rule_id
    rule.rule_key = rule_key
    rule.playbook_version_id = playbook_version_id or uuid.uuid4()
    return rule


@pytest.mark.asyncio
async def test_record_decision_populates_rule_provenance_on_event() -> None:
    position_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    r = _redline(status="proposed", position_id=position_id)

    position = _mock_rule_position(rule_id, position_id)
    rule = _mock_playbook_rule(rule_id)

    session = _mock_session()
    with (
        patch.object(
            ops_module.playbook_repo, "get_rule_position", new=AsyncMock(return_value=position)
        ),
        patch.object(ops_module.playbook_repo, "get_rule", new=AsyncMock(return_value=rule)),
    ):
        _, event = await record_decision(
            session, r, uuid.uuid4(), "liability", "accepted", None
        )

    assert event.rule_id == rule_id
    assert event.rule_key == "liability_cap"
    assert event.position_id == position_id
    assert event.playbook_version_id == rule.playbook_version_id


# ---------------------------------------------------------------------------
# record_decision — accepting a yellow rung creates a playbook_exception
# (task 4.6 item 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accepting_yellow_rung_creates_exception() -> None:
    position_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    approver_role_id = uuid.uuid4()
    r = _redline(status="proposed", position_id=position_id, replacement_text="Agreed text.")

    position = _mock_rule_position(
        rule_id, position_id, zone="yellow", approver_role_id=approver_role_id
    )
    rule = _mock_playbook_rule(rule_id, rule_key="liability_cap")

    session = _mock_session()
    with (
        patch.object(
            ops_module.playbook_repo, "get_rule_position", new=AsyncMock(return_value=position)
        ),
        patch.object(ops_module.playbook_repo, "get_rule", new=AsyncMock(return_value=rule)),
        patch.object(
            ops_module.exception_repo, "create_exception", new=AsyncMock(side_effect=lambda s, e: e)
        ) as create_exception_mock,
    ):
        await record_decision(session, r, uuid.uuid4(), "liability", "accepted", "Agreed text.")

    create_exception_mock.assert_awaited_once()
    created: PlaybookException = create_exception_mock.call_args[0][1]
    assert isinstance(created, PlaybookException)
    assert created.status == "requested"
    assert created.rule_id == rule_id
    assert created.rule_key == "liability_cap"
    assert created.position_id == position_id
    assert created.zone == "yellow"
    assert created.approver_role_id == approver_role_id
    assert created.agreed_text == "Agreed text."


@pytest.mark.asyncio
async def test_accepting_green_rung_creates_no_exception() -> None:
    position_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    r = _redline(status="proposed", position_id=position_id)

    position = _mock_rule_position(rule_id, position_id, zone="green")
    rule = _mock_playbook_rule(rule_id)

    session = _mock_session()
    with (
        patch.object(
            ops_module.playbook_repo, "get_rule_position", new=AsyncMock(return_value=position)
        ),
        patch.object(ops_module.playbook_repo, "get_rule", new=AsyncMock(return_value=rule)),
        patch.object(
            ops_module.exception_repo, "create_exception", new=AsyncMock()
        ) as create_exception_mock,
    ):
        await record_decision(session, r, uuid.uuid4(), "liability", "accepted", None)

    create_exception_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejecting_yellow_rung_creates_no_exception() -> None:
    position_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    r = _redline(status="proposed", position_id=position_id)

    position = _mock_rule_position(rule_id, position_id, zone="yellow", approver_role_id=uuid.uuid4())
    rule = _mock_playbook_rule(rule_id)

    session = _mock_session()
    with (
        patch.object(
            ops_module.playbook_repo, "get_rule_position", new=AsyncMock(return_value=position)
        ),
        patch.object(ops_module.playbook_repo, "get_rule", new=AsyncMock(return_value=rule)),
        patch.object(
            ops_module.exception_repo, "create_exception", new=AsyncMock()
        ) as create_exception_mock,
    ):
        await record_decision(session, r, uuid.uuid4(), "liability", "rejected", None)

    create_exception_mock.assert_not_awaited()
