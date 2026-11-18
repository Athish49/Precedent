"""Unit tests for playbook_repo — all DB access is mocked."""

from __future__ import annotations

import unittest.mock
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.authority import ApproverRole, EscalationPolicy
from app.db.models.playbook import (
    Playbook,
    PlaybookRule,
    PlaybookVersion,
    RedLine,
    RuleDependency,
    RuleObjection,
    RuleParameter,
    RulePosition,
    RuleTestCase,
)
from app.db.models.taxonomy import ClauseFamily, ClauseIssue
from app.db.repositories import playbook_repo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    return AsyncMock()


def _scalar_result(value: object) -> MagicMock:
    """Mock execute() result suitable for scalar_one_or_none()."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = value
    return mock


def _scalars_all_result(items: list) -> MagicMock:
    """Mock execute() result suitable for scalars().all()."""
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


def _rowcount_result(rowcount: int) -> MagicMock:
    """Mock execute() result with rowcount attribute."""
    mock = MagicMock()
    mock.rowcount = rowcount
    return mock


# ---------------------------------------------------------------------------
# Playbook tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_playbook() -> None:
    session = _make_session()
    session.add = MagicMock()

    result = await playbook_repo.create_playbook(session, "NDA Playbook", "nda", precedence=5)

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, Playbook)
    assert added.name == "NDA Playbook"
    assert added.practice_area == "nda"
    assert added.precedence == 5
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_get_playbook_found() -> None:
    pb = MagicMock(spec=Playbook)
    pb.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(pb)

    result = await playbook_repo.get_playbook(session, pb.id)

    assert result is pb
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_playbook_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.get_playbook(session, uuid.uuid4())

    assert result is None
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_playbooks() -> None:
    pb1 = MagicMock(spec=Playbook)
    pb2 = MagicMock(spec=Playbook)

    session = _make_session()
    session.execute.return_value = _scalars_all_result([pb1, pb2])

    result = await playbook_repo.list_playbooks(session)

    assert result == [pb1, pb2]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_playbook() -> None:
    pb_id = uuid.uuid4()
    pb = MagicMock(spec=Playbook)
    pb.id = pb_id

    session = _make_session()
    session.execute.return_value = _scalar_result(pb)

    result = await playbook_repo.update_playbook(session, pb_id, name="Updated Name", precedence=10)

    assert result is pb
    assert pb.name == "Updated Name"
    assert pb.precedence == 10
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_update_playbook_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.update_playbook(session, uuid.uuid4(), name="Ghost")

    assert result is None
    session.flush.assert_not_called()


@pytest.mark.asyncio
async def test_delete_playbook_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(1)

    result = await playbook_repo.delete_playbook(session, uuid.uuid4())

    assert result is True
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_playbook_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(0)

    result = await playbook_repo.delete_playbook(session, uuid.uuid4())

    assert result is False


# ---------------------------------------------------------------------------
# PlaybookRule tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule() -> None:
    session = _make_session()
    session.add = MagicMock()

    playbook_id = uuid.uuid4()
    result = await playbook_repo.create_rule(
        session,
        playbook_id=playbook_id,
        clause_type="indemnification",
        required=True,
        risk_weight=2.0,
    )

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, PlaybookRule)
    assert added.playbook_id == playbook_id
    assert added.clause_type == "indemnification"
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_create_rule_rejects_removed_legacy_column() -> None:
    """``preferred_language`` is no longer a PlaybookRule column (migration
    015): passing it is a hard error, not a silently dropped value."""
    session = _make_session()
    session.add = MagicMock()
    with pytest.raises(TypeError):
        await playbook_repo.create_rule(
            session,
            playbook_id=uuid.uuid4(),
            clause_type="indemnification",
            preferred_language="Each party shall indemnify the other.",
        )


@pytest.mark.asyncio
async def test_get_rule_found() -> None:
    rule = MagicMock(spec=PlaybookRule)
    rule.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(rule)

    result = await playbook_repo.get_rule(session, rule.id)

    assert result is rule
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_rule_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.get_rule(session, uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_list_rules() -> None:
    playbook_id = uuid.uuid4()
    rule1 = MagicMock(spec=PlaybookRule)
    rule2 = MagicMock(spec=PlaybookRule)

    session = _make_session()
    session.execute.return_value = _scalars_all_result([rule1, rule2])

    result = await playbook_repo.list_rules(session, playbook_id)

    assert result == [rule1, rule2]
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_update_rule() -> None:
    rule_id = uuid.uuid4()
    rule = MagicMock(spec=PlaybookRule)
    rule.id = rule_id

    session = _make_session()
    session.execute.return_value = _scalar_result(rule)

    result = await playbook_repo.update_rule(
        session, rule_id, clause_type="liability", required=False
    )

    assert result is rule
    assert rule.clause_type == "liability"
    assert rule.required is False
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_rule_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(1)

    result = await playbook_repo.delete_rule(session, uuid.uuid4())

    assert result is True


@pytest.mark.asyncio
async def test_delete_rule_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _rowcount_result(0)

    result = await playbook_repo.delete_rule(session, uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_get_rules_by_clause_type() -> None:
    playbook_id = uuid.uuid4()
    rule = MagicMock(spec=PlaybookRule)
    rule.clause_type = "indemnification"

    session = _make_session()
    session.execute.return_value = _scalars_all_result([rule])

    result = await playbook_repo.get_rules_by_clause_type(session, playbook_id, "indemnification")

    assert result == [rule]
    session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Playbook version: create, get, list, get-current, copy, publish (task 1.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_version() -> None:
    session = _make_session()
    session.add = MagicMock()
    playbook_id = uuid.uuid4()

    result = await playbook_repo.create_version(
        session, playbook_id, "1.0", change_summary="Initial published version."
    )

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, PlaybookVersion)
    assert added.playbook_id == playbook_id
    assert added.version == "1.0"
    assert added.status == "draft"
    assert added.change_summary == "Initial published version."
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_get_version_found() -> None:
    version = MagicMock(spec=PlaybookVersion)
    version.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(version)

    result = await playbook_repo.get_version(session, version.id)

    assert result is version


@pytest.mark.asyncio
async def test_get_version_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.get_version(session, uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_list_versions() -> None:
    playbook_id = uuid.uuid4()
    v1 = MagicMock(spec=PlaybookVersion)
    v2 = MagicMock(spec=PlaybookVersion)

    session = _make_session()
    session.execute.return_value = _scalars_all_result([v1, v2])

    result = await playbook_repo.list_versions(session, playbook_id)

    assert result == [v1, v2]


@pytest.mark.asyncio
async def test_get_current_version_returns_version() -> None:
    playbook_id = uuid.uuid4()
    version_id = uuid.uuid4()
    pb = MagicMock(spec=Playbook)
    pb.id = playbook_id
    pb.current_version_id = version_id
    version = MagicMock(spec=PlaybookVersion)
    version.id = version_id

    session = _make_session()
    session.execute.side_effect = [_scalar_result(pb), _scalar_result(version)]

    result = await playbook_repo.get_current_version(session, playbook_id)

    assert result is version
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_get_current_version_none_when_playbook_missing() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.get_current_version(session, uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_get_current_version_none_when_no_current_version_set() -> None:
    pb = MagicMock(spec=Playbook)
    pb.current_version_id = None

    session = _make_session()
    session.execute.return_value = _scalar_result(pb)

    result = await playbook_repo.get_current_version(session, uuid.uuid4())

    assert result is None
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_copy_version_deep_copies_rule_and_children() -> None:
    """copy_version builds a new draft version and deep-copies rules plus all
    six child tables, remapping recommended_position_id to the copied
    position (playbook_plan.md section 3.3: "a new draft is created by
    copying the current version")."""
    session = _make_session()
    session.add = MagicMock()

    source_playbook_id = uuid.uuid4()
    source_version_id = uuid.uuid4()
    source_version = MagicMock(spec=PlaybookVersion)
    source_version.id = source_version_id
    source_version.playbook_id = source_playbook_id

    old_position_id = uuid.uuid4()
    rule = MagicMock(spec=PlaybookRule)
    rule.id = uuid.uuid4()
    rule.playbook_id = source_playbook_id
    rule.clause_type = "limitation_of_liability"
    rule.issue_id = uuid.uuid4()
    rule.rule_key = "limitation_of_liability.cap_amount"
    rule.title = "Aggregate liability cap"
    rule.required = True
    rule.risk_weight = 10
    rule.position_summary = "Capped at 12 months of Fees."
    rule.risk_rationale = "Insurance limits."
    rule.negotiable = True
    rule.default_zone = "yellow"
    rule.needs_human_judgment = False
    rule.judgment_note = None
    rule.applies_when = None
    rule.detection_guidance = "Look for aggregate liability."
    rule.source_ref = "RP-04"
    rule.authored_by = "Senior Commercial Counsel"
    rule.approved_by = "General Counsel"
    rule.last_reviewed_at = None

    position = MagicMock(spec=RulePosition)
    position.id = old_position_id
    position.kind = "preferred"
    position.rung = 0
    position.label = "12-month cap"
    position.language = "... twelve (12) months ..."
    position.summary = "Mutual cap at 12 months of Fees."
    position.zone = "green"
    position.approver_role_id = None
    position.conditions = None
    position.give_get = None
    position.internal_note = None

    parameter = MagicMock(spec=RuleParameter)
    parameter.key = "cap_multiple_months"
    parameter.label = "Cap as months of Fees"
    parameter.value_type = "number"
    parameter.unit = "months"
    parameter.direction = "lower_is_better"
    parameter.preferred_value = 12
    parameter.green_limit = 12
    parameter.yellow_limit = 24
    parameter.allowed_values = None
    parameter.extraction_hint = "Convert multiples to months."
    parameter.context_overrides = None

    objection = MagicMock(spec=RuleObjection)
    objection.objection = "Twelve months is too low."
    objection.their_rationale = "Breach risk."
    objection.response = "We address that separately."
    objection.talking_points = ["Point to the super-cap."]
    objection.recommended_position_id = old_position_id
    objection.frequency = "common"
    objection.counterparty_profile = "Large hospital systems"

    rule.positions = [position]
    rule.parameters = [parameter]
    rule.red_lines = []
    rule.objections = [objection]
    rule.dependencies = []
    rule.test_cases = []

    async def _fake_get_version(_session: object, version_id: uuid.UUID) -> PlaybookVersion:
        assert version_id == source_version_id
        return source_version

    async def _fake_get_rules_with_children(
        _session: object, version_id: uuid.UUID
    ) -> list[PlaybookRule]:
        assert version_id == source_version_id
        return [rule]

    with (
        unittest.mock.patch.object(playbook_repo, "get_version", _fake_get_version),
        unittest.mock.patch.object(
            playbook_repo, "get_rules_with_children", _fake_get_rules_with_children
        ),
    ):
        new_version = await playbook_repo.copy_version(session, source_version_id, "1.1")

    added = [call.args[0] for call in session.add.call_args_list]
    new_versions = [obj for obj in added if isinstance(obj, PlaybookVersion)]
    new_rules = [obj for obj in added if isinstance(obj, PlaybookRule)]
    new_positions = [obj for obj in added if isinstance(obj, RulePosition)]
    new_parameters = [obj for obj in added if isinstance(obj, RuleParameter)]
    new_objections = [obj for obj in added if isinstance(obj, RuleObjection)]

    assert len(new_versions) == 1
    assert new_versions[0].version == "1.1"
    assert new_versions[0].status == "draft"
    assert new_versions[0].playbook_id == source_playbook_id
    assert new_version is new_versions[0]

    assert len(new_rules) == 1
    assert new_rules[0].rule_key == "limitation_of_liability.cap_amount"
    assert new_rules[0].playbook_version_id == new_versions[0].id

    assert len(new_positions) == 1
    assert new_positions[0].rule_id == new_rules[0].id
    assert new_positions[0].label == "12-month cap"
    # The rung-0 preferred language travels with the copied position, the
    # only place it lives since migration 015.
    assert new_positions[0].kind == "preferred"
    assert new_positions[0].rung == 0
    assert new_positions[0].language == "... twelve (12) months ..."
    for legacy_column in (
        "preferred_language",
        "acceptable_variations",
        "prohibited_terms",
        "fallback_language",
        "escalation_threshold",
    ):
        assert legacy_column not in vars(new_rules[0])

    assert len(new_parameters) == 1
    assert new_parameters[0].rule_id == new_rules[0].id
    assert new_parameters[0].key == "cap_multiple_months"

    assert len(new_objections) == 1
    assert new_objections[0].rule_id == new_rules[0].id
    # The recommended position reference is remapped to the *copied* position,
    # not the source playbook's position.
    assert new_objections[0].recommended_position_id == new_positions[0].id
    assert new_objections[0].recommended_position_id != old_position_id


@pytest.mark.asyncio
async def test_copy_version_source_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.copy_version(session, uuid.uuid4(), "1.1")

    assert result is None


@pytest.mark.asyncio
async def test_publish_version_first_publish_sets_current_version() -> None:
    playbook_id = uuid.uuid4()
    version_id = uuid.uuid4()

    version = MagicMock(spec=PlaybookVersion)
    version.id = version_id
    version.playbook_id = playbook_id
    version.status = "draft"
    version.effective_from = None
    version.published_at = None
    version.approved_by = None

    pb = MagicMock(spec=Playbook)
    pb.id = playbook_id
    pb.current_version_id = None

    session = _make_session()
    session.execute.side_effect = [_scalar_result(version), _scalar_result(pb)]

    result = await playbook_repo.publish_version(session, version_id, approved_by="General Counsel")

    assert result is version
    assert version.status == "published"
    assert version.published_at is not None
    assert version.effective_from is not None
    assert version.approved_by == "General Counsel"
    assert pb.current_version_id == version_id
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_publish_version_supersedes_previous_current_version() -> None:
    playbook_id = uuid.uuid4()
    old_version_id = uuid.uuid4()
    new_version_id = uuid.uuid4()

    new_version = MagicMock(spec=PlaybookVersion)
    new_version.id = new_version_id
    new_version.playbook_id = playbook_id
    new_version.status = "draft"
    new_version.effective_from = None
    new_version.published_at = None
    new_version.approved_by = None

    pb = MagicMock(spec=Playbook)
    pb.id = playbook_id
    pb.current_version_id = old_version_id

    old_version = MagicMock(spec=PlaybookVersion)
    old_version.id = old_version_id
    old_version.status = "published"
    old_version.effective_to = None

    session = _make_session()
    session.execute.side_effect = [
        _scalar_result(new_version),
        _scalar_result(pb),
        _scalar_result(old_version),
    ]

    result = await playbook_repo.publish_version(session, new_version_id)

    assert result is new_version
    assert old_version.status == "superseded"
    assert old_version.effective_to is not None
    assert new_version.status == "published"
    assert pb.current_version_id == new_version_id


@pytest.mark.asyncio
async def test_publish_version_not_found() -> None:
    session = _make_session()
    session.execute.return_value = _scalar_result(None)

    result = await playbook_repo.publish_version(session, uuid.uuid4())

    assert result is None


# ---------------------------------------------------------------------------
# Rule-children CRUD (task 1.4): one representative create/get/list/update/
# delete cycle per child table, all six tables covered.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule_position() -> None:
    session = _make_session()
    session.add = MagicMock()
    rule_id = uuid.uuid4()

    result = await playbook_repo.create_rule_position(
        session, rule_id, kind="preferred", label="12-month cap",
        language="... twelve (12) months ...", zone="green", rung=0,
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, RulePosition)
    assert added.rule_id == rule_id
    assert added.kind == "preferred"
    assert added.rung == 0
    session.flush.assert_called_once()
    assert result is added


@pytest.mark.asyncio
async def test_get_list_update_delete_rule_position() -> None:
    position = MagicMock(spec=RulePosition)
    position.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(position)
    got = await playbook_repo.get_rule_position(session, position.id)
    assert got is position

    session.execute.return_value = _scalars_all_result([position])
    listed = await playbook_repo.list_rule_positions(session, uuid.uuid4())
    assert listed == [position]

    session.execute.return_value = _scalar_result(position)
    updated = await playbook_repo.update_rule_position(session, position.id, label="Updated")
    assert updated is position
    assert position.label == "Updated"

    session.execute.return_value = _rowcount_result(1)
    deleted = await playbook_repo.delete_rule_position(session, position.id)
    assert deleted is True


@pytest.mark.asyncio
async def test_sync_rule_positions_updates_creates_and_deletes() -> None:
    """``sync_rule_positions`` updates rows named by id in place, creates rows
    without an id, deletes the rest, and first clears any objection's
    ``recommended_position_id`` that points at a deleted position, since
    that FK has no ON DELETE action."""
    rule_id = uuid.uuid4()
    kept = MagicMock(spec=RulePosition)
    kept.id = uuid.uuid4()
    dropped = MagicMock(spec=RulePosition)
    dropped.id = uuid.uuid4()
    objection = MagicMock(spec=RuleObjection)
    objection.recommended_position_id = dropped.id

    session = _make_session()
    session.add = MagicMock()
    session.execute.side_effect = [
        _scalars_all_result([kept, dropped]),  # list_rule_positions
        _scalars_all_result([objection]),  # list_rule_objections
        _rowcount_result(1),  # delete
    ]

    result = await playbook_repo.sync_rule_positions(
        session,
        rule_id,
        [
            {
                "id": kept.id,
                "kind": "preferred",
                "rung": 0,
                "label": "Preferred",
                "language": "Updated preferred text.",
                "zone": "green",
            },
            {
                "kind": "fallback",
                "rung": 1,
                "label": "Fallback 1",
                "language": "Fallback text.",
                "zone": "yellow",
            },
        ],
    )

    assert result[0] is kept
    assert kept.language == "Updated preferred text."
    assert kept.rung == 0
    created = session.add.call_args[0][0]
    assert isinstance(created, RulePosition)
    assert created.rule_id == rule_id
    assert created.kind == "fallback"
    assert created.rung == 1
    assert result[1] is created
    assert objection.recommended_position_id is None
    # The third execute is the DELETE for the dropped position.
    delete_stmt = session.execute.call_args_list[2].args[0]
    assert "DELETE FROM" in str(delete_stmt)


@pytest.mark.asyncio
async def test_sync_rule_positions_unknown_id_creates_new_row() -> None:
    """An id that is not one of this rule's positions is treated as new, so
    a client can never move another rule's position onto this one."""
    session = _make_session()
    session.add = MagicMock()
    session.execute.return_value = _scalars_all_result([])

    await playbook_repo.sync_rule_positions(
        session,
        uuid.uuid4(),
        [{"id": uuid.uuid4(), "kind": "preferred", "rung": 0, "label": "P",
          "language": "L", "zone": "green"}],
    )
    created = session.add.call_args[0][0]
    assert isinstance(created, RulePosition)
    # Only the list query ran: nothing to delete.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_sync_rule_red_lines_forces_rule_scope_and_deletes_missing() -> None:
    rule_id = uuid.uuid4()
    stale = MagicMock(spec=RedLine)
    stale.id = uuid.uuid4()

    session = _make_session()
    session.add = MagicMock()
    session.execute.side_effect = [_scalars_all_result([stale]), _rowcount_result(1)]

    await playbook_repo.sync_rule_red_lines(
        session,
        rule_id,
        [
            {
                "key": "no-unlimited-liability",
                "description": "Prohibited term: 'unlimited liability'.",
                "condition_type": "phrase",
                "condition": {"any": ["unlimited liability"], "negation_guard": True},
                "action": "block",
            }
        ],
    )

    created = session.add.call_args[0][0]
    assert isinstance(created, RedLine)
    assert created.scope == "rule"
    assert created.rule_id == rule_id
    assert created.playbook_id is None
    assert created.condition == {"any": ["unlimited liability"], "negation_guard": True}
    assert session.execute.await_count == 2  # list + delete of the stale row


@pytest.mark.asyncio
async def test_create_rule_parameter() -> None:
    session = _make_session()
    session.add = MagicMock()
    rule_id = uuid.uuid4()

    result = await playbook_repo.create_rule_parameter(
        session, rule_id, key="cap_multiple_months", label="Cap as months of Fees",
        value_type="number", direction="lower_is_better", preferred_value=12,
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, RuleParameter)
    assert added.rule_id == rule_id
    assert added.key == "cap_multiple_months"
    assert added.preferred_value == 12
    assert result is added


@pytest.mark.asyncio
async def test_get_list_update_delete_rule_parameter() -> None:
    parameter = MagicMock(spec=RuleParameter)
    parameter.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(parameter)
    assert await playbook_repo.get_rule_parameter(session, parameter.id) is parameter

    session.execute.return_value = _scalars_all_result([parameter])
    assert await playbook_repo.list_rule_parameters(session, uuid.uuid4()) == [parameter]

    session.execute.return_value = _scalar_result(parameter)
    updated = await playbook_repo.update_rule_parameter(session, parameter.id, yellow_limit=36)
    assert updated is parameter
    assert parameter.yellow_limit == 36

    session.execute.return_value = _rowcount_result(1)
    assert await playbook_repo.delete_rule_parameter(session, parameter.id) is True


@pytest.mark.asyncio
async def test_create_red_line_rule_scoped() -> None:
    session = _make_session()
    session.add = MagicMock()
    rule_id = uuid.uuid4()

    result = await playbook_repo.create_red_line(
        session, scope="rule", key="lol-uncapped", description="Uncapped liability.",
        condition_type="semantic", condition={"test": "..."}, action="block", rule_id=rule_id,
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, RedLine)
    assert added.scope == "rule"
    assert added.rule_id == rule_id
    assert result is added


@pytest.mark.asyncio
async def test_list_red_lines_scopes() -> None:
    rule_red_line = MagicMock(spec=RedLine)
    playbook_red_line = MagicMock(spec=RedLine)
    global_red_line = MagicMock(spec=RedLine)

    session = _make_session()

    session.execute.return_value = _scalars_all_result([rule_red_line])
    assert await playbook_repo.list_red_lines_for_rule(session, uuid.uuid4()) == [rule_red_line]

    session.execute.return_value = _scalars_all_result([playbook_red_line])
    assert await playbook_repo.list_red_lines_for_playbook(session, uuid.uuid4()) == [
        playbook_red_line
    ]

    session.execute.return_value = _scalars_all_result([global_red_line])
    assert await playbook_repo.list_global_red_lines(session) == [global_red_line]


@pytest.mark.asyncio
async def test_get_update_delete_red_line() -> None:
    red_line = MagicMock(spec=RedLine)
    red_line.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(red_line)
    assert await playbook_repo.get_red_line(session, red_line.id) is red_line

    session.execute.return_value = _scalar_result(red_line)
    updated = await playbook_repo.update_red_line(session, red_line.id, action="escalate")
    assert updated is red_line
    assert red_line.action == "escalate"

    session.execute.return_value = _rowcount_result(1)
    assert await playbook_repo.delete_red_line(session, red_line.id) is True


@pytest.mark.asyncio
async def test_create_rule_objection() -> None:
    session = _make_session()
    session.add = MagicMock()
    rule_id = uuid.uuid4()

    result = await playbook_repo.create_rule_objection(
        session, rule_id, objection="Too low.", response="We disagree because...",
        frequency="common",
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, RuleObjection)
    assert added.rule_id == rule_id
    assert added.frequency == "common"
    assert result is added


@pytest.mark.asyncio
async def test_get_list_update_delete_rule_objection() -> None:
    objection = MagicMock(spec=RuleObjection)
    objection.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(objection)
    assert await playbook_repo.get_rule_objection(session, objection.id) is objection

    session.execute.return_value = _scalars_all_result([objection])
    assert await playbook_repo.list_rule_objections(session, uuid.uuid4()) == [objection]

    session.execute.return_value = _scalar_result(objection)
    updated = await playbook_repo.update_rule_objection(session, objection.id, frequency="rare")
    assert updated is objection
    assert objection.frequency == "rare"

    session.execute.return_value = _rowcount_result(1)
    assert await playbook_repo.delete_rule_objection(session, objection.id) is True


@pytest.mark.asyncio
async def test_create_rule_dependency() -> None:
    session = _make_session()
    session.add = MagicMock()
    rule_id = uuid.uuid4()

    result = await playbook_repo.create_rule_dependency(
        session, rule_id, related_rule_key="limitation_of_liability.data_breach_super_cap",
        relation="trade_against",
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, RuleDependency)
    assert added.rule_id == rule_id
    assert added.relation == "trade_against"
    assert result is added


@pytest.mark.asyncio
async def test_get_list_update_delete_rule_dependency() -> None:
    dependency = MagicMock(spec=RuleDependency)
    dependency.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(dependency)
    assert await playbook_repo.get_rule_dependency(session, dependency.id) is dependency

    session.execute.return_value = _scalars_all_result([dependency])
    assert await playbook_repo.list_rule_dependencies(session, uuid.uuid4()) == [dependency]

    session.execute.return_value = _scalar_result(dependency)
    updated = await playbook_repo.update_rule_dependency(
        session, dependency.id, note="Updated note"
    )
    assert updated is dependency
    assert dependency.note == "Updated note"

    session.execute.return_value = _rowcount_result(1)
    assert await playbook_repo.delete_rule_dependency(session, dependency.id) is True


@pytest.mark.asyncio
async def test_create_rule_test_case() -> None:
    session = _make_session()
    session.add = MagicMock()
    rule_id = uuid.uuid4()

    result = await playbook_repo.create_rule_test_case(
        session, rule_id, name="Standard 12-month cap", expected_outcome="compliant",
        expected_zone="green",
    )

    added = session.add.call_args[0][0]
    assert isinstance(added, RuleTestCase)
    assert added.rule_id == rule_id
    assert added.expected_outcome == "compliant"
    assert result is added


@pytest.mark.asyncio
async def test_get_list_update_delete_rule_test_case() -> None:
    test_case = MagicMock(spec=RuleTestCase)
    test_case.id = uuid.uuid4()

    session = _make_session()
    session.execute.return_value = _scalar_result(test_case)
    assert await playbook_repo.get_rule_test_case(session, test_case.id) is test_case

    session.execute.return_value = _scalars_all_result([test_case])
    assert await playbook_repo.list_rule_test_cases(session, uuid.uuid4()) == [test_case]

    session.execute.return_value = _scalar_result(test_case)
    updated = await playbook_repo.update_rule_test_case(session, test_case.id, is_trap=True)
    assert updated is test_case
    assert test_case.is_trap is True

    session.execute.return_value = _rowcount_result(1)
    assert await playbook_repo.delete_rule_test_case(session, test_case.id) is True


# ---------------------------------------------------------------------------
# get_rules_with_children: fixed query count, non-N+1 (task 1.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rules_with_children_empty_version() -> None:
    session = _make_session()
    session.execute.return_value = _scalars_all_result([])

    result = await playbook_repo.get_rules_with_children(session, uuid.uuid4())

    assert result == []
    # Only the rules query runs; no child queries fire for zero rules.
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_rules_with_children_fixed_query_count_and_grouping() -> None:
    version_id = uuid.uuid4()
    rule_a = MagicMock(spec=PlaybookRule)
    rule_a.id = uuid.uuid4()
    rule_b = MagicMock(spec=PlaybookRule)
    rule_b.id = uuid.uuid4()

    position = MagicMock(spec=RulePosition)
    position.rule_id = rule_a.id
    parameter = MagicMock(spec=RuleParameter)
    parameter.rule_id = rule_a.id
    red_line = MagicMock(spec=RedLine)
    red_line.rule_id = rule_b.id
    objection = MagicMock(spec=RuleObjection)
    objection.rule_id = rule_b.id
    dependency = MagicMock(spec=RuleDependency)
    dependency.rule_id = rule_a.id
    test_case = MagicMock(spec=RuleTestCase)
    test_case.rule_id = rule_b.id

    session = _make_session()
    # Order must match playbook_repo._CHILD_MODELS: position, parameter,
    # red_line, objection, dependency, test_case — preceded by the rules query.
    session.execute.side_effect = [
        _scalars_all_result([rule_a, rule_b]),
        _scalars_all_result([position]),
        _scalars_all_result([parameter]),
        _scalars_all_result([red_line]),
        _scalars_all_result([objection]),
        _scalars_all_result([dependency]),
        _scalars_all_result([test_case]),
    ]

    result = await playbook_repo.get_rules_with_children(session, version_id)

    assert result == [rule_a, rule_b]
    # 1 rules query + 1 per child table = 7, fixed regardless of rule count.
    assert session.execute.call_count == 7

    assert rule_a.positions == [position]
    assert rule_a.parameters == [parameter]
    assert rule_a.red_lines == []
    assert rule_a.objections == []
    assert rule_a.dependencies == [dependency]
    assert rule_a.test_cases == []

    assert rule_b.positions == []
    assert rule_b.parameters == []
    assert rule_b.red_lines == [red_line]
    assert rule_b.objections == [objection]
    assert rule_b.dependencies == []
    assert rule_b.test_cases == [test_case]


# ---------------------------------------------------------------------------
# Upsert-by-key helpers (task 1.4; used by the seed loader, task 2.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_playbook_creates_when_absent() -> None:
    session = _make_session()
    session.add = MagicMock()
    session.execute.return_value = _scalar_result(None)

    pb, created = await playbook_repo.upsert_playbook(
        session, "halcyon-baseline", {"name": "Halcyon Baseline", "practice_area": "baseline"}
    )

    assert created is True
    added = session.add.call_args[0][0]
    assert isinstance(added, Playbook)
    assert added.key == "halcyon-baseline"
    assert added.name == "Halcyon Baseline"
    assert pb is added


@pytest.mark.asyncio
async def test_upsert_playbook_updates_when_present() -> None:
    existing = MagicMock(spec=Playbook)
    existing.key = "halcyon-baseline"

    session = _make_session()
    session.execute.return_value = _scalar_result(existing)

    pb, created = await playbook_repo.upsert_playbook(
        session, "halcyon-baseline", {"name": "Renamed Baseline"}
    )

    assert created is False
    assert pb is existing
    assert existing.name == "Renamed Baseline"


@pytest.mark.asyncio
async def test_upsert_clause_family_creates_when_absent() -> None:
    session = _make_session()
    session.add = MagicMock()
    session.execute.return_value = _scalar_result(None)

    family, created = await playbook_repo.upsert_clause_family(
        session,
        "service_levels",
        {"name": "Service Levels", "category": "commercial", "description": "Uptime and credits."},
    )

    assert created is True
    added = session.add.call_args[0][0]
    assert isinstance(added, ClauseFamily)
    assert added.key == "service_levels"
    assert family is added


@pytest.mark.asyncio
async def test_upsert_clause_family_updates_when_present() -> None:
    existing = MagicMock(spec=ClauseFamily)
    existing.key = "service_levels"

    session = _make_session()
    session.execute.return_value = _scalar_result(existing)

    family, created = await playbook_repo.upsert_clause_family(
        session, "service_levels", {"description": "Updated description."}
    )

    assert created is False
    assert family is existing
    assert existing.description == "Updated description."


@pytest.mark.asyncio
async def test_upsert_clause_issue_creates_and_updates() -> None:
    session = _make_session()
    session.add = MagicMock()
    session.execute.return_value = _scalar_result(None)

    issue, created = await playbook_repo.upsert_clause_issue(
        session,
        "limitation_of_liability",
        "cap_amount",
        {"name": "Cap amount", "description": "The liability cap."},
    )

    assert created is True
    added = session.add.call_args[0][0]
    assert isinstance(added, ClauseIssue)
    assert added.family_key == "limitation_of_liability"
    assert added.key == "cap_amount"
    assert issue is added

    existing = MagicMock(spec=ClauseIssue)
    session.execute.return_value = _scalar_result(existing)
    issue2, created2 = await playbook_repo.upsert_clause_issue(
        session, "limitation_of_liability", "cap_amount", {"description": "Updated."}
    )
    assert created2 is False
    assert issue2 is existing
    assert existing.description == "Updated."


@pytest.mark.asyncio
async def test_upsert_approver_role_creates_and_updates() -> None:
    session = _make_session()
    session.add = MagicMock()
    session.execute.return_value = _scalar_result(None)

    role, created = await playbook_repo.upsert_approver_role(
        session,
        "commercial_counsel",
        {"name": "Commercial Counsel", "function": "legal", "level": 2, "default_sla_hours": 24},
    )

    assert created is True
    added = session.add.call_args[0][0]
    assert isinstance(added, ApproverRole)
    assert added.key == "commercial_counsel"
    assert role is added

    existing = MagicMock(spec=ApproverRole)
    session.execute.return_value = _scalar_result(existing)
    role2, created2 = await playbook_repo.upsert_approver_role(
        session, "commercial_counsel", {"default_sla_hours": 48}
    )
    assert created2 is False
    assert existing.default_sla_hours == 48


@pytest.mark.asyncio
async def test_upsert_escalation_policy_creates_and_updates_by_composite_key() -> None:
    """``escalation_policy`` has no stable ``key`` column (unlike the seed
    file's ``key`` field); the upsert helper uses ``(playbook_id,
    clause_type, zone, priority)`` as the natural key instead — see the
    docstring on ``upsert_escalation_policy`` and this task's report."""
    session = _make_session()
    session.add = MagicMock()
    session.execute.return_value = _scalar_result(None)
    approver_role_id = uuid.uuid4()

    policy, created = await playbook_repo.upsert_escalation_policy(
        session,
        playbook_id=None,
        clause_type="limitation_of_liability",
        zone="yellow",
        priority=10,
        defaults={"approver_role_id": approver_role_id, "sla_hours": 24, "consult_role_ids": []},
    )

    assert created is True
    added = session.add.call_args[0][0]
    assert isinstance(added, EscalationPolicy)
    assert added.clause_type == "limitation_of_liability"
    assert added.zone == "yellow"
    assert added.priority == 10
    assert policy is added

    existing = MagicMock(spec=EscalationPolicy)
    session.execute.return_value = _scalar_result(existing)
    policy2, created2 = await playbook_repo.upsert_escalation_policy(
        session,
        playbook_id=None,
        clause_type="limitation_of_liability",
        zone="yellow",
        priority=10,
        defaults={"sla_hours": 48},
    )
    assert created2 is False
    assert existing.sla_hours == 48
