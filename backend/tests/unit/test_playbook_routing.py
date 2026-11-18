"""Tests for the playbook resolution engine (task 4.2;
``playbook_plan.md`` section 5.1).

Covers: base + agreement + overlay merge, override by precedence,
``applies_when`` filtering, party-role selection, an unknown contract_type
still returning the baseline playbook (never zero rules), and deterministic
ordering.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.playbooks import _get_session
from app.db.models.playbook import Playbook
from app.main import app
from app.services.playbook.routing import (
    _paper_scope_matches,
    _party_role_matches,
    matches,
    resolve,
    rules_by_clause_type,
)

_ROUTING_MODULE = "app.services.playbook.routing"

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _make_playbook(
    key: str,
    layer: str = "agreement",
    practice_area: str = "saas_msa",
    party_role: str = "vendor",
    paper_scope: str = "both",
    precedence: int = 20,
    status: str = "active",
    applies_when: dict | None = None,
    current_version_id: uuid.UUID | None = None,
    name: str | None = None,
) -> MagicMock:
    pb = MagicMock(spec=Playbook)
    pb.id = uuid.uuid4()
    pb.key = key
    pb.name = name or key
    pb.layer = layer
    pb.practice_area = practice_area
    pb.party_role = party_role
    pb.paper_scope = paper_scope
    pb.precedence = precedence
    pb.status = status
    pb.applies_when = applies_when
    pb.current_version_id = (
        current_version_id if current_version_id is not None else uuid.uuid4()
    )
    return pb


def _make_rule(
    rule_key: str,
    clause_type: str = "limitation_of_liability",
    playbook_id: uuid.UUID | None = None,
    playbook_version_id: uuid.UUID | None = None,
    risk_weight: float = 5.0,
    required: bool = False,
    applies_when: dict | None = None,
    preferred_text: str = "Standard language.",
) -> SimpleNamespace:
    """A plain object standing in for a ``PlaybookRule`` ORM instance with its
    six child lists already attached, as ``get_rules_with_children`` returns.

    *preferred_text* becomes the language of the rule's single rung-0
    ``preferred`` position. That is the only place a rule's preferred
    language lives since migration 015 dropped the legacy flat column.
    """
    rule_id = uuid.uuid4()
    return SimpleNamespace(
        id=rule_id,
        playbook_id=playbook_id or uuid.uuid4(),
        playbook_version_id=playbook_version_id or uuid.uuid4(),
        clause_type=clause_type,
        issue_id=None,
        rule_key=rule_key,
        title=rule_key,
        position_summary=None,
        risk_rationale=None,
        required=required,
        negotiable=True,
        risk_weight=risk_weight,
        default_zone="yellow",
        needs_human_judgment=False,
        judgment_note=None,
        applies_when=applies_when,
        detection_guidance=None,
        source_ref=None,
        authored_by=None,
        approved_by=None,
        last_reviewed_at=None,
        positions=[_make_preferred_position(rule_id, preferred_text)],
        parameters=[],
        red_lines=[],
        objections=[],
        dependencies=[],
        test_cases=[],
    )


def _make_preferred_position(rule_id: uuid.UUID, language: str) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        rule_id=rule_id,
        kind="preferred",
        rung=0,
        label="Preferred",
        language=language,
        summary=None,
        zone="green",
        approver_role_id=None,
        conditions=None,
        give_get=None,
        internal_note=None,
        created_at=now,
        updated_at=now,
    )


def _make_version(version: str) -> SimpleNamespace:
    return SimpleNamespace(version=version)


class _RepoFixture:
    """Wires ``playbook_repo.list_playbooks`` / ``get_version`` /
    ``get_rules_with_children`` to a fixed scenario, keyed by playbook /
    version id, so ``resolve()`` can be exercised without a real session.
    """

    def __init__(self, playbooks: list[MagicMock]) -> None:
        self.playbooks = playbooks
        self.rules_by_version: dict[uuid.UUID, list[SimpleNamespace]] = {}
        self.version_by_id: dict[uuid.UUID, SimpleNamespace] = {}

    def add_rules(self, playbook: MagicMock, rules: list[SimpleNamespace], version: str) -> None:
        self.rules_by_version[playbook.current_version_id] = rules
        self.version_by_id[playbook.current_version_id] = _make_version(version)

    async def _list_playbooks(self, _session: object) -> list[MagicMock]:
        return self.playbooks

    async def _get_version(self, _session: object, version_id: uuid.UUID) -> SimpleNamespace | None:
        return self.version_by_id.get(version_id)

    async def _get_rules_with_children(
        self, _session: object, version_id: uuid.UUID
    ) -> list[SimpleNamespace]:
        return self.rules_by_version.get(version_id, [])

    def __enter__(self) -> _RepoFixture:
        self._stack = contextlib.ExitStack()
        self._stack.enter_context(
            patch(f"{_ROUTING_MODULE}.playbook_repo.list_playbooks", new=self._list_playbooks)
        )
        self._stack.enter_context(
            patch(f"{_ROUTING_MODULE}.playbook_repo.get_version", new=self._get_version)
        )
        self._stack.enter_context(
            patch(
                f"{_ROUTING_MODULE}.playbook_repo.get_rules_with_children",
                new=self._get_rules_with_children,
            )
        )
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stack.close()


# ---------------------------------------------------------------------------
# matches() — pure predicate
# ---------------------------------------------------------------------------


def test_matches_none_condition_always_matches() -> None:
    assert matches(None, {}) is True
    assert matches(None, {"regimes": ["hipaa"]}) is True


def test_matches_empty_condition_always_matches() -> None:
    assert matches({}, {"anything": "value"}) is True


def test_matches_multi_value_context_intersects() -> None:
    assert matches({"regimes": ["hipaa"]}, {"regimes": ["hipaa", "gdpr"]}) is True
    assert matches({"regimes": ["hipaa"]}, {"regimes": ["gdpr"]}) is False


def test_matches_scalar_context_value() -> None:
    assert matches({"deal_value_band": ["mid", "enterprise"]}, {"deal_value_band": "mid"}) is True
    assert matches({"deal_value_band": ["mid"]}, {"deal_value_band": "standard"}) is False


def test_matches_missing_context_key_fails() -> None:
    assert matches({"deal_value_band": ["mid"]}, {}) is False


def test_matches_all_keys_must_match() -> None:
    condition = {"regimes": ["hipaa"], "region": ["us"]}
    assert matches(condition, {"regimes": ["hipaa"], "region": ["us"]}) is True
    assert matches(condition, {"regimes": ["hipaa"], "region": ["eu"]}) is False


def test_party_role_matches_wildcard_and_equality() -> None:
    assert _party_role_matches("mutual", "vendor") is True
    assert _party_role_matches("mutual", "customer") is True
    assert _party_role_matches("vendor", "vendor") is True
    assert _party_role_matches("vendor", "customer") is False


def test_paper_scope_matches_wildcard_and_equality() -> None:
    assert _paper_scope_matches("both", "own") is True
    assert _paper_scope_matches("both", "counterparty") is True
    assert _paper_scope_matches("own", "own") is True
    assert _paper_scope_matches("own", "counterparty") is False


# ---------------------------------------------------------------------------
# resolve() — base + agreement + overlay merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_merges_base_agreement_and_overlay() -> None:
    """Three distinct rule_keys, one per layer, all survive into the merge."""
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    agreement = _make_playbook(
        "halcyon-saas-msa-vendor", layer="agreement", practice_area="saas_msa", precedence=20
    )
    overlay = _make_playbook(
        "halcyon-hipaa-overlay",
        layer="overlay",
        practice_area="hipaa",
        precedence=30,
        applies_when={"regimes": ["hipaa"]},
    )

    fixture = _RepoFixture([base, agreement, overlay])
    fixture.add_rules(base, [_make_rule("notices.method", clause_type="notices")], "1.0")
    fixture.add_rules(
        agreement, [_make_rule("payment.payment_terms", clause_type="payment")], "1.0"
    )
    fixture.add_rules(
        overlay,
        [
            _make_rule(
                "breach_notification.notification_timeline",
                clause_type="breach_notification",
            )
        ],
        "1.0",
    )

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="saas_msa",
            party_role="vendor",
            paper_origin="own",
            context={"regimes": ["hipaa"]},
        )

    rule_keys = {r.rule_key for r in result.rules}
    assert rule_keys == {
        "notices.method",
        "payment.payment_terms",
        "breach_notification.notification_timeline",
    }
    by_key = {r.rule_key: r for r in result.rules}
    assert by_key["notices.method"].source_playbook_name == "halcyon-baseline"
    assert by_key["payment.payment_terms"].source_playbook_name == "halcyon-saas-msa-vendor"
    assert by_key["breach_notification.notification_timeline"].source_version == "1.0"
    assert set(result.applied_playbook_keys) == {
        "halcyon-baseline",
        "halcyon-saas-msa-vendor",
        "halcyon-hipaa-overlay",
    }
    assert len(result.pinned_version_ids) == 3


# ---------------------------------------------------------------------------
# resolve() — override by precedence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_overlay_overrides_agreement_overrides_base() -> None:
    """Same rule_key defined at all three layers — overlay (30) wins."""
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    agreement = _make_playbook(
        "halcyon-saas-msa-vendor", layer="agreement", practice_area="saas_msa", precedence=20
    )
    overlay = _make_playbook(
        "halcyon-hipaa-overlay",
        layer="overlay",
        practice_area="hipaa",
        precedence=30,
        applies_when={"regimes": ["hipaa"]},
    )

    fixture = _RepoFixture([base, agreement, overlay])
    fixture.add_rules(
        base,
        [_make_rule("breach_notification.notification_timeline", preferred_text="BASE")],
        "1.0",
    )
    fixture.add_rules(
        agreement,
        [_make_rule("breach_notification.notification_timeline", preferred_text="AGREEMENT")],
        "1.0",
    )
    fixture.add_rules(
        overlay,
        [_make_rule("breach_notification.notification_timeline", preferred_text="OVERLAY")],
        "1.0",
    )

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="saas_msa",
            party_role="vendor",
            paper_origin="own",
            context={"regimes": ["hipaa"]},
        )

    assert len(result.rules) == 1
    assert result.rules[0].positions[0].language == "OVERLAY"
    assert result.rules[0].source_playbook_name == "halcyon-hipaa-overlay"


@pytest.mark.asyncio
async def test_resolve_agreement_overrides_base_without_overlay() -> None:
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    agreement = _make_playbook(
        "halcyon-saas-msa-vendor", layer="agreement", practice_area="saas_msa", precedence=20
    )

    fixture = _RepoFixture([base, agreement])
    fixture.add_rules(
        base, [_make_rule("governing_law.choice_of_law", preferred_text="BASE")], "1.0"
    )
    fixture.add_rules(
        agreement,
        [_make_rule("governing_law.choice_of_law", preferred_text="AGREEMENT")],
        "1.0",
    )

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="saas_msa",
            party_role="vendor",
            paper_origin="own",
            context={},
        )

    assert len(result.rules) == 1
    assert result.rules[0].positions[0].language == "AGREEMENT"


# ---------------------------------------------------------------------------
# resolve() — applies_when filtering (rule level and overlay-selection level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_drops_rule_whose_applies_when_does_not_match() -> None:
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    fixture = _RepoFixture([base])
    fixture.add_rules(
        base,
        [
            _make_rule("a.always", applies_when=None),
            _make_rule("a.eu_only", applies_when={"region": ["eu"]}),
        ],
        "1.0",
    )

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="whatever",
            party_role="vendor",
            paper_origin="own",
            context={"region": "us"},
        )

    rule_keys = {r.rule_key for r in result.rules}
    assert rule_keys == {"a.always"}


@pytest.mark.asyncio
async def test_resolve_dropped_winner_is_not_backfilled_by_lower_precedence_rule() -> None:
    """Section 5.1: merge by rule_key (step 5) happens BEFORE the rule-level
    applies_when filter (step 6). When the highest-precedence playbook's rule
    for a key fails its applies_when, the key is dropped entirely — a
    lower-precedence playbook's rule with the same key must NOT fill the gap.
    """
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    agreement = _make_playbook(
        "halcyon-saas-msa-vendor", layer="agreement", practice_area="saas_msa", precedence=20
    )

    fixture = _RepoFixture([base, agreement])
    fixture.add_rules(
        base,
        [
            _make_rule("limitation_of_liability.cap", preferred_text="BASE"),
            _make_rule("notices.method", clause_type="notices", preferred_text="BASE NOTICES"),
        ],
        "1.0",
    )
    fixture.add_rules(
        agreement,
        [
            _make_rule(
                "limitation_of_liability.cap",
                preferred_text="AGREEMENT EU ONLY",
                applies_when={"region": ["eu"]},
            )
        ],
        "2.0",
    )

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="saas_msa",
            party_role="vendor",
            paper_origin="own",
            context={"region": "us"},
        )

    rule_keys = {r.rule_key for r in result.rules}
    # No rule at all for the dropped key — specifically not the base version.
    assert "limitation_of_liability.cap" not in rule_keys
    assert all(r.positions[0].language != "BASE" for r in result.rules)
    # Unrelated base rules still come through.
    assert rule_keys == {"notices.method"}
    # Both playbooks were still selected and pinned.
    assert set(result.pinned_version_ids) == {
        base.current_version_id,
        agreement.current_version_id,
    }


@pytest.mark.asyncio
async def test_resolve_winner_with_matching_applies_when_still_overrides() -> None:
    """Control for the test above: same setup, but the context matches the
    higher-precedence rule's applies_when, so it wins normally."""
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    agreement = _make_playbook(
        "halcyon-saas-msa-vendor", layer="agreement", practice_area="saas_msa", precedence=20
    )

    fixture = _RepoFixture([base, agreement])
    fixture.add_rules(
        base, [_make_rule("limitation_of_liability.cap", preferred_text="BASE")], "1.0"
    )
    fixture.add_rules(
        agreement,
        [
            _make_rule(
                "limitation_of_liability.cap",
                preferred_text="AGREEMENT EU ONLY",
                applies_when={"region": ["eu"]},
            )
        ],
        "2.0",
    )

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="saas_msa",
            party_role="vendor",
            paper_origin="own",
            context={"region": "eu"},
        )

    assert len(result.rules) == 1
    assert result.rules[0].positions[0].language == "AGREEMENT EU ONLY"
    assert result.rules[0].source_playbook_name == "halcyon-saas-msa-vendor"


