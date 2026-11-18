"""Tests for ``POST /api/playbooks/versions/{version_id}/test`` (task 4.10
item 5, ``app/api/routes/playbook_tests.py``).

Same approach as ``test_playbook_versions_api.py``: a dependency override
swaps in a mocked ``AsyncSession``, and ``app.db.repositories.playbook_repo``
functions are patched directly so no real database is touched.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.playbook_tests import _get_session as _pt_get_session
from app.core.llm.schemas.analysis import ExtractedPositionOut, RuleExtractionOut
from app.db.models.playbook import PlaybookRule, PlaybookVersion, RulePosition, RuleTestCase
from app.main import app
from app.services.playbook import testing as test_runner

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset():
    previous = app.dependency_overrides.get(_pt_get_session)
    app.dependency_overrides[_pt_get_session] = _mock_get_session
    yield
    if previous is not None:
        app.dependency_overrides[_pt_get_session] = previous
    else:
        app.dependency_overrides.pop(_pt_get_session, None)


def _make_version(version_id: uuid.UUID, playbook_id: uuid.UUID) -> MagicMock:
    v = MagicMock(spec=PlaybookVersion)
    v.id = version_id
    v.playbook_id = playbook_id
    return v


def _passing_rule() -> MagicMock:
    rule = MagicMock(spec=PlaybookRule)
    rule.id = uuid.uuid4()
    rule.rule_key = "security.safeguards"
    rule.default_zone = "yellow"
    rule.positions = []
    rule.parameters = []
    rule.red_lines = []

    missing_case = MagicMock(spec=RuleTestCase)
    missing_case.name = "No safeguards clause"
    missing_case.sample_text = ""
    missing_case.context = None
    missing_case.expected_outcome = "missing"
    missing_case.expected_zone = "yellow"
    missing_case.expected_position_rung = None
    missing_case.expected_red_line_key = None
    missing_case.is_trap = False
    rule.test_cases = [missing_case]
    return rule


def _model_required_rule() -> MagicMock:
    preferred = MagicMock(spec=RulePosition)
    preferred.id = uuid.uuid4()
    preferred.kind = "preferred"
    preferred.label = "Preferred"
    preferred.rung = None
    preferred.zone = "green"
    preferred.summary = "Preferred language."
    preferred.language = "Preferred language."

    rule = MagicMock(spec=PlaybookRule)
    rule.id = uuid.uuid4()
    rule.rule_key = "limitation_of_liability.cap_amount"
    rule.title = "Cap"
    rule.clause_type = "limitation_of_liability"
    rule.position_summary = "Cap at 12 months."
    rule.detection_guidance = "Look for a cap."
    rule.default_zone = "red"
    rule.positions = [preferred]
    rule.parameters = []
    rule.red_lines = []

    case = MagicMock(spec=RuleTestCase)
    case.name = "12-month cap"
    case.sample_text = "Liability capped at 12 months of fees."
    case.context = None
    case.expected_outcome = "compliant"
    case.expected_zone = "green"
    case.expected_position_rung = None
    case.expected_red_line_key = None
    case.is_trap = False
    rule.test_cases = [case]
    return rule, preferred


def test_test_version_not_found() -> None:
    version_id = uuid.uuid4()
    with patch(
        "app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=None)
    ):
        response = client.post(f"/api/playbooks/versions/{version_id}/test", json={})
    assert response.status_code == 404


def test_test_version_deterministic_by_default() -> None:
    version_id = uuid.uuid4()
    playbook_id = uuid.uuid4()
    version = _make_version(version_id, playbook_id)
    rule = _passing_rule()

    with (
        patch("app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=version)),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=AsyncMock(return_value=[rule]),
        ),
    ):
        response = client.post(f"/api/playbooks/versions/{version_id}/test", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["run_cases"] == 1
    assert body["passed_cases"] == 1
    assert body["failed_cases"] == 0
    assert body["pass_rate"] == 1.0
    assert body["meets_threshold"] is True
    assert body["model_calls_made"] == 0


def test_test_version_opt_in_default_mode_calls_model() -> None:
    version_id = uuid.uuid4()
    playbook_id = uuid.uuid4()
    version = _make_version(version_id, playbook_id)
    rule, preferred = _model_required_rule()

    extraction = RuleExtractionOut(
        rule_key=rule.rule_key,
        position=ExtractedPositionOut(
            match_kind="preferred", position_label=preferred.label, quote="12 months"
        ),
        parameters=[],
        red_lines=[],
    )

    class _FakeGateway:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def call_batch(self, task, items, response_model, cache_prefix=None):  # noqa: ANN001
            self.calls.append({"task": task, "items": items})
            return {"0": extraction}

    fake = _FakeGateway()

    with (
        patch("app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=version)),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=AsyncMock(return_value=[rule]),
        ),
        patch.object(test_runner, "gateway", fake),
    ):
        response = client.post(
            f"/api/playbooks/versions/{version_id}/test", json={"deterministic": False}
        )

    assert response.status_code == 200
    body = response.json()
    assert len(fake.calls) == 1
    assert body["model_calls_made"] == 1
    assert body["passed_cases"] == 1
    assert body["failed_cases"] == 0
