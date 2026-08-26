from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.core.llm.schemas.intelligence import EasyPromptOut
from app.db.repositories import clause_repo, contract_repo

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_EASY_SYSTEM = (_PROMPTS_DIR / "easy_prompt.md").read_text()


@dataclass
class EasyPromptResult:
    structured_prompt: str
    route: str  # "s3" | "s4"


async def generate_easy_prompt(
    session: AsyncSession,
    contract_id: uuid.UUID,
    user_request: str,
) -> EasyPromptResult:
    """NL → structured legal prompt with route tag. One LLM call."""
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    clauses = await clause_repo.get_clauses_for_contract(session, contract_id)
    clause_types = list(dict.fromkeys(c.clause_type for c in clauses))  # ordered, deduplicated

    user_msg = "\n".join([
        f"Contract: {contract.title} ({contract.contract_type or 'unknown type'})",
        f"Clause types present: {', '.join(clause_types)}",
        "",
        f"User request: {user_request}",
    ])
    messages = [
        {"role": "system", "content": _EASY_SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    result: EasyPromptOut = gateway.call_structured(
        "easy_prompt", messages, EasyPromptOut, cache_prefix=_EASY_SYSTEM
    )
    return EasyPromptResult(structured_prompt=result.structured_prompt, route=result.route)