@pytest.mark.asyncio
async def test_resolve_overlay_not_selected_when_applies_when_does_not_match() -> None:
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    overlay = _make_playbook(
        "halcyon-gdpr-overlay",
        layer="overlay",
        practice_area="gdpr",
        precedence=30,
        applies_when={"regimes": ["gdpr"]},
    )

    fixture = _RepoFixture([base, overlay])
    fixture.add_rules(base, [_make_rule("notices.method")], "1.0")
    fixture.add_rules(overlay, [_make_rule("data_transfers.transfer_mechanism")], "1.0")

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="whatever",
            party_role="vendor",
            paper_origin="own",
            context={"regimes": ["hipaa"]},  # no gdpr
        )

    rule_keys = {r.rule_key for r in result.rules}
    assert rule_keys == {"notices.method"}
    assert "halcyon-gdpr-overlay" not in result.applied_playbook_keys


# ---------------------------------------------------------------------------
# resolve() — party-role selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_agreement_playbook_filtered_by_party_role() -> None:
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    vendor_pb = _make_playbook(
        "halcyon-saas-msa-vendor",
        layer="agreement",
        practice_area="saas_msa",
        party_role="vendor",
        precedence=20,
    )
    customer_pb = _make_playbook(
        "halcyon-vendor-msa-customer",
        layer="agreement",
        practice_area="saas_msa",
        party_role="customer",
        precedence=20,
    )

    fixture = _RepoFixture([base, vendor_pb, customer_pb])
    fixture.add_rules(base, [], "1.0")
    fixture.add_rules(
        vendor_pb, [_make_rule("payment.payment_terms", preferred_text="VENDOR")], "1.0"
    )
    fixture.add_rules(
        customer_pb, [_make_rule("payment.payment_terms", preferred_text="CUSTOMER")], "1.0"
    )

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="saas_msa",
            party_role="vendor",
            paper_origin="own",
            context={},
        )

    assert len(result.rules) == 1
    assert result.rules[0].positions[0].language == "VENDOR"
    assert "halcyon-vendor-msa-customer" not in result.applied_playbook_keys


