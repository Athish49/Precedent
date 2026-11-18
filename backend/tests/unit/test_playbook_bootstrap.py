"""Tests for S6 playbook bootstrap batch LLM job (T-038 / task 4.11)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.errors import AppError
from app.api.routes.playbooks import _get_session
from app.core.llm.schemas.playbook import PlaybookBootstrapOut
from app.db.models.playbook import Playbook, PlaybookRule, PlaybookVersion
from app.main import app
from tests.fake_llm import FakeLLMGateway

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK = "playbook.bootstrap"


def _make_playbook(practice_area: str = "nda") -> MagicMock:
    pb = MagicMock(spec=Playbook)
    pb.id = uuid.uuid4()
    pb.practice_area = practice_area
    pb.name = "Test Playbook"
    pb.precedence = 0
    return pb


def _make_clause(
    contract_id: uuid.UUID,
    clause_type: str,
    text: str = "Standard clause text.",
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.contract_id = contract_id
    c.clause_type = clause_type
    c.text = text
    c.ordinal = 1
    return c


def _make_rule(playbook_id: uuid.UUID, clause_type: str) -> MagicMock:
    r = MagicMock(spec=PlaybookRule)
    r.id = uuid.uuid4()
    r.playbook_id = playbook_id
    r.clause_type = clause_type
    return r


def _make_version(
    playbook_id: uuid.UUID,
    status: str = "draft",
    created_at: datetime | None = None,
) -> MagicMock:
    v = MagicMock(spec=PlaybookVersion)
    v.id = uuid.uuid4()
    v.playbook_id = playbook_id
    v.status = status
    v.created_at = created_at or datetime.now(UTC)
    return v


def _make_issue(family_key: str, key: str) -> MagicMock:
    issue = MagicMock()
    issue.id = uuid.uuid4()
    issue.family_key = family_key
    issue.key = key
    issue.name = key.replace("_", " ").title()
    issue.description = f"The {key} issue."
    return issue


class _Taxonomy:
    """In-memory stand-in for ``taxonomy_repo`` as bootstrap uses it."""

    def __init__(
        self,
        issues: dict[str, list[str]] | None = None,
        families: set[str] | None = None,
    ) -> None:
        self.issues: dict[tuple[str, str], MagicMock] = {}
        for family, keys in (issues or {}).items():
            for key in keys:
                self.issues[(family, key)] = _make_issue(family, key)
        # None = every family exists.
        self.families = families
        self.created: list[MagicMock] = []

    async def list_clause_issues(self, session, family_key=None):
        return [i for (f, _k), i in self.issues.items() if family_key in (None, f)]

    async def get_clause_issue_by_key(self, session, family_key, key):
        return self.issues.get((family_key, key))

    async def get_clause_family(self, session, key):
        return None if self.families is not None and key not in self.families else MagicMock()

    async def create_clause_issue(self, session, family_key, key, name, description, **kw):
        issue = _make_issue(family_key, key)
        self.issues[(family_key, key)] = issue
        self.created.append(issue)
        return issue


@pytest.fixture(autouse=True)
def taxonomy(monkeypatch: pytest.MonkeyPatch) -> _Taxonomy:
    """Default: every family exists, none has issues seeded (so every rule
    lands on the ``unclassified`` placeholder). Tests needing seeded issues
    replace the fixture's contents."""
    from app.services.playbook import bootstrap as svc

    tax = _Taxonomy()
    for name in (
        "list_clause_issues", "get_clause_issue_by_key", "get_clause_family", "create_clause_issue"
    ):
        monkeypatch.setattr(svc.taxonomy_repo, name, getattr(tax, name))
    return tax


