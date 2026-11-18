"""Playbook version lifecycle, diff, and rule-child CRUD routes (task 4.8).

Kept in a module separate from ``app/api/routes/playbooks.py`` so this task
never has to touch that file's existing route functions — in particular
``GET /playbooks/resolve``, which a concurrent task (4.2) owns, and
``POST /playbooks/bootstrap``, owned by task 4.1/4.11. ``app/main.py``
auto-discovers every ``router`` under ``app/api/routes/``, so these routes
are picked up with zero changes to ``playbooks.py``.

Route ordering note (same hazard as ``playbooks.py``'s own docstring):
literal sub-paths must be declared before a sibling path with a variable in
the same position, or FastAPI/Starlette will try to parse the literal as the
variable. In this file: ``/playbooks/versions/diff`` before
``/playbooks/versions/{version_id}``. The bare ``/playbooks/red-lines``
(global scope) lives in ``playbooks.py`` instead, next to
``/playbooks/resolve`` — it is two segments, so it collides with
``/playbooks/{playbook_id}`` and needs the same literal-section placement.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.schemas.playbook import (
    PlaybookVersionResponse,
    RedLineCreate,
    RedLineResponse,
    RedLineUpdate,
    RuleDependencyCreate,
    RuleDependencyResponse,
    RuleDependencyUpdate,
    RuleObjectionCreate,
    RuleObjectionResponse,
    RuleObjectionUpdate,
    RuleParameterCreate,
    RuleParameterResponse,
    RuleParameterUpdate,
    RulePositionCreate,
    RulePositionResponse,
    RulePositionUpdate,
    RuleTestCaseCreate,
    RuleTestCaseResponse,
    RuleTestCaseUpdate,
    VersionDiffResponse,
    VersionDraftCreate,
    VersionPublishRequest,
)
from app.services.playbook import versions as versions_service

router = APIRouter(tags=["playbooks"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]

# ── Version lifecycle ────────────────────────────────────────────────────────


@router.get("/playbooks/{playbook_id}/versions", response_model=list[PlaybookVersionResponse])
async def list_versions(
    playbook_id: uuid.UUID, session: SessionDep
) -> list[PlaybookVersionResponse]:
    rows = await versions_service.list_versions(session, playbook_id)
    return [PlaybookVersionResponse.model_validate(v) for v in rows]


@router.post(
    "/playbooks/{playbook_id}/versions", response_model=PlaybookVersionResponse, status_code=201
)
async def create_draft_version(
    playbook_id: uuid.UUID, body: VersionDraftCreate, session: SessionDep
) -> PlaybookVersionResponse:
    version = await versions_service.create_draft(
        session, playbook_id, body.version, body.created_by
    )
    return PlaybookVersionResponse.model_validate(version)


@router.get("/playbooks/versions/diff", response_model=VersionDiffResponse)
async def diff_versions(
    a: Annotated[uuid.UUID, Query(description="First version id")],
    b: Annotated[uuid.UUID, Query(description="Second version id")],
    session: SessionDep,
) -> VersionDiffResponse:
    return await versions_service.diff_versions(session, a, b)


@router.get("/playbooks/versions/{version_id}", response_model=PlaybookVersionResponse)
async def get_version(version_id: uuid.UUID, session: SessionDep) -> PlaybookVersionResponse:
    version = await versions_service.get_version(session, version_id)
    return PlaybookVersionResponse.model_validate(version)


@router.post("/playbooks/versions/{version_id}/publish", response_model=PlaybookVersionResponse)
async def publish_version(
    version_id: uuid.UUID, body: VersionPublishRequest, session: SessionDep
) -> PlaybookVersionResponse:
    version = await versions_service.publish_draft(
        session,
        version_id,
        body.change_summary,
        body.approved_by,
        skip_test_run=body.skip_test_run,
    )
    return PlaybookVersionResponse.model_validate(version)


# ── Rule positions ────────────────────────────────────────────────────────────


@router.get("/playbooks/rules/{rule_id}/positions", response_model=list[RulePositionResponse])
async def list_positions(rule_id: uuid.UUID, session: SessionDep) -> list[RulePositionResponse]:
    rows = await versions_service.list_positions(session, rule_id)
    return [RulePositionResponse.model_validate(p) for p in rows]


@router.post(
    "/playbooks/rules/{rule_id}/positions", response_model=RulePositionResponse, status_code=201
)
async def create_position(
    rule_id: uuid.UUID, body: RulePositionCreate, session: SessionDep
) -> RulePositionResponse:
    position = await versions_service.create_position(session, rule_id, body)
    return RulePositionResponse.model_validate(position)


@router.patch("/playbooks/positions/{position_id}", response_model=RulePositionResponse)
async def update_position(
    position_id: uuid.UUID, body: RulePositionUpdate, session: SessionDep
) -> RulePositionResponse:
    position = await versions_service.update_position(session, position_id, body)
    return RulePositionResponse.model_validate(position)


@router.delete("/playbooks/positions/{position_id}", status_code=204)
async def delete_position(position_id: uuid.UUID, session: SessionDep) -> None:
    await versions_service.delete_position(session, position_id)


# ── Rule parameters ───────────────────────────────────────────────────────────


@router.get("/playbooks/rules/{rule_id}/parameters", response_model=list[RuleParameterResponse])
async def list_parameters(rule_id: uuid.UUID, session: SessionDep) -> list[RuleParameterResponse]:
    rows = await versions_service.list_parameters(session, rule_id)
    return [RuleParameterResponse.model_validate(p) for p in rows]


@router.post(
    "/playbooks/rules/{rule_id}/parameters", response_model=RuleParameterResponse, status_code=201
)
async def create_parameter(
    rule_id: uuid.UUID, body: RuleParameterCreate, session: SessionDep
) -> RuleParameterResponse:
    parameter = await versions_service.create_parameter(session, rule_id, body)
    return RuleParameterResponse.model_validate(parameter)


@router.patch("/playbooks/parameters/{parameter_id}", response_model=RuleParameterResponse)
async def update_parameter(
    parameter_id: uuid.UUID, body: RuleParameterUpdate, session: SessionDep
) -> RuleParameterResponse:
    parameter = await versions_service.update_parameter(session, parameter_id, body)
    return RuleParameterResponse.model_validate(parameter)


@router.delete("/playbooks/parameters/{parameter_id}", status_code=204)
async def delete_parameter(parameter_id: uuid.UUID, session: SessionDep) -> None:
    await versions_service.delete_parameter(session, parameter_id)


# ── Red lines (scope: rule | playbook | global) ──────────────────────────────
#
# Global-scope listing and generic creation live at the bare
# "/playbooks/red-lines" path in ``playbooks.py`` (same ordering reason as
# that file's "/playbooks/resolve": it collides with "/playbooks/{playbook_id}"
# and must be declared in that same literal section). The nested routes here
# are unambiguous (3+ path segments) and need no such ordering care.


@router.get("/playbooks/rules/{rule_id}/red-lines", response_model=list[RedLineResponse])
async def list_rule_red_lines(rule_id: uuid.UUID, session: SessionDep) -> list[RedLineResponse]:
    rows = await versions_service.list_red_lines_for_rule(session, rule_id)
    return [RedLineResponse.model_validate(r) for r in rows]


@router.post(
    "/playbooks/rules/{rule_id}/red-lines", response_model=RedLineResponse, status_code=201
)
async def create_rule_red_line(
    rule_id: uuid.UUID, body: RedLineCreate, session: SessionDep
) -> RedLineResponse:
    """Create a rule-scoped red line. ``scope``/``rule_id`` on the body are
    overridden from the path, so the client only needs to supply the content
    fields."""
    scoped_body = body.model_copy(update={"scope": "rule", "rule_id": rule_id, "playbook_id": None})
    red_line = await versions_service.create_red_line(session, scoped_body)
    return RedLineResponse.model_validate(red_line)


@router.get("/playbooks/{playbook_id}/red-lines", response_model=list[RedLineResponse])
async def list_playbook_red_lines(
    playbook_id: uuid.UUID, session: SessionDep
) -> list[RedLineResponse]:
    rows = await versions_service.list_red_lines_for_playbook(session, playbook_id)
    return [RedLineResponse.model_validate(r) for r in rows]


@router.post("/playbooks/{playbook_id}/red-lines", response_model=RedLineResponse, status_code=201)
async def create_playbook_red_line(
    playbook_id: uuid.UUID, body: RedLineCreate, session: SessionDep
) -> RedLineResponse:
    """Create a playbook-scoped red line. ``scope``/``playbook_id`` on the
    body are overridden from the path."""
    scoped_body = body.model_copy(
        update={"scope": "playbook", "playbook_id": playbook_id, "rule_id": None}
    )
    red_line = await versions_service.create_red_line(session, scoped_body)
    return RedLineResponse.model_validate(red_line)


@router.patch("/playbooks/red-lines/{red_line_id}", response_model=RedLineResponse)
async def update_red_line(
    red_line_id: uuid.UUID, body: RedLineUpdate, session: SessionDep
) -> RedLineResponse:
    red_line = await versions_service.update_red_line(session, red_line_id, body)
    return RedLineResponse.model_validate(red_line)


@router.delete("/playbooks/red-lines/{red_line_id}", status_code=204)
async def delete_red_line(red_line_id: uuid.UUID, session: SessionDep) -> None:
    await versions_service.delete_red_line(session, red_line_id)


# ── Rule objections ───────────────────────────────────────────────────────────


@router.get("/playbooks/rules/{rule_id}/objections", response_model=list[RuleObjectionResponse])
async def list_objections(rule_id: uuid.UUID, session: SessionDep) -> list[RuleObjectionResponse]:
    rows = await versions_service.list_objections(session, rule_id)
    return [RuleObjectionResponse.model_validate(o) for o in rows]


@router.post(
    "/playbooks/rules/{rule_id}/objections", response_model=RuleObjectionResponse, status_code=201
)
async def create_objection(
    rule_id: uuid.UUID, body: RuleObjectionCreate, session: SessionDep
) -> RuleObjectionResponse:
    objection = await versions_service.create_objection(session, rule_id, body)
    return RuleObjectionResponse.model_validate(objection)


@router.patch("/playbooks/objections/{objection_id}", response_model=RuleObjectionResponse)
async def update_objection(
    objection_id: uuid.UUID, body: RuleObjectionUpdate, session: SessionDep
) -> RuleObjectionResponse:
    objection = await versions_service.update_objection(session, objection_id, body)
    return RuleObjectionResponse.model_validate(objection)


@router.delete("/playbooks/objections/{objection_id}", status_code=204)
async def delete_objection(objection_id: uuid.UUID, session: SessionDep) -> None:
    await versions_service.delete_objection(session, objection_id)


# ── Rule dependencies ─────────────────────────────────────────────────────────


@router.get("/playbooks/rules/{rule_id}/dependencies", response_model=list[RuleDependencyResponse])
async def list_dependencies(
    rule_id: uuid.UUID, session: SessionDep
) -> list[RuleDependencyResponse]:
    rows = await versions_service.list_dependencies(session, rule_id)
    return [RuleDependencyResponse.model_validate(d) for d in rows]


@router.post(
    "/playbooks/rules/{rule_id}/dependencies",
    response_model=RuleDependencyResponse,
    status_code=201,
)
async def create_dependency(
    rule_id: uuid.UUID, body: RuleDependencyCreate, session: SessionDep
) -> RuleDependencyResponse:
    dependency = await versions_service.create_dependency(session, rule_id, body)
    return RuleDependencyResponse.model_validate(dependency)


@router.patch("/playbooks/dependencies/{dependency_id}", response_model=RuleDependencyResponse)
async def update_dependency(
    dependency_id: uuid.UUID, body: RuleDependencyUpdate, session: SessionDep
) -> RuleDependencyResponse:
    dependency = await versions_service.update_dependency(session, dependency_id, body)
    return RuleDependencyResponse.model_validate(dependency)


@router.delete("/playbooks/dependencies/{dependency_id}", status_code=204)
async def delete_dependency(dependency_id: uuid.UUID, session: SessionDep) -> None:
    await versions_service.delete_dependency(session, dependency_id)


# ── Rule test cases ───────────────────────────────────────────────────────────


@router.get("/playbooks/rules/{rule_id}/test-cases", response_model=list[RuleTestCaseResponse])
async def list_test_cases(rule_id: uuid.UUID, session: SessionDep) -> list[RuleTestCaseResponse]:
    rows = await versions_service.list_test_cases(session, rule_id)
    return [RuleTestCaseResponse.model_validate(t) for t in rows]


@router.post(
    "/playbooks/rules/{rule_id}/test-cases", response_model=RuleTestCaseResponse, status_code=201
)
async def create_test_case(
    rule_id: uuid.UUID, body: RuleTestCaseCreate, session: SessionDep
) -> RuleTestCaseResponse:
    test_case = await versions_service.create_test_case(session, rule_id, body)
    return RuleTestCaseResponse.model_validate(test_case)


@router.patch("/playbooks/test-cases/{test_case_id}", response_model=RuleTestCaseResponse)
async def update_test_case(
    test_case_id: uuid.UUID, body: RuleTestCaseUpdate, session: SessionDep
) -> RuleTestCaseResponse:
    test_case = await versions_service.update_test_case(session, test_case_id, body)
    return RuleTestCaseResponse.model_validate(test_case)


@router.delete("/playbooks/test-cases/{test_case_id}", status_code=204)
async def delete_test_case(test_case_id: uuid.UUID, session: SessionDep) -> None:
    await versions_service.delete_test_case(session, test_case_id)