@pytest.mark.asyncio
async def test_resolve_mutual_agreement_playbook_applies_to_any_party_role() -> None:
    mutual_pb = _make_playbook(
        "halcyon-mutual-nda",
        layer="agreement",
        practice_area="nda",
        party_role="mutual",
        precedence=20,
    )
    fixture = _RepoFixture([mutual_pb])
    fixture.add_rules(mutual_pb, [_make_rule("confidentiality.standard_of_care")], "1.0")

    with fixture:
        result_vendor = await resolve(object(), "nda", "vendor", "own", {})
        result_customer = await resolve(object(), "nda", "customer", "own", {})

    assert {r.rule_key for r in result_vendor.rules} == {"confidentiality.standard_of_care"}
    assert {r.rule_key for r in result_customer.rules} == {"confidentiality.standard_of_care"}


# ---------------------------------------------------------------------------
# resolve() — unknown contract_type still returns the baseline, not zero rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_unknown_contract_type_returns_baseline_only() -> None:
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    agreement = _make_playbook(
        "halcyon-saas-msa-vendor", layer="agreement", practice_area="saas_msa", precedence=20
    )

    fixture = _RepoFixture([base, agreement])
    fixture.add_rules(
        base,
        [_make_rule("notices.method"), _make_rule("amendment.written_amendment")],
        "1.0",
    )
    fixture.add_rules(agreement, [_make_rule("payment.payment_terms")], "1.0")

    with fixture:
        result = await resolve(
            session=object(),
            contract_type="some_unknown_type",
            party_role="vendor",
            paper_origin="own",
            context={},
        )

    assert len(result.rules) == 2
    rule_keys = {r.rule_key for r in result.rules}
    assert rule_keys == {"notices.method", "amendment.written_amendment"}
    assert result.applied_playbook_keys == ["halcyon-baseline"]


