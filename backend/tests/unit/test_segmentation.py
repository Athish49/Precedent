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


# ── Heading-shape gate (regression: numbered/ALL-CAPS/styled body sentences ────
# were used as heading_text — see task 5.4's end-to-end verification, which
# found 78-100% of segmented clauses in every one of the 12 synthetic corpus
# contracts misclassified as clause_type="other" because of this. Numbered
# sub-clauses still segment separately but inherit the section heading.) ──────


def test_segment_long_numbered_sentence_is_not_a_heading() -> None:
    """A numbered sub-clause that is a full sentence never becomes heading_text,

    even though it starts with decimal numbering (scheme 2) — this is the exact
    failure mode found in the 12-contract corpus: e.g. heading "8. TERM AND
    SURVIVAL" followed by body "8.1 This Agreement remains in effect for two (2)
    years from the Effective Date." produced a clause whose heading_text was
    the 8.1 sentence, which normalizes to clause_type="other". The sub-clause
    still starts its own clause (its numbering is a real boundary), but it
    inherits the enclosing section's heading.
    """
    doc = _make_doc([
        ("8. TERM AND SURVIVAL", False, False),
        (
            "8.1 This Agreement remains in effect for two (2) years "
            "from the Effective Date.",
            False,
            False,
        ),
    ])
    clauses = segment(doc)
    _assert_offsets(doc, clauses)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "8. TERM AND SURVIVAL"
    assert clauses[1].heading_text == "8. TERM AND SURVIVAL"
    assert clauses[1].text.startswith("8.1 This Agreement remains in effect")


def test_segment_numbered_subclauses_are_not_merged_into_section() -> None:
    """Regression: the heading-shape gate must not fold every sub-clause of a

    section into one multi-topic clause. "4.1" (term length) and "4.2"
    (auto-renewal) must stay separate clauses, each carrying the section
    heading, and body paragraphs without numbering stay with their sub-clause.
    """
    doc = _make_doc([
        ("4. TERM AND TERMINATION", False, False),
        (
            "4.1 The initial term of each Order Form is thirty-six (36) months "
            "from the Effective Date.",
            False,
            False,
        ),
        (
            "4.2 Following the Initial Term, this Agreement automatically renews "
            "for successive twelve (12) month periods.",
            False,
            False,
        ),
        ("Either Party may opt out on ninety days notice before renewal.", False, False),
        ("5. SUSPENSION", False, False),
        (
            "5.1 Halcyon may suspend access on reasonable notice for non-payment "
            "of undisputed Fees.",
            False,
            False,
        ),
    ])
    clauses = segment(doc)
    _assert_offsets(doc, clauses)
    assert [c.heading_text for c in clauses] == [
        "4. TERM AND TERMINATION",
        "4. TERM AND TERMINATION",
        "4. TERM AND TERMINATION",
        "5. SUSPENSION",
        "5. SUSPENSION",
    ]
    assert clauses[1].text.startswith("4.1 The initial term")
    assert "automatically renews" not in clauses[1].text
    assert clauses[2].text.startswith("4.2 Following the Initial Term")
    assert clauses[2].text.endswith("before renewal.")
    assert clauses[4].text.startswith("5.1 Halcyon may suspend")


def test_segment_long_numbered_sentence_before_any_heading() -> None:
    """With no preceding real heading, a long numbered sub-clause falls back

    to its own first line as heading_text.
    """
    text = "1.1 This preamble sentence is long enough to fail the heading-shape gate."
    doc = _make_doc([
        (text, False, False),
        ("2. PAYMENT", False, False),
    ])
    clauses = segment(doc)
    _assert_offsets(doc, clauses)
    assert len(clauses) == 2
    assert clauses[0].heading_text == text
    assert clauses[1].heading_text == "2. PAYMENT"


def test_segment_long_allcaps_sentence_is_not_a_heading() -> None:
    """A long ALL-CAPS disclaimer paragraph is body text, not a heading.

    Scheme 5 (ALL CAPS) must not fire on long conspicuous-disclaimer boilerplate
    (common in warranty/liability sections), only on short, title-shaped lines.
    """
    doc = _make_doc([
        ("WARRANTIES", False, True),
        (
            "EXCEPT AS EXPRESSLY SET OUT ABOVE, THE SERVICES ARE PROVIDED "
            '"AS IS." COMPANY DISCLAIMS ALL OTHER WARRANTIES, EXPRESS OR '
            "IMPLIED, INCLUDING MERCHANTABILITY AND FITNESS FOR A PARTICULAR "
            "PURPOSE.",
            False,
            False,
        ),
    ])
    clauses = segment(doc)
    assert len(clauses) == 1
    assert clauses[0].heading_text == "WARRANTIES"
    assert "DISCLAIMS ALL OTHER WARRANTIES" in clauses[0].text


def test_segment_long_sentence_with_structural_heading_style_is_not_a_heading() -> None:
    """A long sentence never becomes heading_text even when the document's own

    structural flag (scheme 1, e.g. a DOCX "Heading" paragraph style) says it
    is a heading. A numbered one still starts its own clause (as any numbered
    sub-clause does), inheriting the section heading; an unnumbered one is
    plain body text.
    """
    doc = _make_doc([
        ("1. DEFINITIONS", False, False),
        (
            '1.1 "Documentation" means the then-current user guides and '
            "specifications for the Services, as updated from time to time.",
            False,
            True,  # is_heading=True, mirroring a mis-styled DOCX paragraph
        ),
        (
            "Capitalised terms used but not defined here have the meaning given "
            "in the Order Form.",
            False,
            True,  # mis-styled, unnumbered
        ),
    ])
    clauses = segment(doc)
    _assert_offsets(doc, clauses)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "1. DEFINITIONS"
    assert clauses[1].heading_text == "1. DEFINITIONS"
    assert clauses[1].text.startswith('1.1 "Documentation" means')
    assert "Capitalised terms used" in clauses[1].text


def test_segment_short_numbered_heading_still_detected() -> None:
    """Guard against over-correcting: short numbered titles remain headings."""
    doc = _make_doc([
        ("9. AUDIT", False, False),
        ("Audit rights are described below.", False, False),
        ("17. GENERAL PROVISIONS", False, False),
        ("Miscellaneous boilerplate follows.", False, False),
    ])
    clauses = segment(doc)
    assert len(clauses) == 2
    assert clauses[0].heading_text == "9. AUDIT"
    assert clauses[1].heading_text == "17. GENERAL PROVISIONS"


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
