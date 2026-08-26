"""Tests for S2 clause↔rule matcher (T-041)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.contract_analysis.rule_matcher import match_clauses_to_rules


def _clause(clause_type: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), clause_type=clause_type)


def _rule(clause_type: str) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.clause_type = clause_type
    return r


# ---------------------------------------------------------------------------
# Core pairing behaviour
# ---------------------------------------------------------------------------


def test_matched_clause_carries_its_rule() -> None:
    """A clause whose type exists in resolved_rules gets that rule."""
    clause = _clause("indemnification")
    rule = _rule("indemnification")
    matches = match_clauses_to_rules([clause], {"indemnification": rule})
    assert len(matches) == 1
    assert matches[0].clause is clause
    assert matches[0].rule is rule


def test_unmatched_clause_has_rule_none() -> None:
    """A clause with no matching rule in resolved_rules gets rule=None."""
    clause = _clause("payment")
    matches = match_clauses_to_rules([clause], {})
    assert len(matches) == 1
    assert matches[0].clause is clause
    assert matches[0].rule is None


def test_unmatched_clause_retained_not_filtered() -> None:
    """Clauses with rule=None are included in the output, not dropped."""
    c1 = _clause("indemnification")
    c2 = _clause("payment")          # no rule
    rule = _rule("indemnification")
    matches = match_clauses_to_rules([c1, c2], {"indemnification": rule})
    assert len(matches) == 2
    assert matches[1].clause is c2
    assert matches[1].rule is None


def test_ordering_preserved() -> None:
    """Output order matches the input clause order."""
    clauses = [_clause(t) for t in ("termination", "confidentiality", "payment")]
    rule_term = _rule("termination")
    rule_conf = _rule("confidentiality")
    matches = match_clauses_to_rules(
        clauses, {"termination": rule_term, "confidentiality": rule_conf}
    )
    assert [m.clause for m in matches] == clauses


def test_multiple_clauses_same_type_each_gets_rule() -> None:
    """Two clauses of the same type both receive the same rule object."""
    c1 = _clause("governing_law")
    c2 = _clause("governing_law")
    rule = _rule("governing_law")
    matches = match_clauses_to_rules([c1, c2], {"governing_law": rule})
    assert matches[0].rule is rule
    assert matches[1].rule is rule


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_clauses_returns_empty_list() -> None:
    rule = _rule("indemnification")
    matches = match_clauses_to_rules([], {"indemnification": rule})
    assert matches == []


def test_empty_rules_all_clauses_have_none() -> None:
    clauses = [_clause(t) for t in ("indemnification", "termination", "payment")]
    matches = match_clauses_to_rules(clauses, {})
    assert all(m.rule is None for m in matches)
    assert len(matches) == 3


def test_extra_rules_not_in_clauses_are_ignored() -> None:
    """resolved_rules may have types not present in clauses — no error raised."""
    clause = _clause("indemnification")
    rules = {
        "indemnification": _rule("indemnification"),
        "governing_law": _rule("governing_law"),
        "termination": _rule("termination"),
    }
    matches = match_clauses_to_rules([clause], rules)
    assert len(matches) == 1
    assert matches[0].rule is rules["indemnification"]


def test_mixed_matched_and_unmatched() -> None:
    """Mixed input: some clauses match, some don't."""
    c_indem = _clause("indemnification")
    c_pay = _clause("payment")
    c_term = _clause("termination")
    rule_indem = _rule("indemnification")
    rule_term = _rule("termination")
    matches = match_clauses_to_rules(
        [c_indem, c_pay, c_term],
        {"indemnification": rule_indem, "termination": rule_term},
    )
    assert matches[0].rule is rule_indem
    assert matches[1].rule is None       # payment has no rule
    assert matches[2].rule is rule_term
