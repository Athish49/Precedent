"""PATCH semantics for the playbook service (task 1.4 item 4).

``update_rule``/``update_playbook`` must use ``model_dump(exclude_unset=True)``
so that:

* a field explicitly sent as ``null`` (e.g. ``title``, ``applies_when``)
  is applied and clears the column, and
* a field the client simply omits from the request body is left untouched —
  it must not reach the repository call at all.

The previous implementation used ``{k: v for k, v in body.model_dump().items()
if v is not None}``, which dropped an explicit ``null`` exactly like an
omitted field, making a nullable column impossible to clear via PATCH. These
tests assert on the kwargs the service passes to the (mocked) repository,
which is where that bug lived.

Task 5.5 adds the child-set half of PATCH: ``positions`` / ``red_lines`` are
synced only when present in the body, and the five removed legacy fields
are rejected outright rather than silently ignored.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.api.errors import AppError
from app.db.models.playbook import Playbook, PlaybookRule
from app.schemas.playbook import PlaybookUpdate, RuleCreate, RuleUpdate
from app.services.playbook import service


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _patch_rule_repo(
    monkeypatch: pytest.MonkeyPatch, rule: MagicMock | None
) -> dict[str, AsyncMock]:
    """Mock every repo call ``service.update_rule`` can make."""
    mocks = {
        "get_rule": AsyncMock(return_value=rule),
        "list_rule_positions": AsyncMock(return_value=[]),
        "list_red_lines_for_rule": AsyncMock(return_value=[]),
        "update_rule": AsyncMock(return_value=rule),
        "get_rule_with_children": AsyncMock(return_value=rule),
        "sync_rule_positions": AsyncMock(return_value=[]),
        "sync_rule_red_lines": AsyncMock(return_value=[]),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(service.playbook_repo, name, mock)
    return mocks


def _rule(rule_id: uuid.UUID) -> MagicMock:
    rule = MagicMock(spec=PlaybookRule)
    rule.id = rule_id
    rule.playbook_version_id = None  # legacy unversioned rule: never draft-gated
    rule.rule_key = "indemnification.general"
    return rule


# ---------------------------------------------------------------------------
# RuleUpdate: a nullable field can be cleared; an omitted field is untouched.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_rule_clears_explicit_null_field(monkeypatch: pytest.MonkeyPatch) -> None:
    rule_id = uuid.uuid4()
    rule = _rule(rule_id)
    mocks = _patch_rule_repo(monkeypatch, rule)

    session = _make_session()
    body = RuleUpdate(title=None)  # explicitly sent as null

    result = await service.update_rule(session, rule_id, body)

    assert result is rule
    mocks["update_rule"].assert_called_once()
    _, kwargs = mocks["update_rule"].call_args
    # Only the explicitly-set field is forwarded, and it keeps its null value.
    assert kwargs == {"title": None}


@pytest.mark.asyncio
async def test_update_rule_omitted_field_not_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A field absent from the request body must not appear in the kwargs
    passed to the repository at all — not even as ``None`` — so the column
    it maps to is left completely unchanged. Omitted child lists are not
    synced either."""
    rule_id = uuid.uuid4()
    mocks = _patch_rule_repo(monkeypatch, _rule(rule_id))

    session = _make_session()
    body = RuleUpdate()  # nothing set at all

    await service.update_rule(session, rule_id, body)

    mocks["update_rule"].assert_called_once()
    _, kwargs = mocks["update_rule"].call_args
    assert kwargs == {}
    mocks["sync_rule_positions"].assert_not_called()
    mocks["sync_rule_red_lines"].assert_not_called()


@pytest.mark.asyncio
async def test_update_rule_mixes_explicit_null_with_explicit_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule_id = uuid.uuid4()
    mocks = _patch_rule_repo(monkeypatch, _rule(rule_id))

    session = _make_session()
    body = RuleUpdate(applies_when=None, required=True)

    await service.update_rule(session, rule_id, body)

    _, kwargs = mocks["update_rule"].call_args
    assert kwargs == {"applies_when": None, "required": True}
    # clause_type, title, etc. were never mentioned, so they must not be in
    # the kwargs — forwarding them as None would null them.
    assert "clause_type" not in kwargs
    assert "title" not in kwargs
    # Child lists are never forwarded as rule columns.
    assert "positions" not in kwargs
    assert "red_lines" not in kwargs


