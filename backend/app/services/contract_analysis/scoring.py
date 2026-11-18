"""S2 scoring — severity-weighted contract risk score, normalised to 0-1.

Converts a flag list into a ``ContractScore`` for persistence (``risk_score``
table). Rewritten for task 4.5 (``playbook_plan.md`` section 5.3) to replace
the old raw, unbounded sum (``playbook_status.md`` defect #2: "``gate.py``
auto-applies below 0.4 and escalates at 0.7 ... Auto-apply can only happen
with zero flags, when there is nothing to apply") with a score that is always
between 0 and 1.

Scoring model (``playbook_plan.md`` section 5.3)
-------------------------------------------------
    Flag points  = severity_base(flag.severity) x rule.risk_weight
    Contract score = total points / (9 x sum(risk_weight over resolved rules)),
                      capped at 1.0

``severity_base`` is a geometric scale (low=1, medium=3, high=9) that ensures
a single high-severity flag always outweighs many low-severity ones.
Ungoverned flags (no matching rule — ``flag.rule_key`` is ``None`` or not
among the contract's resolved rules) use ``risk_weight=1``.

The denominator is "9 x sum of risk_weight over every rule resolved for this
contract" (not just the rules that happened to produce a flag): the
theoretical worst case, every resolved rule breached at the worst severity,
scores exactly 1.0. The cap still matters even so, because the same
``rule_key`` can be flagged more than once (e.g. the same issue checked
against two clauses of the same family), which can push the raw total above
the denominator.

If no rules were resolved at all (``resolved_rules`` is empty — normally
unreachable, since resolution always returns at least the baseline
playbook's rules, but defended against here), the denominator is 0; a
division is avoided and the score fails safe to 1.0 when there is anything
to flag, 0.0 when there is nothing.

``max_clause_severity`` is determined by explicit severity ordering, NOT
lexicographic sort, since ``max(["low","high","medium"])`` would silently
return ``"medium"`` (alphabetical).

``max_zone`` (task 4.5 item 3; ``risk_score.max_zone`` column, migration 012)
is the worst zone among all flags on the contract — ``"green"`` < ``"yellow"``
< ``"red"`` — or ``None`` when no flag carries a zone (e.g. an all-ungoverned
contract, or one with no flags at all). ``max_zone_for_flags`` is exported so
``app/workflows/gate.py`` can apply the same ordering to decide the gate
outcome directly from the flag list, without re-deriving it from this
module's own severity arithmetic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

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

# Explicit ordering used for max_zone — same reasoning: zone names must not
# be compared lexicographically ("red" < "yellow" alphabetically, which is
# backwards).
_ZONE_ORDER: dict[str, int] = {
    "green": 1,
    "yellow": 2,
    "red": 3,
}

_DEFAULT_RISK_WEIGHT = 1.0

# Version string baked into risk_score rows so the gate (or any report) can
# tell at a glance whether a row predates the 0-1 normalisation (task 4.5;
# "v1" rows carry the old raw, unbounded scale described above).
WEIGHTS_VERSION = "v2"


# ---------------------------------------------------------------------------
# Duck-typed shapes this module reads but does not own
# ---------------------------------------------------------------------------


@runtime_checkable
class _ZonedFlag(Protocol):
    zone: str | None


@runtime_checkable
class _ResolvedRuleLike(Protocol):
    rule_key: str | None
    risk_weight: float


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass
class ContractScore:
    """Result of scoring a flag list for one contract.

    Maps directly to the ``risk_score`` DB table. ``clause_id=None``
    indicates a contract-level roll-up. ``max_zone`` defaults to ``None`` so
    existing callers that construct a ``ContractScore`` without it (tests
    outside this task's scope) keep working.
    """

    score: float
    max_clause_severity: str | None
    weights_version: str
    contract_id: uuid.UUID
    clause_id: uuid.UUID | None = None
    max_zone: str | None = None


# ---------------------------------------------------------------------------
# Shared zone ordering (used by this module and by app/workflows/gate.py)
# ---------------------------------------------------------------------------


def max_zone_for_flags(flags: Any) -> str | None:
    """The worst zone among *flags*, or ``None`` if none carries a zone.

    Accepts anything iterable of objects with a ``.zone`` attribute —
    ``AnalysisFlag`` (this package's in-memory dataclass) and
    ``app.schemas.analysis.FlagDTO`` (the persisted-flag read shape the gate
    works from) both qualify, so both this module and ``workflows/gate.py``
    can call it with their own flag type.
    """
    worst: str | None = None
    worst_rank = 0
    for flag in flags:
        zone = getattr(flag, "zone", None)
        rank = _ZONE_ORDER.get(zone, 0)
        if rank > worst_rank:
            worst_rank = rank
            worst = zone
    return worst


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_flags(
    contract_id: uuid.UUID,
    flags: list[AnalysisFlag],
    resolved_rules: Any,
) -> ContractScore:
    """Compute a severity-weighted, 0-1-normalised risk score for *contract_id*.

    Args:
        contract_id:    UUID of the contract being scored.
        flags:          Combined Layer 1 + Layer 2 flag list (may be empty).
        resolved_rules: Every rule resolved for this contract (e.g.
                         ``ResolveResponse.rules`` — every surviving
                         ``rule_key``, not just the ones that produced a
                         flag). Used two ways: (1) to look up each flag's own
                         ``risk_weight`` by matching ``flag.rule_key``,
                         falling back to the default weight of 1 when the
                         flag is ungoverned or its rule_key is not among
                         these; (2) to compute the normalising denominator,
                         ``9 x sum(risk_weight over resolved_rules)``. Any
                         iterable of objects with ``rule_key``/``risk_weight``
                         attributes works (duck-typed, not isinstance-checked,
                         so tests can pass simple stand-ins).

    Returns:
        A ``ContractScore`` with the aggregate score (always in [0, 1]),
        worst severity seen, worst zone seen, and weights version. score=0.0
        and max_clause_severity=max_zone=None when there are no flags.
    """
    if not flags:
        return ContractScore(
            score=0.0,
            max_clause_severity=None,
            weights_version=WEIGHTS_VERSION,
            contract_id=contract_id,
            max_zone=None,
        )

    rules_by_key: dict[str, _ResolvedRuleLike] = {}
    for rule in resolved_rules or ():
        key = getattr(rule, "rule_key", None)
        if key:
            rules_by_key[key] = rule

    total = 0.0
    max_order = 0
    max_severity: str | None = None

    for flag in flags:
        base = _SEVERITY_BASE.get(flag.severity, _SEVERITY_BASE["low"])
        rule = rules_by_key.get(flag.rule_key) if flag.rule_key else None
        weight = rule.risk_weight if rule is not None else _DEFAULT_RISK_WEIGHT
        total += base * weight

        order = _SEVERITY_ORDER.get(flag.severity, 0)
        if order > max_order:
            max_order = order
            max_severity = flag.severity

    weight_sum = sum((getattr(rule, "risk_weight", 0.0) or 0.0) for rule in (resolved_rules or ()))
    denominator = 9.0 * weight_sum
    if denominator > 0:
        score = min(total / denominator, 1.0)
    else:
        # No rules resolved at all — nothing to normalise against. Fail safe:
        # any flag at all means full red (1.0); no flags already returned
        # above, but a caller could pass flags with no resolved_rules deliberately.
        score = 1.0 if total > 0 else 0.0

    return ContractScore(
        score=score,
        max_clause_severity=max_severity,
        weights_version=WEIGHTS_VERSION,
        contract_id=contract_id,
        max_zone=max_zone_for_flags(flags),
    )