# ---------------------------------------------------------------------------
# resolve() — deterministic ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_tie_break_by_playbook_key_not_insertion_order() -> None:
    """Two overlays share precedence; the alphabetically-first key wins,
    regardless of the order list_playbooks returns them in."""
    gdpr = _make_playbook(
        "halcyon-gdpr-overlay",
        layer="overlay",
        practice_area="gdpr",
        precedence=30,
        applies_when={"regimes": ["gdpr"]},
    )
    hipaa = _make_playbook(
        "halcyon-hipaa-overlay",
        layer="overlay",
        practice_area="hipaa",
        precedence=30,
        applies_when={"regimes": ["hipaa"]},
    )

    fixture = _RepoFixture([hipaa, gdpr])  # deliberately reversed vs. key order
    fixture.add_rules(
        hipaa,
        [_make_rule("breach_notification.notification_timeline", preferred_text="HIPAA")],
        "1.0",
    )
    fixture.add_rules(
        gdpr,
        [_make_rule("breach_notification.notification_timeline", preferred_text="GDPR")],
        "1.0",
    )

    with fixture:
        result = await resolve(
            object(), "whatever", "vendor", "own", {"regimes": ["hipaa", "gdpr"]}
        )

    # "halcyon-gdpr-overlay" < "halcyon-hipaa-overlay" alphabetically.
    assert result.rules[0].positions[0].language == "GDPR"