@pytest.mark.asyncio
async def test_update_rule_not_found_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_rule_repo(monkeypatch, None)

    session = _make_session()

    with pytest.raises(AppError):
        await service.update_rule(session, uuid.uuid4(), RuleUpdate(required=True))


@pytest.mark.asyncio
async def test_update_rule_positions_synced_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sending ``positions`` syncs the rule's positions (rung-0 preferred
    language is a position now), and ``red_lines`` syncs rule-scoped red
    lines. An empty list is a real "replace with nothing"."""
    rule_id = uuid.uuid4()
    existing_position_id = uuid.uuid4()
    mocks = _patch_rule_repo(monkeypatch, _rule(rule_id))

    body = RuleUpdate(
        positions=[
            {
                "id": existing_position_id,
                "kind": "preferred",
                "rung": 0,
                "label": "Preferred",
                "language": "New preferred text.",
                "zone": "green",
            }
        ],
        red_lines=[],
    )
    await service.update_rule(_make_session(), rule_id, body)

    _, kwargs = mocks["update_rule"].call_args
    assert kwargs == {}
    mocks["sync_rule_positions"].assert_awaited_once()
    args, _ = mocks["sync_rule_positions"].call_args
    assert args[1] == rule_id
    assert args[2][0]["id"] == existing_position_id
    assert args[2][0]["language"] == "New preferred text."
    mocks["sync_rule_red_lines"].assert_awaited_once()
    assert mocks["sync_rule_red_lines"].call_args.args[2] == []


@pytest.mark.parametrize(
    "legacy_field, value",
    [
        ("preferred_language", "x"),
        ("acceptable_variations", ["x"]),
        ("prohibited_terms", ["x"]),
        ("fallback_language", "x"),
        ("escalation_threshold", 0.5),
    ],
)
def test_rule_bodies_reject_removed_legacy_fields(legacy_field: str, value: object) -> None:
    """The five legacy flat fields were dropped (migration 015). A stale
    client sending one gets a validation error (422 at the API), never a
    silent no-op."""
    with pytest.raises(ValidationError):
        RuleUpdate(**{legacy_field: value})
    with pytest.raises(ValidationError):
        RuleCreate(clause_type="indemnification", **{legacy_field: value})


# ---------------------------------------------------------------------------
# PlaybookUpdate: same semantics.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_playbook_omitted_field_not_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook_id = uuid.uuid4()
    pb = MagicMock(spec=Playbook)
    pb.id = playbook_id

    mock_update_playbook = AsyncMock(return_value=pb)
    monkeypatch.setattr(service.playbook_repo, "update_playbook", mock_update_playbook)

    session = _make_session()
    body = PlaybookUpdate(name="Renamed")  # only name sent

    await service.update_playbook(session, playbook_id, body)

    _, kwargs = mock_update_playbook.call_args
    assert kwargs == {"name": "Renamed"}
    assert "practice_area" not in kwargs
    assert "precedence" not in kwargs


@pytest.mark.asyncio
async def test_update_playbook_explicit_null_practice_area_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``practice_area`` is NOT NULL on the table, so sending it as explicit
    null must still be rejected by validation — exclude_unset only changes
    whether the field is forwarded when *set*, not whether a set-but-invalid
    value passes validation."""
    mock_update_playbook = AsyncMock()
    monkeypatch.setattr(service.playbook_repo, "update_playbook", mock_update_playbook)

    session = _make_session()
    body = PlaybookUpdate(practice_area=None)

    with pytest.raises(AppError):
        await service.update_playbook(session, uuid.uuid4(), body)

    mock_update_playbook.assert_not_called()


@pytest.mark.asyncio
async def test_update_playbook_no_fields_set_forwards_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = uuid.uuid4()
    pb = MagicMock(spec=Playbook)
    pb.id = playbook_id

    mock_update_playbook = AsyncMock(return_value=pb)
    monkeypatch.setattr(service.playbook_repo, "update_playbook", mock_update_playbook)

    session = _make_session()
    body = PlaybookUpdate()

    await service.update_playbook(session, playbook_id, body)

    _, kwargs = mock_update_playbook.call_args
    assert kwargs == {}


# ---------------------------------------------------------------------------
# Draft gate (task 5.5): child syncs and versioned creates are refused on a
# non-draft version, like the versions API's child-row endpoints.
# ---------------------------------------------------------------------------


def _version(status: str) -> MagicMock:
    from app.db.models.playbook import PlaybookVersion

    v = MagicMock(spec=PlaybookVersion)
    v.id = uuid.uuid4()
    v.status = status
    return v


