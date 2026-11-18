"""Unit tests for S6 Playbook & Rules API endpoints (T-036).

All DB calls are mocked via dependency override — no real database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.playbooks import _get_session
from app.db.models.playbook import Playbook, PlaybookRule
from app.main import app

# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_PB_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()


def _make_playbook(
    pb_id: uuid.UUID = _PB_ID,
    name: str = "NDA Playbook",
    practice_area: str = "nda",
    precedence: int = 0,
) -> MagicMock:
    pb = MagicMock(spec=Playbook)
    pb.id = pb_id
    pb.name = name
    pb.practice_area = practice_area
    pb.precedence = precedence
    pb.created_at = _NOW
    pb.updated_at = _NOW
    return pb


def _make_position(
    rule_id: uuid.UUID = _RULE_ID,
    kind: str = "preferred",
    rung: int | None = 0,
    language: str = "Standard indemnification language.",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        rule_id=rule_id,
        kind=kind,
        rung=rung,
        label="Preferred",
        language=language,
        summary=None,
        zone="green",
        approver_role_id=None,
        conditions=None,
        give_get=None,
        internal_note=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_rule(
    rule_id: uuid.UUID = _RULE_ID,
    playbook_id: uuid.UUID = _PB_ID,
    clause_type: str = "indemnification",
    with_children: bool = True,
) -> MagicMock:
    """A PlaybookRule stand-in. With *with_children*, it carries the six
    child lists the way ``attach_children`` leaves them, including one rung-0
    preferred position (where preferred language lives since migration 015)."""
    rule = MagicMock(spec=PlaybookRule)
    rule.id = rule_id
    rule.playbook_id = playbook_id
    rule.playbook_version_id = None
    rule.clause_type = clause_type
    rule.issue_id = None
    rule.rule_key = f"{clause_type}.general"
    rule.title = None
    rule.position_summary = None
    rule.risk_rationale = None
    rule.required = True
    rule.negotiable = None
    rule.risk_weight = 1.5
    rule.default_zone = None
    rule.needs_human_judgment = None
    rule.judgment_note = None
    rule.applies_when = None
    rule.detection_guidance = None
    rule.source_ref = None
    rule.authored_by = None
    rule.approved_by = None
    rule.last_reviewed_at = None
    if with_children:
        rule.positions = [_make_position(rule_id)]
        rule.parameters = []
        rule.red_lines = []
        rule.objections = []
        rule.dependencies = []
        rule.test_cases = []
    return rule


mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)

# ── Helpers ───────────────────────────────────────────────────────────────────

_UNKNOWN_ID = str(uuid.uuid4())


def _scalar(value: object) -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


def _scalars_all(items: list) -> MagicMock:
    m = MagicMock()
    m.scalars.return_value.all.return_value = items
    return m


def _rowcount(n: int) -> MagicMock:
    m = MagicMock()
    m.rowcount = n
    return m


# ── Playbook list ─────────────────────────────────────────────────────────────


def test_list_playbooks_empty() -> None:
    mock_session.execute = AsyncMock(return_value=_scalars_all([]))
    response = client.get("/api/playbooks")
    assert response.status_code == 200
    assert response.json() == []


def test_list_playbooks_returns_items() -> None:
    pb = _make_playbook()
    mock_session.execute = AsyncMock(return_value=_scalars_all([pb]))
    response = client.get("/api/playbooks")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "NDA Playbook"
    assert body[0]["practice_area"] == "nda"


# ── Playbook create ───────────────────────────────────────────────────────────


def test_create_playbook_success() -> None:
    pb = _make_playbook()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with patch(
        "app.db.repositories.playbook_repo.create_playbook",
        new=AsyncMock(return_value=pb),
    ):
        response = client.post(
            "/api/playbooks",
            json={"name": "NDA Playbook", "practice_area": "nda", "precedence": 0},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "NDA Playbook"
    assert body["practice_area"] == "nda"


def test_create_playbook_invalid_practice_area() -> None:
    response = client.post(
        "/api/playbooks",
        json={"name": "X", "practice_area": "invalid"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_practice_area"


# ── Get playbook by id ────────────────────────────────────────────────────────


def test_get_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.get(f"/api/playbooks/{_UNKNOWN_ID}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_playbook_with_rules() -> None:
    pb = _make_playbook()
    rule = _make_rule(with_children=False)
    preferred = [_make_position()]

    call_count = 0

    async def _multi_execute(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar(pb)
        if call_count == 2:
            return _scalars_all([rule])
        # attach_children: one query per child table.
        if call_count == 3:
            return _scalars_all(preferred)
        return _scalars_all([])

    mock_session.execute = _multi_execute

    response = client.get(f"/api/playbooks/{_PB_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "NDA Playbook"
    assert len(body["rules"]) == 1
    assert body["rules"][0]["clause_type"] == "indemnification"
    # Children are loaded and returned; preferred language is a position.
    assert body["rules"][0]["positions"][0]["kind"] == "preferred"
    assert body["rules"][0]["positions"][0]["rung"] == 0
    assert body["rules"][0]["positions"][0]["language"] == "Standard indemnification language."
    assert "preferred_language" not in body["rules"][0]


# ── Update playbook ───────────────────────────────────────────────────────────


def test_update_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.patch(
        f"/api/playbooks/{_UNKNOWN_ID}",
        json={"name": "New Name"},
    )
    assert response.status_code == 404


def test_update_playbook_success() -> None:
    pb = _make_playbook(name="Updated")

    with patch(
        "app.db.repositories.playbook_repo.get_playbook",
        new=AsyncMock(return_value=pb),
    ):
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        response = client.patch(
            f"/api/playbooks/{_PB_ID}",
            json={"name": "Updated"},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated"


# ── Delete playbook ───────────────────────────────────────────────────────────


def test_delete_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_rowcount(0))
    response = client.delete(f"/api/playbooks/{_UNKNOWN_ID}")
    assert response.status_code == 404


def test_delete_playbook_success() -> None:
    mock_session.execute = AsyncMock(return_value=_rowcount(1))
    mock_session.commit = AsyncMock()
    response = client.delete(f"/api/playbooks/{_PB_ID}")
    assert response.status_code == 204


# ── Rules list ────────────────────────────────────────────────────────────────


def test_list_rules_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.get(f"/api/playbooks/{_UNKNOWN_ID}/rules")
    assert response.status_code == 404


def test_list_rules_success() -> None:
    pb = _make_playbook()
    rule = _make_rule(with_children=False)
    preferred = [_make_position()]

    call_count = 0

    async def _multi_execute(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _scalar(pb)
        if call_count == 2:
            return _scalars_all([rule])
        # attach_children: one query per child table.
        if call_count == 3:
            return _scalars_all(preferred)
        return _scalars_all([])

    mock_session.execute = _multi_execute

    response = client.get(f"/api/playbooks/{_PB_ID}/rules")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["clause_type"] == "indemnification"
    assert body[0]["positions"][0]["language"] == "Standard indemnification language."
    for key in ("parameters", "red_lines", "objections", "dependencies", "test_cases"):
        assert body[0][key] == []


# ── Rule create ───────────────────────────────────────────────────────────────


def test_create_rule_playbook_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.post(
        f"/api/playbooks/{_UNKNOWN_ID}/rules",
        json={"clause_type": "indemnification"},
    )
    assert response.status_code == 404


def test_create_rule_success() -> None:
    pb = _make_playbook()
    rule = _make_rule()

    with (
        patch(
            "app.db.repositories.playbook_repo.get_playbook",
            new=AsyncMock(return_value=pb),
        ),
        patch(
            "app.db.repositories.playbook_repo.create_rule",
            new=AsyncMock(return_value=rule),
        ) as mock_create,
        patch(
            "app.db.repositories.playbook_repo.get_rule_with_children",
            new=AsyncMock(return_value=rule),
        ),
        patch("app.db.repositories.playbook_repo.sync_rule_positions") as mock_sync_pos,
        patch("app.db.repositories.playbook_repo.sync_rule_red_lines") as mock_sync_rl,
    ):
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        response = client.post(
            f"/api/playbooks/{_PB_ID}/rules",
            json={"clause_type": "indemnification", "required": True, "risk_weight": 1.5},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["clause_type"] == "indemnification"
    assert body["required"] is True
    assert body["positions"][0]["kind"] == "preferred"
    _, kwargs = mock_create.call_args
    assert kwargs["clause_type"] == "indemnification"
    assert "positions" not in kwargs and "red_lines" not in kwargs
    # No inline children sent → no child writes.
    mock_sync_pos.assert_not_called()
    mock_sync_rl.assert_not_called()


def test_create_rule_with_inline_positions_and_red_lines() -> None:
    """The child-table replacement for the five legacy fields: preferred
    (rung 0), fallback (rung 1) and acceptable-variant positions plus a
    prohibited-phrase red line, all created with the rule."""
    pb = _make_playbook()
    rule = _make_rule()

    with (
        patch(
            "app.db.repositories.playbook_repo.get_playbook",
            new=AsyncMock(return_value=pb),
        ),
        patch(
            "app.db.repositories.playbook_repo.create_rule",
            new=AsyncMock(return_value=rule),
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rule_with_children",
            new=AsyncMock(return_value=rule),
        ),
        patch(
            "app.db.repositories.playbook_repo.sync_rule_positions",
            new=AsyncMock(return_value=[]),
        ) as mock_sync_pos,
        patch(
            "app.db.repositories.playbook_repo.sync_rule_red_lines",
            new=AsyncMock(return_value=[]),
        ) as mock_sync_rl,
    ):
        mock_session.commit = AsyncMock()
        response = client.post(
            f"/api/playbooks/{_PB_ID}/rules",
            json={
                "clause_type": "indemnification",
                "positions": [
                    {"id": str(uuid.uuid4()), "kind": "preferred", "rung": 0,
                     "label": "Preferred", "language": "Mutual indemnity.", "zone": "green"},
                    {"kind": "fallback", "rung": 1, "label": "Fallback 1",
                     "language": "Capped indemnity.", "zone": "yellow"},
                    {"kind": "acceptable_variant", "label": "Variant 1",
                     "language": "Each party indemnifies the other.", "zone": "green"},
                ],
                "red_lines": [
                    {"key": "no-unlimited", "description": "No unlimited indemnity.",
                     "condition_type": "phrase",
                     "condition": {"any": ["unlimited indemnity"], "negation_guard": True},
                     "action": "block"},
                ],
            },
        )

    assert response.status_code == 201
    args, _ = mock_sync_pos.call_args
    assert args[1] == _RULE_ID
    positions = args[2]
    assert [p["kind"] for p in positions] == ["preferred", "fallback", "acceptable_variant"]
    assert positions[0]["language"] == "Mutual indemnity."
    # On create, any client-supplied id is ignored.
    assert all("id" not in p for p in positions)
    red_lines = mock_sync_rl.call_args.args[2]
    assert red_lines[0]["condition"] == {"any": ["unlimited indemnity"], "negation_guard": True}


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
def test_create_and_update_rule_reject_legacy_fields(legacy_field: str, value: object) -> None:
    """A client still sending a removed legacy field gets 422, not a silent no-op."""
    response = client.post(
        f"/api/playbooks/{_PB_ID}/rules",
        json={"clause_type": "indemnification", legacy_field: value},
    )
    assert response.status_code == 422
    response = client.patch(f"/api/playbooks/rules/{_RULE_ID}", json={legacy_field: value})
    assert response.status_code == 422


# ── Rule update ───────────────────────────────────────────────────────────────


def test_update_rule_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.patch(
        f"/api/playbooks/rules/{_UNKNOWN_ID}",
        json={"clause_type": "liability"},
    )
    assert response.status_code == 404


def test_update_rule_success() -> None:
    rule = _make_rule(clause_type="liability")

    with (
        patch(
            "app.db.repositories.playbook_repo.get_rule",
            new=AsyncMock(return_value=rule),
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rule_with_children",
            new=AsyncMock(return_value=rule),
        ),
    ):
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        response = client.patch(
            f"/api/playbooks/rules/{_RULE_ID}",
            json={"clause_type": "liability"},
        )

    assert response.status_code == 200
    assert response.json()["clause_type"] == "liability"
    assert response.json()["positions"][0]["rung"] == 0


def test_update_rule_syncs_positions() -> None:
    """Changing a rule's preferred language = PATCHing its positions list."""
    rule = _make_rule()
    existing_position_id = uuid.uuid4()

    with (
        patch(
            "app.db.repositories.playbook_repo.get_rule",
            new=AsyncMock(return_value=rule),
        ),
        patch(
            "app.db.repositories.playbook_repo.get_rule_with_children",
            new=AsyncMock(return_value=rule),
        ),
        patch(
            "app.db.repositories.playbook_repo.sync_rule_positions",
            new=AsyncMock(return_value=[]),
        ) as mock_sync_pos,
        patch(
            "app.db.repositories.playbook_repo.sync_rule_red_lines",
            new=AsyncMock(return_value=[]),
        ) as mock_sync_rl,
    ):
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        response = client.patch(
            f"/api/playbooks/rules/{_RULE_ID}",
            json={
                "positions": [
                    {"id": str(existing_position_id), "kind": "preferred", "rung": 0,
                     "label": "Preferred", "language": "Revised.", "zone": "green"},
                ]
            },
        )

    assert response.status_code == 200
    positions = mock_sync_pos.call_args.args[2]
    assert positions[0]["id"] == existing_position_id
    assert positions[0]["language"] == "Revised."
    mock_sync_rl.assert_not_called()  # red_lines omitted → untouched


