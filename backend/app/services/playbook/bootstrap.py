"""S6 Playbook bootstrap — batch LLM job (T-038).

Loads a corpus of contract clauses, groups them by clause_type, and uses the
Anthropic Message Batches API to extract preferred language + acceptable
variations for each type.  Creates PlaybookRule rows for clause types not
already present in the target playbook.

Seeding policy (SC-3):
- Seeds `preferred_language` and `acceptable_variations` ONLY.
- `prohibited_terms` is NOT mined from executed contracts; it comes from
  the template seed managed by humans post-bootstrap.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import gateway
from app.core.llm.schemas.playbook import PlaybookBootstrapOut
from app.db.repositories import clause_repo, playbook_repo
from app.api.errors import AppError

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_PATH = (
    Path(__file__).parent.parent.parent / "core" / "llm" / "prompts" / "playbook_bootstrap.md"
)
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

# Max clauses sampled per type and max chars per clause sent to the LLM.
_MAX_SAMPLES = 5
_MAX_CHARS = 1_000


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_bootstrap(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    contract_ids: list[uuid.UUID],
) -> int:
    """Seed *playbook_id* with rules extracted from *contract_ids*.

    Skips clause types that already have a rule in the playbook (idempotent).

    Returns:
        Number of new PlaybookRule rows created.
    """
    pb = await playbook_repo.get_playbook(session, playbook_id)
    if pb is None:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")

    if not contract_ids:
        return 0

    # Load all clauses for the corpus in one query.
    clauses = await clause_repo.get_clauses_for_contracts(session, contract_ids)
    if not clauses:
        return 0

    # Group by clause_type.
    by_type: dict[str, list] = {}
    for clause in clauses:
        by_type.setdefault(clause.clause_type, []).append(clause)

    # Skip types that already have a rule — protects human edits.
    existing = await playbook_repo.list_rules(session, playbook_id)
    existing_types = {r.clause_type for r in existing}
    new_types = {ct: cl for ct, cl in by_type.items() if ct not in existing_types}

    if not new_types:
        return 0

    # Build one batch item per new clause_type.
    items: list[dict] = []
    for clause_type, type_clauses in new_types.items():
        samples = type_clauses[:_MAX_SAMPLES]
        clause_texts = "\n\n---\n\n".join(c.text[:_MAX_CHARS] for c in samples)
        items.append(
            {
                "id": clause_type,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Clause type: {clause_type}\n\n"
                            f"Analyze the following {len(samples)} sample(s) "
                            f"and extract preferred language and acceptable variations.\n\n"
                            f"{clause_texts}"
                        ),
                    },
                ],
            }
        )

    # Batch call — synchronous gateway (consistent with rest of codebase).
    results: dict[str, PlaybookBootstrapOut] = gateway.call_batch(
        task="playbook.bootstrap",
        items=items,
        response_model=PlaybookBootstrapOut,
        cache_prefix="playbook_bootstrap",
    )

    # Persist rules — use the dict key (custom_id) as the authoritative
    # clause_type so the fake gateway's identical preset still creates
    # distinct rules per type.
    created = 0
    for clause_type, parsed in results.items():
        await playbook_repo.create_rule(
            session,
            playbook_id=playbook_id,
            clause_type=clause_type,
            preferred_language=parsed.preferred_language,
            acceptable_variations=parsed.acceptable_variations or None,
        )
        created += 1

    await session.commit()
    return created
