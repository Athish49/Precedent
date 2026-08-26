"""In-memory data structures shared across S2 analysis layers (T-040–T-044).

AnalysisFlag mirrors the `flag` DB table columns; review_run_id is omitted and
set at persist time (T-044).

ClauseRuleMatch pairs each clause with its resolved playbook rule (T-041).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.schemas.playbook import RuleResponse


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


@dataclass
class ClauseRuleMatch:
    """Pairs a clause with its resolved playbook rule (or None if ungoverned).

    Ungoverned clauses (rule=None) are retained so T-042 can flag language that
    the playbook does not cover on counterparty-paper contracts.
    """

    clause: Any
    rule: RuleResponse | None
