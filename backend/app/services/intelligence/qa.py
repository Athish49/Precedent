from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.core.llm.schemas.qa import QAAnswerOut
from app.db.models.qa_cache import QACache
from app.db.repositories import clause_repo, contract_repo, qa_cache_repo

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_QA_SYSTEM = (_PROMPTS_DIR / "qa_answer.md").read_text()


@dataclass
class QAResult:
    answer: str
    citations: list[dict]
    cached: bool


async def answer_question(
    session: AsyncSession,
    contract_id: uuid.UUID,
    question: str,
) -> QAResult:
    cached = await qa_cache_repo.get_cached_answer(session, contract_id, question)
    if cached is not None:
        return QAResult(answer=cached.answer, citations=cached.citations or [], cached=True)

    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    clauses = await clause_repo.get_clauses_for_contract(session, contract_id)

    clause_blocks = "\n\n".join(
        f"[Clause {c.ordinal} — {c.clause_type}]\n{c.text}"
        for c in clauses
    )
    user_msg = f"Question: {question}\n\n{clause_blocks}"

    messages = [
        {"role": "system", "content": _QA_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    result: QAAnswerOut = gateway.call_structured(
        "qa_answer", messages, QAAnswerOut, cache_prefix=_QA_SYSTEM
    )

    ordinal_map = {c.ordinal: c for c in clauses}
    citations = []
    for cit in result.citations:
        clause = ordinal_map.get(cit.clause_ordinal)
        if clause is not None:
            citations.append({
                "clause_id": str(clause.id),
                "char_start": clause.char_start,
                "char_end": clause.char_end,
                "excerpt": cit.excerpt,
            })

    entry = QACache(
        contract_id=contract_id,
        question=question,
        answer=result.answer,
        citations=citations,
    )
    await qa_cache_repo.create_cached_answer(session, entry)
    await session.commit()

    return QAResult(answer=result.answer, citations=citations, cached=False)