_PREFERRED = {
    "kind": "preferred", "rung": 0, "label": "P", "language": "L", "zone": "green",
}


@pytest.mark.asyncio
async def test_update_rule_positions_on_published_version_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule(uuid.uuid4())
    published = _version("published")
    rule.playbook_version_id = published.id
    mocks = _patch_rule_repo(monkeypatch, rule)
    monkeypatch.setattr(service.playbook_repo, "get_version", AsyncMock(return_value=published))

    with pytest.raises(AppError) as exc:
        await service.update_rule(_make_session(), rule.id, RuleUpdate(positions=[_PREFERRED]))
    assert exc.value.status_code == 409
    mocks["update_rule"].assert_not_called()
    mocks["sync_rule_positions"].assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"risk_weight": 9.0},
        {"applies_when": {"region": "eu"}},
        {"default_zone": "red"},
        {"required": False},
        {"title": "New"},
    ],
)
async def test_update_rule_scalar_only_on_published_version_409(
    monkeypatch: pytest.MonkeyPatch, body: dict
) -> None:
    """A scalar-only PATCH on a published version changes live resolution
    and scoring, so it is draft-gated like a child sync: 409, nothing
    written, nothing logged."""
    rule = _rule(uuid.uuid4())
    published = _version("published")
    rule.playbook_version_id = published.id
    mocks = _patch_rule_repo(monkeypatch, rule)
    monkeypatch.setattr(service.playbook_repo, "get_version", AsyncMock(return_value=published))
    log = AsyncMock()
    monkeypatch.setattr(service.playbook_repo, "create_change_log_entry", log)
    session = _make_session()

    with pytest.raises(AppError) as exc:
        await service.update_rule(session, rule.id, RuleUpdate(**body))
    assert exc.value.status_code == 409
    assert exc.value.code == "version_not_draft"
    mocks["update_rule"].assert_not_called()
    log.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_rule_scalar_on_draft_logs_one_entry_per_changed_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a draft, scalar PATCH works and writes one ``modified`` change-log
    row per field whose value actually changed (unchanged fields: none)."""
    rule = _rule(uuid.uuid4())
    draft = _version("draft")
    rule.playbook_version_id = draft.id
    rule.risk_weight = 5.0
    rule.default_zone = "yellow"
    rule.required = True  # sent unchanged → not logged
    mocks = _patch_rule_repo(monkeypatch, rule)
    monkeypatch.setattr(service.playbook_repo, "get_version", AsyncMock(return_value=draft))
    log = AsyncMock()
    monkeypatch.setattr(service.playbook_repo, "create_change_log_entry", log)
    session = _make_session()

    await service.update_rule(
        session, rule.id, RuleUpdate(risk_weight=8.0, default_zone="red", required=True)
    )

    mocks["update_rule"].assert_called_once()
    session.commit.assert_awaited_once()
    entries = {c.kwargs["field_path"]: c.kwargs for c in log.call_args_list}
    assert set(entries) == {"risk_weight", "default_zone"}
    assert entries["risk_weight"]["change_type"] == "modified"
    assert entries["risk_weight"]["old_value"] == 5.0
    assert entries["risk_weight"]["new_value"] == 8.0
    assert entries["default_zone"]["old_value"] == "yellow"
    assert entries["default_zone"]["new_value"] == "red"
    assert all(e["playbook_version_id"] == draft.id for e in entries.values())
    assert all(e["rule_key"] == "indemnification.general" for e in entries.values())


@pytest.mark.asyncio
async def test_update_rule_scalar_on_legacy_rule_not_gated_or_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legacy rule with no version is ungated and has nothing to log to."""
    rule = _rule(uuid.uuid4())  # playbook_version_id = None
    mocks = _patch_rule_repo(monkeypatch, rule)
    get_version = AsyncMock()
    monkeypatch.setattr(service.playbook_repo, "get_version", get_version)
    log = AsyncMock()
    monkeypatch.setattr(service.playbook_repo, "create_change_log_entry", log)

    await service.update_rule(_make_session(), rule.id, RuleUpdate(title="New"))
    get_version.assert_not_called()
    log.assert_not_called()
    mocks["update_rule"].assert_called_once()


# ---------------------------------------------------------------------------
# delete_rule: draft-gated and logged like update_rule.
# ---------------------------------------------------------------------------


