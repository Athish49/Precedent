"""Parse test for the synthetic contract corpus (task 5.2).

Proves that all 12 DOCX files built by ``python -m seed.contracts.build``
parse correctly with the application's existing document parser and
segmenter. Seed code is one of the few places allowed to import from
``app`` (playbook_implementation.md section 3.0, rule 1); nothing under
``app`` imports back from ``seed``.

This test only exercises parsing and segmentation; it does not call the
resolution engine, the evaluator or the model, and it does not touch the
database or the object store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.document_processing.parsers import parse
from app.services.document_processing.segmentation import segment

CONTRACTS_DOCX_DIR = Path(__file__).parent.parent / "contracts" / "data" / "halcyon" / "docx"
CONTRACTS_SOURCE_DIR = Path(__file__).parent.parent / "contracts" / "data" / "halcyon" / "source"

EXPECTED_CONTRACT_COUNT = 12


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
def test_each_contract_parses_with_existing_parser(docx_path: Path) -> None:
    """Every contract parses to non-empty canonical text with detected headings."""
    file_bytes = docx_path.read_bytes()

    parsed = parse(file_bytes, "docx")
    assert parsed.canonical_text.strip(), f"{docx_path.name} produced empty canonical text"
    assert parsed.structure_signals, f"{docx_path.name} produced no structure signals"

    clauses = segment(parsed)
    assert clauses, f"{docx_path.name} segmented into zero clauses"

    headed = [c for c in clauses if c.heading_text]
    assert headed, f"{docx_path.name} segmented with no detected headings"

    # The numbered-heading invariant the parser guarantees: slicing
    # canonical_text at each clause's offsets reproduces its text exactly.
    for clause in clauses:
        assert parsed.canonical_text[clause.char_start : clause.char_end] == clause.text


def test_each_contract_is_at_least_a_few_pages_of_content() -> None:
    """Loose proxy for the "6 to 15 pages" sizing in the task brief.

    Rather than render pages, this checks each contract's canonical text is
    long enough to plausibly correspond to several pages of a real contract
    (roughly 500+ words), and segments into double-digit clause counts.
    """
    for docx_path in _docx_files():
        parsed = parse(docx_path.read_bytes(), "docx")
        word_count = len(parsed.canonical_text.split())
        clauses = segment(parsed)
        assert word_count >= 400, f"{docx_path.name} looks too short ({word_count} words)"
        assert len(clauses) >= 15, f"{docx_path.name} segmented into too few clauses"
