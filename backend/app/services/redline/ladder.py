"""Pure helpers for walking a resolved rule's position ladder.

Task 4.6 (``playbook_implementation.md``); semantics from
``playbook_plan.md`` section 5.4 ("Redlines and negotiation"): the preferred
redline uses rung 0; alternatives are the rule's fallback rungs, in order,
filtered by ``conditions``; the model adapts defined terms but does not
invent positions; the counterparty comment draws on the matching
objection's ``response``.

Kept separate from ``llm_call.py``/``persist.py``/``operations.py`` so each
piece (which rungs are offered, how the model's output is reconciled
against them, which objection is the best match) is unit-testable on its
own, without a mocked LLM gateway or DB session.
"""

from __future__ import annotations

from app.core.llm.schemas.redline import AlternativeProposal
from app.schemas.playbook import ResolvedRule, RuleObjectionResponse, RulePositionResponse
from app.services.playbook.routing import matches

PREFERRED_POSITION = "preferred"
_FALLBACK_PREFIX = "fallback_"


def position_label(rung: int | None) -> str:
    """The ``redline.position`` string for a rung: 0/None -> 'preferred', n -> 'fallback_n'.

    Matches the widened ``ck_redline_position`` check (migration 012):
    ``position = 'preferred' OR position ~ '^fallback_[0-9]+$'``.
    """
    if rung is None or rung == 0:
        return PREFERRED_POSITION
    return f"{_FALLBACK_PREFIX}{rung}"


def rung_from_position(position: str) -> int:
    """Inverse of ``position_label``. Raises ``ValueError`` for anything else,
    including the old bare literal ``"fallback"`` — that string is exactly
    the bug task 4.6 fixes; nothing should write it again."""
    if position == PREFERRED_POSITION:
        return 0
    if position.startswith(_FALLBACK_PREFIX):
        suffix = position[len(_FALLBACK_PREFIX) :]
        if suffix.isdigit():
            return int(suffix)
    raise ValueError(f"Not a recognised redline position: {position!r}")


def select_offered_positions(
    rule: ResolvedRule | None,
    context: dict | None,
) -> tuple[RulePositionResponse | None, list[RulePositionResponse]]:
    """Return ``(preferred_position, fallback_positions)`` for *rule*.

    The preferred position is the rung-0 (``kind == "preferred"``) row.
    Fallback positions are every ``kind == "fallback"`` row whose
    ``conditions`` match *context* (``matches()`` — same semantics task 4.2
    uses for a rule's own ``applies_when``: playbook_plan.md section 3.11),
    sorted by ``rung`` ascending ("alternatives ... in rung order", task 4.6
    item 1). ``acceptable_variant`` rows and any fallback with no ``rung``
    are never returned here — they are not part of the concession ladder a
    redline steps through.
    """
    if rule is None:
        return None, []

    preferred = next((p for p in rule.positions if p.kind == "preferred"), None)
    fallbacks = [
        p
        for p in rule.positions
        if p.kind == "fallback" and p.rung is not None and matches(p.conditions, context)
    ]
    fallbacks.sort(key=lambda p: p.rung)  # type: ignore[arg-type,return-value]
    return preferred, fallbacks


def rung0_language(rule: ResolvedRule | None) -> str | None:
    """The rule's preferred-position language, from its ``rule_position`` rows.

    Returns the ``kind == "preferred"`` position's language if there is one,
    otherwise the language of any position at ``rung == 0``, otherwise
    ``None``. That includes a missing rule. This is the only source of
    "playbook preferred language" since migration 015 dropped the legacy
    flat column. It is shared by redline generation (review pipeline and
    redlines API) and drafting.
    """
    if rule is None:
        return None
    for position in rule.positions:
        if position.kind == PREFERRED_POSITION:
            return position.language
    for position in rule.positions:
        if position.rung == 0:
            return position.language
    return None


def select_best_objection(
    rule: ResolvedRule | None,
    fallback_positions: list[RulePositionResponse],
) -> RuleObjectionResponse | None:
    """Pick the objection to draw the counterparty comment from (task 4.6 item 2).

    ``rule_objection.recommended_position_id`` means "where to move if the
    objection holds" (``playbook_plan.md`` section 3.8). So the best match
    for *this* redline's comment is the objection recommending the
    lowest-rung fallback we are actually prepared to offer — i.e. the
    concession this objection, if raised, would lead to next. Ties (more
    than one objection recommending the same rung) are broken by ``id`` for
    determinism. Returns ``None`` when no objection recommends any rung on
    offer, or when there is no rule or no offered fallback at all.
    """
    if rule is None or not fallback_positions:
        return None

    rung_by_position_id = {p.id: p.rung for p in fallback_positions}
    candidates = [
        o
        for o in rule.objections
        if o.recommended_position_id is not None
        and o.recommended_position_id in rung_by_position_id
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda o: (rung_by_position_id[o.recommended_position_id], str(o.id)))
    return candidates[0]


def reconcile_alternatives(
    raw: list[AlternativeProposal],
    fallback_positions: list[RulePositionResponse],
) -> list[AlternativeProposal]:
    """Reconcile the model's alternatives against the actual fallback ladder.

    Task 4.6 item 1: "the model may adapt wording but must not invent a new
    position; each alternative carries its position_id."

    - When *fallback_positions* is non-empty, the result has exactly
      ``len(fallback_positions)`` entries, one per offered rung in rung
      order, zipped by index with *raw* for wording. Each entry's
      ``position_id``/``rung`` are overwritten from the canonical
      position — never trusted from the model. If the model returned fewer
      entries than there are fallback positions, the missing ones fall back
      to that position's own canonical ``language``/``label`` instead of
      being silently dropped, so a thin model response never loses a rung.
      Extra model-produced entries beyond the fallback count are dropped:
      with real positions on offer, anything past the ladder would be an
      invented position.
    - When *fallback_positions* is empty (no rule matched, or no fallback
      rung's ``conditions`` matched this context — the free-form path),
      *raw* is returned with each entry stamped with a sequential
      ``rung`` (1, 2, ...) and ``position_id=None``, so the toggle
      operation (item 3) still has a rung number to step through.
    """
    if not fallback_positions:
        return [
            AlternativeProposal(label=alt.label, text=alt.text, position_id=None, rung=index + 1)
            for index, alt in enumerate(raw)
        ]

    ordered = sorted(fallback_positions, key=lambda p: p.rung)  # type: ignore[arg-type,return-value]
    reconciled: list[AlternativeProposal] = []
    for index, position in enumerate(ordered):
        if index < len(raw):
            text = raw[index].text
            label = raw[index].label
        else:
            text = position.language
            label = position.label
        reconciled.append(
            AlternativeProposal(label=label, text=text, position_id=position.id, rung=position.rung)
        )
    return reconciled
