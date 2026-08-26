"""Tests for T-039 seed_playbooks script."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.playbook import Playbook
from app.services.document_processing.clause_types import _SYNONYMS
from scripts.seed_playbooks import _TEMPLATES, seed_all

# Canonical clause_type values derived from the synonym dictionary.
_CANONICAL = set(_SYNONYMS.values())


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_playbook(name: str, practice_area: str) -> MagicMock:
    pb = MagicMock(spec=Playbook)
    pb.id = uuid.uuid4()
    pb.name = name
    pb.practice_area = practice_area
    pb.precedence = 10
    return pb


# ---------------------------------------------------------------------------
# Template data integrity tests (pure Python — no async, no mocks)
# ---------------------------------------------------------------------------


def test_five_templates_defined() -> None:
    assert len(_TEMPLATES) == 5


def test_practice_areas_cover_all_regimes() -> None:
    areas = {t["practice_area"] for t in _TEMPLATES}
    assert areas == {"nda", "dpa", "saas_msa", "hipaa", "gdpr"}


def test_all_clause_types_are_canonical() -> None:
    """Every clause_type in every template must be a canonical value."""
    bad: list[str] = []
    for template in _TEMPLATES:
        for rule in template["rules"]:
            ct = rule["clause_type"]
            if ct not in _CANONICAL:
                bad.append(f"{template['name']}: {ct!r}")
    assert not bad, "Non-canonical clause_types found:\n" + "\n".join(bad)


def test_regulatory_playbooks_have_prohibited_terms() -> None:
    """DPA, HIPAA, and GDPR templates must each have at least one rule with prohibited_terms."""
    regulatory = {"dpa", "hipaa", "gdpr"}
    for template in _TEMPLATES:
        if template["practice_area"] not in regulatory:
            continue
        has_prohibited = any(
            rule.get("prohibited_terms") for rule in template["rules"]
        )
        assert has_prohibited, (
            f"{template['name']} has no rules with prohibited_terms — "
            "regulatory templates require them"
        )


def test_required_true_on_core_clauses() -> None:
    """Each template must mark at least half its rules as required=True."""
    for template in _TEMPLATES:
        rules = template["rules"]
        required_count = sum(1 for r in rules if r.get("required"))
        assert required_count >= len(rules) // 2, (
            f"{template['name']}: only {required_count}/{len(rules)} rules are required"
        )


def test_risk_weights_in_range() -> None:
    for template in _TEMPLATES:
        for rule in template["rules"]:
            w = rule.get("risk_weight", 0.0)
            assert 0.0 <= w <= 10.0, (
                f"{template['name']}/{rule['clause_type']}: risk_weight {w} out of range"
            )


# ---------------------------------------------------------------------------
# seed_all unit tests (mocked session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_all_creates_all_playbooks() -> None:
    """seed_all creates one playbook per template when DB is empty."""
    mock_session = AsyncMock()
    created_pbs: list[str] = []
    created_rules: list[tuple[str, str]] = []  # (playbook_name, clause_type)

    async def _mock_create_playbook(session, name, practice_area, precedence=0):
        pb = _make_playbook(name, practice_area)
        created_pbs.append(name)
        return pb

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        r = MagicMock()
        r.id = uuid.uuid4()
        r.clause_type = clause_type
        created_rules.append((str(playbook_id), clause_type))
        return r

    with (
        patch("scripts.seed_playbooks.playbook_repo.list_playbooks", return_value=[]),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_playbook",
            side_effect=_mock_create_playbook,
        ),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
    ):
        counts = await seed_all(mock_session)

    assert len(counts) == 5
    assert set(created_pbs) == {t["name"] for t in _TEMPLATES}
    # Verify at least one rule per playbook
    for name in created_pbs:
        template_rule_count = next(
            len(t["rules"]) for t in _TEMPLATES if t["name"] == name
        )
        assert template_rule_count > 0


@pytest.mark.asyncio
async def test_seed_all_returns_correct_rule_counts() -> None:
    """counts returned match the number of rules in each template."""
    mock_session = AsyncMock()

    async def _mock_create_playbook(session, name, practice_area, precedence=0):
        return _make_playbook(name, practice_area)

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        r = MagicMock()
        r.id = uuid.uuid4()
        return r

    with (
        patch("scripts.seed_playbooks.playbook_repo.list_playbooks", return_value=[]),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_playbook",
            side_effect=_mock_create_playbook,
        ),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
    ):
        counts = await seed_all(mock_session)

    for template in _TEMPLATES:
        assert counts[template["name"]] == len(template["rules"]), (
            f"{template['name']}: expected {len(template['rules'])} rules, "
            f"got {counts[template['name']]}"
        )


@pytest.mark.asyncio
async def test_seed_all_idempotent_skips_existing() -> None:
    """seed_all returns 0 rules for playbooks whose name already exists."""
    mock_session = AsyncMock()
    existing = [_make_playbook(t["name"], t["practice_area"]) for t in _TEMPLATES]

    with (
        patch("scripts.seed_playbooks.playbook_repo.list_playbooks", return_value=existing),
        patch("scripts.seed_playbooks.playbook_repo.create_playbook") as mock_create,
        patch("scripts.seed_playbooks.playbook_repo.create_rule") as mock_rule,
    ):
        counts = await seed_all(mock_session)

    mock_create.assert_not_called()
    mock_rule.assert_not_called()
    assert all(v == 0 for v in counts.values())


@pytest.mark.asyncio
async def test_seed_all_partial_idempotency() -> None:
    """seed_all seeds only the templates not already present."""
    mock_session = AsyncMock()

    # Pre-seed only NDA and DPA
    existing = [
        _make_playbook(t["name"], t["practice_area"])
        for t in _TEMPLATES
        if t["practice_area"] in ("nda", "dpa")
    ]

    created_names: list[str] = []

    async def _mock_create_playbook(session, name, practice_area, precedence=0):
        created_names.append(name)
        return _make_playbook(name, practice_area)

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        r = MagicMock()
        r.id = uuid.uuid4()
        return r

    with (
        patch(
            "scripts.seed_playbooks.playbook_repo.list_playbooks", return_value=existing
        ),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_playbook",
            side_effect=_mock_create_playbook,
        ),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
    ):
        counts = await seed_all(mock_session)

    # NDA and DPA already exist → 0
    assert counts["NDA Standard"] == 0
    assert counts["DPA Standard"] == 0
    # The other three were created
    assert "SaaS MSA Standard" in created_names
    assert "HIPAA Standard" in created_names
    assert "GDPR Standard" in created_names


@pytest.mark.asyncio
async def test_seed_all_commits_after_each_playbook() -> None:
    """session.commit() is called once per new playbook (not per rule)."""
    mock_session = AsyncMock()

    async def _mock_create_playbook(session, name, practice_area, precedence=0):
        return _make_playbook(name, practice_area)

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        r = MagicMock()
        r.id = uuid.uuid4()
        return r

    with (
        patch("scripts.seed_playbooks.playbook_repo.list_playbooks", return_value=[]),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_playbook",
            side_effect=_mock_create_playbook,
        ),
        patch(
            "scripts.seed_playbooks.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
    ):
        await seed_all(mock_session)

    # One commit per template (5 total)
    assert mock_session.commit.call_count == 5
