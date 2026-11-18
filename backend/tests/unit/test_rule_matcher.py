"""Tests for S2 clause↔rule-family matcher (T-041; rewritten by task 4.4)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.contract_analysis.rule_matcher import (
    issue_key_for_rule,
    match_clauses_to_rules,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clause(clause_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), clause_type=clause_type)


def _rule(clause_type: str, rule_key: str | None = None) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.clause_type = clause_type
    r.rule_key = rule_key or f"{clause_type}.issue"
    return r


def _resolved(*rules) -> SimpleNamespace:
    return SimpleNamespace(rules=list(rules))


# ---------------------------------------------------------------------------
# Core pairing behaviour
# ---------------------------------------------------------------------------


def test_matched_clause_carries_its_rules() -> None:
    """A clause whose type has a resolved rule gets it in its `rules` list."""
    clause = _clause("indemnification")
    rule = _rule("indemnification")
    matches = match_clauses_to_rules([clause], _resolved(rule))
    assert len(matches) == 1
    assert matches[0].clause is clause
    assert matches[0].rules == [rule]


def test_unmatched_clause_has_empty_rules() -> None:
    """A clause with no matching rule gets rules=[]."""
    clause = _clause("payment")
    matches = match_clauses_to_rules([clause], _resolved())
    assert len(matches) == 1
    assert matches[0].clause is clause
    assert matches[0].rules == []


def test_unmatched_clause_retained_not_filtered() -> None:
    """Clauses with rules=[] are included in the output, not dropped."""
    c1 = _clause("indemnification")
    c2 = _clause("payment")          # no rule
    rule = _rule("indemnification")
    matches = match_clauses_to_rules([c1, c2], _resolved(rule))
    assert len(matches) == 2
    assert matches[1].clause is c2
    assert matches[1].rules == []


def test_ordering_preserved() -> None:
    """Output order matches the input clause order."""
    clauses = [_clause(t) for t in ("termination", "confidentiality", "payment")]
    rule_term = _rule("termination")
    rule_conf = _rule("confidentiality")
    matches = match_clauses_to_rules(clauses, _resolved(rule_term, rule_conf))
    assert [m.clause for m in matches] == clauses


def test_multiple_clauses_same_type_each_get_rules() -> None:
    """Two clauses of the same type both receive the same rule list."""
    c1 = _clause("governing_law")
    c2 = _clause("governing_law")
    rule = _rule("governing_law")
    matches = match_clauses_to_rules([c1, c2], _resolved(rule))
    assert matches[0].rules == [rule]
    assert matches[1].rules == [rule]


def test_multiple_rules_same_clause_type_all_grouped() -> None:
    """Several rule_keys sharing a clause_type (a "family") all end up on
    the matching clause — the core behaviour task 4.4 needs that the old
    one-rule-per-clause_type dict shape could not represent."""
    clause = _clause("limitation_of_liability")
    cap = _rule("limitation_of_liability", "limitation_of_liability.cap_amount")
    carveouts = _rule("limitation_of_liability", "limitation_of_liability.cap_carve_outs")
    consequential = _rule(
        "limitation_of_liability", "limitation_of_liability.consequential_damages_exclusion"
    )
    matches = match_clauses_to_rules([clause], _resolved(cap, carveouts, consequential))
    assert len(matches) == 1
    assert matches[0].rules == [cap, carveouts, consequential]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_clauses_returns_empty_list() -> None:
    rule = _rule("indemnification")
    matches = match_clauses_to_rules([], _resolved(rule))
    assert matches == []


def test_empty_rules_all_clauses_have_no_rules() -> None:
    clauses = [_clause(t) for t in ("indemnification", "termination", "payment")]
    matches = match_clauses_to_rules(clauses, _resolved())
    assert all(m.rules == [] for m in matches)
    assert len(matches) == 3


def test_extra_rules_not_in_clauses_are_ignored() -> None:
    """resolved.rules may have types not present in clauses — no error raised."""
    clause = _clause("indemnification")
    rules = [
        _rule("indemnification"),
        _rule("governing_law"),
        _rule("termination"),
    ]
    matches = match_clauses_to_rules([clause], _resolved(*rules))
    assert len(matches) == 1
    assert matches[0].rules == [rules[0]]


def test_mixed_matched_and_unmatched() -> None:
    """Mixed input: some clauses match, some don't."""
    c_indem = _clause("indemnification")
    c_pay = _clause("payment")
    c_term = _clause("termination")
    rule_indem = _rule("indemnification")
    rule_term = _rule("termination")
    matches = match_clauses_to_rules(
        [c_indem, c_pay, c_term], _resolved(rule_indem, rule_term)
    )
    assert matches[0].rules == [rule_indem]
    assert matches[1].rules == []       # payment has no rule
    assert matches[2].rules == [rule_term]


# ---------------------------------------------------------------------------
# issue_key_for_rule
# ---------------------------------------------------------------------------


def test_issue_key_for_rule_strips_family_prefix() -> None:
    rule = _rule("limitation_of_liability", "limitation_of_liability.cap_amount")
    assert issue_key_for_rule(rule) == "cap_amount"


def test_issue_key_for_rule_no_dot_returns_whole_key() -> None:
    rule = _rule("governing_law", "choice_of_law")
    assert issue_key_for_rule(rule) == "choice_of_law"


def test_issue_key_for_rule_falls_back_to_id_when_rule_key_none() -> None:
    rule = _rule("payment")
    rule.rule_key = None
    assert issue_key_for_rule(rule) == str(rule.id)