# ── Rule delete ───────────────────────────────────────────────────────────────


def test_delete_rule_not_found() -> None:
    mock_session.execute = AsyncMock(return_value=_scalar(None))
    response = client.delete(f"/api/playbooks/rules/{_UNKNOWN_ID}")
    assert response.status_code == 404


def test_delete_rule_success() -> None:
    with patch(
        "app.db.repositories.playbook_repo.get_rule",
        new=AsyncMock(return_value=_make_rule()),  # legacy, unversioned
    ):
        mock_session.execute = AsyncMock(return_value=_rowcount(1))
        mock_session.commit = AsyncMock()
        response = client.delete(f"/api/playbooks/rules/{_RULE_ID}")
    assert response.status_code == 204


def _versioned_rule(status: str) -> tuple[MagicMock, MagicMock]:
    from app.db.models.playbook import PlaybookVersion

    version = MagicMock(spec=PlaybookVersion)
    version.id = uuid.uuid4()
    version.status = status
    rule = _make_rule()
    rule.playbook_version_id = version.id
    return rule, version


def test_patch_rule_scalar_on_published_version_returns_409() -> None:
    rule, published = _versioned_rule("published")
    with (
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.get_version",
            new=AsyncMock(return_value=published),
        ),
        patch("app.db.repositories.playbook_repo.update_rule", new=AsyncMock()) as mock_update,
    ):
        response = client.patch(f"/api/playbooks/rules/{_RULE_ID}", json={"risk_weight": 9.0})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_not_draft"
    mock_update.assert_not_called()


def test_delete_rule_on_published_version_returns_409() -> None:
    rule, published = _versioned_rule("published")
    with (
        patch("app.db.repositories.playbook_repo.get_rule", new=AsyncMock(return_value=rule)),
        patch(
            "app.db.repositories.playbook_repo.get_version",
            new=AsyncMock(return_value=published),
        ),
        patch("app.db.repositories.playbook_repo.delete_rule", new=AsyncMock()) as mock_delete,
    ):
        response = client.delete(f"/api/playbooks/rules/{_RULE_ID}")
    assert response.status_code == 409
    mock_delete.assert_not_called()
