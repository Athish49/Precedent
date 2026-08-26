from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import gateway
from app.workflows.version_comparison import compare_versions

_PROMPTS_DIR = Path(__file__).parent.parent / "core" / "llm" / "prompts"
_SYSTEM = (_PROMPTS_DIR / "version_semantic_summary.md").read_text()

_TASK = "version_semantic_summary"


@dataclass
class SemanticSummaryResult:
    contract_id: uuid.UUID
    v_a: uuid.UUID
    v_b: uuid.UUID
    v_a_number: int
    v_b_number: int
    summary: str
    modified_clause_types: list[str]


async def summarize_diff(
    session: AsyncSession,
    contract_id: uuid.UUID,
    v_a: uuid.UUID,
    v_b: uuid.UUID,
) -> SemanticSummaryResult:
    """LLM semantic summary of changes between two versions."""
    diff_result = await compare_versions(session, contract_id, v_a, v_b)

    modified = [cd for cd in diff_result.clause_diffs if cd.change_type == "modified"]
    modified_types = sorted({cd.clause_type for cd in modified})

    lines = [
        f"Contract versions: v{diff_result.v_a_number} → v{diff_result.v_b_number}",
        f"Total clauses: {len(diff_result.clause_diffs)}",
        f"Modified clauses: {len(modified)}",
        "",
    ]
    for cd in modified:
        lines.append(f"## {cd.heading_text or cd.clause_type} (ordinal {cd.ordinal})")
        for ch in cd.changes:
            if ch["op"] != "equal":
                snippet = ch["text"][:200]
                lines.append(f"  [{ch['op'].upper()}] {snippet!r}")
        lines.append("")

    if not modified:
        lines.append("(No clause-level modifications detected in the change set.)")

    user_content = "\n".join(lines)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]
    summary_text = gateway.call_text(_TASK, messages, cache_prefix=_SYSTEM)

    return SemanticSummaryResult(
        contract_id=contract_id,
        v_a=v_a,
        v_b=v_b,
        v_a_number=diff_result.v_a_number,
        v_b_number=diff_result.v_b_number,
        summary=summary_text,
        modified_clause_types=modified_types,
    )