def _patch_delete_repo(
    monkeypatch: pytest.MonkeyPatch, rule: MagicMock | None, version: MagicMock | None = None
) -> dict[str, AsyncMock]:
    mocks = {
        "get_rule": AsyncMock(return_value=rule),
        "get_version": AsyncMock(return_value=version),
        "delete_rule": AsyncMock(return_value=True),
        "create_change_log_entry": AsyncMock(),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(service.playbook_repo, name, mock)
    return mocks


@pytest.mark.asyncio
async def test_delete_rule_on_published_version_409(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = _rule(uuid.uuid4())
    published = _version("published")
    rule.playbook_version_id = published.id
    mocks = _patch_delete_repo(monkeypatch, rule, published)
    session = _make_session()

    with pytest.raises(AppError) as exc:
        await service.delete_rule(session, rule.id)
    assert exc.value.status_code == 409
    assert exc.value.code == "version_not_draft"
    mocks["delete_rule"].assert_not_called()
    mocks["create_change_log_entry"].assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_delete_rule_on_draft_logs_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = _rule(uuid.uuid4())
    draft = _version("draft")
    rule.playbook_version_id = draft.id
    for field in service.versions._RULE_SCALAR_FIELDS:
        setattr(rule, field, None)
    rule.clause_type = "indemnification"
    rule.risk_weight = 7.0
    mocks = _patch_delete_repo(monkeypatch, rule, draft)
    session = _make_session()

    await service.delete_rule(session, rule.id)

    mocks["delete_rule"].assert_awaited_once()
    session.commit.assert_awaited_once()
    mocks["create_change_log_entry"].assert_awaited_once()
    kwargs = mocks["create_change_log_entry"].call_args.kwargs
    assert kwargs["change_type"] == "removed"
    assert kwargs["playbook_version_id"] == draft.id
    assert kwargs["rule_key"] == "indemnification.general"
    assert kwargs["old_value"]["rule_key"] == "indemnification.general"
    assert kwargs["old_value"]["risk_weight"] == 7.0
    assert kwargs["old_value"]["clause_type"] == "indemnification"
    assert kwargs["new_value"] is None


@pytest.mark.asyncio
async def test_delete_rule_legacy_rule_not_gated_or_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule(uuid.uuid4())  # no version
    mocks = _patch_delete_repo(monkeypatch, rule)

    await service.delete_rule(_make_session(), rule.id)

    mocks["get_version"].assert_not_called()
    mocks["create_change_log_entry"].assert_not_called()
    mocks["delete_rule"].assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rule_not_found_404(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_delete_repo(monkeypatch, None)

    with pytest.raises(AppError) as exc:
        await service.delete_rule(_make_session(), uuid.uuid4())
    assert exc.value.status_code == 404
    mocks["delete_rule"].assert_not_called()


@pytest.mark.asyncio
async def test_update_rule_positions_on_draft_logs_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule(uuid.uuid4())
    draft = _version("draft")
    rule.playbook_version_id = draft.id
    mocks = _patch_rule_repo(monkeypatch, rule)
    monkeypatch.setattr(service.playbook_repo, "get_version", AsyncMock(return_value=draft))
    log = AsyncMock()
    monkeypatch.setattr(service.playbook_repo, "create_change_log_entry", log)

    await service.update_rule(_make_session(), rule.id, RuleUpdate(positions=[_PREFERRED]))

    mocks["sync_rule_positions"].assert_awaited_once()
    log.assert_awaited_once()
    kwargs = log.call_args.kwargs
    assert kwargs["playbook_version_id"] == draft.id
    assert kwargs["change_type"] == "positions_synced"
    assert kwargs["old_value"] == []
    assert kwargs["new_value"][0]["language"] == "L"


@pytest.mark.asyncio
async def test_create_rule_into_published_version_409(monkeypatch: pytest.MonkeyPatch) -> None:
    published = _version("published")
    monkeypatch.setattr(
        service.playbook_repo, "get_playbook", AsyncMock(return_value=MagicMock(spec=Playbook))
    )
    monkeypatch.setattr(service.playbook_repo, "get_version", AsyncMock(return_value=published))
    create = AsyncMock()
    monkeypatch.setattr(service.playbook_repo, "create_rule", create)

    body = RuleCreate(
        clause_type="indemnification", playbook_version_id=published.id, positions=[_PREFERRED]
    )
    with pytest.raises(AppError) as exc:
        await service.create_rule(_make_session(), uuid.uuid4(), body)
    assert exc.value.status_code == 409
    create.assert_not_called()
