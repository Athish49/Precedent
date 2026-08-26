"""Tests for S2 Layer 1 deterministic structural analysis (T-040)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.contract_analysis.layer1_structural import run_layer1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clause(
    clause_type: str,
    text: str = "Standard clause text.",
    char_start: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        clause_type=clause_type,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )


def _rule(
    clause_type: str,
    required: bool = True,
    prohibited_terms: list[str] | None = None,
) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.clause_type = clause_type
    r.required = required
    r.prohibited_terms = prohibited_terms or []
    return r


# ---------------------------------------------------------------------------
# Missing-clause checks
# ---------------------------------------------------------------------------


def test_missing_required_clause_flagged() -> None:
    """A required clause absent from the contract produces a missing flag."""
    contract_id = uuid.uuid4()
    rule = _rule("indemnification", required=True)
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"indemnification": rule})
    assert len(flags) == 1
    f = flags[0]
    assert f.flag_type == "missing"
    assert f.severity == "high"
    assert f.source == "deterministic"
    assert f.clause_type == "indemnification"
    assert f.clause_id is None
    assert f.char_start is None
    assert f.char_end is None
    assert f.matched_rule_id == rule.id


def test_present_required_clause_not_flagged() -> None:
    """A required clause that is present produces no missing flag."""
    contract_id = uuid.uuid4()
    rule = _rule("indemnification", required=True)
    clause = _clause("indemnification")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"indemnification": rule})
    assert all(f.flag_type != "missing" for f in flags)


def test_non_required_absent_clause_not_flagged() -> None:
    """An absent clause that is not required produces no flag."""
    contract_id = uuid.uuid4()
    rule = _rule("governing_law", required=False)
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"governing_law": rule})
    assert flags == []


def test_multiple_missing_required_clauses() -> None:
    """Each missing required clause produces its own flag."""
    contract_id = uuid.uuid4()
    rules = {
        "indemnification": _rule("indemnification", required=True),
        "termination": _rule("termination", required=True),
        "governing_law": _rule("governing_law", required=False),
    }
    flags = run_layer1(contract_id, clauses=[], resolved_rules=rules)
    missing_types = {f.clause_type for f in flags if f.flag_type == "missing"}
    assert missing_types == {"indemnification", "termination"}


def test_missing_flag_detail_contains_rule_id() -> None:
    """Missing flag detail records the playbook_rule_id for T-044 lookup."""
    contract_id = uuid.uuid4()
    rule = _rule("confidentiality", required=True)
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"confidentiality": rule})
    assert flags[0].detail["playbook_rule_id"] == str(rule.id)


# ---------------------------------------------------------------------------
# Prohibited-term checks
# ---------------------------------------------------------------------------


def test_prohibited_term_match_produces_flag() -> None:
    """A prohibited term found in clause text produces a prohibited flag."""
    contract_id = uuid.uuid4()
    rule = _rule("limitation_of_liability", required=True, prohibited_terms=["no limitation"])
    clause = _clause("limitation_of_liability", text="There shall be no limitation on damages.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"limitation_of_liability": rule},
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1
    f = prohibited[0]
    assert f.severity == "high"
    assert f.source == "deterministic"
    assert f.clause_id == clause.id
    assert f.matched_rule_id == rule.id
    assert f.detail["matched_term"] == "no limitation"


def test_prohibited_term_case_insensitive() -> None:
    """Prohibited-term match is case-insensitive."""
    contract_id = uuid.uuid4()
    rule = _rule("indemnification", prohibited_terms=["unlimited indemnification"])
    clause = _clause("indemnification", text="This grants UNLIMITED INDEMNIFICATION to all.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"indemnification": rule},
    )
    assert any(f.flag_type == "prohibited" for f in flags)


def test_prohibited_term_char_offsets_contract_level() -> None:
    """char_start/char_end are contract-level offsets (clause.char_start + match offset)."""
    contract_id = uuid.uuid4()
    rule = _rule("limitation_of_liability", prohibited_terms=["unlimited liability"])
    text = "The agreement includes unlimited liability for all breaches."
    clause = _clause("limitation_of_liability", text=text, char_start=500)
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"limitation_of_liability": rule},
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1
    f = prohibited[0]
    in_clause_start = text.lower().index("unlimited liability")
    assert f.char_start == 500 + in_clause_start
    assert f.char_end == 500 + in_clause_start + len("unlimited liability")


def test_multiple_term_occurrences_produce_multiple_flags() -> None:
    """Each occurrence of a prohibited term in a clause produces its own flag."""
    contract_id = uuid.uuid4()
    rule = _rule("confidentiality", prohibited_terms=["no obligation"])
    text = "There is no obligation to disclose. There is no obligation to act."
    clause = _clause("confidentiality", text=text)
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"confidentiality": rule},
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 2


def test_multiple_prohibited_terms_each_flagged() -> None:
    """Each distinct prohibited term that matches produces its own flag."""
    contract_id = uuid.uuid4()
    rule = _rule(
        "indemnification",
        prohibited_terms=["unlimited indemnification", "indemnify regardless"],
    )
    text = "This provides unlimited indemnification and shall indemnify regardless of fault."
    clause = _clause("indemnification", text=text)
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"indemnification": rule},
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 2
    matched = {f.detail["matched_term"] for f in prohibited}
    assert matched == {"unlimited indemnification", "indemnify regardless"}


def test_clause_with_no_matching_rule_not_flagged() -> None:
    """A clause whose type has no rule in resolved_rules is not checked."""
    contract_id = uuid.uuid4()
    clause = _clause("payment", text="Payment shall be unlimited and unconditional.")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={})
    assert flags == []


def test_clause_with_empty_prohibited_terms_not_flagged() -> None:
    """A clause whose rule has no prohibited_terms produces no prohibited flag."""
    contract_id = uuid.uuid4()
    rule = _rule("governing_law", required=True, prohibited_terms=[])
    clause = _clause("governing_law", text="Governed by the laws of Delaware.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"governing_law": rule},
    )
    assert not any(f.flag_type == "prohibited" for f in flags)


# ---------------------------------------------------------------------------
# Combined behaviour
# ---------------------------------------------------------------------------


def test_run_layer1_combines_both_checks() -> None:
    """run_layer1 returns both missing and prohibited flags in one call."""
    contract_id = uuid.uuid4()
    rule_indem = _rule(
        "indemnification", required=True, prohibited_terms=["unlimited indemnification"]
    )
    rule_term = _rule("termination", required=True, prohibited_terms=[])
    clause_indem = _clause(
        "indemnification",
        text="This grants unlimited indemnification to all.",
    )
    # termination clause is absent
    resolved_rules = {
        "indemnification": rule_indem,
        "termination": rule_term,
    }
    flags = run_layer1(contract_id, clauses=[clause_indem], resolved_rules=resolved_rules)
    types = {f.flag_type for f in flags}
    assert "missing" in types      # termination absent
    assert "prohibited" in types   # unlimited indemnification match


def test_empty_contract_all_required_missing() -> None:
    """No clauses at all → all required rules produce missing flags."""
    contract_id = uuid.uuid4()
    rules = {
        "data_protection": _rule("data_protection", required=True),
        "compliance": _rule("compliance", required=True),
        "audit": _rule("audit", required=True),
    }
    flags = run_layer1(contract_id, clauses=[], resolved_rules=rules)
    assert len(flags) == 3
    assert all(f.flag_type == "missing" for f in flags)


def test_no_rules_no_flags() -> None:
    """With no resolved rules, no flags are ever raised."""
    contract_id = uuid.uuid4()
    clause = _clause("indemnification", text="Party A shall indemnify Party B in all cases.")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={})
    assert flags == []
