"""S2 clause↔rule-family matcher (T-041; rewritten by task 4.4).

Groups each clause with *every* resolved rule that shares its ``clause_type``
— the clause's "family" of negotiated issues (``playbook_implementation.md``
task 4.4: "the model receives the resolved rules for that clause's family").
A clause family usually carries several rule_keys (e.g.
``limitation_of_liability`` → ``cap_amount``, ``cap_carve_outs``,
``consequential_damages_exclusion``, ``data_breach_super_cap``), unlike the
one-rule-per-clause-type shape the resolution engine used before task 4.2's
rewrite. ``routing.rules_by_clause_type`` deliberately keeps that lossy
one-rule shape for callers not yet rewritten (4.3's layer1, 4.6's redlines);
this module is layer2_content's rewritten caller.

Clauses whose type has no rule are retained with rules=[] so Layer 2 can
still inspect ungoverned language on counterparty-paper contracts.
"""

from __future__ import annotations

from app.schemas.playbook import ResolvedRule, ResolveResponse
from app.services.contract_analysis.models import ClauseRuleMatch


def match_clauses_to_rules(
    clauses: list,
    resolved: ResolveResponse,
) -> list[ClauseRuleMatch]:
    """Pair each clause with every resolved rule sharing its ``clause_type``.

    Args:
        clauses:  All Clause objects for the contract, in ordinal order.
        resolved: The full ``ResolveResponse`` from ``playbook.routing.resolve``.

    Returns:
        One ClauseRuleMatch per clause, in the same order as `clauses`. Each
        match's ``rules`` list is in ``resolved.rules``' deterministic
        (rule_key-sorted) order; clauses with no matching rule get ``rules=[]``.
    """
    by_type: dict[str, list[ResolvedRule]] = {}
    for rule in resolved.rules:
        by_type.setdefault(rule.clause_type, []).append(rule)

    return [
        ClauseRuleMatch(clause=clause, rules=by_type.get(clause.clause_type, []))
        for clause in clauses
    ]


def issue_key_for_rule(rule: ResolvedRule) -> str:
    """Return the issue-only portion of a rule's identity.

    ``rule_key`` is ``{family}.{issue}`` by convention
    (``playbook_implementation.md`` section 3.1, e.g.
    ``limitation_of_liability.cap_amount``). ``clause.issue_keys`` (task 1.3's
    migration 012 column) records issues, not full rule_keys, so this strips
    the family prefix. Falls back to the rule's id when ``rule_key`` is unset
    (should not happen for seeded content, but the column is nullable).
    """
    key = rule.rule_key or str(rule.id)
    return key.rsplit(".", 1)[-1] if "." in key else key
