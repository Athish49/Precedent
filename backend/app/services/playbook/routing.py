"""S6 Playbook routing — deterministic multi-playbook resolve.

`resolve(session, contract_type)` expands a contract type to applicable
practice areas, fetches matching playbooks, and merges their rules by
precedence into one type-keyed rule set.

Merge semantics:
  - Playbooks are processed highest-precedence-first; ties broken by
    practice_area alphabetically (deterministic across any DB ordering).
  - For each clause_type, the first (highest-priority) rule wins.
    Lower-precedence playbooks fill in clause_types not yet covered.
  - This is winner-takes-all per clause_type, not union — except the caller
    (S2) may iterate the full merged dict to apply per-clause checks.

Expansion (`_applicable_areas`):
  - Identity default: a contract_type maps to itself only.
  - This is the reversible minimal version; T-060 (Review Pipeline) will
    supply richer signals (upload context, multi-type tagging) when wiring
    the full pipeline.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import playbook_repo
from app.schemas.playbook import ResolveResponse, RuleResponse

# ---------------------------------------------------------------------------
# Practice-area expansion
# ---------------------------------------------------------------------------

_VALID_AREAS = frozenset({"hipaa", "gdpr", "saas_msa", "nda", "dpa"})


def _applicable_areas(contract_type: str) -> list[str]:
    """Return the ordered list of practice areas that apply for *contract_type*.

    Default: identity (contract_type is itself a practice area).
    Unknown types fall through to an empty list so the caller gets an empty
    rule set rather than a crash — caller raises 400 upstream if needed.
    """
    if contract_type in _VALID_AREAS:
        return [contract_type]
    return []


# ---------------------------------------------------------------------------
# Deterministic merge
# ---------------------------------------------------------------------------


def _merge_rules(
    playbooks_with_rules: list[tuple[str, list[RuleResponse]]],
) -> dict[str, RuleResponse]:
    """Merge rules from multiple playbooks into one clause_type-keyed dict.

    Args:
        playbooks_with_rules: list of (practice_area, rules) tuples, already
            sorted highest-precedence-first (ties: practice_area ASC).

    Returns:
        dict mapping clause_type → winning RuleResponse.
    """
    merged: dict[str, RuleResponse] = {}
    for _area, rules in playbooks_with_rules:
        for rule in rules:
            if rule.clause_type not in merged:
                merged[rule.clause_type] = rule
    return merged


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def resolve(session: AsyncSession, contract_type: str) -> ResolveResponse:
    """Resolve all applicable playbooks for *contract_type* and merge rules.

    Returns a :class:`ResolveResponse` with the merged type-keyed rule set.
    Unknown contract_type → empty rule set (no 404; callers decide on policy).
    """
    areas = _applicable_areas(contract_type)

    playbooks = await playbook_repo.list_playbooks_by_areas(session, areas)

    # Fetch rules for each playbook and pair with practice_area.
    playbooks_with_rules: list[tuple[str, list[RuleResponse]]] = []
    for pb in playbooks:
        raw_rules = await playbook_repo.list_rules(session, pb.id)
        rule_responses = [RuleResponse.model_validate(r) for r in raw_rules]
        playbooks_with_rules.append((pb.practice_area, rule_responses))

    merged = _merge_rules(playbooks_with_rules)

    applied = list(dict.fromkeys(pb.practice_area for pb in playbooks))

    return ResolveResponse(
        contract_type=contract_type,
        applied_practice_areas=applied,
        rules=merged,
    )
