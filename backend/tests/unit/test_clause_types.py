"""Unit tests for the clause-type normalizer (T-022)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.document_processing import clause_types
from app.services.document_processing.clause_types import (
    clear_synonym_cache,
    load_synonym_cache,
    normalize_clause_type,
    set_synonym_cache,
)

# ---------------------------------------------------------------------------
# Exact-match tests
# ---------------------------------------------------------------------------


def test_exact_match_indemnification():
    assert normalize_clause_type("Indemnification") == "indemnification"


def test_exact_match_hold_harmless():
    assert normalize_clause_type("Hold Harmless") == "indemnification"


def test_exact_match_limitation_of_liability():
    assert normalize_clause_type("Limitation of Liability") == "limitation_of_liability"


def test_exact_match_governing_law():
    assert normalize_clause_type("Governing Law") == "governing_law"


def test_exact_match_liability_cap():
    assert normalize_clause_type("Liability Cap") == "limitation_of_liability"


def test_exact_match_termination_for_cause():
    assert normalize_clause_type("Termination for Cause") == "termination"


def test_exact_match_non_disclosure():
    assert normalize_clause_type("Non-Disclosure") == "confidentiality"


def test_exact_match_nda():
    assert normalize_clause_type("NDA") == "confidentiality"


def test_exact_match_work_product():
    assert normalize_clause_type("Work Product") == "intellectual_property"


def test_exact_match_arbitration():
    assert normalize_clause_type("Arbitration") == "dispute_resolution"


def test_exact_match_fees():
    assert normalize_clause_type("Fees") == "payment"


def test_exact_match_representations_and_warranties():
    assert normalize_clause_type("Representations and Warranties") == "warranties"


def test_exact_match_force_majeure():
    assert normalize_clause_type("Force Majeure") == "force_majeure"


def test_exact_match_assignment():
    assert normalize_clause_type("Assignment") == "assignment"


def test_exact_match_entire_agreement():
    assert normalize_clause_type("Entire Agreement") == "entire_agreement"


def test_exact_match_amendment():
    assert normalize_clause_type("Amendment") == "amendment"


def test_exact_match_notices():
    assert normalize_clause_type("Notices") == "notices"


def test_exact_match_definitions():
    assert normalize_clause_type("Definitions") == "definitions"


def test_exact_match_term():
    assert normalize_clause_type("Term") == "term"


def test_exact_match_compliance():
    assert normalize_clause_type("Compliance") == "compliance"


def test_exact_match_data_protection():
    assert normalize_clause_type("Data Protection") == "data_protection"


def test_exact_match_audit():
    assert normalize_clause_type("Audit") == "audit"


def test_exact_match_insurance():
    assert normalize_clause_type("Insurance") == "insurance"


# ---------------------------------------------------------------------------
# Leading-numbering stripping tests (regression: task 5.4's end-to-end
# verification found that a numbered heading like "9. AUDIT" — exactly as the
# segmenter stores it in heading_text, numbering intact — scored only ~77 on
# token_sort_ratio against the "audit" dictionary key (below the 80 cutoff),
# because the numeric prefix makes up a large fraction of a short string. This
# silently failed short canonical names across the corpus while longer ones
# (e.g. "indemnification") were long enough to tolerate the prefix.)
# ---------------------------------------------------------------------------


def test_strips_decimal_prefix_exact_match():
    # Without stripping, "9. audit" vs "audit" scores ~77 — below the fuzzy
    # cutoff of 80 — so this previously fell through to "other".
    assert normalize_clause_type("9. AUDIT") == "audit"


def test_strips_two_digit_decimal_prefix():
    assert normalize_clause_type("11. Audit") == "audit"


def test_strips_subclause_decimal_prefix():
    assert normalize_clause_type("4.1 Term") == "term"


def test_strips_alpha_prefix():
    assert normalize_clause_type("(a) Term") == "term"


def test_strips_roman_prefix():
    assert normalize_clause_type("iv. Insurance") == "insurance"


def test_strip_leading_numbering_leaves_unnumbered_text_unchanged():
    assert normalize_clause_type("Insurance") == "insurance"


def test_fuzzy_match_term_and_survival():
    # Common real-world heading pattern (NDAs/confidentiality agreements),
    # parallel to the existing "term and termination" entry — added because
    # task 5.4's corpus hit exactly this heading for a clause whose body text
    # sets the contract's term.
    assert normalize_clause_type("Term and Survival") == "term"
    assert normalize_clause_type("8. TERM AND SURVIVAL") == "term"


# ---------------------------------------------------------------------------
# Fuzzy-match tests
# ---------------------------------------------------------------------------


def test_fuzzy_match_variation_indemnification():
    # Slight misspelling / extra words
    assert normalize_clause_type("Indemnification and Hold Harmless") == "indemnification"


def test_fuzzy_match_limitation_typo():
    # "Limitaton" — one character dropped
    assert normalize_clause_type("Limitaton of Liability") == "limitation_of_liability"


def test_fuzzy_match_force_majeure_variation():
    assert normalize_clause_type("Force Majeure Events") == "force_majeure"


def test_fuzzy_match_governing_law_jurisdiction():
    assert normalize_clause_type("Governing Law and Jurisdiction") == "governing_law"


def test_fuzzy_match_data_privacy():
    assert normalize_clause_type("Data Privacy") == "data_protection"


def test_fuzzy_match_audit_rights():
    assert normalize_clause_type("Audit Rights") == "audit"


# ---------------------------------------------------------------------------
# None and unknown heading tests
# ---------------------------------------------------------------------------


def test_none_returns_other():
    assert normalize_clause_type(None) == "other"


def test_empty_string_returns_other():
    assert normalize_clause_type("") == "other"


def test_whitespace_only_returns_other():
    assert normalize_clause_type("   ") == "other"


def test_unknown_heading_returns_other():
    assert normalize_clause_type("Miscellaneous") == "other"


def test_unknown_heading_general_returns_other():
    assert normalize_clause_type("General Provisions") == "other"


def test_unknown_heading_signature_returns_other():
    assert normalize_clause_type("Signature Page") == "other"


# ---------------------------------------------------------------------------
# Coverage test: all 20 canonical types mapped from at least one synonym
# ---------------------------------------------------------------------------

_CANONICAL_TYPE_SAMPLES: list[tuple[str, str]] = [
    ("Indemnification", "indemnification"),
    ("Limitation of Liability", "limitation_of_liability"),
    ("Termination", "termination"),
    ("Confidentiality", "confidentiality"),
    ("Intellectual Property", "intellectual_property"),
    ("Governing Law", "governing_law"),
    ("Dispute Resolution", "dispute_resolution"),
    ("Payment", "payment"),
    ("Warranties", "warranties"),
    ("Force Majeure", "force_majeure"),
    ("Assignment", "assignment"),
    ("Entire Agreement", "entire_agreement"),
    ("Amendment", "amendment"),
    ("Notices", "notices"),
    ("Definitions", "definitions"),
    ("Term", "term"),
    ("Compliance", "compliance"),
    ("Data Protection", "data_protection"),
    ("Audit", "audit"),
    ("Insurance", "insurance"),
]


@pytest.mark.parametrize("heading,expected", _CANONICAL_TYPE_SAMPLES)
def test_all_canonical_types_covered(heading: str, expected: str):
    assert normalize_clause_type(heading) == expected


# ---------------------------------------------------------------------------
# Determinism test
# ---------------------------------------------------------------------------


def test_determinism_known_heading():
    heading = "Indemnification and Hold Harmless"
    first = normalize_clause_type(heading)
    second = normalize_clause_type(heading)
    assert first == second


def test_determinism_unknown_heading():
    heading = "Miscellaneous"
    assert normalize_clause_type(heading) == normalize_clause_type(heading)


def test_determinism_none():
    assert normalize_clause_type(None) == normalize_clause_type(None)


# ---------------------------------------------------------------------------
# Case / whitespace insensitivity
# ---------------------------------------------------------------------------


def test_case_insensitive_upper():
    assert normalize_clause_type("INDEMNIFICATION") == "indemnification"


def test_case_insensitive_mixed():
    assert normalize_clause_type("gOvErNiNg LaW") == "governing_law"


def test_leading_trailing_whitespace():
    assert normalize_clause_type("  Termination  ") == "termination"


# ---------------------------------------------------------------------------
# DB-backed synonym cache (task 5.5): no live database connection needed —
# `tests/conftest.py`'s autouse fixture populates the cache for every test
# in the suite from the clause_family seed migrations' literal data. These
# tests exercise the cache mechanism itself: an unpopulated cache fails
# loudly, `set_synonym_cache` populates it directly, and `load_synonym_cache`
# (the function `app.main`'s lifespan calls at startup) populates it from a
# mocked AsyncSession/`list_clause_families` the same way `test_taxonomy_repo
# .py` mocks DB access elsewhere.
# ---------------------------------------------------------------------------


def test_unpopulated_cache_raises():
    clear_synonym_cache()
    try:
        with pytest.raises(RuntimeError):
            normalize_clause_type("Indemnification")
    finally:
        # Restore a populated cache so later tests in this module aren't
        # affected by import/collection order quirks (the autouse fixture
        # also re-populates it before each test regardless).
        set_synonym_cache({"indemnification": "indemnification"})


@pytest.mark.asyncio
async def test_load_synonym_cache_populates_from_clause_family_table():
    family_a = MagicMock()
    family_a.key = "indemnification"
    family_a.synonyms = ["indemnification", "indemnity"]
    family_b = MagicMock()
    family_b.key = "termination"
    family_b.synonyms = ["termination", "term and termination"]

    session = AsyncMock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.db.repositories.taxonomy_repo.list_clause_families",
            AsyncMock(return_value=[family_a, family_b]),
        )
        await load_synonym_cache(session)

    assert normalize_clause_type("Indemnity") == "indemnification"
    assert normalize_clause_type("Term and Termination") == "termination"
    assert clause_types._synonym_map == {
        "indemnification": "indemnification",
        "indemnity": "indemnification",
        "termination": "termination",
        "term and termination": "termination",
    }
