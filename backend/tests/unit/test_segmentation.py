"""Unit tests for the clause segmenter (T-021)."""

from __future__ import annotations

from app.services.document_processing.parsers import ParsedDocument, StructureSignal
from app.services.document_processing.segmentation import SegmentedClause, segment

# ── Test helpers ────────────────────────────────────────────────────────────────


def _make_doc(blocks: list[tuple[str, bool, bool]]) -> ParsedDocument:
    """Build a ``ParsedDocument`` from a list of (text, is_bold, is_heading) triples.

    Blocks are joined with ``\\n\\n`` to form ``canonical_text``, mirroring
    what the real parsers produce.
    """
    signals: list[StructureSignal] = []
    texts = [b[0] for b in blocks]
    canonical = "\n\n".join(texts)
    cursor = 0
    for text, is_bold, is_heading in blocks:
        signals.append(
            StructureSignal(
                char_start=cursor,
                char_end=cursor + len(text),
                is_bold=is_bold,
                font_size=None,
                is_heading=is_heading,
                heading_level=None,
                raw_text=text,
            )
        )
        cursor += len(text) + 2  # +2 for "\n\n"
    return ParsedDocument(canonical_text=canonical, structure_signals=signals)


def _assert_offsets(doc: ParsedDocument, clauses: list[SegmentedClause]) -> None:
    """Assert the offset invariant for every clause."""
    for clause in clauses:
        assert doc.canonical_text[clause.char_start : clause.char_end] == clause.text, (
            f"Offset mismatch for {clause.clause_id!r}: "
            f"expected {clause.text!r}, "
            f"got {doc.canonical_text[clause.char_start:clause.char_end]!r}"
        )


# ── Heading-scheme tests ────────────────────────────────────────────────────────


def test_segment_structural_headings() -> None:
    """Signals with is_heading=True are detected as clause boundaries."""
    doc = _make_doc([
        ("Definitions", False, True),
        ("'Agreement' means this contract.", False, False),
        ("Term", False, True),
        ("The term is one year.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "Definitions"
    assert clauses[1].heading_text == "Term"


def test_segment_decimal_headings() -> None:
    """Decimal-numbered lines (1., 1.1, 2.3.4) are detected as headings."""
    doc = _make_doc([
        ("1. Definitions", False, False),
        ("Body text for definitions.", False, False),
        ("2.1 Payment Terms", False, False),
        ("Payment is due in 30 days.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "1. Definitions"
    assert clauses[1].heading_text == "2.1 Payment Terms"


def test_segment_alpha_headings() -> None:
    """Alpha-numbered lines like (a) or b. are detected as headings."""
    doc = _make_doc([
        ("(a) Term", False, False),
        ("The initial term shall be twelve months.", False, False),
        ("b. Renewal", False, False),
        ("This agreement renews automatically.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "(a) Term"
    assert clauses[1].heading_text == "b. Renewal"


def test_segment_roman_headings() -> None:
    """Roman-numeral lines like iv. or (ii) are detected as headings."""
    doc = _make_doc([
        ("iv. Termination", False, False),
        ("Either party may terminate.", False, False),
        ("(ii) Notice", False, False),
        ("Notice must be in writing.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "iv. Termination"
    assert clauses[1].heading_text == "(ii) Notice"


def test_segment_allcaps_headings() -> None:
    """ALL-CAPS lines of >= 4 chars are detected as headings."""
    doc = _make_doc([
        ("INDEMNIFICATION", False, False),
        ("Each party shall indemnify the other.", False, False),
        ("GOVERNING LAW", False, False),
        ("This agreement is governed by New York law.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "INDEMNIFICATION"
    assert clauses[1].heading_text == "GOVERNING LAW"


def test_segment_bold_headings() -> None:
    """Signals with is_bold=True are detected as headings."""
    doc = _make_doc([
        ("Confidentiality", True, False),
        ("Each party shall keep information secret.", False, False),
        ("Warranties", True, False),
        ("Seller makes no express warranties.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "Confidentiality"
    assert clauses[1].heading_text == "Warranties"


# ── Unstructured fallback ───────────────────────────────────────────────────────


def test_segment_unstructured_fallback() -> None:
    """When no heading signals are found, one clause per paragraph with heading_text=None."""
    doc = _make_doc([
        ("This is the first paragraph.", False, False),
        ("This is the second paragraph.", False, False),
        ("This is the third paragraph.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 3
    for clause in clauses:
        assert clause.heading_text is None


# ── Invariant and metadata tests ────────────────────────────────────────────────


def test_segment_offsets_correct() -> None:
    """canonical_text[clause.char_start:clause.char_end] == clause.text for all clauses."""
    doc = _make_doc([
        ("1. Definitions", False, False),
        ("'Agreement' means this contract.", False, False),
        ("2. Term", False, False),
        ("The term is one year.", False, False),
        ("3. Payment", False, False),
        ("Payment is due net-30.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 3
    _assert_offsets(doc, clauses)


def test_segment_determinism() -> None:
    """Same ParsedDocument input produces identical output on two calls."""
    doc = _make_doc([
        ("CONFIDENTIALITY", False, False),
        ("All information shared is confidential.", False, False),
        ("TERM", False, False),
        ("This agreement lasts two years.", False, False),
    ])
    result_a = segment(doc)
    result_b = segment(doc)
    assert result_a == result_b


def test_segment_clause_ids() -> None:
    """clause_ids are 'c0000', 'c0001', etc., matching the ordinal."""
    doc = _make_doc([
        ("1. First", False, False),
        ("Body of first.", False, False),
        ("2. Second", False, False),
        ("Body of second.", False, False),
        ("3. Third", False, False),
        ("Body of third.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 3
    for i, clause in enumerate(clauses):
        assert clause.clause_id == f"c{i:04d}"
        assert clause.ordinal == i


def test_segment_empty_doc() -> None:
    """An empty ParsedDocument returns an empty list."""
    doc = ParsedDocument(canonical_text="", structure_signals=[])
    assert segment(doc) == []


def test_segment_body_before_first_heading() -> None:
    """Body paragraphs that appear before the first heading are not dropped."""
    doc = _make_doc([
        ("Preamble paragraph with no heading.", False, False),
        ("1. Definitions", False, False),
        ("Body of definitions.", False, False),
    ])
    clauses = segment(doc)
    # The preamble should appear as a clause with heading_text=None
    assert clauses[0].heading_text is None
    assert "Preamble" in clauses[0].text
    assert clauses[1].heading_text == "1. Definitions"
    _assert_offsets(doc, clauses)


def test_segment_offsets_unstructured() -> None:
    """Offset invariant holds for unstructured (fallback) docs too."""
    doc = _make_doc([
        ("Paragraph one text here.", False, False),
        ("Paragraph two text here.", False, False),
    ])
    clauses = segment(doc)
    _assert_offsets(doc, clauses)
