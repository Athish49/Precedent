from __future__ import annotations

import json
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import gateway
from app.schemas.playbook import ResolvedRule
from app.services.drafting import frequency_tracker
from app.services.playbook import routing as playbook_routing
from app.services.redline import ladder
from app.services.repository import vector

# ---------------------------------------------------------------------------
# Load system prompts once at import time
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"


def _load(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text()


_CLAUSE_SYSTEM = _load("drafting_clause.md")
_POLISH_SYSTEM = _load("drafting_document_polish.md")
_PRECEDENT_SYSTEM = _load("drafting_precedent.md")
_MEMO_SYSTEM = _load("drafting_memo.md")


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass
class DraftResult:
    text: str
    source: str  # "playbook" | "frequency" | "llm" | "template"


# ---------------------------------------------------------------------------
# Internal LLM helpers
# ---------------------------------------------------------------------------


def _call_clause_llm(
    clause_type: str,
    context: str | None,
    instruction: str | None,
    *,
    contract_type: str | None = None,
    party_role: str | None = None,
    paper_origin: str | None = None,
    deal_context: dict[str, Any] | None = None,
) -> str:
    user_parts = [f"Clause type: {clause_type}"]
    if contract_type:
        user_parts.append(f"Contract type: {contract_type}")
    if party_role:
        user_parts.append(f"Party role: {party_role}")
    if paper_origin:
        user_parts.append(f"Paper origin: {paper_origin}")
    if deal_context:
        user_parts.append(
            f"Deal context: {json.dumps(deal_context, sort_keys=True, default=str)}"
        )
    if context:
        user_parts.append(f"Context: {context}")
    if instruction:
        user_parts.append(f"Instruction: {instruction}")
    messages = [
        {"role": "system", "content": _CLAUSE_SYSTEM},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
    return gateway.call_text("drafting_clause", messages)


def _call_polish_llm(rendered: str) -> str:
    messages = [
        {"role": "system", "content": _POLISH_SYSTEM},
        {"role": "user", "content": f"Rendered document:\n\n{rendered}"},
    ]
    return gateway.call_text("drafting_document_polish", messages)


def _call_precedent_llm(
    clause_type: str,
    precedent_texts: list[str],
    context: dict,
) -> str:
    examples = "\n\n---\n\n".join(
        f"Example {i + 1}:\n{t}" for i, t in enumerate(precedent_texts)
    )
    user_parts = [
        f"Clause type: {clause_type}",
        f"Precedent examples:\n{examples}",
    ]
    if context:
        user_parts.append(f"Context: {context}")
    messages = [
        {"role": "system", "content": _PRECEDENT_SYSTEM},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    return gateway.call_text("drafting_precedent", messages)


def _call_memo_llm(context: dict) -> str:
    messages = [
        {"role": "system", "content": _MEMO_SYSTEM},
        {"role": "user", "content": f"Context: {context}"},
    ]
    return gateway.call_text("drafting_memo", messages)


# ---------------------------------------------------------------------------
# Template renderer
# ---------------------------------------------------------------------------


def _render_template(template: str, variables: dict) -> str:
    return string.Template(template).safe_substitute(variables)


# ---------------------------------------------------------------------------
# Playbook lookup (task 4.7; playbook_implementation.md section 4.7)
# ---------------------------------------------------------------------------


def _find_resolved_rule(
    rules: list[ResolvedRule], clause_type_or_issue: str
) -> ResolvedRule | None:
    """Find the rule matching the requested clause type *or* issue.

    ``rule_key`` is ``{family}.{issue}`` (task 4.2). A caller may pass the
    full key (``limitation_of_liability.cap_amount``), the bare issue
    (``cap_amount``), or the clause family / type (``limitation_of_liability``).
    Checked in that order, most specific first; ``resolved.rules`` is already
    sorted deterministically by ``rule_key`` (task 4.2), so the clause-type
    fallback — which can match several rules sharing a family — picks the
    same one every time via ``routing.rules_by_clause_type``.
    """
    for rule in rules:
        if rule.rule_key == clause_type_or_issue:
            return rule
    for rule in rules:
        if rule.rule_key and rule.rule_key.split(".", 1)[-1] == clause_type_or_issue:
            return rule
    by_clause_type = {
        rule.clause_type: rule for rule in sorted(rules, key=lambda r: r.rule_key or "")
    }
    return by_clause_type.get(clause_type_or_issue)


def _preferred_language(rule: ResolvedRule) -> str | None:
    """Rung-0 / ``preferred``-kind position's language, or ``None``.

    Delegates to ``ladder.rung0_language``, the shared helper redline
    generation also uses.
    """
    return ladder.rung0_language(rule)


async def _lookup_playbook_language(
    session: AsyncSession,
    clause_type: str,
    *,
    contract_type: str | None,
    party_role: str | None,
    paper_origin: str | None,
    deal_context: dict[str, Any] | None,
) -> str | None:
    """Resolve the playbook (task 4.2) and return rung-0 language for
    *clause_type*, or ``None`` when no resolved rule matches the requested
    clause type/issue or the matched rule has no preferred position.

    Resolution always runs, with the same fallbacks the review pipeline,
    redline route and contract analysis use for a contract missing these
    facts: an unknown/missing ``contract_type`` resolves as ``""`` (no
    agreement playbook matches, so the baseline playbook plus any matching
    overlays still apply — task 4.2), a missing ``party_role`` as
    ``"vendor"``, and a missing ``paper_origin`` as ``"own"``.
    ``deal_context`` is passed through as the resolution context, so overlay
    playbooks and rules with an ``applies_when`` condition apply here exactly
    as they do in review (playbook_plan.md section 5.5).
    """
    resolved = await playbook_routing.resolve(
        session,
        contract_type or "",
        party_role or "vendor",
        paper_origin or "own",
        context=deal_context or {},
    )
    rule = _find_resolved_rule(resolved.rules, clause_type)
    if rule is None:
        return None
    return _preferred_language(rule)


# ---------------------------------------------------------------------------
# Public drafting functions
# ---------------------------------------------------------------------------


DraftMode = Literal["playbook", "frequency", "llm"]


async def draft_clause(
    session: AsyncSession,
    clause_type: str,
    *,
    context: str | None = None,
    instruction: str | None = None,
    preferred_language: str | None = None,
    contract_type: str | None = None,
    party_role: str | None = None,
    paper_origin: str | None = None,
    deal_context: dict[str, Any] | None = None,
    mode: DraftMode | None = None,
) -> DraftResult:
    """Cascade: caller override → playbook → frequency → LLM.

    ``context`` is free-text description, passed to the LLM prompt only.
    ``deal_context`` is the structured resolution context (e.g.
    ``{"regimes": ["hipaa"], "deal_value_band": "mid"}``) handed to
    ``routing.resolve()`` so overlay playbooks and ``applies_when`` rule
    conditions apply; it is also rendered into the LLM prompt so a
    fall-through draft still sees the deal facts.

    ``mode`` picks where the cascade starts:

    * ``None`` / ``"playbook"`` — full cascade (override → playbook →
      frequency → LLM).
    * ``"frequency"`` — skip the playbook step (override and resolution);
      frequency → LLM.
    * ``"llm"`` — skip straight to the LLM (used by the frontend's
      NL-rewrite action).
    """
    use_playbook = mode in (None, "playbook")
    use_frequency = mode in (None, "playbook", "frequency")

    if use_playbook:
        if preferred_language:
            return DraftResult(text=preferred_language, source="playbook")

        playbook_text = await _lookup_playbook_language(
            session,
            clause_type,
            contract_type=contract_type,
            party_role=party_role,
            paper_origin=paper_origin,
            deal_context=deal_context,
        )
        if playbook_text is not None:
            return DraftResult(text=playbook_text, source="playbook")

    if use_frequency:
        freq = await frequency_tracker.most_common_clause(
            session,
            clause_type,
            contract_type=contract_type,
            counterparty_id=None,
        )
        if freq is not None:
            return DraftResult(text=freq.text, source="frequency")

    text = _call_clause_llm(
        clause_type,
        context,
        instruction,
        contract_type=contract_type,
        party_role=party_role,
        paper_origin=paper_origin,
        deal_context=deal_context,
    )
    return DraftResult(text=text, source="llm")


async def draft_document(
    session: AsyncSession,  # noqa: ARG001 — kept for interface consistency
    template: str,
    variables: dict,
    *,
    polish: bool = False,
) -> DraftResult:
    """Render $variable template; optional LLM polish."""
    rendered = _render_template(template, variables)
    if not polish:
        return DraftResult(text=rendered, source="template")

    polished = _call_polish_llm(rendered)
    return DraftResult(text=polished, source="llm")


async def draft_precedent(
    session: AsyncSession,
    clause_type: str,
    *,
    context: dict | None = None,
) -> DraftResult:
    """Vector search → style-matched LLM."""
    context = context or {}
    query = context.get("query") or clause_type
    results = await vector.precedent_search(query, session, clause_type=clause_type, limit=3)
    precedent_texts = [r.text for r in results]
    text = _call_precedent_llm(clause_type, precedent_texts, context)
    return DraftResult(text=text, source="llm")


async def draft_memo(
    context: dict,
) -> DraftResult:
    """LLM memo/action-letter drafting."""
    text = _call_memo_llm(context)
    return DraftResult(text=text, source="llm")