@pytest.mark.asyncio
async def test_resolve_output_order_independent_of_input_order() -> None:
    """Final rules list is sorted by rule_key, regardless of fetch order."""
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    fixture = _RepoFixture([base])
    fixture.add_rules(
        base,
        [
            _make_rule("z.last"),
            _make_rule("a.first"),
            _make_rule("m.middle"),
        ],
        "1.0",
    )

    with fixture:
        result = await resolve(object(), "whatever", "vendor", "own", {})

    assert [r.rule_key for r in result.rules] == ["a.first", "m.middle", "z.last"]


# ---------------------------------------------------------------------------
# rules_by_clause_type()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rules_by_clause_type_collapses_to_one_per_clause_type() -> None:
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="baseline", precedence=10)
    fixture = _RepoFixture([base])
    fixture.add_rules(
        base,
        [
            _make_rule("limitation_of_liability.cap_amount", clause_type="limitation_of_liability"),
            _make_rule(
                "limitation_of_liability.cap_carve_outs", clause_type="limitation_of_liability"
            ),
            _make_rule("payment.payment_terms", clause_type="payment"),
        ],
        "1.0",
    )

    with fixture:
        result = await resolve(object(), "whatever", "vendor", "own", {})

    by_clause_type = rules_by_clause_type(result)
    assert set(by_clause_type.keys()) == {"limitation_of_liability", "payment"}
    # Deterministic: the first rule_key alphabetically for the clause type.
    assert (
        by_clause_type["limitation_of_liability"].rule_key
        == "limitation_of_liability.cap_amount"
    )


