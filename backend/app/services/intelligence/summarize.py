from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.db.repositories import analysis_repo, contract_repo, redline_repo

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_SUMMARIZE_SYSTEM = (_PROMPTS_DIR / "summarize.md").read_text()
_SUMMARIZE_REDLINES_SYSTEM = (_PROMPTS_DIR / "summarize_redlines.md").read_text()


@dataclass
class SummaryResult:
    summary: str


@dataclass
class RedlineSummaryResult:
    summary: str
    clause_type: str


async def summarize_contract(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> SummaryResult:
    """Risk-aware summary grounded on S1 metadata + S2 flags. One LLM call."""
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found.")

    flags = await analysis_repo.get_flags_for_contract(session, contract_id)
    risk = await analysis_repo.get_risk_score_for_contract(session, contract_id)

    if risk is not None:
        risk_section = f"Score: {risk.score:.2f} | Max severity: {risk.max_clause_severity}"
    else:
        risk_section = "No risk score computed yet"

    flag_lines = "\n".join(
        f"- [{f.severity.upper()}] {f.flag_type}: {f.detail}" for f in flags
    )

    user_content = (
        f"## Contract metadata\n"
        f"Title: {contract.title}\n"
        f"Type: {contract.contract_type or 'unknown'}\n"
        f"Paper origin: {contract.paper_origin}\n"
        f"\n## Risk score\n"
        f"{risk_section}\n"
        f"\n## Flags ({len(flags)} total)\n"
        f"{flag_lines}"
    )

    messages = [
        {"role": "system", "content": _SUMMARIZE_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    text = gateway.call_text("summarize_contract", messages, cache_prefix=_SUMMARIZE_SYSTEM)
    return SummaryResult(summary=text)


async def summarize_redlines(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> RedlineSummaryResult:
    """Redline-thread summary. One LLM call."""
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found.")

    redlines = await redline_repo.get_redlines_for_contract(session, contract_id)
    if not redlines:
        return RedlineSummaryResult(
            summary="No redlines generated for this contract.", clause_type=""
        )

    redline_blocks = "\n".join(
        f"### Redline {i + 1} — {r.clause_type} ({r.status})\n"
        f"Position: {r.position}\n"
        f"Replacement: {r.replacement_text}\n"
        f"Explanation: {r.explanation}\n"
        f"Counterparty comment: {r.counterparty_comment}\n"
        for i, r in enumerate(redlines)
    )

    user_content = (
        f"## Redline thread for contract: {contract.title}\n"
        f"{redline_blocks}"
    )

    messages = [
        {"role": "system", "content": _SUMMARIZE_REDLINES_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    text = gateway.call_text(
        "summarize_redlines", messages, cache_prefix=_SUMMARIZE_REDLINES_SYSTEM
    )
    return RedlineSummaryResult(summary=text, clause_type=redlines[0].clause_type)
