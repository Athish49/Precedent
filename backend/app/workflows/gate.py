"""The three-zone gate (task 4.5; ``playbook_plan.md`` section 5.3).

Replaces the old raw-aggregate-score thresholds (``playbook_status.md``
defect #2: "``scoring.py`` returns a raw sum ... ``gate.py:28`` auto-applies
below 0.4 and escalates at 0.7 ... Auto-apply can only happen with zero
flags") with a decision driven by the worst zone among the contract's flags:

    None or green -> auto_applied  (no routing)
    Yellow         -> needs_approval (approver: position, else the matrix)
    Red            -> escalated      (matrix; a `block` red line cannot be
                                       approved below `general_counsel`)

A quality failure in redline generation (``interference_detected`` on any
redline's rationale) still forces ``escalated``, regardless of zone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.review_run import ReviewRun
from app.db.repositories import authority_repo, contract_repo, playbook_repo, review_run_repo
from app.schemas.analysis import FlagDTO
from app.services.contract_analysis.scoring import max_zone_for_flags
from app.services.playbook.routing import matches
from app.workflows.review_pipeline import PipelineResult

# playbook_plan.md section 2.3 / seed authority.yaml: the top legal approver.
# A `block`-action red line must never route below this role (section 5.3's
# gate table: "block red lines cannot be approved below the top legal
# role"), so this key is forced directly rather than discovered through a
# position or the escalation matrix.
_GENERAL_COUNSEL_KEY = "general_counsel"

# Section 5.3's gate table: yellow needs an approver but may still auto-run
# once one signs off; red always escalates. (Red is handled as a special
# case in evaluate_gate rather than through this map, since a quality
# failure also forces "escalated" even out of a yellow zone.)
_ZONE_TO_DECISION = {"yellow": "needs_approval", "red": "escalated"}


@dataclass
class GateResult:
    review_run_id: uuid.UUID
    contract_id: uuid.UUID
    gate_decision: str          # "auto_applied" | "needs_approval" | "escalated"
    gate_reason: dict           # worst zone, quality-failure flag, and approver routing
    pipeline: PipelineResult


# ---------------------------------------------------------------------------
# Quality failure (unchanged hard-stop, independent of zone)
# ---------------------------------------------------------------------------


def _quality_failure(pipeline: PipelineResult) -> bool:
    """``playbook_plan.md`` section 5.3: "A quality failure in redline
    generation still forces ``escalated``" — regardless of the worst zone.
    """
    return any(bool(rdto.rationale.get("interference_detected")) for rdto in pipeline.redlines)


# ---------------------------------------------------------------------------
# Approver resolution (playbook_plan.md sections 3.12 and 5.3)
# ---------------------------------------------------------------------------


async def _flag_rule_context(
    session: AsyncSession, flag: FlagDTO
) -> tuple[uuid.UUID | None, str | None]:
    """The flag's ``playbook_id`` and ``clause_type``, for matrix matching.

    Ungoverned flags (``matched_rule_id`` is ``None``) still carry a
    ``clause_type`` in ``detail`` — ``contract_analysis/service.py`` folds
    it in there because the ``flag`` table has no ``clause_type`` column —
    so they can still match a clause-scoped or global policy even with no
    ``playbook_id`` to match on.
    """
    clause_type = flag.detail.get("clause_type") if isinstance(flag.detail, dict) else None
    if flag.matched_rule_id is None:
        return None, clause_type
    rule = await playbook_repo.get_rule(session, flag.matched_rule_id)
    if rule is None:
        return None, clause_type
    return rule.playbook_id, (rule.clause_type or clause_type)


async def _block_red_line_override(
    session: AsyncSession, flags: list[FlagDTO]
) -> dict | None:
    """A ``block`` red line forces ``general_counsel``, ahead of any position
    or escalation-matrix lookup (sections 3.12 and 5.3)."""
    for flag in flags:
        if flag.red_line_id is None:
            continue
        red_line = await playbook_repo.get_red_line(session, flag.red_line_id)
        if red_line is not None and red_line.action == "block":
            role = await authority_repo.get_approver_role_by_key(session, _GENERAL_COUNSEL_KEY)
            return {
                "approver_role": _GENERAL_COUNSEL_KEY,
                "sla_hours": role.default_sla_hours if role is not None else None,
                "required_info": {},
                "approver_source": "block_red_line",
                "red_line_key": red_line.key,
            }
    return None


async def _position_approver(session: AsyncSession, flags: list[FlagDTO]) -> dict | None:
    """A matched position's own ``approver_role_id`` takes precedence over
    the escalation matrix (section 3.12: "A position's own approver_role_id
    takes precedence over the matrix.")."""
    for flag in flags:
        if flag.position_id is None:
            continue
        position = await playbook_repo.get_rule_position(session, flag.position_id)
        if position is None or position.approver_role_id is None:
            continue
        role = await authority_repo.get_approver_role(session, position.approver_role_id)
        if role is not None:
            return {
                "approver_role": role.key,
                "sla_hours": role.default_sla_hours,
                "required_info": {},
                "approver_source": "position",
            }
    return None


async def _red_line_approver(session: AsyncSession, flags: list[FlagDTO]) -> dict | None:
    """A red line's own ``approver_role_id`` — a named approver for a
    non-``block`` (``escalate``) red line — checked after the position and
    before the matrix."""
    for flag in flags:
        if flag.red_line_id is None:
            continue
        red_line = await playbook_repo.get_red_line(session, flag.red_line_id)
        if red_line is None or red_line.approver_role_id is None:
            continue
        role = await authority_repo.get_approver_role(session, red_line.approver_role_id)
        if role is not None:
            return {
                "approver_role": role.key,
                "sla_hours": role.default_sla_hours,
                "required_info": {},
                "approver_source": "red_line",
                "red_line_key": red_line.key,
            }
    return None


def _policy_specificity(policy: Any) -> int:
    return (1 if policy.playbook_id is not None else 0) + (
        1 if policy.clause_type is not None else 0
    )


async def _escalation_matrix_approver(
    session: AsyncSession,
    flags: list[FlagDTO],
    zone: str,
    context: dict[str, Any],
) -> dict | None:
    """``authority_repo.list_escalation_policies`` (task 1.4), filtered to
    the policies applicable to this zone and a flag's playbook/clause_type,
    most specific match first and ties broken by priority (section 3.12:
    "Most specific match wins; ties broken by priority").

    ``list_escalation_policies`` itself only filters by exact equality (its
    own docstring: "does not by itself implement the 'null means all'
    fallback"), so the null-means-wildcard matching and specificity ranking
    happen here, in Python, over the zone-filtered set.
    """
    policies = await authority_repo.list_escalation_policies(session, zone=zone)
    if not policies:
        return None

    for flag in flags:
        playbook_id, clause_type = await _flag_rule_context(session, flag)
        candidates = [
            policy
            for policy in policies
            if (policy.playbook_id is None or policy.playbook_id == playbook_id)
            and (policy.clause_type is None or policy.clause_type == clause_type)
            and matches(policy.conditions, context)
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda p: (-_policy_specificity(p), -p.priority))
        policy = candidates[0]
        role = await authority_repo.get_approver_role(session, policy.approver_role_id)
        if role is not None:
            return {
                "approver_role": role.key,
                "sla_hours": policy.sla_hours,
                "required_info": policy.required_info,
                "approver_source": "escalation_matrix",
            }
    return None


async def _resolve_approver(
    session: AsyncSession,
    flags: list[FlagDTO],
    worst_zone: str,
    context: dict[str, Any],
) -> dict:
    """Resolve who approves a yellow/red decision.

    Order: a ``block`` red line forces ``general_counsel`` outright; else a
    matched position's own approver; else a red line's own named approver;
    else the escalation matrix, most specific match first; else "no
    approver configured" — the common case today, with no seed data loaded
    (``playbook_implementation.md`` task 4.5's "Done when"). That last case
    still returns a decision rather than crashing or blocking.
    """
    worst_flags = [f for f in flags if f.zone == worst_zone]

    for resolver in (_block_red_line_override, _position_approver, _red_line_approver):
        result = await resolver(session, worst_flags)
        if result is not None:
            return result

    result = await _escalation_matrix_approver(session, worst_flags, worst_zone, context)
    if result is not None:
        return result

    return {
        "approver_role": None,
        "sla_hours": None,
        "required_info": {},
        "approver_source": "none_configured",
        "note": "no approver is configured for this zone",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def evaluate_gate(
    session: AsyncSession,
    pipeline: PipelineResult,
    trigger: str = "manual",
) -> GateResult:
    # 1. Create the review_run, pinning the playbook versions this review
    #    ran against (task 4.5 item 6; ReviewRun.playbook_version_ids,
    #    migration 012) so the decision is reproducible later even if the
    #    playbooks change. JSONB needs plain strings, not uuid.UUID objects.
    pinned = [str(v) for v in pipeline.pinned_version_ids]
    run = ReviewRun(
        contract_id=pipeline.contract_id,
        trigger=trigger,
        status="running",
        playbook_version_ids=pinned or None,
    )
    run = await review_run_repo.create_review_run(session, run)
    await session.flush()

    # 2. The worst zone among all flags decides the outcome (section 5.3),
    #    not a raw aggregate score.
    flags = pipeline.analysis.flags
    worst_zone = max_zone_for_flags(flags)
    quality_failure = _quality_failure(pipeline)

    if worst_zone in ("yellow", "red"):
        contract = await contract_repo.get_contract(session, pipeline.contract_id)
        context = (contract.context if contract is not None else None) or {}
        approver = await _resolve_approver(session, flags, worst_zone, context)
        decision = (
            "escalated"
            if (worst_zone == "red" or quality_failure)
            else _ZONE_TO_DECISION[worst_zone]
        )
        reason = {
            "worst_zone": worst_zone,
            "quality_failure": quality_failure,
            **approver,
        }
    elif quality_failure:
        # No governed deviation reached yellow/red, but the redline itself
        # failed its own quality check — still escalate, with no flag to
        # resolve an approver from.
        decision = "escalated"
        reason = {
            "worst_zone": worst_zone,
            "quality_failure": True,
            "approver_role": None,
            "sla_hours": None,
            "required_info": {},
            "approver_source": "none_configured",
            "note": "no approver is configured for this zone",
        }
    else:
        decision = "auto_applied"
        reason = {
            "worst_zone": worst_zone,
            "quality_failure": False,
        }

    # 3. Persist the decision.
    run = await review_run_repo.complete_review_run(session, run, decision, reason)
    await session.commit()

    return GateResult(
        review_run_id=run.id,
        contract_id=pipeline.contract_id,
        gate_decision=decision,
        gate_reason=reason,
        pipeline=pipeline,
    )
