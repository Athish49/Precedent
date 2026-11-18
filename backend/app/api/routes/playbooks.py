"""S6 API — Playbook & Rules CRUD + Resolve endpoints (T-036, T-037).

Route ordering note: /playbooks/resolve MUST be declared before
/playbooks/{playbook_id} to prevent FastAPI treating "resolve" as a UUID.
/playbooks/bootstrap (T-038) belongs in the same literal slot.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.base import get_session_factory
from app.db.repositories import authority_repo, contract_repo, playbook_repo, taxonomy_repo
from app.schemas.playbook import (
    AgreementTypeResponse,
    ApproverRoleResponse,
    BootstrapRequest,
    BootstrapResponse,
    ClauseFamilyResponse,
    ClauseIssueResponse,
    ContextDimensionResponse,
    EscalationPolicyResponse,
    PlaybookCreate,
    PlaybookResponse,
    PlaybookUpdate,
    PlaybookWithRulesResponse,
    RedLineCreate,
    RedLineResponse,
    ResolveResponse,
    RuleCreate,
    RuleResponse,
    RuleUpdate,
    TaxonomyListResponse,
)
from app.services.playbook import bootstrap as bootstrap_service
from app.services.playbook import service
from app.services.playbook import versions as versions_service
from app.services.playbook.routing import resolve as resolve_playbooks

router = APIRouter(tags=["playbooks"])

# ── Session dependency ────────────────────────────────────────────────────────


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]

# ── Playbook list + create ────────────────────────────────────────────────────


@router.get("/playbooks", response_model=list[PlaybookResponse])
async def list_playbooks(session: SessionDep) -> list[PlaybookResponse]:
    playbooks = await service.list_playbooks(session)
    return [PlaybookResponse.model_validate(pb) for pb in playbooks]


@router.post("/playbooks", response_model=PlaybookResponse, status_code=201)
async def create_playbook(body: PlaybookCreate, session: SessionDep) -> PlaybookResponse:
    pb = await service.create_playbook(session, body)
    return PlaybookResponse.model_validate(pb)


# ── Literal sub-paths (before /{playbook_id}) ────────────────────────────────


@router.get("/playbooks/resolve", response_model=ResolveResponse)
async def resolve(
    contract_type: str = Query(..., description="Contract type / practice area to resolve"),
    party_role: str = Query(
        "vendor", description="Halcyon's role in the deal: vendor, customer or mutual"
    ),
    paper_origin: str = Query(
        "own", description="Whose paper the contract is on: own or counterparty"
    ),
    context: str | None = Query(
        None,
        description=(
            "JSON-encoded context object, e.g. "
            '{"deal_value_band": "mid", "regimes": ["hipaa"]}'
        ),
    ),
    session: AsyncSession = Depends(_get_session),
) -> ResolveResponse:
    """Resolve and merge every applicable playbook for one deal's facts
    (``playbook_plan.md`` section 5.1): the base playbook, the agreement
    playbook matching *contract_type*/*party_role*/*paper_origin*, and every
    overlay whose ``applies_when`` matches *context*.
    """
    parsed_context: dict = {}
    if context:
        try:
            parsed_context = json.loads(context)
        except ValueError as exc:
            raise AppError(400, "invalid_context", "context must be a JSON object") from exc
        if not isinstance(parsed_context, dict):
            raise AppError(400, "invalid_context", "context must be a JSON object")
    return await resolve_playbooks(session, contract_type, party_role, paper_origin, parsed_context)


@router.post("/playbooks/bootstrap", response_model=BootstrapResponse)
async def bootstrap_playbook(
    body: BootstrapRequest,
    session: AsyncSession = Depends(_get_session),
) -> BootstrapResponse:
    """Seed a playbook with rules extracted from a contract corpus via batch LLM.

    Accepts either an explicit list of contract IDs or a contract_type filter
    (loads up to 1 000 contracts of that type).  Clause types that already
    have a rule in the playbook are skipped.
    """
    if body.contract_ids:
        contract_ids = body.contract_ids
    else:
        contracts, _ = await contract_repo.list_contracts(
            session,
            contract_type=body.contract_type,
            limit=1000,
        )
        contract_ids = [c.id for c in contracts]

    count = await bootstrap_service.run_bootstrap(session, body.playbook_id, contract_ids)
    return BootstrapResponse(created_rule_count=count)


# ── Taxonomy, authority and global-red-line lookups (task 4.8 item 6) ───────
#
# These sit at a bare "/playbooks/<literal>" path, the same shape as
# "/playbooks/resolve" and "/playbooks/bootstrap" above, and for the same
# reason must be declared before "/playbooks/{playbook_id}" below: Starlette
# matches that pattern's default string converter against any single path
# segment, so a literal declared after it would never be reached — the
# request would 422 trying to parse e.g. "taxonomy" as a UUID instead.


@router.get("/playbooks/taxonomy", response_model=TaxonomyListResponse)
async def list_taxonomy(session: SessionDep) -> TaxonomyListResponse:
    """Agreement types, clause families and clause issues in one read."""
    agreement_types = await taxonomy_repo.list_agreement_types(session)
    clause_families = await taxonomy_repo.list_clause_families(session)
    clause_issues = await taxonomy_repo.list_clause_issues(session)
    return TaxonomyListResponse(
        agreement_types=[AgreementTypeResponse.model_validate(a) for a in agreement_types],
        clause_families=[ClauseFamilyResponse.model_validate(f) for f in clause_families],
        clause_issues=[ClauseIssueResponse.model_validate(i) for i in clause_issues],
    )


@router.get("/playbooks/roles", response_model=list[ApproverRoleResponse])
async def list_roles(session: SessionDep) -> list[ApproverRoleResponse]:
    roles = await authority_repo.list_approver_roles(session)
    return [ApproverRoleResponse.model_validate(r) for r in roles]


@router.get("/playbooks/context-dimensions", response_model=list[ContextDimensionResponse])
async def list_context_dimensions(session: SessionDep) -> list[ContextDimensionResponse]:
    dimensions = await taxonomy_repo.list_context_dimensions(session)
    return [ContextDimensionResponse.model_validate(d) for d in dimensions]


@router.get("/playbooks/escalation-policies", response_model=list[EscalationPolicyResponse])
async def list_escalation_policies(
    session: SessionDep,
    playbook_id: uuid.UUID | None = Query(None),
    clause_type: str | None = Query(None),
    zone: str | None = Query(None),
) -> list[EscalationPolicyResponse]:
    policies = await authority_repo.list_escalation_policies(
        session, playbook_id=playbook_id, clause_type=clause_type, zone=zone
    )
    return [EscalationPolicyResponse.model_validate(p) for p in policies]


@router.get("/playbooks/red-lines", response_model=list[RedLineResponse])
async def list_global_red_lines(session: SessionDep) -> list[RedLineResponse]:
    """Global-scope red lines (apply to every playbook).

    Playbook-scoped and rule-scoped red lines are listed and created at
    ``/playbooks/{playbook_id}/red-lines`` and ``/playbooks/rules/{rule_id}/red-lines``
    (``app/api/routes/playbook_versions.py``).
    """
    red_lines = await versions_service.list_global_red_lines(session)
    return [RedLineResponse.model_validate(r) for r in red_lines]


@router.post("/playbooks/red-lines", response_model=RedLineResponse, status_code=201)
async def create_red_line(body: RedLineCreate, session: SessionDep) -> RedLineResponse:
    """Create a red line at any scope. A rule-scoped one is draft-gated and
    logged to ``playbook_change_log``; playbook- and global-scoped ones are
    not attached to any version.
    """
    red_line = await versions_service.create_red_line(session, body)
    return RedLineResponse.model_validate(red_line)


# ── Rule sub-resource (prefix playbooks/rules/) — before /{id} to avoid ambiguity ──


@router.patch("/playbooks/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: uuid.UUID, body: RuleUpdate, session: SessionDep
) -> RuleResponse:
    rule = await service.update_rule(session, rule_id, body)
    return RuleResponse.model_validate(rule)


@router.delete("/playbooks/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: uuid.UUID, session: SessionDep) -> None:
    await service.delete_rule(session, rule_id)


# ── Single playbook (/playbooks/{id}) — MUST come after all literals ──────────


@router.get("/playbooks/{playbook_id}", response_model=PlaybookWithRulesResponse)
async def get_playbook(
    playbook_id: uuid.UUID, session: SessionDep
) -> PlaybookWithRulesResponse:
    pb = await service.get_playbook(session, playbook_id)
    rules = await playbook_repo.list_rules_with_children(session, playbook_id)
    response = PlaybookWithRulesResponse.model_validate(pb)
    response.rules = [RuleResponse.model_validate(r) for r in rules]
    return response


@router.patch("/playbooks/{playbook_id}", response_model=PlaybookResponse)
async def update_playbook(
    playbook_id: uuid.UUID, body: PlaybookUpdate, session: SessionDep
) -> PlaybookResponse:
    pb = await service.update_playbook(session, playbook_id, body)
    return PlaybookResponse.model_validate(pb)


@router.delete("/playbooks/{playbook_id}", status_code=204)
async def delete_playbook(playbook_id: uuid.UUID, session: SessionDep) -> None:
    await service.delete_playbook(session, playbook_id)


# ── Rules nested under playbook ───────────────────────────────────────────────


@router.get("/playbooks/{playbook_id}/rules", response_model=list[RuleResponse])
async def list_rules(
    playbook_id: uuid.UUID, session: SessionDep
) -> list[RuleResponse]:
    rules = await service.list_rules(session, playbook_id)
    return [RuleResponse.model_validate(r) for r in rules]


@router.post("/playbooks/{playbook_id}/rules", response_model=RuleResponse, status_code=201)
async def create_rule(
    playbook_id: uuid.UUID, body: RuleCreate, session: SessionDep
) -> RuleResponse:
    rule = await service.create_rule(session, playbook_id, body)
    return RuleResponse.model_validate(rule)
