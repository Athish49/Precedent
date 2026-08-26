"""S2 clause↔rule matcher (T-041).

Maps each clause to its type-matching playbook rule so downstream layers
(Layer 1, Layer 2) only receive the rule(s) relevant to each clause rather
than the full playbook.

Clauses whose type has no rule are retained with rule=None so T-042 can
still inspect ungoverned language on counterparty-paper contracts.
"""

from __future__ import annotations

from app.schemas.playbook import RuleResponse
from app.services.contract_analysis.models import ClauseRuleMatch


def match_clauses_to_rules(
    clauses: list,
    resolved_rules: dict[str, RuleResponse],
) -> list[ClauseRuleMatch]:
    """Pair each clause with its resolved playbook rule.

    Args:
        clauses:        All Clause objects for the contract, in ordinal order.
        resolved_rules: Type-keyed rule map produced by playbook resolve().

    Returns:
        One ClauseRuleMatch per clause, in the same order as `clauses`.
        Clauses with no matching rule have rule=None.
    """
    return [
        ClauseRuleMatch(clause=clause, rule=resolved_rules.get(clause.clause_type))
        for clause in clauses
    ]
