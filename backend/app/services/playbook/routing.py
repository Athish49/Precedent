"""Playbook resolution engine (task 4.2; ``playbook_plan.md`` section 5.1).

``resolve(session, contract_type, party_role, paper_origin, context)`` selects
every playbook that applies to a deal's facts — the company baseline, the
matching agreement playbook, and any regulatory overlays whose context
condition matches — pins each one's current (published) version, and merges
their rules into one list keyed by ``rule_key``. The highest-precedence
playbook wins per key; ties are broken deterministically by playbook ``key``.

Layer selection (section 5.1, steps 1-3):
  1. Base: every active playbook with ``layer == "base"``. There is exactly
     one in the seeded data (``halcyon-baseline``), but nothing here assumes
     that; any number of active base playbooks are all selected.
  2. Agreement: active playbooks with ``layer == "agreement"`` whose
     ``practice_area`` equals *contract_type*, whose ``party_role`` matches
     *party_role*, and whose ``paper_scope`` matches *paper_origin*.
  3. Overlay: active playbooks with ``layer == "overlay"`` whose
     ``applies_when`` matches *context*. The plan's section 5.1 text names
     only ``applies_when`` as the overlay filter (unlike step 2's three-part
     test for agreement playbooks), so overlay selection here deliberately
     does not also filter on ``party_role``/``paper_scope`` — see this task's
     report for that judgment call.

"Party role matches" / "paper scope matches" (not spelled out further by the
plan) are read the same way the seed data's own values imply: a playbook's
``party_role == "mutual"`` or ``paper_scope == "both"`` is a wildcard that
matches any input; otherwise the values must be equal. This is this module's
other judgment call — see the task report.

Precedence convention (section 7.1): base 10, agreement 20, overlay 30. A
rule's precedence is its *playbook's* precedence, not any property of the
rule itself. Playbooks are processed highest-precedence-first; equal
precedence is broken by playbook ``key`` ascending, never by DB or dict
iteration order, so repeated resolutions of the same facts always merge the
same way (section 5.1 step 5: "sort ties deterministically by playbook key").

Rule-level ``applies_when`` (step 6) is evaluated after the merge order is
fixed, dropping any winning rule whose own context condition does not match
— it does not make a dropped rule's key available to a lower-precedence
playbook's rule with the same key.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.playbook import Playbook
from app.db.repositories import playbook_repo
from app.schemas.playbook import ResolvedRule, ResolveResponse

# ---------------------------------------------------------------------------
# Pure predicates
# ---------------------------------------------------------------------------


def matches(condition: dict[str, Any] | None, context: dict[str, Any] | None) -> bool:
    """Does *context* satisfy *condition*?

    ``playbook_plan.md`` section 3.11: "A condition (``applies_when``,
    ``conditions``, ``context_overrides``) is a JSON object mapping a
    dimension key to the list of values it matches. All keys must match. An
    empty or null condition always matches." For example ``{"regimes":
    ["hipaa"]}`` matches a context carrying ``"regimes": ["hipaa", "gdpr"]``.

    A context value may be a single scalar (most dimensions, e.g.
    ``deal_value_band``) or a list (the multi-value ``regimes`` dimension);
    either way this matches when at least one of the context's values for
    that key is among the condition's allowed values.
    """
    if not condition:
        return True
    context = context or {}
    for key, allowed in condition.items():
        allowed_values = allowed if isinstance(allowed, (list, tuple, set)) else [allowed]
        if key not in context or context[key] is None:
            return False
        actual = context[key]
        actual_values = actual if isinstance(actual, (list, tuple, set)) else [actual]
        if not any(value in allowed_values for value in actual_values):
            return False
    return True


def _party_role_matches(playbook_party_role: str, party_role: str) -> bool:
    """``mutual`` is a wildcard; otherwise the roles must be equal."""
    return playbook_party_role == "mutual" or playbook_party_role == party_role


def _paper_scope_matches(playbook_paper_scope: str, paper_origin: str) -> bool:
    """``both`` is a wildcard; otherwise the scope must equal the origin."""
    return playbook_paper_scope == "both" or playbook_paper_scope == paper_origin


# ---------------------------------------------------------------------------
# Layer selection
# ---------------------------------------------------------------------------


def _select_applicable_playbooks(
    playbooks: list[Playbook],
    contract_type: str,
    party_role: str,
    paper_origin: str,
    context: dict[str, Any],
) -> list[Playbook]:
    """Return every active base, matching agreement, and matching overlay
    playbook, sorted highest-precedence-first with ties broken by ``key``.
    """
    active = [pb for pb in playbooks if pb.status == "active"]

    base = [pb for pb in active if pb.layer == "base"]
    agreement = [
        pb
        for pb in active
        if pb.layer == "agreement"
        and pb.practice_area == contract_type
        and _party_role_matches(pb.party_role, party_role)
        and _paper_scope_matches(pb.paper_scope, paper_origin)
    ]
    overlay = [
        pb for pb in active if pb.layer == "overlay" and matches(pb.applies_when, context)
    ]

    applicable = [*base, *agreement, *overlay]
    applicable.sort(key=lambda pb: (-pb.precedence, pb.key or ""))
    return applicable


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def resolve(
    session: AsyncSession,
    contract_type: str,
    party_role: str,
    paper_origin: str,
    context: dict[str, Any] | None = None,
) -> ResolveResponse:
    """Resolve and merge every applicable playbook for one deal's facts.

    ``playbook_plan.md`` section 5.1. Unknown *contract_type* (no agreement
    playbook's ``practice_area`` matches) still returns the baseline
    playbook's rules — never zero rules — because step 1 selects the base
    playbook unconditionally.
    """
    context = context or {}

    all_playbooks = await playbook_repo.list_playbooks(session)
    applicable = _select_applicable_playbooks(
        all_playbooks, contract_type, party_role, paper_origin, context
    )

    merged: dict[str, ResolvedRule] = {}
    # Every rule_key already owned by a higher-precedence (or tie-break-
    # earlier) playbook, whether or not its winning rule survived the
    # applies_when check. Kept separate from ``merged`` so a winner dropped
    # at step 6 still blocks lower-precedence rules with the same key
    # (section 5.1: merge by precedence at step 5, THEN filter at step 6).
    claimed_keys: set[str] = set()
    pinned_version_ids: list[uuid.UUID] = []
    applied_playbook_keys: list[str] = []

    for pb in applicable:
        version_id = pb.current_version_id
        if version_id is None:
            # Selected, but has no published version to pull rules from.
            continue

        pinned_version_ids.append(version_id)
        applied_playbook_keys.append(pb.key or str(pb.id))

        version = await playbook_repo.get_version(session, version_id)
        source_version = version.version if version is not None else ""

        rules = await playbook_repo.get_rules_with_children(session, version_id)
        for rule in rules:
            rule_key = rule.rule_key or str(rule.id)
            if rule_key in claimed_keys:
                # Step 5: a higher-precedence (or tie-break-earlier) playbook
                # already owns this rule_key — regardless of whether its rule
                # was then dropped by applies_when below.
                continue
            claimed_keys.add(rule_key)
            if not matches(rule.applies_when, context):
                # Step 6: the winning rule does not apply to this deal. The
                # key stays claimed, so no lower-precedence playbook's rule
                # with the same key can backfill it.
                continue
            # Attach provenance as plain attributes before validating —
            # these are exactly the extra fields ResolvedRule needs beyond
            # what PlaybookRule's own columns and get_rules_with_children's
            # attached child lists already provide. All negotiating language
            # comes from those child lists (positions / red_lines); the rule
            # row itself carries none.
            rule.source_playbook_id = pb.id
            rule.source_playbook_name = pb.name
            rule.source_version = source_version
            merged[rule_key] = ResolvedRule.model_validate(rule)

    resolved_rules = sorted(merged.values(), key=lambda r: r.rule_key or "")

    return ResolveResponse(
        contract_type=contract_type,
        party_role=party_role,
        paper_origin=paper_origin,
        rules=resolved_rules,
        pinned_version_ids=pinned_version_ids,
        applied_playbook_keys=applied_playbook_keys,
    )


# ---------------------------------------------------------------------------
# Back-compat helper for clause-type-keyed callers (tasks 4.3-4.6 not landed
# yet): converts the new per-rule_key list into the old per-clause_type dict
# shape so existing callers keep working until they are rewritten to use
# rule_key/issue-level matching directly.
# ---------------------------------------------------------------------------


def rules_by_clause_type(resolved: ResolveResponse) -> dict[str, ResolvedRule]:
    """Collapse ``resolved.rules`` to one rule per ``clause_type``.

    Several distinct ``rule_key``s can share a ``clause_type`` (a clause
    family usually has several negotiated issues), so this necessarily loses
    information the old identity-routed model never had to represent. The
    first rule encountered for a clause_type wins; ``resolved.rules`` is
    already in deterministic (rule_key-sorted) order, so this is stable
    across calls with the same inputs.
    """
    out: dict[str, ResolvedRule] = {}
    for rule in resolved.rules:
        out.setdefault(rule.clause_type, rule)
    return out


def rules_by_rule_key(resolved: ResolveResponse) -> dict[str, ResolvedRule]:
    """Index ``resolved.rules`` by ``rule_key`` (unique after the merge)."""
    return {rule.rule_key: rule for rule in resolved.rules if rule.rule_key}


def rule_for_flag(
    flag_rule_key: str | None,
    clause_type: str,
    by_rule_key: dict[str, ResolvedRule],
    by_clause_type: dict[str, ResolvedRule],
) -> ResolvedRule | None:
    """The resolved rule whose ladder a flag's redline should use.

    A flag that carries a ``rule_key`` was produced by that specific rule, so
    its ladder (positions / fallbacks / objections) and its decision-event
    provenance must come from that rule — never from whichever rule in the
    same clause family happens to sort first in ``rules_by_clause_type``.
    If that rule_key is not in the resolved set (e.g. dropped by its
    ``applies_when``), the result is ``None`` (free-form path) rather than a
    clause-type guess, which would reintroduce the wrong-ladder bug.

    Only flags with no ``rule_key`` at all — free-standing quality flags,
    and global/playbook-scope red-line flags that are not tied to a single
    rule — fall back to the legacy clause-type lookup, since there is no
    more specific rule identity to go on.
    """
    if flag_rule_key:
        return by_rule_key.get(flag_rule_key)
    return by_clause_type.get(clause_type)
