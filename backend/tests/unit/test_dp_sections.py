"""Tests for app/services/document_processing/sections.py (task 2.3).

SectionHint construction for the fixture cases is a small test-only adapter
over the recorded extract.json's `clauses` list. The real adapter
(`map_hints`) belongs to task 2.5 and is not imported here.
"""

from __future__ import annotations

import pytest

from app.services.document_processing.canonical import build_canonical
from app.services.document_processing.sections import segment
from app.services.document_processing.types import CanonicalDocument, SectionHint
from tests.ingest_fixtures import all_cases, load_case

_MSA_CASES = ["msa_styled_docx", "msa_runin_docx", "msa_runin_pdf", "msa_scanned_pdf"]


def _hints_from_extract(extract_dict: dict) -> list[SectionHint]:
    """Build SectionHints directly from extract.json's clause list (test-only)."""
    raw_clauses = (extract_dict.get("output", {}).get("value", {}) or {}).get("clauses") or []
    return [
        SectionHint(
            section_number=c.get("section_number"),
            title=c.get("title"),
            family=c.get("family"),
        )
        for c in raw_clauses
    ]


def _build_doc_and_hints(case: str) -> tuple[CanonicalDocument, list[SectionHint], dict]:
    extract_dict, parse_blocks, answers = load_case(case)
    document = build_canonical(parse_blocks)
    hints = _hints_from_extract(extract_dict)
    return document, hints, answers


def test_all_fixture_cases_load() -> None:
    assert set(all_cases()) >= {
        "msa_styled_docx",
        "msa_runin_docx",
        "msa_runin_pdf",
        "msa_scanned_pdf",
        "no_sections",
        "blank",
        "corrupt_docx_processed",
    }


@pytest.mark.parametrize("case", _MSA_CASES)
def test_fourteen_anchored_sections_with_preamble_and_signature(case: str) -> None:
    document, hints, answers = _build_doc_and_hints(case)
    clauses, warnings = segment(document, hints)

    anchored_sections = [c for c in clauses if c.level == 1 and c.section_number is not None]
    assert len(anchored_sections) == 14
    assert all(c.anchored for c in anchored_sections)

    preambles = [c for c in clauses if c.clause_type == "preamble"]
    assert len(preambles) == 1
    assert preambles[0].title is None
    assert preambles[0].type_source == "none"

    signature_blocks = [c for c in clauses if c.clause_type == "signature_block"]
    assert len(signature_blocks) == 1

    expected = [(s["number"], s["title"]) for s in answers["sections"]]
    actual = [(c.section_number, c.title) for c in anchored_sections]
    assert actual == expected

    # No section was anchored by the fallback rule.
    assert warnings == [] or "low_anchor_rate" not in warnings


@pytest.mark.parametrize("case", _MSA_CASES)
def test_no_false_splits_at_known_traps(case: str) -> None:
    document, hints, _answers = _build_doc_and_hints(case)
    clauses, _warnings = segment(document, hints)

    forbidden_starts = ("30 days", "90 days", "I.", "EXCEPT AS EXPRESSLY")
    for clause in clauses:
        stripped = clause.text.strip()
        for bad in forbidden_starts:
            assert not stripped.startswith(bad), (
                f"clause in {case} starts at trap text {bad!r}: {stripped[:60]!r}"
            )


@pytest.mark.parametrize("case", _MSA_CASES)
def test_sections_two_and_ten_have_a_and_b_children(case: str) -> None:
    document, hints, _answers = _build_doc_and_hints(case)
    clauses, _warnings = segment(document, hints)

    by_ordinal = {c.ordinal: c for c in clauses}
    for section_number in ("2", "10"):
        section = next(
            c for c in clauses if c.level == 1 and c.section_number == section_number
        )
        children = sorted(
            (c for c in clauses if c.parent_ordinal == section.ordinal),
            key=lambda c: c.ordinal,
        )
        assert len(children) == 2
        assert children[0].text.strip().startswith("(a)")
        assert children[1].text.strip().startswith("(b)")
        for child in children:
            assert child.level == 2
            assert by_ordinal[child.parent_ordinal] is section


@pytest.mark.parametrize("case", _MSA_CASES)
def test_text_matches_exact_slice_for_every_clause(case: str) -> None:
    document, hints, _answers = _build_doc_and_hints(case)
    clauses, _warnings = segment(document, hints)

    for clause in clauses:
        assert clause.text == document.text[clause.char_start : clause.char_end]


@pytest.mark.parametrize("case", _MSA_CASES)
def test_level_one_clauses_partition_the_text(case: str) -> None:
    document, hints, _answers = _build_doc_and_hints(case)
    clauses, _warnings = segment(document, hints)

    level1 = sorted((c for c in clauses if c.level == 1), key=lambda c: c.char_start)
    assert level1[0].char_start == 0
    assert level1[-1].char_end == len(document.text)
    for prev, nxt in zip(level1, level1[1:]):
        assert prev.char_end <= nxt.char_start
        gap = document.text[prev.char_end : nxt.char_start]
        assert gap.strip() == ""


