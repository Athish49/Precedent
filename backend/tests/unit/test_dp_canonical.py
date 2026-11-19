"""Tests for the canonical text builder (document_processing/canonical.py)."""

from __future__ import annotations

import re

import pytest

from app.services.document_processing.canonical import build_canonical
from app.services.document_processing.types import CanonicalDocument
from tests.ingest_fixtures import all_cases, load_case

CONTRACT_CASES = ["msa_styled_docx", "msa_runin_docx", "msa_runin_pdf", "msa_scanned_pdf"]

_SEPARATOR_ROW_RE = re.compile(r"^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$")


def _build(name: str) -> CanonicalDocument:
    _extract, blocks, _answers = load_case(name)
    return build_canonical(blocks)


def test_all_fixture_cases_load_and_build() -> None:
    for name in all_cases():
        _extract, blocks, _answers = load_case(name)
        doc = build_canonical(blocks)
        assert isinstance(doc, CanonicalDocument)


@pytest.mark.parametrize("name", all_cases())
def test_offset_invariant_holds_for_every_kept_block(name: str) -> None:
    doc = _build(name)
    for block in doc.blocks:
        if block.dropped:
            assert block.char_start == -1
            assert block.char_end == -1
            continue
        assert block.char_start >= 0
        assert block.char_end >= block.char_start
        assert doc.text[block.char_start : block.char_end] == block.text


@pytest.mark.parametrize("name", CONTRACT_CASES)
def test_header_and_footers_absent(name: str) -> None:
    doc = _build(name)
    assert "Halcyon Systems, Inc. - Confidential" not in doc.text
    footer_lines = [
        line for line in doc.text.splitlines() if re.match(r"^MSA-\d{4}-\d+ Page \d+$", line)
    ]
    assert footer_lines == []


def test_header_blocks_marked_dropped() -> None:
    doc = _build("msa_styled_docx")
    header_blocks = [b for b in doc.blocks if b.type == "header"]
    assert header_blocks, "fixture should contain at least one header block"
    for block in header_blocks:
        assert block.dropped is True

    # Repeated header on later pages (tagged heading/text) is also dropped.
    repeated = [
        b
        for b in doc.blocks
        if not b.dropped
        and "halcyon systems" in b.text.lower()
        and "confidential" in b.text.lower()
    ]
    assert repeated == []


def test_footer_and_page_number_blocks_marked_dropped() -> None:
    doc = _build("msa_styled_docx")
    for block in doc.blocks:
        if block.type in ("footer", "page_number"):
            assert block.dropped is True


def test_styled_docx_fee_table_joined_across_page_break() -> None:
    doc = _build("msa_styled_docx")
    tables = [b for b in doc.blocks if b.type == "table" and not b.dropped]
    assert len(tables) == 1, "the two page-split table blocks should merge into one"

    table_text = tables[0].text
    lines = [line for line in table_text.split("\n") if line.strip()]
    separator_lines = [line for line in lines if _SEPARATOR_ROW_RE.match(line)]
    data_lines = [line for line in lines if not _SEPARATOR_ROW_RE.match(line)]

    # Exactly one separator row survives (the first table's); the second
    # table's separator is dropped on merge.
    assert len(separator_lines) == 1
    assert len(data_lines) == 4

    # The content from both page-split table blocks is present.
    assert "Platform subscription" in table_text
    assert "Premium support" in table_text
    assert "Total annual Fees" in table_text

    # The merged-away second table block is recorded as dropped.
    merged_away = [
        b
        for b in doc.blocks
        if b.type == "table" and b.dropped and "Premium support" in b.text
    ]
    assert merged_away, "the second table block should be present but marked dropped"


def test_no_stray_space_in_third_party_runin_pdf() -> None:
    doc = _build("msa_runin_pdf")
    assert "third-party" in doc.text
    assert "third- party" not in doc.text


def test_blank_case_yields_empty_text_without_error() -> None:
    doc = _build("blank")
    assert doc.text == ""
    assert doc.blocks == ()
    assert doc.page_count == 0


def test_corrupt_docx_processed_case_does_not_error() -> None:
    doc = _build("corrupt_docx_processed")
    assert isinstance(doc.text, str)
    assert len(doc.text) < 200


def test_no_sections_case_builds_plain_paragraphs() -> None:
    doc = _build("no_sections")
    assert "Acme Corp" in doc.text
    assert doc.blocks
    for block in doc.blocks:
        assert not block.dropped


def test_markdown_heading_marks_stripped() -> None:
    blocks = [
        {
            "type": "heading",
            "content": "# MASTER SERVICES AGREEMENT",
            "metadata": {"page": {"number": 1}},
        },
        {
            "type": "section_heading",
            "content": "### 1. Definitions",
            "metadata": {"page": {"number": 1}},
        },
    ]
    doc = build_canonical(blocks)
    assert "#" not in doc.text
    assert "MASTER SERVICES AGREEMENT" in doc.text
    assert "1. Definitions" in doc.text


def test_bold_marks_stripped() -> None:
    blocks = [
        {
            "type": "text",
            "content": "This is **important** text.",
            "metadata": {"page": {"number": 1}},
        }
    ]
    doc = build_canonical(blocks)
    assert "**" not in doc.text
    assert "This is important text." == doc.text


def test_private_use_bullet_character_replaced_with_dash() -> None:
    blocks = [
        {
            "type": "text",
            "content": " First bullet point",
            "metadata": {"page": {"number": 1}},
        }
    ]
    doc = build_canonical(blocks)
    assert "" not in doc.text
    assert doc.text.startswith("- First bullet point")


def test_line_break_hyphen_closed_up_conservatively() -> None:
    blocks = [
        {
            "type": "text",
            "content": "a third- party claim",
            "metadata": {"page": {"number": 1}},
        }
    ]
    doc = build_canonical(blocks)
    assert "third-party" in doc.text
    assert "third- party" not in doc.text


def test_blocks_joined_with_blank_line() -> None:
    blocks = [
        {"type": "text", "content": "First paragraph.", "metadata": {"page": {"number": 1}}},
        {"type": "text", "content": "Second paragraph.", "metadata": {"page": {"number": 1}}},
    ]
    doc = build_canonical(blocks)
    assert doc.text == "First paragraph.\n\nSecond paragraph."


def test_empty_block_list_returns_empty_document() -> None:
    doc = build_canonical([])
    assert doc.text == ""
    assert doc.blocks == ()
    assert doc.page_count == 0
