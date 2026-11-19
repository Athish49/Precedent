"""
Unit tests for document_processing/parties.py — task 2.6.
"""
import pytest

from app.services.document_processing.parties import (
    assign_roles,
    link_signatory,
    normalize_party_name,
)
from app.services.document_processing.types import PartyDraft, SignatoryDraft


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _party(name: str, role: str = "other") -> PartyDraft:
    return PartyDraft(
        name=name,
        role_label=None,
        entity_type=None,
        jurisdiction=None,
        address=None,
        role=role,
    )


def _sig(party_name: str | None) -> SignatoryDraft:
    return SignatoryDraft(
        printed_name=None,
        title=None,
        party_name=party_name,
        is_signed=None,
        signed_date=None,
    )


# ---------------------------------------------------------------------------
# normalize_party_name
# ---------------------------------------------------------------------------

class TestNormalizePartyName:
    def test_strips_comma_and_suffix_period(self):
        assert normalize_party_name("Halcyon Care, Inc.") == "halcyon care inc"

    def test_drops_leading_the(self):
        assert normalize_party_name("The Acme Corporation") == "acme corporation"

    def test_uppercase_llc(self):
        assert normalize_party_name("BETA LLC") == "beta llc"

    def test_bare_role_word_unchanged(self):
        assert normalize_party_name("Supplier") == "supplier"

    def test_does_not_drop_the_mid_word(self):
        # "theory" should not become "ory"
        result = normalize_party_name("Theory Corp")
        assert result == "theory corp"

    def test_empty_string(self):
        assert normalize_party_name("") == ""

    def test_collapses_whitespace(self):
        assert normalize_party_name("  Foo   Bar  ") == "foo bar"


# ---------------------------------------------------------------------------
# assign_roles
# ---------------------------------------------------------------------------

class TestAssignRoles:
    # 1. Own organisation listed first.
    def test_own_first_counterparty_second(self):
        parties = [_party("Halcyon Care, Inc."), _party("Beta Corp")]
        result, warnings = assign_roles(parties, ["Halcyon Care, Inc."])
        assert warnings == []
        assert result[0].role == "own"
        assert result[1].role == "counterparty"

    # 2. Own organisation listed second → same result regardless of order.
    def test_own_second_counterparty_first(self):
        parties = [_party("Beta Corp"), _party("Halcyon Care, Inc.")]
        result, warnings = assign_roles(parties, ["Halcyon Care, Inc."])
        assert warnings == []
        assert result[0].role == "counterparty"
        assert result[1].role == "own"

    # 3. Own org absent from parties → warning, no counterparty assigned.
    def test_own_org_absent_gives_warning(self):
        parties = [_party("Alpha Ltd"), _party("Beta Corp")]
        result, warnings = assign_roles(parties, ["Halcyon Care, Inc."])
        assert "own_org_not_found" in warnings
        # No counterparty should be assigned.
        assert all(p.role == "other" for p in result)

    # 4. own_org_names is empty → warning, all roles stay "other".
    def test_empty_own_org_names_gives_warning(self):
        parties = [_party("Alpha Ltd"), _party("Beta Corp")]
        result, warnings = assign_roles(parties, [])
        assert "own_org_not_configured" in warnings
        assert all(p.role == "other" for p in result)

    # 5. Three parties (own + two others) → own, counterparty, other.
    def test_three_parties(self):
        parties = [
            _party("Halcyon Care, Inc."),
            _party("Alpha Ltd"),
            _party("Beta Corp"),
        ]
        result, warnings = assign_roles(parties, ["Halcyon Care, Inc."])
        assert warnings == []
        assert result[0].role == "own"
        assert result[1].role == "counterparty"
        assert result[2].role == "other"

    # 6. Only own organisation present → warning no_counterparty.
    def test_only_own_org_gives_no_counterparty_warning(self):
        parties = [_party("Halcyon Care, Inc.")]
        result, warnings = assign_roles(parties, ["Halcyon Care, Inc."])
        assert "no_counterparty" in warnings
        assert result[0].role == "own"

    # 7. Prefix match: "Halcyon Care, Inc." matches setting "Halcyon Care".
    def test_prefix_match(self):
        parties = [_party("Halcyon Care, Inc."), _party("Beta Corp")]
        result, warnings = assign_roles(parties, ["Halcyon Care"])
        assert warnings == []
        assert result[0].role == "own"
        assert result[1].role == "counterparty"

    def test_original_parties_not_mutated(self):
        """assign_roles must return new objects; originals stay "other"."""
        parties = [_party("Halcyon Care, Inc."), _party("Beta Corp")]
        assign_roles(parties, ["Halcyon Care, Inc."])
        assert parties[0].role == "other"
        assert parties[1].role == "other"


# ---------------------------------------------------------------------------
# link_signatory
# ---------------------------------------------------------------------------

class TestLinkSignatory:
    # 8. Case-insensitive match.
    def test_case_insensitive_match(self):
        parties = [
            _party("Alpha Ltd"),
            _party("Halcyon Systems, Inc."),
        ]
        sig = _sig("HALCYON SYSTEMS, INC.")
        assert link_signatory(sig, parties) == 1

    # 9. None party_name returns None.
    def test_none_party_name_returns_none(self):
        parties = [_party("Alpha Ltd")]
        sig = _sig(None)
        assert link_signatory(sig, parties) is None

    def test_no_match_returns_none(self):
        parties = [_party("Alpha Ltd")]
        sig = _sig("Beta Corp")
        assert link_signatory(sig, parties) is None

    def test_exact_match_first_party(self):
        parties = [_party("Halcyon Care, Inc."), _party("Beta Corp")]
        sig = _sig("Halcyon Care, Inc.")
        assert link_signatory(sig, parties) == 0
