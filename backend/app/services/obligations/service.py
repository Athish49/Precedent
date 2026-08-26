from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.core.llm.schemas.obligation import ObligationOut
from app.db.models.obligation import Obligation
from app.db.repositories import clause_repo, contract_repo, obligation_repo

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_SYSTEM = (_PROMPTS_DIR / "obligation_extract.md").read_text()


async def extract(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> list[Obligation]:
    """Extract obligations from a contract using LLM grounded on S1 metadata.

    Persists Obligation rows with char citations. One LLM call.
    Re-entrant: deletes prior obligations before persisting new ones.
    """
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    clauses = await clause_repo.get_clauses_for_contract(session, contract_id)

    clause_blocks = "\n\n".join(
        f"[Clause {c.ordinal} — {c.clause_type}]\n{c.text}"
        for c in clauses
    )
    user_msg = "\n".join([
        f"Contract: {contract.title}",
        f"Type: {contract.contract_type or 'unknown'}",
        f"Paper origin: {contract.paper_origin}",
        "",
        clause_blocks,
    ])
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    result: ObligationOut = gateway.call_structured(
        "obligation_extract", messages, ObligationOut, cache_prefix=_SYSTEM
    )

    ordinal_map = {c.ordinal: c for c in clauses}

    # Delete prior obligations (re-entrant)
    await session.execute(
        delete(Obligation).where(Obligation.contract_id == contract_id)
    )

    persisted: list[Obligation] = []
    for item in result.obligations:
        clause = ordinal_map.get(item.clause_ordinal)
        ob = Obligation(
            contract_id=contract_id,
            commitment=item.commitment,
            owner=item.owner,
            deadline=_parse_date(item.deadline),
            deliverable=item.deliverable,
            char_start=clause.char_start if clause else None,
            char_end=clause.char_end if clause else None,
            status="open",
        )
        ob = await obligation_repo.create_obligation(session, ob)
        persisted.append(ob)

    await session.commit()
    return persisted


async def get_obligations(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> list[Obligation]:
    """Return persisted obligations for a contract."""
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")
    return await obligation_repo.get_obligations_for_contract(session, contract_id)


def _parse_date(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None
