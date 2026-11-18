"""In-memory data structures shared across S2 analysis layers (T-040–T-044).

AnalysisFlag mirrors the `flag` DB table columns; review_run_id is omitted and
set at persist time (T-044). Task 4.3/4.4 add the zone-evaluator fields
(``rule_key``, ``zone``, ``position_id``, ``red_line_id``, ``parameter_values``)
mirroring the new ``flag`` columns from migration 012 (task 1.3) — populated by
whichever layer actually ran a finding through ``evaluate_finding``: Layer 1
for structural (phrase/regex/parameter/missing) findings, Layer 2 for
LLM-extracted (position/parameter/semantic-red-line) findings.

ClauseRuleMatch pairs each clause with its resolved playbook rules (task 4.4):
every ``ResolvedRule`` sharing the clause's ``clause_type`` (its "family" —
e.g. ``limitation_of_liability`` usually carries several rule_keys, one per
negotiated issue), not just one. This replaces the single-rule pairing T-041
used before the resolution engine (task 4.2) could return more than one rule
per clause type.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.schemas.playbook import ResolvedRule


@dataclass
class AnalysisFlag:
    contract_id: uuid.UUID
    # missing | prohibited | non_standard | high_risk | vague | inconsistent | deviation
    flag_type: str
    severity: str           # low | medium | high
    source: str             # deterministic | llm
    clause_type: str
    clause_id: uuid.UUID | None = None
    char_start: int | None = None
    char_end: int | None = None
    detail: dict = field(default_factory=dict)
    matched_rule_id: uuid.UUID | None = None
    # Zone-evaluator fields (task 4.3 evaluate_finding / task 4.4 wiring).
    # None when the flag predates the evaluator (or the evaluator found no
    # position/red_line to cite, e.g. a "default_zone" deviation).
    rule_key: str | None = None
    zone: str | None = None
    position_id: uuid.UUID | None = None
    red_line_id: uuid.UUID | None = None
    parameter_values: dict | None = None


@dataclass
class ClauseRuleMatch:
    """Pairs a clause with every resolved rule in its clause-type family.

    Ungoverned clauses (``rules == []``) are retained so Layer 2 can flag
    language the playbook does not cover on counterparty-paper contracts.
    """

    clause: Any
    rules: list[ResolvedRule] = field(default_factory=list)
