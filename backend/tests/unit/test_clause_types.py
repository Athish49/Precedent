"""Unit tests for the clause-type normalizer (T-022)."""

import pytest

from app.services.document_processing.clause_types import normalize_clause_type

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
