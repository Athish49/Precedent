from __future__ import annotations

import string
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import gateway
from app.services.drafting import frequency_tracker
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
    context: dict,
    instruction: str | None,
) -> str:
    user_parts = [f"Clause type: {clause_type}"]
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
# Public drafting functions
# ---------------------------------------------------------------------------


async def draft_clause(
    session: AsyncSession,
    clause_type: str,
    *,
    context: dict | None = None,
    instruction: str | None = None,
    preferred_language: str | None = None,
) -> DraftResult:
    """Cascade: playbook → frequency → LLM."""
    context = context or {}

    if preferred_language:
        return DraftResult(text=preferred_language, source="playbook")

    contract_type = context.get("contract_type")
    counterparty_id_str = context.get("counterparty_id")
    counterparty_id = uuid.UUID(counterparty_id_str) if counterparty_id_str else None

    freq = await frequency_tracker.most_common_clause(
        session,
        clause_type,
        contract_type=contract_type,
        counterparty_id=counterparty_id,
    )
    if freq is not None:
        return DraftResult(text=freq.text, source="frequency")

    text = _call_clause_llm(clause_type, context, instruction)
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
