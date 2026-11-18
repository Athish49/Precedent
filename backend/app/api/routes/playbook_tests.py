"""Rule test-case runner route (task 4.10 item 5).

Kept in its own file so this task never touches ``app/api/routes/
playbook_versions.py`` (task 4.8's file) beyond what the publish-gate wiring
needed in ``app/services/playbook/versions.py``. ``app/main.py``
auto-discovers every ``router`` under ``app/api/routes/``, so this route is
picked up with zero changes to any other routes file.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory
from app.schemas.playbook_testing import (
    CaseResultResponse,
    GroupStatsResponse,
    TestRunResponse,
    VersionTestRequest,
)
from app.services.playbook import testing as test_runner
from app.services.playbook import versions as versions_service

router = APIRouter(tags=["playbooks"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


def _group_response(groups: dict[str, test_runner.GroupStats]) -> dict[str, GroupStatsResponse]:
    return {
        key: GroupStatsResponse(total=stats.total, passed=stats.passed, pass_rate=stats.pass_rate)
        for key, stats in groups.items()
    }


def _to_response(summary: test_runner.TestRunSummary) -> TestRunResponse:
    return TestRunResponse(
        total_cases=summary.total_cases,
        run_cases=summary.run_cases,
        skipped_cases=summary.skipped_cases,
        passed_cases=summary.passed_cases,
        failed_cases=summary.failed_cases,
        pass_rate=summary.pass_rate,
        meets_threshold=summary.meets_threshold,
        model_calls_required=summary.model_calls_required,
        model_calls_made=summary.model_calls_made,
        by_playbook=_group_response(summary.by_playbook),
        by_rule=_group_response(summary.by_rule),
        by_expected_outcome=_group_response(summary.by_expected_outcome),
        failures=[
            CaseResultResponse(
                playbook_key=f.playbook_key,
                rule_key=f.rule_key,
                test_case_name=f.test_case_name,
                expected_outcome=f.expected_outcome,
                expected_zone=f.expected_zone,
                expected_position_rung=f.expected_position_rung,
                expected_red_line_key=f.expected_red_line_key,
                actual_outcome=f.actual_outcome,
                actual_zone=f.actual_zone,
                actual_position_rung=f.actual_position_rung,
                actual_red_line_key=f.actual_red_line_key,
                passed=f.passed,
                skipped=f.skipped,
                skip_reason=f.skip_reason,
                reason=f.reason,
                is_trap=f.is_trap,
            )
            for f in summary.failures
        ],
    )


@router.post("/playbooks/versions/{version_id}/test", response_model=TestRunResponse)
async def test_version(
    version_id: uuid.UUID, body: VersionTestRequest, session: SessionDep
) -> TestRunResponse:
    """Run every rule's test cases for *version_id* and return the pass-rate
    summary (``app/services/playbook/testing.py``). Defaults to deterministic
    mode — set ``deterministic: false`` to opt into the cost-bearing default
    mode, which makes one batched model call per case that needs it."""
    summary = await versions_service.run_tests_for_version(
        session, version_id, deterministic=body.deterministic
    )
    return _to_response(summary)
