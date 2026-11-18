"""Unit tests for task 4.8 — playbook version lifecycle, diff, and
rule-child CRUD endpoints (``app/api/routes/playbook_versions.py``,
``app/api/routes/playbooks.py``'s new lookup routes).

Same approach as the existing ``test_playbooks_api.py``: a dependency
override swaps in a mocked ``AsyncSession``, and ``app.db.repositories.*``
functions are patched directly with ``AsyncMock`` so no real database is
touched (``playbook_implementation.md`` section 1: "Write and test against
mocked sessions").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.playbook_versions import _get_session as _pv_get_session
from app.api.routes.playbooks import _get_session as _pb_get_session
from app.db.models.playbook import (
    PlaybookRule,
    PlaybookVersion,
    RedLine,
    RuleObjection,
    RulePosition,
    RuleTestCase,
)
from app.main import app

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


client = TestClient(app, raise_server_exceptions=False)


def _reset_session() -> None:
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


def _make_version(
    version_id: uuid.UUID | None = None,
    playbook_id: uuid.UUID | None = None,
    status: str = "draft",
    change_summary: str | None = "Initial draft",
) -> MagicMock:
    v = MagicMock(spec=PlaybookVersion)
    v.id = version_id or uuid.uuid4()
    v.playbook_id = playbook_id or uuid.uuid4()
    v.version = "1.1"
    v.status = status
    v.effective_from = None
    v.effective_to = None
    v.change_summary = change_summary
    v.created_by = "tester"
    v.approved_by = None
    v.published_at = None
    v.created_at = _NOW
    v.updated_at = _NOW
    return v


def _make_rule(
    rule_id: uuid.UUID | None = None,
    playbook_version_id: uuid.UUID | None = None,
    rule_key: str = "liability-cap",
    negotiable: bool = False,
    risk_weight: float = 1.0,
    risk_rationale: str = "This is sentence one. This is sentence two.",
    positions: list | None = None,
    red_lines: list | None = None,
    objections: list | None = None,
    test_cases: list | None = None,
) -> MagicMock:
    rule = MagicMock(spec=PlaybookRule)
    rule.id = rule_id or uuid.uuid4()
    rule.playbook_id = uuid.uuid4()
    rule.playbook_version_id = playbook_version_id
    rule.clause_type = "liability"
    rule.issue_id = None
    rule.rule_key = rule_key
    rule.title = "Liability cap"
    rule.negotiable = negotiable
    rule.risk_weight = risk_weight
    rule.risk_rationale = risk_rationale
    rule.position_summary = None
    rule.default_zone = None
    rule.needs_human_judgment = None
    rule.judgment_note = None
    rule.applies_when = None
    rule.detection_guidance = None
    rule.source_ref = None
    rule.authored_by = None
    rule.approved_by = None
    rule.last_reviewed_at = None
    rule.required = True
    rule.positions = positions if positions is not None else []
    rule.parameters = []
    rule.red_lines = red_lines if red_lines is not None else []
    rule.objections = objections if objections is not None else []
    rule.dependencies = []
    rule.test_cases = test_cases if test_cases is not None else []
    return rule


def _compliant_rule(
    rule_id: uuid.UUID | None = None, playbook_version_id: uuid.UUID | None = None
) -> MagicMock:
    """A rule that satisfies every minimum from playbook_plan.md section 7.2."""
    preferred = MagicMock(spec=RulePosition)
    preferred.kind = "preferred"
    variant = MagicMock(spec=RulePosition)
    variant.kind = "acceptable_variant"
    return _make_rule(
        rule_id=rule_id,
        playbook_version_id=playbook_version_id,
        negotiable=False,
        risk_weight=3.0,
        positions=[preferred, variant],
        test_cases=[MagicMock(spec=RuleTestCase) for _ in range(5)],
    )


def _make_position(
    position_id: uuid.UUID | None = None, rule_id: uuid.UUID | None = None
) -> MagicMock:
    p = MagicMock(spec=RulePosition)
    p.id = position_id or uuid.uuid4()
    p.rule_id = rule_id or uuid.uuid4()
    p.kind = "fallback"
    p.rung = 1
    p.label = "Fallback 1"
    p.language = "Liability is capped at 18 months of fees."
    p.summary = None
    p.zone = "yellow"
    p.approver_role_id = None
    p.conditions = None
    p.give_get = None
    p.internal_note = None
    p.created_at = _NOW
    p.updated_at = _NOW
    return p


def _make_red_line(
    red_line_id: uuid.UUID | None = None,
    scope: str = "global",
    rule_id: uuid.UUID | None = None,
    playbook_id: uuid.UUID | None = None,
) -> MagicMock:
    r = MagicMock(spec=RedLine)
    r.id = red_line_id or uuid.uuid4()
    r.scope = scope
    r.rule_id = rule_id
    r.playbook_id = playbook_id
    r.key = "uncapped-liability"
    r.description = "Uncapped aggregate liability for Halcyon."
    r.condition_type = "phrase"
    r.condition = {"phrases": ["uncapped liability"]}
    r.action = "block"
    r.approver_role_id = None
    r.rationale = None
    r.created_at = _NOW
    r.updated_at = _NOW
    return r


@pytest.fixture(autouse=True)
def _reset():
    # ``app.api.routes.playbooks._get_session`` is overridden both here and
    # in ``test_playbooks_api.py`` (same dependency key: both exercise
    # routes in ``playbooks.py``). Save/restore around each test rather than
    # setting it once at import time, so this file's tests and that file's
    # tests give each other back whatever override was in place before —
    # correct regardless of which module pytest collects first.
    previous_pv = app.dependency_overrides.get(_pv_get_session)
    previous_pb = app.dependency_overrides.get(_pb_get_session)
    app.dependency_overrides[_pv_get_session] = _mock_get_session
    app.dependency_overrides[_pb_get_session] = _mock_get_session
    _reset_session()
    yield
    if previous_pv is not None:
        app.dependency_overrides[_pv_get_session] = previous_pv
    else:
        app.dependency_overrides.pop(_pv_get_session, None)
    if previous_pb is not None:
        app.dependency_overrides[_pb_get_session] = previous_pb
    else:
        app.dependency_overrides.pop(_pb_get_session, None)


# ---------------------------------------------------------------------------
# Version lifecycle: list / create draft
# ---------------------------------------------------------------------------


def test_list_versions_not_found() -> None:
    with patch("app.db.repositories.playbook_repo.get_playbook", new=AsyncMock(return_value=None)):
        response = client.get(f"/api/playbooks/{uuid.uuid4()}/versions")
    assert response.status_code == 404


def test_list_versions_success() -> None:
    pb_id = uuid.uuid4()
    pb = MagicMock(current_version_id=uuid.uuid4())
    version = _make_version(playbook_id=pb_id)
    with (
        patch("app.db.repositories.playbook_repo.get_playbook", new=AsyncMock(return_value=pb)),
        patch(
            "app.db.repositories.playbook_repo.list_versions",
            new=AsyncMock(return_value=[version]),
        ),
    ):
        response = client.get(f"/api/playbooks/{pb_id}/versions")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_draft_no_current_version() -> None:
    pb = MagicMock(current_version_id=None)
    with patch("app.db.repositories.playbook_repo.get_playbook", new=AsyncMock(return_value=pb)):
        response = client.post(
            f"/api/playbooks/{uuid.uuid4()}/versions", json={"version": "1.1"}
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "no_current_version"


def test_create_draft_success() -> None:
    current_id = uuid.uuid4()
    pb = MagicMock(current_version_id=current_id)
    new_version = _make_version(status="draft")
    with (
        patch("app.db.repositories.playbook_repo.get_playbook", new=AsyncMock(return_value=pb)),
        patch(
            "app.db.repositories.playbook_repo.copy_version",
            new=AsyncMock(return_value=new_version),
        ) as copy_mock,
    ):
        response = client.post(
            f"/api/playbooks/{uuid.uuid4()}/versions",
            json={"version": "1.1", "created_by": "tester"},
        )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    copy_mock.assert_awaited_once()
    assert copy_mock.call_args.args[1] == current_id


# ---------------------------------------------------------------------------
# Publish: draft-publish cycle, 409 on non-draft, 400 on minimums
# ---------------------------------------------------------------------------


def test_publish_requires_draft_409() -> None:
    version_id = uuid.uuid4()
    published_version = _make_version(version_id=version_id, status="published")
    with patch(
        "app.db.repositories.playbook_repo.get_version",
        new=AsyncMock(return_value=published_version),
    ):
        response = client.post(
            f"/api/playbooks/versions/{version_id}/publish",
            json={"change_summary": "x", "approved_by": "gc"},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_not_draft"


def test_publish_requires_approver() -> None:
    version_id = uuid.uuid4()
    draft = _make_version(version_id=version_id, status="draft")
    with patch(
        "app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=draft)
    ):
        response = client.post(
            f"/api/playbooks/versions/{version_id}/publish",
            json={"change_summary": "x"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "approver_required"


def test_publish_minimums_not_met() -> None:
    version_id = uuid.uuid4()
    draft = _make_version(version_id=version_id, status="draft")
    incomplete_rule = _make_rule(playbook_version_id=version_id, positions=[], test_cases=[])
    with (
        patch(
            "app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=draft)
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=AsyncMock(return_value=[incomplete_rule]),
        ),
    ):
        response = client.post(
            f"/api/playbooks/versions/{version_id}/publish",
            json={"change_summary": "x", "approved_by": "gc"},
        )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "minimums_not_met"
    assert "liability-cap" in body["error"]["detail"]
    assert "missing a 'preferred' position" in body["error"]["detail"]["liability-cap"]


def test_publish_success_full_cycle() -> None:
    """The draft-publish cycle: create a draft, then publish it once its
    one rule satisfies every minimum."""
    version_id = uuid.uuid4()
    draft = _make_version(version_id=version_id, status="draft", change_summary="Q1 refresh")
    compliant = _compliant_rule(playbook_version_id=version_id)
    published = _make_version(version_id=version_id, status="published")

    with (
        patch(
            "app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=draft)
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=AsyncMock(return_value=[compliant]),
        ),
        patch(
            "app.db.repositories.playbook_repo.publish_version",
            new=AsyncMock(return_value=published),
        ) as publish_mock,
    ):
        response = client.post(
            f"/api/playbooks/versions/{version_id}/publish",
            json={"approved_by": "general_counsel"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    publish_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Publish gate: task 4.10's test-case pass-rate threshold
# ---------------------------------------------------------------------------


def _rule_with_one_failing_missing_case(
    playbook_version_id: uuid.UUID,
) -> MagicMock:
    """Satisfies every task 4.8 minimum (preferred + acceptable_variant
    positions, >= 5 test cases, two-sentence rationale, low risk_weight so no
    red line is required) but fails the new deterministic test-case gate:
    its one decidable ('missing') case expects a zone its rule.default_zone
    does not produce. The other four test cases are plain mocks with no
    real sample_text/expected_outcome set — not decidable deterministically,
    so the gate (always deterministic) skips them and judges on the one
    decided case alone."""
    preferred = MagicMock(spec=RulePosition)
    preferred.kind = "preferred"
    variant = MagicMock(spec=RulePosition)
    variant.kind = "acceptable_variant"

    failing_case = MagicMock(spec=RuleTestCase)
    failing_case.name = "No clause at all"
    failing_case.sample_text = ""
    failing_case.context = None
    failing_case.expected_outcome = "missing"
    failing_case.expected_zone = "yellow"  # rule.default_zone is None -> actual zone "red"
    failing_case.expected_position_rung = None
    failing_case.expected_red_line_key = None
    failing_case.is_trap = False

    other_cases = [MagicMock(spec=RuleTestCase) for _ in range(4)]

    rule = _make_rule(
        playbook_version_id=playbook_version_id,
        negotiable=False,
        risk_weight=3.0,
        positions=[preferred, variant],
        test_cases=[failing_case, *other_cases],
    )
    rule.default_zone = None
    return rule


def test_publish_blocked_when_test_pass_rate_below_threshold() -> None:
    version_id = uuid.uuid4()
    draft = _make_version(version_id=version_id, status="draft")
    failing_rule = _rule_with_one_failing_missing_case(playbook_version_id=version_id)

    with (
        patch(
            "app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=draft)
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=AsyncMock(return_value=[failing_rule]),
        ),
        patch(
            "app.db.repositories.playbook_repo.publish_version"
        ) as publish_mock,
    ):
        response = client.post(
            f"/api/playbooks/versions/{version_id}/publish",
            json={"approved_by": "general_counsel"},
        )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "test_pass_rate_below_threshold"
    assert body["error"]["detail"]["pass_rate"] == 0.0
    publish_mock.assert_not_called()


def test_publish_succeeds_with_skip_test_run() -> None:
    """``skip_test_run: true`` bypasses the new gate entirely, so the same
    failing rule that blocks publish above does not block it here."""
    version_id = uuid.uuid4()
    draft = _make_version(version_id=version_id, status="draft")
    failing_rule = _rule_with_one_failing_missing_case(playbook_version_id=version_id)
    published = _make_version(version_id=version_id, status="published")

    with (
        patch(
            "app.db.repositories.playbook_repo.get_version", new=AsyncMock(return_value=draft)
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=AsyncMock(return_value=[failing_rule]),
        ),
        patch(
            "app.db.repositories.playbook_repo.publish_version",
            new=AsyncMock(return_value=published),
        ) as publish_mock,
    ):
        response = client.post(
            f"/api/playbooks/versions/{version_id}/publish",
            json={"approved_by": "general_counsel", "skip_test_run": True},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    publish_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def test_diff_versions() -> None:
    version_a_id, version_b_id = uuid.uuid4(), uuid.uuid4()
    rule_a = _make_rule(rule_key="same-rule", risk_weight=1.0)
    rule_a_changed_key = rule_a.rule_key
    rule_b = _make_rule(rule_key="same-rule", risk_weight=5.0)
    rule_b.id = rule_a.id
    only_in_b = _make_rule(rule_key="new-rule")

    async def _fake_get_version(session, vid):
        return _make_version(version_id=vid)

    async def _fake_get_rules_with_children(session, vid):
        if vid == version_a_id:
            return [rule_a]
        return [rule_b, only_in_b]

    with (
        patch(
            "app.db.repositories.playbook_repo.get_version", new=_fake_get_version
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=_fake_get_rules_with_children,
        ),
    ):
        response = client.get(
            f"/api/playbooks/versions/diff?a={version_a_id}&b={version_b_id}"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["rules_added"] == ["new-rule"]
    assert body["rules_removed"] == []
    assert len(body["rules_modified"]) == 1
    modified = body["rules_modified"][0]
    assert modified["rule_key"] == rule_a_changed_key
    changed_fields = {f["field"] for f in modified["field_changes"]}
    assert "risk_weight" in changed_fields
    # The five legacy flat fields are gone from the diff (migration 015).
    for legacy in ("preferred_language", "acceptable_variations", "prohibited_terms",
                   "fallback_language", "escalation_threshold"):
        assert legacy not in changed_fields
    assert modified["child_changes"] == []


def _position_row(
    rule_id: uuid.UUID, kind: str, rung: int | None, label: str, language: str, zone: str
) -> RulePosition:
    """A real (unsaved) RulePosition with a fresh id, as copy_version makes."""
    return RulePosition(
        id=uuid.uuid4(), rule_id=rule_id, kind=kind, rung=rung, label=label,
        language=language, summary=None, zone=zone, approver_role_id=None,
        conditions=None, give_get=None, internal_note=None,
        created_at=_NOW, updated_at=_NOW,
    )


def _red_line_row(rule_id: uuid.UUID, key: str, phrase: str) -> RedLine:
    return RedLine(
        id=uuid.uuid4(), scope="rule", rule_id=rule_id, playbook_id=None, key=key,
        description=f"Prohibited term: {phrase!r}.", condition_type="phrase",
        condition={"any": [phrase], "negation_guard": True}, action="block",
        approver_role_id=None, rationale=None, created_at=_NOW, updated_at=_NOW,
    )


def _objection_row(rule_id: uuid.UUID, recommended: RulePosition | None) -> RuleObjection:
    return RuleObjection(
        id=uuid.uuid4(), rule_id=rule_id, objection="Too low.", their_rationale=None,
        response="We disagree.", talking_points=None,
        recommended_position_id=recommended.id if recommended else None,
        frequency=None, counterparty_profile=None, created_at=_NOW, updated_at=_NOW,
    )


def test_diff_versions_child_rows() -> None:
    """Task 5.5: what the legacy flat fields used to show in the change log
    (preferred / fallback / variant language, prohibited terms) now shows
    as row-level child changes, matched by natural key across versions.

    Rows copied unchanged, with fresh ids, do not show up at all.
    """
    version_a_id, version_b_id = uuid.uuid4(), uuid.uuid4()
    rule_a = _make_rule(rule_key="cap")
    rule_b = _make_rule(rule_key="cap")

    pref_a = _position_row(rule_a.id, "preferred", 0, "Preferred", "12 months.", "green")
    var_a = _position_row(rule_a.id, "acceptable_variant", None, "Variant 1", "One year.", "green")
    rule_a.positions = [pref_a, var_a]
    rule_a.red_lines = [_red_line_row(rule_a.id, "no-unlimited", "unlimited liability")]
    rule_a.objections = [_objection_row(rule_a.id, pref_a)]

    pref_b = _position_row(rule_b.id, "preferred", 0, "Preferred", "18 months.", "green")
    var_b = _position_row(rule_b.id, "acceptable_variant", None, "Variant 1", "One year.", "green")
    fb_b = _position_row(rule_b.id, "fallback", 1, "Fallback 1", "24 months.", "yellow")
    rule_b.positions = [pref_b, var_b, fb_b]
    rule_b.red_lines = []
    # Same objection, still recommending the preferred position: the ids
    # differ but the natural key ("preferred:0") is the same, so no change.
    rule_b.objections = [_objection_row(rule_b.id, pref_b)]

    async def _fake_get_version(session, vid):
        return _make_version(version_id=vid)

    async def _fake_get_rules_with_children(session, vid):
        return [rule_a] if vid == version_a_id else [rule_b]

    with (
        patch("app.db.repositories.playbook_repo.get_version", new=_fake_get_version),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=_fake_get_rules_with_children,
        ),
    ):
        response = client.get(f"/api/playbooks/versions/diff?a={version_a_id}&b={version_b_id}")

    assert response.status_code == 200
    (modified,) = response.json()["rules_modified"]
    assert modified["field_changes"] == []
    changes = {(c["child_type"], c["key"]): c for c in modified["child_changes"]}
    assert set(changes) == {
        ("positions", "preferred:0"),
        ("positions", "fallback:1"),
        ("red_lines", "no-unlimited"),
    }

    preferred = changes[("positions", "preferred:0")]
    assert preferred["change_type"] == "modified"
    assert preferred["changed_fields"] == ["language"]
    assert preferred["old_value"]["language"] == "12 months."
    assert preferred["new_value"]["language"] == "18 months."
    assert "id" not in preferred["old_value"]
    assert "created_at" not in preferred["old_value"]

    assert changes[("positions", "fallback:1")]["change_type"] == "added"
    assert changes[("positions", "fallback:1")]["old_value"] is None
    removed = changes[("red_lines", "no-unlimited")]
    assert removed["change_type"] == "removed"
    assert removed["old_value"]["condition"] == {
        "any": ["unlimited liability"], "negation_guard": True
    }

    assert modified["child_counts"] == {
        "positions": {"count_a": 2, "count_b": 3},
        "red_lines": {"count_a": 1, "count_b": 0},
    }


def test_diff_versions_objection_recommended_position_change() -> None:
    """An objection re-pointed at a different rung shows up as a modified
    objection, compared via ``recommended_position_key`` (not the raw id)."""
    version_a_id, version_b_id = uuid.uuid4(), uuid.uuid4()
    rule_a = _make_rule(rule_key="cap")
    rule_b = _make_rule(rule_key="cap")
    fb1_a = _position_row(rule_a.id, "fallback", 1, "F1", "x", "yellow")
    fb2_a = _position_row(rule_a.id, "fallback", 2, "F2", "y", "yellow")
    fb1_b = _position_row(rule_b.id, "fallback", 1, "F1", "x", "yellow")
    fb2_b = _position_row(rule_b.id, "fallback", 2, "F2", "y", "yellow")
    rule_a.positions, rule_b.positions = [fb1_a, fb2_a], [fb1_b, fb2_b]
    rule_a.objections = [_objection_row(rule_a.id, fb1_a)]
    rule_b.objections = [_objection_row(rule_b.id, fb2_b)]

    async def _fake_get_version(session, vid):
        return _make_version(version_id=vid)

    async def _fake_get_rules_with_children(session, vid):
        return [rule_a] if vid == version_a_id else [rule_b]

    with (
        patch("app.db.repositories.playbook_repo.get_version", new=_fake_get_version),
        patch(
            "app.db.repositories.playbook_repo.get_rules_with_children",
            new=_fake_get_rules_with_children,
        ),
    ):
        response = client.get(f"/api/playbooks/versions/diff?a={version_a_id}&b={version_b_id}")

    (modified,) = response.json()["rules_modified"]
    (change,) = modified["child_changes"]
    assert change["child_type"] == "objections"
    assert change["changed_fields"] == ["recommended_position_key"]
    assert change["old_value"]["recommended_position_key"] == "fallback:1"
    assert change["new_value"]["recommended_position_key"] == "fallback:2"


# ---------------------------------------------------------------------------
# Rule-child CRUD: draft-only (409) + change-log on edit
# ---------------------------------------------------------------------------


def test_create_position_on_published_version_409() -> None:
    version_id = uuid.uuid4()
    rule = _make_rule(playbook_version_id=version_id)
    published_version = _make_version(version_id=version_id, status="published")
    with (
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.get_version",
            new=AsyncMock(return_value=published_version),
        ),
    ):
        response = client.post(
            f"/api/playbooks/rules/{rule.id}/positions",
            json={
                "kind": "fallback",
                "label": "Fallback 1",
                "language": "...",
                "zone": "yellow",
            },
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_not_draft"


def test_create_position_on_draft_logs_change() -> None:
    version_id = uuid.uuid4()
    rule = _make_rule(playbook_version_id=version_id)
    draft_version = _make_version(version_id=version_id, status="draft")
    new_position = _make_position(rule_id=rule.id)

    with (
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.get_version",
            new=AsyncMock(return_value=draft_version),
        ),
        patch(
            "app.db.repositories.playbook_repo.create_rule_position",
            new=AsyncMock(return_value=new_position),
        ),
        patch(
            "app.db.repositories.playbook_repo.create_change_log_entry",
            new=AsyncMock(),
        ) as log_mock,
    ):
        response = client.post(
            f"/api/playbooks/rules/{rule.id}/positions",
            json={
                "kind": "fallback",
                "label": "Fallback 1",
                "language": "Liability capped at 18 months of fees.",
                "zone": "yellow",
            },
        )
    assert response.status_code == 201
    log_mock.assert_awaited_once()
    kwargs = log_mock.call_args.kwargs
    assert kwargs["playbook_version_id"] == version_id
    assert kwargs["change_type"] == "position_created"
    assert kwargs["rule_key"] == rule.rule_key


def test_delete_position_on_draft_logs_change() -> None:
    version_id = uuid.uuid4()
    rule = _make_rule(playbook_version_id=version_id)
    draft_version = _make_version(version_id=version_id, status="draft")
    position = _make_position(rule_id=rule.id)

    with (
        patch(
            "app.db.repositories.playbook_repo.get_rule_position",
            new=AsyncMock(return_value=position),
        ),
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.get_version",
            new=AsyncMock(return_value=draft_version),
        ),
        patch(
            "app.db.repositories.playbook_repo.delete_rule_position",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.db.repositories.playbook_repo.create_change_log_entry",
            new=AsyncMock(),
        ) as log_mock,
    ):
        response = client.delete(f"/api/playbooks/positions/{position.id}")
    assert response.status_code == 204
    log_mock.assert_awaited_once()
    assert log_mock.call_args.kwargs["change_type"] == "position_deleted"


def test_update_objection_on_published_version_409() -> None:
    version_id = uuid.uuid4()
    rule = _make_rule(playbook_version_id=version_id)
    objection = MagicMock(spec=RuleObjection)
    objection.id = uuid.uuid4()
    objection.rule_id = rule.id
    objection.objection = "Too strict"
    objection.their_rationale = None
    objection.response = "This is market standard."
    objection.talking_points = None
    objection.recommended_position_id = None
    objection.frequency = None
    objection.counterparty_profile = None
    objection.created_at = _NOW
    objection.updated_at = _NOW
    published_version = _make_version(version_id=version_id, status="superseded")

    with (
        patch(
            "app.db.repositories.playbook_repo.get_rule_objection",
            new=AsyncMock(return_value=objection),
        ),
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.get_version",
            new=AsyncMock(return_value=published_version),
        ),
    ):
        response = client.patch(
            f"/api/playbooks/objections/{objection.id}", json={"response": "Updated response."}
        )
    assert response.status_code == 409


def test_legacy_rule_with_no_version_is_editable_and_logs_nothing() -> None:
    """A rule predating task 1.2 has playbook_version_id=None: always
    editable, and no change-log row is written (nothing to attach it to)."""
    rule = _make_rule(playbook_version_id=None)
    new_position = _make_position(rule_id=rule.id)

    with (
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.create_rule_position",
            new=AsyncMock(return_value=new_position),
        ),
        patch(
            "app.db.repositories.playbook_repo.create_change_log_entry", new=AsyncMock()
        ) as log_mock,
    ):
        response = client.post(
            f"/api/playbooks/rules/{rule.id}/positions",
            json={"kind": "preferred", "label": "Preferred", "language": "...", "zone": "green"},
        )
    assert response.status_code == 201
    log_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# Red lines: scope handling
# ---------------------------------------------------------------------------


def test_create_global_red_line_no_draft_check() -> None:
    red_line = _make_red_line(scope="global")
    with patch(
        "app.db.repositories.playbook_repo.create_red_line",
        new=AsyncMock(return_value=red_line),
    ):
        response = client.post(
            "/api/playbooks/red-lines",
            json={
                "scope": "global",
                "key": "no-training-on-data",
                "description": "No training third-party models on Customer Data.",
                "condition_type": "phrase",
                "condition": {"phrases": ["train"]},
                "action": "block",
            },
        )
    assert response.status_code == 201
    assert response.json()["scope"] == "global"


def test_create_rule_red_line_on_published_version_409() -> None:
    version_id = uuid.uuid4()
    rule = _make_rule(playbook_version_id=version_id)
    published_version = _make_version(version_id=version_id, status="published")
    with (
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.get_version",
            new=AsyncMock(return_value=published_version),
        ),
    ):
        response = client.post(
            f"/api/playbooks/rules/{rule.id}/red-lines",
            json={
                "scope": "rule",
                "rule_id": str(rule.id),
                "key": "uncapped",
                "description": "Uncapped liability.",
                "condition_type": "phrase",
                "condition": {"phrases": ["uncapped"]},
                "action": "block",
            },
        )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Lookups: taxonomy, roles, context dimensions, escalation policies
# ---------------------------------------------------------------------------


def test_list_taxonomy_empty() -> None:
    with (
        patch(
            "app.db.repositories.taxonomy_repo.list_agreement_types", new=AsyncMock(return_value=[])
        ),
        patch(
            "app.db.repositories.taxonomy_repo.list_clause_families", new=AsyncMock(return_value=[])
        ),
        patch(
            "app.db.repositories.taxonomy_repo.list_clause_issues", new=AsyncMock(return_value=[])
        ),
    ):
        response = client.get("/api/playbooks/taxonomy")
    assert response.status_code == 200
    body = response.json()
    assert body == {"agreement_types": [], "clause_families": [], "clause_issues": []}


def test_list_roles_empty() -> None:
    with patch(
        "app.db.repositories.authority_repo.list_approver_roles", new=AsyncMock(return_value=[])
    ):
        response = client.get("/api/playbooks/roles")
    assert response.status_code == 200
    assert response.json() == []


def test_list_escalation_policies_empty() -> None:
    with patch(
        "app.db.repositories.authority_repo.list_escalation_policies",
        new=AsyncMock(return_value=[]),
    ):
        response = client.get("/api/playbooks/escalation-policies")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Cascade delete: declarative confirmation that the six child tables and
# playbook_version/playbook_rule all carry ON DELETE CASCADE back to
# playbook (migrations 011/012). A real cascade can only be proven against
# Postgres, which ground rule 1 forbids running against in this task; this
# checks the SQLAlchemy metadata the migrations are expected to produce.
# ---------------------------------------------------------------------------


def test_cascade_delete_foreign_keys_configured() -> None:
    from app.db.models.playbook import (
        PlaybookChangeLog,
        PlaybookRule,
        PlaybookVersion,
        RedLine,
        RuleDependency,
        RuleObjection,
        RuleParameter,
        RulePosition,
        RuleTestCase,
    )

    def _ondelete(model, column_name: str) -> str | None:
        column = model.__table__.columns[column_name]
        for fk in column.foreign_keys:
            return fk.ondelete
        return None

    assert _ondelete(PlaybookVersion, "playbook_id") == "CASCADE"
    assert _ondelete(PlaybookRule, "playbook_id") == "CASCADE"
    assert _ondelete(PlaybookChangeLog, "playbook_version_id") == "CASCADE"
    for child in (RulePosition, RuleParameter, RuleObjection, RuleDependency, RuleTestCase):
        assert _ondelete(child, "rule_id") == "CASCADE", child.__name__
    assert _ondelete(RedLine, "rule_id") == "CASCADE"


def test_delete_playbook_route_still_present_and_working() -> None:
    """Confirms the delete route task 4.8 was told to check for ("add one if
    missing") already exists and works — it does, so nothing was added."""
    with patch(
        "app.db.repositories.playbook_repo.delete_playbook", new=AsyncMock(return_value=True)
    ):
        response = client.delete(f"/api/playbooks/{uuid.uuid4()}")
    assert response.status_code == 204
