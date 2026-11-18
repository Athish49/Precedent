"""Request/response schemas for the rule test-case runner (task 4.10).

Kept separate from ``app/schemas/playbook.py`` (task 4.8's file) since this
task owns its own new route and service module and does not need to touch
that file beyond the one ``VersionPublishRequest.skip_test_run`` field the
publish-gate wiring requires.
"""

from __future__ import annotations

from pydantic import BaseModel


class VersionTestRequest(BaseModel):
    """Body for ``POST /playbooks/versions/{version_id}/test``.

    ``deterministic`` defaults to ``True`` (free, no model calls) — an API
    caller must explicitly opt into the cost-bearing default mode by setting
    this to ``False``, since there is no interactive confirmation prompt at
    this layer the way there is in ``scripts/run_rule_tests.py``.
    """

    deterministic: bool = True


class GroupStatsResponse(BaseModel):
    total: int
    passed: int
    pass_rate: float


class CaseResultResponse(BaseModel):
    playbook_key: str
    rule_key: str
    test_case_name: str
    expected_outcome: str
    expected_zone: str | None = None
    expected_position_rung: int | None = None
    expected_red_line_key: str | None = None
    actual_outcome: str | None = None
    actual_zone: str | None = None
    actual_position_rung: int | None = None
    actual_red_line_key: str | None = None
    passed: bool
    skipped: bool
    skip_reason: str | None = None
    reason: str | None = None
    is_trap: bool


class TestRunResponse(BaseModel):
    total_cases: int
    run_cases: int
    skipped_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    meets_threshold: bool
    model_calls_required: int
    model_calls_made: int
    by_playbook: dict[str, GroupStatsResponse]
    by_rule: dict[str, GroupStatsResponse]
    by_expected_outcome: dict[str, GroupStatsResponse]
    failures: list[CaseResultResponse]