# ---------------------------------------------------------------------------
# API-level /playbooks/resolve
# ---------------------------------------------------------------------------

mock_session = AsyncMock()


async def _routing_mock_session():
    yield mock_session


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _patch_resolve_session():
    """Own the dependency override for the duration of each test in this file.

    Without this, test_playbooks_api.py's module-level override (same key)
    would shadow this file's mock_session, or vice versa.
    """
    prev = app.dependency_overrides.get(_get_session)
    app.dependency_overrides[_get_session] = _routing_mock_session
    yield
    if prev is None:
        app.dependency_overrides.pop(_get_session, None)
    else:
        app.dependency_overrides[_get_session] = prev


def test_resolve_route_passes_query_params_through() -> None:
    with patch(
        "app.api.routes.playbooks.resolve_playbooks",
        new=AsyncMock(return_value=_empty_resolve_response()),
    ) as mock_resolve:
        response = client.get(
            "/api/playbooks/resolve",
            params={
                "contract_type": "saas_msa",
                "party_role": "customer",
                "paper_origin": "counterparty",
                "context": json.dumps({"regimes": ["hipaa"]}),
            },
        )

    assert response.status_code == 200
    mock_resolve.assert_called_once_with(
        mock_session, "saas_msa", "customer", "counterparty", {"regimes": ["hipaa"]}
    )


def test_resolve_route_defaults_party_role_and_paper_origin() -> None:
    with patch(
        "app.api.routes.playbooks.resolve_playbooks",
        new=AsyncMock(return_value=_empty_resolve_response()),
    ) as mock_resolve:
        response = client.get("/api/playbooks/resolve", params={"contract_type": "nda"})

    assert response.status_code == 200
    mock_resolve.assert_called_once_with(mock_session, "nda", "vendor", "own", {})


