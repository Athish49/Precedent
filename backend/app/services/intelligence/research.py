from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.db.repositories import contract_repo

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_RESEARCH_SYSTEM = (_PROMPTS_DIR / "research_synthesize.md").read_text()


@dataclass
class ResearchResult:
    answer: str
    sources: list[dict]  # passthrough of input search_results


async def synthesize_research(
    session: AsyncSession,
    contract_id: uuid.UUID,
    question: str,
    search_results: list[dict],  # [{"title": str, "snippet": str, "url": str}]
) -> ResearchResult:
    """Synthesize search results into a cited answer grounded in contract context. One LLM call."""
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    results_text = "\n\n".join(
        f"[{i+1}] {r.get('title', '')}\n{r.get('snippet', '')}"
        for i, r in enumerate(search_results)
    )
    user_msg = "\n".join([
        f"Contract: {contract.title} ({contract.contract_type or 'unknown'})",
        f"Question: {question}",
        "",
        "Search results:",
        results_text or "(no search results provided)",
    ])
    messages = [
        {"role": "system", "content": _RESEARCH_SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    answer = gateway.call_text("research_synthesize", messages, cache_prefix=_RESEARCH_SYSTEM)
    return ResearchResult(answer=answer, sources=search_results)