def test_no_sections_fixture_returns_sensible_output_without_error() -> None:
    extract_dict, parse_blocks, _answers = load_case("no_sections")
    document = build_canonical(parse_blocks)
    hints = _hints_from_extract(extract_dict)
    assert hints == []

    clauses, warnings = segment(document, hints)

    assert len(clauses) >= 1
    for clause in clauses:
        assert clause.text == document.text[clause.char_start : clause.char_end]
    # The whole document is covered.
    level1 = sorted((c for c in clauses if c.level == 1), key=lambda c: c.char_start)
    assert level1[0].char_start == 0
    assert level1[-1].char_end == len(document.text)


def test_blank_fixture_returns_single_clause_without_error() -> None:
    _extract_dict, parse_blocks, _answers = load_case("blank")
    document = build_canonical(parse_blocks)
    clauses, _warnings = segment(document, [])
    assert len(clauses) == 1
    assert clauses[0].text == ""
    assert clauses[0].char_start == 0
    assert clauses[0].char_end == 0


def test_corrupt_docx_fixture_returns_single_clause_without_error() -> None:
    _extract_dict, parse_blocks, _answers = load_case("corrupt_docx_processed")
    document = build_canonical(parse_blocks)
    clauses, _warnings = segment(document, [])
    assert len(clauses) == 1
    assert clauses[0].text == document.text


def test_unanchored_hint_adds_warning_and_is_skipped() -> None:
    blocks = [
        {"type": "section_heading", "content": "1. Definitions", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Terms are defined here.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="1", title="Definitions", family=None),
        SectionHint(section_number="2", title="Does Not Exist", family=None),
    ]
    clauses, warnings = segment(document, hints)

    assert "section_not_anchored:2 Does Not Exist" in warnings
    sections = [c for c in clauses if c.level == 1 and c.section_number is not None]
    assert len(sections) == 1
    assert sections[0].section_number == "1"