def test_resolve_route_invalid_context_json_returns_400() -> None:
    response = client.get(
        "/api/playbooks/resolve",
        params={"contract_type": "nda", "context": "{not valid json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_context"


def test_resolve_route_missing_contract_type_param() -> None:
    response = client.get("/api/playbooks/resolve")
    assert response.status_code == 422


def _empty_resolve_response():
    from app.schemas.playbook import ResolveResponse

    return ResolveResponse(
        contract_type="x",
        party_role="vendor",
        paper_origin="own",
        rules=[],
        pinned_version_ids=[],
        applied_playbook_keys=[],
    )


# ---------------------------------------------------------------------------
# Task 5.5: ResolvedRule is built from child tables only.
# ---------------------------------------------------------------------------


def test_resolved_rule_has_no_legacy_flat_fields() -> None:
    """``ResolvedRule`` (and ``RuleResponse``, which it extends) no longer
    expose the five legacy flat fields. Negotiating language is read from
    ``positions`` / ``red_lines``."""
    from app.schemas.playbook import ResolvedRule, RuleResponse

    for legacy in (
        "preferred_language",
        "acceptable_variations",
        "prohibited_terms",
        "fallback_language",
        "escalation_threshold",
    ):
        assert legacy not in ResolvedRule.model_fields
        assert legacy not in RuleResponse.model_fields
    assert issubclass(ResolvedRule, RuleResponse)
    for child in ("positions", "parameters", "red_lines", "objections", "dependencies",
                  "test_cases"):
        assert child in ResolvedRule.model_fields


@pytest.mark.asyncio
async def test_resolve_carries_positions_and_red_lines_from_children() -> None:
    base = _make_playbook("halcyon-baseline", layer="base", practice_area="saas_msa", precedence=10)
    rule = _make_rule("limitation_of_liability.cap_amount", preferred_text="Twelve months.")
    now = datetime.now(UTC)
    rule.red_lines = [
        SimpleNamespace(
            id=uuid.uuid4(), scope="rule", rule_id=rule.id, playbook_id=None,
            key="no-unlimited", description="No unlimited liability.",
            condition_type="phrase",
            condition={"any": ["unlimited liability"], "negation_guard": True},
            action="block", approver_role_id=None, rationale=None,
            created_at=now, updated_at=now,
        )
    ]
    fixture = _RepoFixture([base])
    fixture.add_rules(base, [rule], "1.0")

    with fixture:
        result = await resolve(
            session=object(), contract_type="saas_msa", party_role="vendor", paper_origin="own"
        )

    (resolved,) = result.rules
    assert [(p.kind, p.rung, p.language) for p in resolved.positions] == [
        ("preferred", 0, "Twelve months.")
    ]
    assert resolved.red_lines[0].condition == {
        "any": ["unlimited liability"], "negation_guard": True
    }
    assert "preferred_language" not in resolved.model_dump()


# ---------------------------------------------------------------------------
# rules_by_rule_key / rule_for_flag — per-flag ladder selection
# ---------------------------------------------------------------------------


def test_rule_for_flag_prefers_rule_key_over_clause_type() -> None:
    from app.services.playbook.routing import rule_for_flag

    a = SimpleNamespace(rule_key="lol.a", clause_type="lol")
    b = SimpleNamespace(rule_key="lol.b", clause_type="lol")
    by_key = {"lol.a": a, "lol.b": b}
    by_type = {"lol": a}
    assert rule_for_flag("lol.b", "lol", by_key, by_type) is b
    assert rule_for_flag(None, "lol", by_key, by_type) is a
    assert rule_for_flag("", "lol", by_key, by_type) is a
    # A rule_key that is not in the resolved set must NOT guess by clause type.
    assert rule_for_flag("lol.missing", "lol", by_key, by_type) is None


def test_rules_by_rule_key_indexes_every_rule() -> None:
    from app.services.playbook.routing import rules_by_rule_key

    a = SimpleNamespace(rule_key="lol.a", clause_type="lol")
    b = SimpleNamespace(rule_key="lol.b", clause_type="lol")
    resolved = SimpleNamespace(rules=[a, b])
    assert rules_by_rule_key(resolved) == {"lol.a": a, "lol.b": b}  # type: ignore[arg-type]
