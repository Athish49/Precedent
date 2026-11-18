"""S2 analysis orchestrator — wires Layers 1+2, scoring, and persistence (T-044)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.models.analysis import Flag, RiskScore
from app.db.repositories import analysis_repo, clause_repo, contract_repo, playbook_repo
from app.schemas.analysis import AnalysisResult, FlagDTO, RiskDTO
from app.schemas.playbook import ResolveResponse
from app.services.contract_analysis.layer1_structural import (
    group_rules_by_clause_type,
    rule_scope_red_line_hits,
    run_layer1,
)
from app.services.contract_analysis.layer2_content import run_layer2
from app.services.contract_analysis.rule_matcher import issue_key_for_rule, match_clauses_to_rules
from app.services.contract_analysis.scoring import score_flags
from app.services.playbook.routing import resolve


_STRUCTURAL_CONDITION_TYPES = frozenset({"phrase", "regex"})


async def _scope_red_lines(session: AsyncSession, resolved: ResolveResponse) -> list[Any]:
    """Every playbook-scope red line of each playbook that contributed a rule
    to *resolved*, plus every global-scope red line, deduplicated by id.

    Rule-scope red lines are not fetched here: they already travel on each
    ``ResolvedRule.red_lines``.
    """
    source_playbook_ids = {r.source_playbook_id for r in resolved.rules}
    fetched: list[Any] = []
    for playbook_id in source_playbook_ids:
        fetched.extend(await playbook_repo.list_red_lines_for_playbook(session, playbook_id))
    fetched.extend(await playbook_repo.list_global_red_lines(session))

    seen: set[Any] = set()
    red_lines: list[Any] = []
    for rl in fetched:
        if rl.scope not in ("playbook", "global") or rl.id in seen:
            continue
        seen.add(rl.id)
        red_lines.append(rl)
    return red_lines


def _split_scope_red_lines(
    red_lines: list[Any],
) -> tuple[list[Any], list[Any], list[Any]]:
    """Split playbook/global red lines by who evaluates them.

    Returns ``(playbook_structural, global_structural, semantic)``:

    - ``phrase``/``regex`` -> Layer 1 (``run_layer1``'s
      ``playbook_red_lines``/``global_red_lines``), text-matched against
      every clause in the contract.
    - ``semantic`` -> Layer 2's once-per-contract LLM check.
    - ``parameter`` -> neither. A parameter condition needs a value
      extracted for one specific rule, and a playbook/global red line is not
      tied to any rule. Global parameter red lines are rejected by the seed
      validator (``red_line.global_parameter``) and the seed has no
      playbook-scope red lines at all, so this drops nothing today.
    """
    playbook_structural: list[Any] = []
    global_structural: list[Any] = []
    semantic: list[Any] = []
    for rl in red_lines:
        if rl.condition_type == "semantic":
            semantic.append(rl)
        elif rl.condition_type in _STRUCTURAL_CONDITION_TYPES:
            (playbook_structural if rl.scope == "playbook" else global_structural).append(rl)
    return playbook_structural, global_structural, semantic


async def analyze(session: AsyncSession, contract_id: uuid.UUID) -> AnalysisResult:
    """Run full S2 analysis for a contract and persist results.

    Re-entrant: deletes prior flags and risk score before persisting new ones.
    """
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    resolved = await resolve(
        session,
        contract.contract_type or "",
        contract.party_role or "vendor",
        contract.paper_origin,
        contract.context,
    )
    clauses = await clause_repo.get_clauses_for_contract(session, contract_id)

    # Playbook/global red lines: phrase/regex ones are checked structurally
    # by Layer 1 against every clause; semantic ones by Layer 2's
    # per-contract LLM check.
    playbook_structural, global_structural, semantic_red_lines = _split_scope_red_lines(
        await _scope_red_lines(session, resolved)
    )

    # Layer 1 gets every resolved rule, grouped by clause family (not the
    # one-rule-per-clause_type routing.rules_by_clause_type collapse), so
    # every rule's red lines are checked and a family is "missing" only when
    # none of its required rules is matched.
    layer1_flags = run_layer1(
        contract_id,
        clauses,
        group_rules_by_clause_type(resolved.rules),
        playbook_red_lines=playbook_structural,
        global_red_lines=global_structural,
    )
    matches = match_clauses_to_rules(clauses, resolved)

    # Record which issues apply to each clause (task 4.4 item 4; clause.
    # issue_keys from migration 012 / task 1.3) independently of whether any
    # of those rules end up producing a flag — mutated in place and
    # persisted by the commit below, the same pattern as `contract.status`.
    for m in matches:
        issue_keys = sorted({issue_key_for_rule(r) for r in m.rules})
        m.clause.issue_keys = issue_keys or None

    layer2_flags = run_layer2(
        contract_id,
        contract.paper_origin,
        matches,
        contract.context,
        semantic_red_lines,
        layer1_red_line_hits=rule_scope_red_line_hits(layer1_flags),
    )

    all_flags = layer1_flags + layer2_flags
    # Score against every rule resolved for this contract (task 4.5;
    # playbook_plan.md section 5.3) — the normalising denominator needs every
    # surviving rule_key, and several rule_keys commonly share one clause_type.
    contract_score = score_flags(contract_id, all_flags, resolved.rules)

    # Replace strategy: clear prior analysis before persisting new results.
    await analysis_repo.delete_flags_for_contract(session, contract_id)
    await analysis_repo.delete_risk_score_for_contract(session, contract_id)

    flag_rows = [
        Flag(
            contract_id=f.contract_id,
            clause_id=f.clause_id,
            flag_type=f.flag_type,
            severity=f.severity,
            source=f.source,
            char_start=f.char_start,
            char_end=f.char_end,
            # Fold clause_type into detail — the flag table has no clause_type column.
            # Missing-clause flags have clause_id=None, so this is the only durable
            # record of which clause type was absent.
            detail={**f.detail, "clause_type": f.clause_type},
            matched_rule_id=f.matched_rule_id,
            rule_key=f.rule_key,
            position_id=f.position_id,
            red_line_id=f.red_line_id,
            zone=f.zone,
            parameter_values=f.parameter_values,
        )
        for f in all_flags
    ]
    persisted_flags = await analysis_repo.bulk_create_flags(session, flag_rows)

    risk_row = RiskScore(
        contract_id=contract_id,
        score=contract_score.score,
        max_clause_severity=contract_score.max_clause_severity,
        weights_version=contract_score.weights_version,
        max_zone=contract_score.max_zone,
    )
    persisted_risk = await analysis_repo.create_risk_score(session, risk_row)

    contract.status = "analyzed"
    await session.commit()

    flag_dtos = [FlagDTO.model_validate(f) for f in persisted_flags]
    risk_dto = RiskDTO(
        score=persisted_risk.score,
        max_clause_severity=persisted_risk.max_clause_severity,
        weights_version=persisted_risk.weights_version,
        # getattr, not direct access: test doubles for persisted_risk (e.g.
        # a bare SimpleNamespace) may predate this column.
        max_zone=getattr(persisted_risk, "max_zone", None),
    )
    return AnalysisResult(flags=flag_dtos, risk=risk_dto)


async def get_analysis(session: AsyncSession, contract_id: uuid.UUID) -> AnalysisResult:
    """Return stored analysis for a contract.

    Returns empty flags and null risk when no analysis has been run yet.
    Raises 404 only if the contract itself does not exist.
    """
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    flags = await analysis_repo.get_flags_for_contract(session, contract_id)
    risk = await analysis_repo.get_risk_score_for_contract(session, contract_id)

    flag_dtos = [FlagDTO.model_validate(f) for f in flags]
    risk_dto = (
        RiskDTO(
            score=risk.score,
            max_clause_severity=risk.max_clause_severity,
            weights_version=risk.weights_version,
            max_zone=getattr(risk, "max_zone", None),
        )
        if risk is not None
        else None
    )
    return AnalysisResult(flags=flag_dtos, risk=risk_dto)