def test_low_anchor_rate_warning_when_under_eighty_percent_anchored() -> None:
    blocks = [
        {"type": "section_heading", "content": "1. Definitions", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Terms are defined here.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [SectionHint(section_number="1", title="Definitions", family=None)] + [
        SectionHint(section_number=str(n), title=f"Missing {n}", family=None) for n in range(2, 7)
    ]
    _clauses, warnings = segment(document, hints)
    assert "low_anchor_rate" in warnings


def test_high_anchor_rate_has_no_low_anchor_rate_warning() -> None:
    blocks = [
        {"type": "section_heading", "content": "1. Definitions", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Terms are defined here.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "2. Term", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This agreement lasts one year.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="1", title="Definitions", family=None),
        SectionHint(section_number="2", title="Term", family=None),
    ]
    _clauses, warnings = segment(document, hints)
    assert "low_anchor_rate" not in warnings


def test_alpha_subclauses_nest_under_their_section() -> None:
    blocks = [
        {"type": "section_heading", "content": "2. Services", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Supplier shall provide the services.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "(a) Supplier shall act professionally.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "(b) Customer shall cooperate reasonably.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "3. Term", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This agreement lasts one year.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="2", title="Services", family=None),
        SectionHint(section_number="3", title="Term", family=None),
    ]
    clauses, _warnings = segment(document, hints)

    section2 = next(c for c in clauses if c.section_number == "2")
    children = sorted(
        (c for c in clauses if c.parent_ordinal == section2.ordinal), key=lambda c: c.ordinal
    )
    assert [c.text.strip()[:3] for c in children] == ["(a)", "(b)"]
    assert all(c.level == 2 for c in children)
    for clause in clauses:
        assert clause.text == document.text[clause.char_start : clause.char_end]


def test_numeric_subsections_nest_by_dotted_number() -> None:
    blocks = [
        {"type": "section_heading", "content": "6. Confidentiality", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "6.1 Scope. Each party shall protect information.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "6.1.1 Exceptions apply to public information.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "6.1.2 Exceptions also apply to independently developed information.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "6.2 Duration. The obligations survive for five years.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "7. Governing Law", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This agreement is governed by Delaware law.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="6", title="Confidentiality", family=None),
        SectionHint(section_number="7", title="Governing Law", family=None),
    ]
    clauses, warnings = segment(document, hints)
    assert warnings == []

    section6 = next(c for c in clauses if c.section_number == "6")
    direct_children = sorted(
        (c for c in clauses if c.parent_ordinal == section6.ordinal), key=lambda c: c.ordinal
    )
    assert len(direct_children) == 2
    assert all(c.level == 2 for c in direct_children)
    assert direct_children[0].text.strip().startswith("6.1 Scope")
    assert direct_children[1].text.strip().startswith("6.2 Duration")

    sixpointone = direct_children[0]
    grandchildren = sorted(
        (c for c in clauses if c.parent_ordinal == sixpointone.ordinal), key=lambda c: c.ordinal
    )
    assert len(grandchildren) == 2
    assert all(c.level == 3 for c in grandchildren)
    assert grandchildren[0].text.strip().startswith("6.1.1")
    assert grandchildren[1].text.strip().startswith("6.1.2")

    for clause in clauses:
        assert clause.text == document.text[clause.char_start : clause.char_end]


def test_no_hints_at_all_uses_fallback_rule() -> None:
    blocks = [
        {"type": "text", "content": "1. Definitions. Terms are defined here.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "30 days after the event, this applies anyway.", "metadata": {"page": {"number": 1}}},
        {
            "type": "section_heading",
            "content": "IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR ANY INDIRECT OR CONSEQUENTIAL DAMAGES ARISING",
            "metadata": {"page": {"number": 1}},
        },
        {"type": "text", "content": "2. Term. This agreement lasts one year.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    clauses, _warnings = segment(document, [])

    sections = [c for c in clauses if c.level == 1 and c.section_number is not None]
    assert {c.section_number for c in sections} == {"1", "2"}
    assert all(c.anchored is False for c in sections)

    # The all-caps disclaimer (over 8 words) must not start a clause.
    for clause in clauses:
        assert not clause.text.strip().startswith("IN NO EVENT SHALL")

    # "30 days..." must not start a clause either.
    for clause in clauses:
        assert not clause.text.strip().startswith("30 days")

    for clause in clauses:
        assert clause.text == document.text[clause.char_start : clause.char_end]


def test_title_less_duplicate_hint_does_not_false_split_on_subclause() -> None:
    """Verification doc section 5.3 / proposed change #9: a second,
    title-less hint for a section number already anchored by its titled
    twin must not match the leading digits of an unrelated "9.1" sub-
    clause elsewhere in the document. It should go unanchored instead."""
    blocks = [
        {"type": "section_heading", "content": "9. Security", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "9.1 Halcyon shall maintain administrative, technical and physical safeguards.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "9.2 Safeguards are reviewed annually.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "10. Term", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This agreement lasts one year.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="9", title="Security", family="security"),
        SectionHint(section_number="9", title=None, family="security"),
        SectionHint(section_number="10", title="Term", family=None),
    ]
    clauses, warnings = segment(document, hints)

    sections = [c for c in clauses if c.level == 1 and c.section_number == "9"]
    assert len(sections) == 1
    assert sections[0].title == "Security"

    # The orphaned title-less duplicate hint goes unanchored (the same
    # path as any other hint whose number was already claimed), not a
    # spurious extra clause starting at "9.1".
    assert "section_not_anchored:9" in warnings
    # "9.1" is still a legitimate level-2 sub-clause of section 9 -- the
    # bug would have made it a spurious extra *level-1* clause instead.
    for clause in clauses:
        if clause.level == 1:
            assert not clause.text.strip().startswith("9.1")


def test_bare_number_hint_still_anchors_normal_section() -> None:
    """The negative lookahead must not regress the normal case: a hint
    for section "9" with no "9.1" sub-clause nearby still anchors at a
    bare "9." prefix."""
    blocks = [
        {"type": "section_heading", "content": "9. Confidentiality", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Each party shall protect the other's confidential information.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "10. Term", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This agreement lasts one year.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="9", title="Confidentiality", family=None),
        SectionHint(section_number="10", title="Term", family=None),
    ]
    clauses, warnings = segment(document, hints)

    sections = [c for c in clauses if c.level == 1 and c.section_number is not None]
    assert [s.section_number for s in sections] == ["9", "10"]
    assert all(s.anchored for s in sections)
    assert warnings == [] or "low_anchor_rate" not in warnings


def test_title_less_number_only_hint_anchors_bare_number_not_ninety() -> None:
    """Exercise the number-only anchor path directly (a hint with no
    title at all, not just an orphaned duplicate): the lookahead must
    still anchor a bare "9)" / "9." prefix, and must not let a bare "9"
    hint match "90 days" either."""
    blocks = [
        {"type": "text", "content": "90 days after signing, this clause applies regardless.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "9) Confidentiality", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Each party shall protect confidential information.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [SectionHint(section_number="9", title=None, family=None)]
    clauses, _warnings = segment(document, hints)

    sections = [c for c in clauses if c.level == 1 and c.section_number == "9"]
    assert len(sections) == 1
    assert sections[0].anchored is True
    assert not sections[0].text.strip().startswith("90 days")


def test_appendix_fallback_picks_up_trailing_unhinted_exhibit() -> None:
    """Verification doc section 5.1a / proposed change #3: an unhinted
    "Exhibit A" trailing after the last hinted section becomes its own
    clause instead of merging into the last numbered section."""
    blocks = [
        {"type": "section_heading", "content": "1. Definitions", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Terms are defined here.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "2. Services", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Supplier shall provide the services.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "3. Term", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This agreement lasts one year.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Exhibit A - Sample Order Form", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This is the sample order form text.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="1", title="Definitions", family=None),
        SectionHint(section_number="2", title="Services", family=None),
        SectionHint(section_number="3", title="Term", family=None),
    ]
    clauses, _warnings = segment(document, hints)

    exhibit = next(c for c in clauses if c.section_number == "Exhibit A")
    assert exhibit.level == 1
    assert exhibit.anchored is False
    assert exhibit.title == "Sample Order Form"
    assert exhibit.text.strip().startswith("Exhibit A")

    section3 = next(c for c in clauses if c.section_number == "3")
    assert "Exhibit A" not in section3.text

    for clause in clauses:
        assert clause.text == document.text[clause.char_start : clause.char_end]


def test_appendix_fallback_picks_up_schedule_between_two_sections() -> None:
    """An unhinted "Schedule 1" appearing between two anchored sections
    (not at the very end) is picked up as its own clause without
    corrupting the boundary of the section before or after it."""
    blocks = [
        {"type": "section_heading", "content": "16. Miscellaneous", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This section covers miscellaneous terms.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Schedule 1: Description of Services", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "The services are described here in detail.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "17. Notices", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Notices shall be sent in writing.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="16", title="Miscellaneous", family=None),
        SectionHint(section_number="17", title="Notices", family=None),
    ]
    clauses, _warnings = segment(document, hints)

    schedule = next(c for c in clauses if c.section_number == "Schedule 1")
    assert schedule.level == 1
    assert schedule.anchored is False
    assert schedule.title == "Description of Services"

    section16 = next(c for c in clauses if c.section_number == "16")
    section17 = next(c for c in clauses if c.section_number == "17")
    assert "Schedule 1" not in section16.text
    assert section16.char_end == schedule.char_start
    assert schedule.char_end == section17.char_start
    assert section17.text.strip().startswith("17. Notices")

    for clause in clauses:
        assert clause.text == document.text[clause.char_start : clause.char_end]


def test_appendix_fallback_does_not_fire_on_body_paragraph_mentioning_schedule() -> None:
    """A body paragraph that happens to start with "Schedule 1 sets out
    ..." (not a heading line) must not be mistaken for an appendix
    heading -- the regex is end-anchored and heading-shaped precisely so
    this kind of false positive is excluded."""
    blocks = [
        {"type": "section_heading", "content": "16. Miscellaneous", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Schedule 1 sets out the fees payable under this Agreement.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "17. Notices", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Notices shall be sent in writing.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="16", title="Miscellaneous", family=None),
        SectionHint(section_number="17", title="Notices", family=None),
    ]
    clauses, _warnings = segment(document, hints)

    assert not any(c.section_number == "Schedule 1" for c in clauses)
    section16 = next(c for c in clauses if c.section_number == "16")
    assert "Schedule 1 sets out" in section16.text


def test_appendix_fallback_does_not_fire_inside_anchored_section_body() -> None:
    """A mid-sentence cross-reference to "Exhibit A" inside an anchored
    section's own body must not spawn a spurious clause."""
    blocks = [
        {"type": "section_heading", "content": "5. Orders", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Orders are placed per the form attached, see Exhibit A for details.", "metadata": {"page": {"number": 1}}},
        {"type": "section_heading", "content": "6. Term", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "This agreement lasts one year.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    hints = [
        SectionHint(section_number="5", title="Orders", family=None),
        SectionHint(section_number="6", title="Term", family=None),
    ]
    clauses, _warnings = segment(document, hints)

    assert not any(c.section_number == "Exhibit A" for c in clauses)
    sections = [c for c in clauses if c.level == 1 and c.section_number is not None]
    assert [s.section_number for s in sections] == ["5", "6"]


def test_fallback_whole_document_single_clause_when_nothing_matches() -> None:
    blocks = [
        {"type": "text", "content": "This is a plain contract with no headings at all.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "It just keeps going in plain paragraphs.", "metadata": {"page": {"number": 1}}},
    ]
    document = build_canonical(blocks)
    clauses, warnings = segment(document, [])
    assert len(clauses) == 1
    assert clauses[0].level == 1
    assert clauses[0].char_start == 0
    assert clauses[0].char_end == len(document.text)
    assert clauses[0].text == document.text
    assert warnings == []
