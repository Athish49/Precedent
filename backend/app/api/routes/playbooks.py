"""S6 API — Playbook & Rules CRUD + Resolve endpoints (T-036, T-037).

Route ordering note: /playbooks/resolve MUST be declared before
/playbooks/{playbook_id} to prevent FastAPI treating "resolve" as a UUID.
/playbooks/bootstrap (T-038) belongs in the same literal slot.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.db.repositories import contract_repo, playbook_repo
from app.schemas.playbook import (
    BootstrapRequest,
    BootstrapResponse,
    PlaybookCreate,
    PlaybookResponse,
    PlaybookUpdate,
    PlaybookWithRulesResponse,
    ResolveResponse,
    RuleCreate,
    RuleResponse,
    RuleUpdate,
)
from app.services.playbook import bootstrap as bootstrap_service
from app.services.playbook import service
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
    contract_type: str = Query(..., description="Practice area / contract type to resolve"),
    session: AsyncSession = Depends(_get_session),
) -> ResolveResponse:
    """Return the merged type-keyed rule set for a given contract type.

    Fetches all playbooks whose practice_area applies to *contract_type*,
    then merges rules by precedence (higher wins per clause_type).
    """
    return await resolve_playbooks(session, contract_type)


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
    rules = await playbook_repo.list_rules(session, playbook_id)
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