def _make_position_recorder() -> tuple[list[dict], AsyncMock]:
    """Return (captured positions, async side-effect) for create_rule_position."""
    captured: list[dict] = []

    async def _create(session, rule_id, kind, label, language, zone, **kwargs):
        pos = MagicMock()
        pos.id = uuid.uuid4()
        pos.rule_id = rule_id
        pos.kind = kind
        pos.label = label
        pos.language = language
        pos.zone = zone
        captured.append(
            {"rule_id": rule_id, "kind": kind, "label": label, "language": language, "zone": zone}
        )
        return pos

    return captured, AsyncMock(side_effect=_create)


# ---------------------------------------------------------------------------
# Unit tests for run_bootstrap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_creates_rules_from_corpus() -> None:
    """Bootstrap seeds a 'preferred' and 'acceptable_variant' rule_position
    per clause_type, on a new rule in the draft version, authored_by bootstrap."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    draft = _make_version(pb.id, status="draft")
    cid = uuid.uuid4()

    clause_indem = _make_clause(cid, "indemnification", "Party A shall indemnify...")
    clause_term = _make_clause(cid, "termination", "Either party may terminate...")

    preset = PlaybookBootstrapOut(
        clause_type="indemnification",
        preferred_language="Party A shall indemnify Party B.",
        acceptable_variations=["Each party indemnifies the other."],
    )
    fake = FakeLLMGateway(structured_responses={_TASK: preset})

    mock_session = AsyncMock()

    created_rules: list[dict] = []

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        rule = MagicMock(spec=PlaybookRule)
        rule.id = uuid.uuid4()
        rule.playbook_id = playbook_id
        rule.clause_type = clause_type
        created_rules.append({"clause_type": clause_type, **kwargs})
        return rule

    captured_positions, create_position_mock = _make_position_recorder()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause_indem, clause_term],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_versions",
            return_value=[draft],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules_for_version",
            return_value=[],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule_position",
            create_position_mock,
        ),
    ):
        count = await svc.run_bootstrap(mock_session, pb.id, [cid])

    # Two distinct clause_types → two rules created
    assert count == 2
    types_created = {r["clause_type"] for r in created_rules}
    assert types_created == {"indemnification", "termination"}

    # Every rule bootstrap creates is tied to the draft version and stamped
    # authored_by="bootstrap" — never a published version, never anonymous.
    for r in created_rules:
        assert r["playbook_version_id"] == draft.id
        assert r["authored_by"] == "bootstrap"
        # {family}.{issue} convention, never a bare clause_type.
        assert r["rule_key"] == f"{r['clause_type']}.unclassified"
        assert r["issue_id"] is not None

    # Legacy preferred_language/acceptable_variations columns are no longer
    # written directly by bootstrap — only rule_position rows are.
    for r in created_rules:
        assert "preferred_language" not in r
        assert "acceptable_variations" not in r
        assert "prohibited_terms" not in r

    # One 'preferred' and exactly len(acceptable_variations) 'acceptable_variant'
    # positions were created per rule.
    kinds = [p["kind"] for p in captured_positions]
    assert kinds.count("preferred") == 2  # one per rule
    assert kinds.count("acceptable_variant") == 2  # fake preset returns 1 per rule
    assert all(p["zone"] == "green" for p in captured_positions)


@pytest.mark.asyncio
async def test_bootstrap_skips_existing_clause_types() -> None:
    """Clause types that already have a rule in the draft version are not overwritten."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    draft = _make_version(pb.id, status="draft")
    cid = uuid.uuid4()

    existing_rule = _make_rule(pb.id, "indemnification")
    clause_indem = _make_clause(cid, "indemnification")
    clause_term = _make_clause(cid, "termination")

    preset = PlaybookBootstrapOut(
        clause_type="termination",
        preferred_language="Either party may terminate.",
        acceptable_variations=[],
    )
    fake = FakeLLMGateway(structured_responses={_TASK: preset})

    created_rules: list[dict] = []

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        created_rules.append({"clause_type": clause_type})
        return _make_rule(playbook_id, clause_type)

    _captured_positions, create_position_mock = _make_position_recorder()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause_indem, clause_term],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_versions",
            return_value=[draft],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules_for_version",
            return_value=[existing_rule],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule_position",
            create_position_mock,
        ),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [cid])

    # Only "termination" is new; "indemnification" already exists in the draft
    assert count == 1
    assert created_rules[0]["clause_type"] == "termination"


