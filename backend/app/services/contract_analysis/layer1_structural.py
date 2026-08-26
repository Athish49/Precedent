"""S2 Layer 1 — deterministic structural analysis (T-040).

Two checks, no LLM:
  - missing-clause: required clause types absent from the contract.
  - prohibited-term: clause text contains a term explicitly banned by the rule.

Assumption: clause.text is the verbatim contract slice [char_start:char_end].
If segmentation normalises whitespace the citation offsets will drift; verify
against real segmentation output before trusting char_start/char_end in T-044.
"""

from __future__ import annotations

import re
import uuid

from app.schemas.playbook import RuleResponse
from app.services.contract_analysis.models import AnalysisFlag


def run_layer1(
    contract_id: uuid.UUID,
    clauses: list,
    resolved_rules: dict[str, RuleResponse],
) -> list[AnalysisFlag]:
    """Run both structural checks and return the combined flag list.

    Args:
        contract_id:    UUID of the contract being analysed.
        clauses:        All Clause ORM objects for the contract.
        resolved_rules: Type-keyed rule map from playbook resolve() — only rules
                        present here are checked; clause types with no rule are
                        skipped.
    """
    flags: list[AnalysisFlag] = []
    flags.extend(_check_missing(contract_id, clauses, resolved_rules))
    flags.extend(_check_prohibited(contract_id, clauses, resolved_rules))
    return flags


# ---------------------------------------------------------------------------
# Missing-clause check
# ---------------------------------------------------------------------------


def _check_missing(
    contract_id: uuid.UUID,
    clauses: list,
    resolved_rules: dict[str, RuleResponse],
) -> list[AnalysisFlag]:
    """Flag required clause types that are absent from the contract."""
    present_types = {c.clause_type for c in clauses}
    flags: list[AnalysisFlag] = []
    for clause_type, rule in resolved_rules.items():
        if rule.required and clause_type not in present_types:
            flags.append(
                AnalysisFlag(
                    contract_id=contract_id,
                    flag_type="missing",
                    severity="high",
                    source="deterministic",
                    clause_type=clause_type,
                    clause_id=None,
                    char_start=None,
                    char_end=None,
                    detail={"playbook_rule_id": str(rule.id)},
                    matched_rule_id=rule.id,
                )
            )
    return flags


# ---------------------------------------------------------------------------
# Prohibited-term check
# ---------------------------------------------------------------------------


def _check_prohibited(
    contract_id: uuid.UUID,
    clauses: list,
    resolved_rules: dict[str, RuleResponse],
) -> list[AnalysisFlag]:
    """Flag every occurrence of a prohibited term found in clause text."""
    flags: list[AnalysisFlag] = []
    for clause in clauses:
        rule = resolved_rules.get(clause.clause_type)
        if not rule or not rule.prohibited_terms:
            continue
        for term in rule.prohibited_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for match in pattern.finditer(clause.text):
                excerpt_start = max(0, match.start() - 50)
                flags.append(
                    AnalysisFlag(
                        contract_id=contract_id,
                        flag_type="prohibited",
                        severity="high",
                        source="deterministic",
                        clause_type=clause.clause_type,
                        clause_id=clause.id,
                        char_start=clause.char_start + match.start(),
                        char_end=clause.char_start + match.end(),
                        detail={
                            "matched_term": term,
                            "clause_excerpt": clause.text[
                                excerpt_start : match.end() + 50
                            ],
                        },
                        matched_rule_id=rule.id,
                    )
                )
    return flags
