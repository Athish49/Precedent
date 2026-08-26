"""S2 analysis orchestrator — wires Layers 1+2, scoring, and persistence (T-044)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.models.analysis import Flag, RiskScore
from app.db.repositories import analysis_repo, clause_repo, contract_repo
from app.schemas.analysis import AnalysisResult, FlagDTO, RiskDTO
from app.services.contract_analysis.layer1_structural import run_layer1
from app.services.contract_analysis.layer2_content import run_layer2
from app.services.contract_analysis.rule_matcher import match_clauses_to_rules
from app.services.contract_analysis.scoring import score_flags
from app.services.playbook.routing import resolve


async def analyze(session: AsyncSession, contract_id: uuid.UUID) -> AnalysisResult:
    """Run full S2 analysis for a contract and persist results.

    Re-entrant: deletes prior flags and risk score before persisting new ones.
    """
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    resolved = await resolve(session, contract.contract_type or "")
    rules = resolved.rules

    clauses = await clause_repo.get_clauses_for_contract(session, contract_id)

    layer1_flags = run_layer1(contract_id, clauses, rules)
    matches = match_clauses_to_rules(clauses, rules)
    layer2_flags = run_layer2(contract_id, contract.paper_origin, matches)

    all_flags = layer1_flags + layer2_flags
    contract_score = score_flags(contract_id, all_flags, rules)

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
        )
        for f in all_flags
    ]
    persisted_flags = await analysis_repo.bulk_create_flags(session, flag_rows)

    risk_row = RiskScore(
        contract_id=contract_id,
        score=contract_score.score,
        max_clause_severity=contract_score.max_clause_severity,
        weights_version=contract_score.weights_version,
    )
    persisted_risk = await analysis_repo.create_risk_score(session, risk_row)

    contract.status = "analyzed"
    await session.commit()

    flag_dtos = [FlagDTO.model_validate(f) for f in persisted_flags]
    risk_dto = RiskDTO(
        score=persisted_risk.score,
        max_clause_severity=persisted_risk.max_clause_severity,
        weights_version=persisted_risk.weights_version,
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
        )
        if risk is not None
        else None
    )
    return AnalysisResult(flags=flag_dtos, risk=risk_dto)