@pytest.mark.asyncio
async def test_bootstrap_empty_corpus_returns_zero() -> None:
    """No contracts in corpus → 0 rules created, no LLM call made."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    fake = FakeLLMGateway()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[],
        ),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [uuid.uuid4()])

    assert count == 0
    assert fake.calls == []


@pytest.mark.asyncio
async def test_bootstrap_empty_contract_ids_returns_zero() -> None:
    """Empty contract_ids list short-circuits before any DB or LLM call."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    fake = FakeLLMGateway()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [])

    assert count == 0
    assert fake.calls == []


@pytest.mark.asyncio
async def test_bootstrap_404_on_missing_playbook() -> None:
    """Missing playbook raises AppError 404."""
    from app.services.playbook import bootstrap as svc

    with patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=None):
        mock_session = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await svc.run_bootstrap(mock_session, uuid.uuid4(), [uuid.uuid4()])

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_bootstrap_all_types_already_exist_returns_zero() -> None:
    """All clause types already have rules in the draft → no LLM call, 0 created."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    draft = _make_version(pb.id, status="draft")
    cid = uuid.uuid4()
    clause = _make_clause(cid, "indemnification")
    existing = _make_rule(pb.id, "indemnification")

    fake = FakeLLMGateway()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_versions",
            return_value=[draft],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules_for_version",
            return_value=[existing],
        ),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [cid])

    assert count == 0
    assert fake.calls == []


# ---------------------------------------------------------------------------
# rule_key convention (playbook_plan.md section 3.4): every bootstrapped rule
# gets a real issue_id and a "{clause_type}.{issue_key}" rule_key, so it can
# merge with / be overridden by a seeded rule in routing.resolve.
# ---------------------------------------------------------------------------


async def _run_with_preset(
    taxonomy: _Taxonomy, clauses: list, preset: PlaybookBootstrapOut
) -> tuple[int, list[dict], FakeLLMGateway]:
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    draft = _make_version(pb.id, status="draft")
    fake = FakeLLMGateway(structured_responses={_TASK: preset})
    created_rules: list[dict] = []

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        created_rules.append({"clause_type": clause_type, **kwargs})
        return _make_rule(playbook_id, clause_type)

    _captured, create_position_mock = _make_position_recorder()
    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=clauses,
        ),
        patch("app.services.playbook.bootstrap.playbook_repo.list_versions", return_value=[draft]),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules_for_version",
            return_value=[],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule_position",
            create_position_mock,
        ),
    ):
        count = await svc.run_bootstrap(AsyncMock(), pb.id, [uuid.uuid4()])
    return count, created_rules, fake


@pytest.mark.asyncio
async def test_bootstrap_rule_key_uses_model_classified_issue(taxonomy: _Taxonomy) -> None:
    """The model's issue_key, when it is one of the family's issues, sets
    issue_id and a qualified rule_key; the issues are offered in the prompt."""
    from app.services.playbook.bootstrap import _BootstrapIssueOut

    taxonomy.issues.clear()
    for key in ("cap_amount", "carve_outs"):
        taxonomy.issues[("limitation_of_liability", key)] = _make_issue(
            "limitation_of_liability", key
        )
    cid = uuid.uuid4()
    preset = _BootstrapIssueOut(
        clause_type="limitation_of_liability",
        preferred_language="Liability is capped at fees paid.",
        acceptable_variations=[],
        issue_key="cap_amount",
    )

    count, created, fake = await _run_with_preset(
        taxonomy, [_make_clause(cid, "limitation_of_liability")], preset
    )

    assert count == 1
    expected = taxonomy.issues[("limitation_of_liability", "cap_amount")]
    assert created[0]["rule_key"] == "limitation_of_liability.cap_amount"
    assert created[0]["issue_id"] == expected.id
    assert taxonomy.created == []  # no placeholder needed
    user_msg = fake.calls[0]["items"][0]["messages"][1]["content"]
    assert "- cap_amount:" in user_msg and "- carve_outs:" in user_msg


@pytest.mark.asyncio
@pytest.mark.parametrize("issue_key", [None, "made_up_issue"])
async def test_bootstrap_unmatched_issue_uses_placeholder(
    taxonomy: _Taxonomy, issue_key: str | None
) -> None:
    """No match (null) or a key the family does not have → the family's
    'unclassified' placeholder issue, created once, never an unqualified key."""
    from app.services.playbook.bootstrap import _BootstrapIssueOut

    taxonomy.issues[("indemnification", "scope")] = _make_issue("indemnification", "scope")
    preset = _BootstrapIssueOut(
        clause_type="indemnification",
        preferred_language="Party A shall indemnify Party B.",
        acceptable_variations=[],
        issue_key=issue_key,
    )

    count, created, _ = await _run_with_preset(
        taxonomy, [_make_clause(uuid.uuid4(), "indemnification")], preset
    )

    assert count == 1
    assert created[0]["rule_key"] == "indemnification.unclassified"
    assert [i.key for i in taxonomy.created] == ["unclassified"]
    assert created[0]["issue_id"] == taxonomy.created[0].id


@pytest.mark.asyncio
async def test_bootstrap_reuses_existing_placeholder_issue(taxonomy: _Taxonomy) -> None:
    placeholder = _make_issue("termination", "unclassified")
    taxonomy.issues[("termination", "unclassified")] = placeholder
    preset = PlaybookBootstrapOut(
        clause_type="termination", preferred_language="Either party may terminate.",
        acceptable_variations=[],
    )

    _count, created, fake = await _run_with_preset(
        taxonomy, [_make_clause(uuid.uuid4(), "termination")], preset
    )

    assert created[0]["issue_id"] == placeholder.id
    assert created[0]["rule_key"] == "termination.unclassified"
    assert taxonomy.created == []
    # The placeholder itself is never offered to the model as a choice.
    assert "- unclassified:" not in fake.calls[0]["items"][0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_bootstrap_skips_type_with_no_clause_family(taxonomy: _Taxonomy) -> None:
    """A clause_type with no clause_family row cannot get an issue: it is
    skipped (no LLM item, no rule) rather than written with a bare key."""
    taxonomy.families = {"indemnification"}
    cid = uuid.uuid4()
    preset = PlaybookBootstrapOut(
        clause_type="indemnification", preferred_language="X.", acceptable_variations=[],
    )

    count, created, fake = await _run_with_preset(
        taxonomy, [_make_clause(cid, "indemnification"), _make_clause(cid, "mystery")], preset
    )

    assert count == 1
    assert [r["clause_type"] for r in created] == ["indemnification"]
    assert [i["id"] for i in fake.calls[0]["items"]] == ["indemnification"]
    for r in created:
        assert "." in r["rule_key"]


# ---------------------------------------------------------------------------
# Draft-only enforcement (task 4.11): bootstrap never writes to a published
# version. It does not auto-create a draft either — see bootstrap.py's
# module docstring for why. It 409s instead, and the caller must create a
# draft first through the versions API (task 4.8).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_rejects_when_current_version_is_published() -> None:
    """Playbook's only version is published → 409, nothing is written."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    published = _make_version(pb.id, status="published")
    cid = uuid.uuid4()
    clause = _make_clause(cid, "indemnification")

    fake = FakeLLMGateway()
    create_rule_mock = AsyncMock()
    _captured_positions, create_position_mock = _make_position_recorder()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_versions",
            return_value=[published],
        ),
        patch("app.services.playbook.bootstrap.playbook_repo.create_rule", create_rule_mock),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule_position",
            create_position_mock,
        ),
    ):
        mock_session = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await svc.run_bootstrap(mock_session, pb.id, [cid])

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "no_draft_version"
    # Nothing was ever written, and the LLM was never called.
    assert fake.calls == []
    create_rule_mock.assert_not_called()
    create_position_mock.assert_not_called()
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_rejects_when_no_versions_exist() -> None:
    """Playbook has no versions at all (pre-versioning legacy state) → 409."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    cid = uuid.uuid4()
    clause = _make_clause(cid, "indemnification")

    fake = FakeLLMGateway()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_versions",
            return_value=[],
        ),
    ):
        mock_session = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await svc.run_bootstrap(mock_session, pb.id, [cid])

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_bootstrap_uses_draft_when_published_version_also_exists() -> None:
    """A published current version plus a separate draft → writes go to the
    draft only; the published version is never touched."""
    from app.services.playbook import bootstrap as svc

    pb = _make_playbook()
    published = _make_version(
        pb.id, status="published", created_at=datetime.now(UTC) - timedelta(days=1)
    )
    draft = _make_version(pb.id, status="draft", created_at=datetime.now(UTC))
    cid = uuid.uuid4()
    clause = _make_clause(cid, "indemnification")

    preset = PlaybookBootstrapOut(
        clause_type="indemnification",
        preferred_language="Party A shall indemnify Party B.",
        acceptable_variations=[],
    )
    fake = FakeLLMGateway(structured_responses={_TASK: preset})

    created_rules: list[dict] = []

    async def _mock_create_rule(session, playbook_id, clause_type, **kwargs):
        rule = MagicMock(spec=PlaybookRule)
        rule.id = uuid.uuid4()
        created_rules.append({"clause_type": clause_type, **kwargs})
        return rule

    _captured_positions, create_position_mock = _make_position_recorder()

    with (
        patch.object(svc, "gateway", fake),
        patch("app.services.playbook.bootstrap.playbook_repo.get_playbook", return_value=pb),
        patch(
            "app.services.playbook.bootstrap.clause_repo.get_clauses_for_contracts",
            return_value=[clause],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_versions",
            return_value=[published, draft],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.list_rules_for_version",
            return_value=[],
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule",
            side_effect=_mock_create_rule,
        ),
        patch(
            "app.services.playbook.bootstrap.playbook_repo.create_rule_position",
            create_position_mock,
        ),
    ):
        mock_session = AsyncMock()
        count = await svc.run_bootstrap(mock_session, pb.id, [cid])

    assert count == 1
    assert created_rules[0]["playbook_version_id"] == draft.id


# ---------------------------------------------------------------------------
# Sampling across contracts (task 4.11): the old bug took the first N
# clauses found, which (given the query orders by contract_id then ordinal)
# could all come from the same one or two contracts. The fix spreads the
# sample across distinct contracts first.
# ---------------------------------------------------------------------------


def test_sample_across_contracts_spreads_across_distinct_contracts() -> None:
    from app.services.playbook.bootstrap import _sample_across_contracts

    contract_ids = [uuid.uuid4() for _ in range(3)]
    clauses = []
    for cid in contract_ids:
        for i in range(3):  # 3 clauses per contract, 9 total
            c = MagicMock()
            c.contract_id = cid
            c.text = f"clause {i} for {cid}"
            clauses.append(c)

    samples = _sample_across_contracts(clauses, max_samples=5)

    assert len(samples) == 5
    # Round-robin guarantees every contract contributes its first clause
    # before any contract contributes a second — so among the first 3
    # samples, all 3 distinct contracts must appear.
    first_three_contract_ids = {c.contract_id for c in samples[:3]}
    assert first_three_contract_ids == set(contract_ids)


def test_sample_across_contracts_returns_all_when_under_max() -> None:
    from app.services.playbook.bootstrap import _sample_across_contracts

    cid = uuid.uuid4()
    clauses = [MagicMock(contract_id=cid) for _ in range(3)]

    samples = _sample_across_contracts(clauses, max_samples=5)

    assert samples == clauses


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

mock_session = AsyncMock()


async def _bootstrap_mock_session():
    yield mock_session


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _patch_bootstrap_session():
    prev = app.dependency_overrides.get(_get_session)
    app.dependency_overrides[_get_session] = _bootstrap_mock_session
    yield
    if prev is None:
        app.dependency_overrides.pop(_get_session, None)
    else:
        app.dependency_overrides[_get_session] = prev


def test_bootstrap_api_with_contract_ids() -> None:
    """POST /playbooks/bootstrap with explicit contract_ids returns created count."""
    playbook_id = uuid.uuid4()
    contract_id = uuid.uuid4()

    with patch(
        "app.api.routes.playbooks.bootstrap_service.run_bootstrap",
        new_callable=AsyncMock,
        return_value=3,
    ):
        response = client.post(
            "/api/playbooks/bootstrap",
            json={
                "playbook_id": str(playbook_id),
                "contract_ids": [str(contract_id)],
            },
        )

    assert response.status_code == 200
    assert response.json()["created_rule_count"] == 3


def test_bootstrap_api_with_contract_type() -> None:
    """POST /playbooks/bootstrap with contract_type loads contracts then bootstraps."""
    from app.db.models.contract import Contract

    playbook_id = uuid.uuid4()
    contract_id = uuid.uuid4()

    fake_contract = MagicMock(spec=Contract)
    fake_contract.id = contract_id

    with (
        patch(
            "app.api.routes.playbooks.contract_repo.list_contracts",
            new_callable=AsyncMock,
            return_value=([fake_contract], 1),
        ),
        patch(
            "app.api.routes.playbooks.bootstrap_service.run_bootstrap",
            new_callable=AsyncMock,
            return_value=2,
        ) as mock_run,
    ):
        response = client.post(
            "/api/playbooks/bootstrap",
            json={"playbook_id": str(playbook_id), "contract_type": "nda"},
        )

    assert response.status_code == 200
    assert response.json()["created_rule_count"] == 2
    # Verify contract IDs were resolved and passed through
    call_args = mock_run.call_args
    assert contract_id in call_args.args[2]


def test_bootstrap_api_missing_corpus_returns_422() -> None:
    """Neither contract_ids nor contract_type → 422 validation error."""
    response = client.post(
        "/api/playbooks/bootstrap",
        json={"playbook_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


def test_bootstrap_api_missing_playbook_id_returns_422() -> None:
    """Missing playbook_id → 422 validation error."""
    response = client.post(
        "/api/playbooks/bootstrap",
        json={"contract_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 422


def test_bootstrap_api_propagates_404() -> None:
    """AppError 404 from bootstrap service is surfaced as HTTP 404."""
    with patch(
        "app.api.routes.playbooks.bootstrap_service.run_bootstrap",
        new_callable=AsyncMock,
        side_effect=AppError(404, "not_found", "Playbook not found"),
    ):
        response = client.post(
            "/api/playbooks/bootstrap",
            json={
                "playbook_id": str(uuid.uuid4()),
                "contract_ids": [str(uuid.uuid4())],
            },
        )

    assert response.status_code == 404


def test_bootstrap_api_propagates_409_on_published_only() -> None:
    """AppError 409 (no draft version) is surfaced as HTTP 409, per task 4.11."""
    with patch(
        "app.api.routes.playbooks.bootstrap_service.run_bootstrap",
        new_callable=AsyncMock,
        side_effect=AppError(409, "no_draft_version", "No draft version"),
    ):
        response = client.post(
            "/api/playbooks/bootstrap",
            json={
                "playbook_id": str(uuid.uuid4()),
                "contract_ids": [str(uuid.uuid4())],
            },
        )

    assert response.status_code == 409
