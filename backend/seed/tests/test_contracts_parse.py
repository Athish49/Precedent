"""Corpus sanity checks for the synthetic contract corpus (doc_proc task 5.3).

Proves that all 12 DOCX files built by ``python -m seed.contracts.build``
exist, open cleanly with ``python-docx``, and carry numbered headings. Seed
code is one of the few places allowed to import from ``app``
(playbook_implementation.md section 3.0, rule 1), but this test imports
nothing from ``app`` at all: the old pipeline's parser and segmenter
modules it used to exercise were deleted in doc_proc task 5.1, and this
test no longer proves parsing or segmentation accuracy — that is now proved
against the live Extend API by task 6.2's corpus run (see
``document_processing_verification.md`` at the repository root), not by a
unit test here.

This test only checks that the corpus exists and is well-formed DOCX with
heading structure; it does not call the resolution engine, the evaluator or
any model, and it does not touch the database or the object store.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from docx import Document

CONTRACTS_DOCX_DIR = Path(__file__).parent.parent / "contracts" / "data" / "halcyon" / "docx"
CONTRACTS_SOURCE_DIR = Path(__file__).parent.parent / "contracts" / "data" / "halcyon" / "source"

EXPECTED_CONTRACT_COUNT = 12

# Same numbering schemes seed/contracts/build.py uses to decide which lines
# become Word "Heading 1"/"Heading 2" paragraphs: "1. ", "1.1 ", "2.3.4 ", or
# a line that is all capitals and at least 4 characters.
_RE_NUMBERED_HEADING = re.compile(r"^\s*\d+(\.\d+)*\s*[-:.)]*\s+\S")
_RE_ALL_CAPS = re.compile(r"^[A-Z0-9 ,.'()/&-]{4,}$")


def _docx_files() -> list[Path]:
    if not CONTRACTS_DOCX_DIR.is_dir():
        return []
    return sorted(CONTRACTS_DOCX_DIR.glob("*.docx"))


def test_source_corpus_has_twelve_contracts() -> None:
    source_files = sorted(CONTRACTS_SOURCE_DIR.glob("*.md"))
    assert len(source_files) == EXPECTED_CONTRACT_COUNT, (
        f"expected {EXPECTED_CONTRACT_COUNT} source contracts under "
        f"{CONTRACTS_SOURCE_DIR}, found {len(source_files)}"
    )


def test_docx_corpus_has_twelve_files() -> None:
    docx_files = _docx_files()
    assert docx_files, (
        f"no DOCX files found under {CONTRACTS_DOCX_DIR}; "
        "run `python -m seed.contracts.build` first"
    )
    assert len(docx_files) == EXPECTED_CONTRACT_COUNT, (
        f"expected {EXPECTED_CONTRACT_COUNT} built DOCX contracts, found {len(docx_files)}"
    )


@pytest.mark.parametrize("docx_path", _docx_files(), ids=lambda p: p.name)
def test_each_contract_opens_with_python_docx(docx_path: Path) -> None:
    """Every DOCX file opens cleanly and has non-empty paragraph text."""
    document = Document(str(docx_path))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    assert paragraphs, f"{docx_path.name} opened with no non-empty paragraphs"


@pytest.mark.parametrize("docx_path", _docx_files(), ids=lambda p: p.name)
def test_each_contract_has_numbered_headings(docx_path: Path) -> None:
    """Every contract has paragraphs styled as a Word heading, and at least
    one of those headings is numbered (``1.``, ``1.1`` ...) or in full
    capitals — the two signals ``seed/contracts/build.py`` uses to decide
    what becomes a heading in the first place.
    """
    document = Document(str(docx_path))
    heading_paragraphs = [
        p.text.strip()
        for p in document.paragraphs
        if p.style is not None and p.style.name.startswith("Heading") and p.text.strip()
    ]
    assert heading_paragraphs, f"{docx_path.name} has no Word heading-styled paragraphs"

    numbered_or_caps = [
        text
        for text in heading_paragraphs
        if _RE_NUMBERED_HEADING.match(text) or _RE_ALL_CAPS.match(text)
    ]
    assert numbered_or_caps, (
        f"{docx_path.name} has heading paragraphs but none look numbered or "
        f"all-caps: {heading_paragraphs[:5]!r}"
    )


def test_each_contract_is_at_least_a_few_pages_of_content() -> None:
    """Loose proxy for the "6 to 15 pages" sizing in the task brief.

    Rather than render pages, this checks each contract's paragraph text is
    long enough to plausibly correspond to several pages of a real contract
    (roughly 400+ words) and has a double-digit number of headings.
    """
    for docx_path in _docx_files():
        document = Document(str(docx_path))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        word_count = sum(len(text.split()) for text in paragraphs)
        heading_count = sum(
            1
            for p in document.paragraphs
            if p.style is not None and p.style.name.startswith("Heading") and p.text.strip()
        )
        assert word_count >= 400, f"{docx_path.name} looks too short ({word_count} words)"
        assert heading_count >= 15, (
            f"{docx_path.name} has too few headings ({heading_count})"
        )
