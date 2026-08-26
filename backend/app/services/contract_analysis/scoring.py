"""S2 scoring — severity-weighted contract risk score (T-043).

Converts a flag list into a ``ContractScore`` for T-044 to persist.

Scoring model
-------------
Each flag contributes:

    severity_base(flag.severity) × rule.risk_weight

where ``severity_base`` is a geometric scale (low=1, medium=3, high=9) that
ensures a single high-severity flag always outweighs many low-severity ones.
Ungoverned flags (no matching rule) use ``risk_weight=1.0``.

``max_clause_severity`` is determined by explicit severity ordering, NOT
lexicographic sort, since ``max(["low","high","medium"])`` would silently
return ``"medium"`` (alphabetical).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.schemas.playbook import RuleResponse
from app.services.contract_analysis.models import AnalysisFlag

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Geometric scale: high must dominate many lows.
_SEVERITY_BASE: dict[str, float] = {
    "low": 1.0,
    "medium": 3.0,
    "high": 9.0,
}

# Explicit ordering used for max_clause_severity — never rely on str ordering.
_SEVERITY_ORDER: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

_DEFAULT_RISK_WEIGHT = 1.0

# Version string baked into risk_score rows so the gate can detect stale scores
# if the weight schema changes.
WEIGHTS_VERSION = "v1"


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass
class ContractScore:
    """Result of scoring a flag list for one contract.

    Maps directly to the ``risk_score`` DB table (T-044 persists it).
    ``clause_id=None`` indicates a contract-level roll-up.
    """

    score: float
    max_clause_severity: str | None
    weights_version: str
    contract_id: uuid.UUID
    clause_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_flags(
    contract_id: uuid.UUID,
    flags: list[AnalysisFlag],
    resolved_rules: dict[str, RuleResponse],
) -> ContractScore:
    """Compute a severity-weighted risk score for *contract_id*.

    Args:
        contract_id:    UUID of the contract being scored.
        flags:          Combined Layer 1 + Layer 2 flag list (may be empty).
        resolved_rules: Type-keyed rule map used to look up risk_weight per flag.
                        Ungoverned flags (clause_type not in this dict) use
                        the default weight of 1.0.

    Returns:
        A ``ContractScore`` with the aggregate score, worst severity seen, and
        weights version.  score=0.0 and max_clause_severity=None when there are
        no flags.
    """
    if not flags:
        return ContractScore(
            score=0.0,
            max_clause_severity=None,
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
        )

    total = 0.0
    max_order = 0
    max_severity: str | None = None

    for flag in flags:
        base = _SEVERITY_BASE.get(flag.severity, _SEVERITY_BASE["low"])
        rule = resolved_rules.get(flag.clause_type)
        weight = rule.risk_weight if rule is not None else _DEFAULT_RISK_WEIGHT
        total += base * weight

        order = _SEVERITY_ORDER.get(flag.severity, 0)
        if order > max_order:
            max_order = order
            max_severity = flag.severity

    return ContractScore(
        score=total,
        max_clause_severity=max_severity,
        weights_version=WEIGHTS_VERSION,
        contract_id=contract_id,
    )
