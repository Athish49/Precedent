"""Tests for document_processing/types.py (task 0.2)."""
import dataclasses
from datetime import date

import pytest

from app.services.document_processing.types import (
    Block,
    CanonicalDocument,
    ClauseDraft,
    FieldValue,
    IngestResult,
    PartyDraft,
    SectionHint,
    SignatoryDraft,
)


# ---------------------------------------------------------------------------
# Helpers to build one instance of each type
# ---------------------------------------------------------------------------

def make_block(index: int = 0, char_start: int = 0, char_end: int = 10) -> Block:
    return Block(
        index=index,
        type="text",
        text="Hello world",
        page=1,
        char_start=char_start,
        char_end=char_end,
    )


def make_canonical_document() -> CanonicalDocument:
    b = make_block()
    return CanonicalDocument(
        text="Hello world",
        blocks=(b,),
        page_count=1,
    )


def make_section_hint() -> SectionHint:
    return SectionHint(
        section_number="1",
        title="Definitions",
        family="definitions",
    )


def make_clause_draft(ordinal: int = 0, level: int = 1, parent_ordinal: int | None = None) -> ClauseDraft:
    return ClauseDraft(
        ordinal=ordinal,
        level=level,
        parent_ordinal=parent_ordinal,
        section_number="1",
        title="Definitions",
        heading_text="1. Definitions",
        text="As used herein...",
        char_start=0,
        char_end=18,
        page_start=1,
        page_end=1,
    )


def make_field_value() -> FieldValue:
    return FieldValue(
        field_key="governing_law",
        value="Delaware",
        source="extract",
        confidence="high",
        quote="governed by the laws of Delaware",
        page=5,
        char_start=1000,
        char_end=1032,
        clause_ordinal=3,
    )


def make_party_draft() -> PartyDraft:
    return PartyDraft(
        name="Acme Corp.",
        role_label="Customer",
        entity_type="corporation",
        jurisdiction="Delaware",
        address="123 Main St",
    )


def make_signatory_draft() -> SignatoryDraft:
    return SignatoryDraft(
        printed_name="Jane Doe",
        title="CEO",
        party_name="Acme Corp.",
        is_signed=True,
        signed_date=date(2026, 1, 15),
    )


def make_ingest_result(clauses: tuple[ClauseDraft, ...] | None = None) -> IngestResult:
    if clauses is None:
        clauses = (make_clause_draft(),)
    return IngestResult(
        document=make_canonical_document(),
        title="Master Services Agreement",
        contract_type="saas_msa",
        clauses=clauses,
        fields=(make_field_value(),),
        parties=(make_party_draft(),),
        signatories=(make_signatory_draft(),),
        warnings=("low_anchor_rate",),
    )


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_block(self):
        b = make_block()
        assert b.index == 0
        assert b.type == "text"
        assert b.dropped is False

    def test_canonical_document(self):
        doc = make_canonical_document()
        assert doc.page_count == 1
        assert len(doc.blocks) == 1

    def test_section_hint(self):
        h = make_section_hint()
        assert h.section_number == "1"
        assert h.family == "definitions"

    def test_clause_draft_defaults(self):
        c = make_clause_draft()
        assert c.clause_type == "other"
        assert c.type_source == "none"
        assert c.issue_keys == ()
        assert c.anchored is True

    def test_field_value(self):
        f = make_field_value()
        assert f.source == "extract"
        assert f.confidence == "high"

    def test_party_draft_defaults(self):
        p = make_party_draft()
        assert p.role == "other"

    def test_signatory_draft(self):
        s = make_signatory_draft()
        assert s.is_signed is True
        assert s.signed_date == date(2026, 1, 15)

    def test_ingest_result(self):
        r = make_ingest_result()
        assert r.contract_type == "saas_msa"
        assert len(r.warnings) == 1


# ---------------------------------------------------------------------------
# Frozen / immutability tests
# ---------------------------------------------------------------------------

class TestFrozen:
    def test_block_frozen(self):
        b = make_block()
        with pytest.raises(dataclasses.FrozenInstanceError):
            b.type = "heading"  # type: ignore[misc]

    def test_canonical_document_frozen(self):
        doc = make_canonical_document()
        with pytest.raises(dataclasses.FrozenInstanceError):
            doc.text = "changed"  # type: ignore[misc]

    def test_section_hint_frozen(self):
        h = make_section_hint()
        with pytest.raises(dataclasses.FrozenInstanceError):
            h.title = "changed"  # type: ignore[misc]

    def test_clause_draft_frozen(self):
        c = make_clause_draft()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.clause_type = "liability"  # type: ignore[misc]

    def test_field_value_frozen(self):
        f = make_field_value()
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.value = "changed"  # type: ignore[misc]

    def test_party_draft_frozen(self):
        p = make_party_draft()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.role = "own"  # type: ignore[misc]

    def test_signatory_draft_frozen(self):
        s = make_signatory_draft()
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.printed_name = "changed"  # type: ignore[misc]

    def test_ingest_result_frozen(self):
        r = make_ingest_result()
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.title = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IngestResult.level1() tests
# ---------------------------------------------------------------------------

class TestLevel1:
    def test_returns_only_level1(self):
        c1 = make_clause_draft(ordinal=0, level=1)
        c2 = make_clause_draft(ordinal=1, level=2, parent_ordinal=0)
        c3 = make_clause_draft(ordinal=2, level=1)
        r = make_ingest_result(clauses=(c1, c2, c3))
        result = r.level1()
        assert all(c.level == 1 for c in result)
        assert len(result) == 2

    def test_returned_in_ordinal_order(self):
        # Insert in reverse ordinal order; level1() must sort them.
        c3 = make_clause_draft(ordinal=4, level=1)
        c1 = make_clause_draft(ordinal=0, level=1)
        c2 = make_clause_draft(ordinal=2, level=1)
        r = make_ingest_result(clauses=(c3, c1, c2))
        result = r.level1()
        ordinals = [c.ordinal for c in result]
        assert ordinals == sorted(ordinals)

    def test_empty_when_no_level1(self):
        c = make_clause_draft(ordinal=0, level=2, parent_ordinal=None)
        r = make_ingest_result(clauses=(c,))
        assert r.level1() == ()

    def test_returns_tuple(self):
        r = make_ingest_result()
        assert isinstance(r.level1(), tuple)
