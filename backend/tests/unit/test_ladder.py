"""Unit tests for task 4.6's pure ladder helpers (``app.services.redline.ladder``).

``playbook_plan.md`` section 5.4: the preferred redline uses rung 0;
alternatives are the rule's fallback rungs, in order, filtered by
``conditions``; the model adapts defined terms but does not invent
positions; the counterparty comment draws on the matching objection's
``response``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.llm.schemas.redline import AlternativeProposal
from app.schemas.playbook import RuleObjectionResponse, RulePositionResponse
from app.services.redline import ladder

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _position(
    kind: str = "fallback",
    rung: int | None = 1,
    label: str = "Fallback 1",
    language: str = "Fallback language.",
    zone: str = "green",
    conditions: dict | None = None,
    position_id: uuid.UUID | None = None,
    approver_role_id: uuid.UUID | None = None,
) -> RulePositionResponse:
    return RulePositionResponse(
        id=position_id or uuid.uuid4(),
        rule_id=uuid.uuid4(),
        kind=kind,
        rung=rung,
        label=label,
        language=language,
        summary=None,
        zone=zone,
        approver_role_id=approver_role_id,
        conditions=conditions,
        give_get=None,
        internal_note=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _objection(
    response: str = "We agree to move to the fallback.",
    recommended_position_id: uuid.UUID | None = None,
    objection_id: uuid.UUID | None = None,
) -> RuleObjectionResponse:
    return RuleObjectionResponse(
        id=objection_id or uuid.uuid4(),
        rule_id=uuid.uuid4(),
        objection="The counterparty objects to the cap.",
        their_rationale=None,
        response=response,
        talking_points=None,
        recommended_position_id=recommended_position_id,
        frequency=None,
        counterparty_profile=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _rule(positions: list, objections: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(positions=positions, objections=objections or [])


# ---------------------------------------------------------------------------
# position_label / rung_from_position
# ---------------------------------------------------------------------------


def test_position_label_rung_zero_is_preferred() -> None:
    assert ladder.position_label(0) == "preferred"


def test_position_label_rung_none_is_preferred() -> None:
    assert ladder.position_label(None) == "preferred"


def test_position_label_fallback_rung() -> None:
    assert ladder.position_label(1) == "fallback_1"
    assert ladder.position_label(2) == "fallback_2"


def test_rung_from_position_round_trip() -> None:
    for rung in (0, 1, 2, 7):
        assert ladder.rung_from_position(ladder.position_label(rung)) == rung


def test_rung_from_position_rejects_bare_fallback_literal() -> None:
    """The exact bug task 1.3's agent flagged: the bare literal "fallback"
    is not a valid redline position any more (migration 012 widened the
    check to 'preferred' or 'fallback_[0-9]+')."""
    with pytest.raises(ValueError):
        ladder.rung_from_position("fallback")


# ---------------------------------------------------------------------------
# select_offered_positions
# ---------------------------------------------------------------------------


def test_select_offered_positions_no_rule_returns_empty() -> None:
    preferred, fallbacks = ladder.select_offered_positions(None, {})
    assert preferred is None
    assert fallbacks == []


def test_select_offered_positions_returns_preferred() -> None:
    pref = _position(kind="preferred", rung=0, label="Preferred")
    rule = _rule([pref])
    preferred, fallbacks = ladder.select_offered_positions(rule, {})
    assert preferred is pref
    assert fallbacks == []


def test_select_offered_positions_orders_fallbacks_by_rung() -> None:
    f2 = _position(rung=2, label="Fallback 2")
    f1 = _position(rung=1, label="Fallback 1")
    rule = _rule([f2, f1])
    _, fallbacks = ladder.select_offered_positions(rule, {})
    assert [p.rung for p in fallbacks] == [1, 2]


def test_select_offered_positions_filters_by_conditions() -> None:
    """A fallback whose conditions don't match the contract's context is dropped."""
    allowed = _position(rung=1, conditions={"deal_value_band": ["enterprise", "strategic"]})
    disallowed = _position(rung=2, conditions={"deal_value_band": ["strategic"]})
    rule = _rule([allowed, disallowed])

    _, fallbacks = ladder.select_offered_positions(rule, {"deal_value_band": "enterprise"})

    assert [p.id for p in fallbacks] == [allowed.id]


def test_select_offered_positions_empty_conditions_always_match() -> None:
    f = _position(rung=1, conditions=None)
    rule = _rule([f])
    _, fallbacks = ladder.select_offered_positions(rule, {})
    assert fallbacks == [f]


def test_select_offered_positions_ignores_acceptable_variant() -> None:
    variant = _position(kind="acceptable_variant", rung=None)
    rule = _rule([variant])
    _, fallbacks = ladder.select_offered_positions(rule, {})
    assert fallbacks == []


# ---------------------------------------------------------------------------
# rung0_language (task 5.5): the redline / drafting fallback for a rule's
# preferred language, from positions only (the legacy flat column is gone).
# ---------------------------------------------------------------------------


def test_rung0_language_no_rule_returns_none() -> None:
    assert ladder.rung0_language(None) is None


def test_rung0_language_prefers_preferred_kind() -> None:
    rule = _rule(
        [
            _position(kind="fallback", rung=1, language="Fallback."),
            _position(kind="preferred", rung=0, language="Preferred."),
        ]
    )
    assert ladder.rung0_language(rule) == "Preferred."


def test_rung0_language_falls_back_to_any_rung_zero_position() -> None:
    """A rung-0 position that is not kind 'preferred' still supplies the
    language. This is the case where select_offered_positions returns no
    preferred position and the redline callers fall back to this helper."""
    rule = _rule(
        [
            _position(kind="fallback", rung=1, language="Fallback."),
            _position(kind="acceptable_variant", rung=0, language="Rung zero."),
        ]
    )
    preferred, _ = ladder.select_offered_positions(rule, None)
    assert preferred is None
    assert ladder.rung0_language(rule) == "Rung zero."


def test_rung0_language_none_without_rung_zero_position() -> None:
    rule = _rule(
        [
            _position(kind="fallback", rung=1),
            _position(kind="acceptable_variant", rung=None),
        ]
    )
    assert ladder.rung0_language(rule) is None


# ---------------------------------------------------------------------------
# select_best_objection
# ---------------------------------------------------------------------------


def test_select_best_objection_no_rule_returns_none() -> None:
    assert ladder.select_best_objection(None, []) is None


def test_select_best_objection_no_fallbacks_returns_none() -> None:
    rule = _rule([], [_objection()])
    assert ladder.select_best_objection(rule, []) is None


def test_select_best_objection_matches_recommended_position() -> None:
    fallback = _position(rung=1)
    objection = _objection(
        response="We'll move to the 18-month cap.", recommended_position_id=fallback.id
    )
    rule = _rule([fallback], [objection])

    best = ladder.select_best_objection(rule, [fallback])

    assert best is objection


def test_select_best_objection_prefers_lowest_rung() -> None:
    f1 = _position(rung=1)
    f2 = _position(rung=2)
    obj_for_f2 = _objection(recommended_position_id=f2.id)
    obj_for_f1 = _objection(recommended_position_id=f1.id)
    rule = _rule([f1, f2], [obj_for_f2, obj_for_f1])

    best = ladder.select_best_objection(rule, [f1, f2])

    assert best is obj_for_f1


def test_select_best_objection_returns_none_when_no_objection_matches_offer() -> None:
    fallback = _position(rung=1)
    unrelated_objection = _objection(recommended_position_id=uuid.uuid4())
    rule = _rule([fallback], [unrelated_objection])

    assert ladder.select_best_objection(rule, [fallback]) is None


# ---------------------------------------------------------------------------
# reconcile_alternatives
# ---------------------------------------------------------------------------


def test_reconcile_alternatives_freeform_stamps_sequential_rungs() -> None:
    raw = [
        AlternativeProposal(label="A", text="Text A"),
        AlternativeProposal(label="B", text="Text B"),
    ]
    reconciled = ladder.reconcile_alternatives(raw, [])
    assert [a.rung for a in reconciled] == [1, 2]
    assert all(a.position_id is None for a in reconciled)


def test_reconcile_alternatives_stamps_position_id_and_rung_in_order() -> None:
    f1 = _position(rung=1, label="Fallback 1")
    f2 = _position(rung=2, label="Fallback 2")
    raw = [
        AlternativeProposal(label="Model label 1", text="Model text 1"),
        AlternativeProposal(label="Model label 2", text="Model text 2"),
    ]

    reconciled = ladder.reconcile_alternatives(raw, [f1, f2])

    assert [a.position_id for a in reconciled] == [f1.id, f2.id]
    assert [a.rung for a in reconciled] == [1, 2]
    # Wording from the model survives.
    assert reconciled[0].text == "Model text 1"
    assert reconciled[1].text == "Model text 2"


def test_reconcile_alternatives_pads_missing_with_canonical_language() -> None:
    """The model under-produced (only one alternative for two fallback rungs):
    the missing rung falls back to the playbook's own language, never dropped."""
    f1 = _position(rung=1, label="Fallback 1", language="Canonical fallback 1 text.")
    f2 = _position(rung=2, label="Fallback 2", language="Canonical fallback 2 text.")
    raw = [AlternativeProposal(label="Model label 1", text="Model text 1")]

    reconciled = ladder.reconcile_alternatives(raw, [f1, f2])

    assert len(reconciled) == 2
    assert reconciled[1].text == "Canonical fallback 2 text."
    assert reconciled[1].position_id == f2.id


def test_reconcile_alternatives_drops_extras_beyond_offered_rungs() -> None:
    """The model over-produced: with real positions on offer, anything past
    the ladder would be an invented position, so it is dropped."""
    f1 = _position(rung=1)
    raw = [
        AlternativeProposal(label="A", text="Text A"),
        AlternativeProposal(label="B", text="Text B"),
        AlternativeProposal(label="C", text="Text C"),
    ]

    reconciled = ladder.reconcile_alternatives(raw, [f1])

    assert len(reconciled) == 1
    assert reconciled[0].position_id == f1.id
