"""Tests for document_processing/invariants.py (task 2.7).

One passing and one failing test per invariant (6 × 2 = 12 invariant tests),
plus a minimal-valid-result smoke test.
"""
import pytest

from app.services.document_processing.invariants import InvariantError, check_result
from app.services.document_processing.types import (
    Block,
    CanonicalDocument,
    ClauseDraft,
    FieldValue,
    IngestResult,
    PartyDraft,
    SignatoryDraft,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAMILY_KEYS: frozenset[str] = frozenset(
    {
        "other",
        "definitions",
        "governing_law",
        "limitation_of_liability",
        "indemnification",
        "confidentiality",
        "termination",
        "payment",
    }
)

# Minimal FieldDef-like objects so we don't depend on fields.py
class _FieldDef:
    def __init__(self, kind: str, enum=None):
        self.kind = kind
        self.enum = enum


REGISTRY: dict = {
    "governing_law": _FieldDef("string"),
    "auto_renewal": _FieldDef("boolean"),
    "initial_term_months": _FieldDef("integer"),
    "dispute_resolution": _FieldDef("enum", enum={"litigation", "arbitration", "mediation"}),
}


def _doc(text: str) -> CanonicalDocument:
    return CanonicalDocument(text=text, blocks=(), page_count=1)


def _clause(
    ordinal: int,
    text: str,
    char_start: int,
    char_end: int,
    level: int = 1,
    parent_ordinal: int | None = None,
    clause_type: str = "other",
) -> ClauseDraft:
    return ClauseDraft(
        ordinal=ordinal,
        level=level,
        parent_ordinal=parent_ordinal,
        section_number=None,
        title=None,
        heading_text=None,
        text=text,
        char_start=char_start,
        char_end=char_end,
        page_start=1,
        page_end=1,
        clause_type=clause_type,
    )


def _field(
    key: str,
    value,
    char_start: int | None = None,
    char_end: int | None = None,
    quote: str | None = None,
) -> FieldValue:
    return FieldValue(
        field_key=key,
        value=value,
        source="extract",
        confidence="high" if char_start is not None else "low",
        quote=quote,
        page=1,
        char_start=char_start,
        char_end=char_end,
        clause_ordinal=None,
    )


def _result(
    text: str,
    clauses=(),
    fields=(),
) -> IngestResult:
    return IngestResult(
        document=_doc(text),
        title=None,
        contract_type=None,
        clauses=tuple(clauses),
        fields=tuple(fields),
        parties=(),
        signatories=(),
        warnings=(),
    )


# ---------------------------------------------------------------------------
# Minimal valid result (smoke test)
# ---------------------------------------------------------------------------

def test_minimal_valid_result_no_violations():
    """An empty-clauses result with no fields returns no violations."""
    result = _result("hello world")
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert violations == []


# ---------------------------------------------------------------------------
# Invariant 1: text slice
# ---------------------------------------------------------------------------

def test_inv1_pass():
    text = "Alpha Beta Gamma"
    c = _clause(0, "Alpha Beta Gamma", 0, 16)
    result = _result(text, [c])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert not any("text slice mismatch" in v for v in violations)


def test_inv1_fail():
    text = "Alpha Beta Gamma"
    # text field says "WRONG" but slice 0:5 is "Alpha"
    c = _clause(0, "WRONG", 0, 5)
    result = _result(text, [c])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("text slice mismatch" in v and "0" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 2: level-1 order / coverage
# ---------------------------------------------------------------------------

def test_inv2_pass():
    text = "AAAA  BBBB"
    # two level-1 clauses; gap between offset 4 and 6 is "  " (whitespace only)
    c0 = _clause(0, "AAAA", 0, 4)
    c1 = _clause(1, "BBBB", 6, 10)
    result = _result(text, [c0, c1])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert not any("level-1" in v for v in violations)


def test_inv2_fail_overlap():
    text = "AAAA_BBBB"
    # c0 ends at 5, c1 starts at 3 — overlap
    c0 = _clause(0, "AAAA_", 0, 5)
    c1 = _clause(1, "A_BBB", 3, 8)
    result = _result(text, [c0, c1])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("level-1 clauses" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 3: child inside parent
# ---------------------------------------------------------------------------

def test_inv3_pass():
    text = "ParentXXChildXXEnd"
    parent = _clause(0, "ParentXXChildXXEnd", 0, 18, level=1)
    child = _clause(1, "Child", 8, 13, level=2, parent_ordinal=0)
    result = _result(text, [parent, child])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert not any("outside parent range" in v for v in violations)


def test_inv3_fail():
    text = "ParentXXChildXXEnd"
    parent = _clause(0, "Parent", 0, 6, level=1)
    # child starts at 8, outside parent's [0,6)
    child = _clause(1, "Child", 8, 13, level=2, parent_ordinal=0)
    result = _result(text, [parent, child])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("outside parent range" in v and "1" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 4: clause_type validity / duplicate preamble / signature_block
# ---------------------------------------------------------------------------

def test_inv4_pass():
    text = "PreambleXXSection"
    c0 = _clause(0, "Preamble", 0, 8, clause_type="preamble")
    c1 = _clause(1, "XXSection", 8, 17, clause_type="governing_law")
    result = _result(text, [c0, c1])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert not any(
        "unknown clause_type" in v or "duplicate" in v for v in violations
    )


def test_inv4_fail_unknown_type():
    text = "SomeSection"
    c = _clause(0, "SomeSection", 0, 11, clause_type="NONEXISTENT_TYPE")
    result = _result(text, [c])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("unknown clause_type" in v for v in violations)


def test_inv4_fail_duplicate_preamble():
    text = "Preamble1Preamble2"
    c0 = _clause(0, "Preamble1", 0, 9, clause_type="preamble")
    c1 = _clause(1, "Preamble2", 9, 18, clause_type="preamble")
    result = _result(text, [c0, c1])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("duplicate preamble" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 5: field key in registry + valid value
# ---------------------------------------------------------------------------

def test_inv5_pass():
    text = "some contract text"
    f = _field("governing_law", "New York")
    result = _result(text, fields=[f])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert not any("field governing_law" in v for v in violations)


def test_inv5_fail_unknown_key():
    text = "some contract text"
    f = _field("UNKNOWN_FIELD_KEY", "whatever")
    result = _result(text, fields=[f])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("unknown key" in v for v in violations)


def test_inv5_fail_invalid_value():
    text = "some contract text"
    # auto_renewal expects boolean; passing a string should fail
    f = _field("auto_renewal", "not_a_bool")
    result = _result(text, fields=[f])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("invalid value" in v for v in violations)


def test_inv5_fail_enum_value():
    text = "some contract text"
    # dispute_resolution enum is {litigation, arbitration, mediation}
    f = _field("dispute_resolution", "negotiation")
    result = _result(text, fields=[f])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("invalid value" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 6: quote offset mismatch
# ---------------------------------------------------------------------------

def test_inv6_pass():
    text = "The governing law is New York."
    # quote is "New York" at offsets 21:29
    f = _field("governing_law", "New York", char_start=21, char_end=29, quote="New York")
    result = _result(text, fields=[f])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert not any("quote offset mismatch" in v for v in violations)


def test_inv6_fail():
    text = "The governing law is New York."
    # quote says "Delaware" but slice 21:29 is "New York"
    f = _field("governing_law", "Delaware", char_start=21, char_end=29, quote="Delaware")
    result = _result(text, fields=[f])
    violations = check_result(result, FAMILY_KEYS, REGISTRY)
    assert any("quote offset mismatch" in v and "governing_law" in v for v in violations)
