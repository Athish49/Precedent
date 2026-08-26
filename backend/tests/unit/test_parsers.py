"""Unit tests for app.services.document_processing.parsers.

PDF tests mock pdfplumber.open to avoid requiring a real PDF file or reportlab.
DOCX tests create in-memory documents with python-docx.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from docx import Document

from app.services.document_processing import parsers
from app.services.document_processing.parsers import ParsedDocument, parse

# ── DOCX helpers ──────────────────────────────────────────────────────────────


def _build_docx(paragraphs: list[tuple[str, str]]) -> bytes:
    """Build a DOCX in memory.

    Args:
        paragraphs: List of (text, style_name) pairs.
                    Use ``"Normal"`` for body text, ``"Heading 1"`` etc. for headings.

    Returns:
        Raw DOCX bytes.
    """
    doc = Document()
    for text, style in paragraphs:
        doc.add_paragraph(text, style=style)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_bold_docx() -> bytes:
    """Build a DOCX where the first paragraph contains a bold run."""
    doc = Document()
    para = doc.add_paragraph()
    run = para.add_run("Bold text here")
    run.bold = True
    doc.add_paragraph("Normal text here", style="Normal")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── PDF mock helpers ───────────────────────────────────────────────────────────


def _make_pdf_mock(pages_words: list[list[dict]]) -> MagicMock:
    """Return a mock that stands in for ``pdfplumber.open(...)`` as a context manager.

    Args:
        pages_words: One list of word-dicts per page.  Each dict must have at minimum:
            ``text``, ``size``, ``fontname``, ``top``, ``bottom``, ``x0``.
    """
    mock_pages = []
    for words in pages_words:
        page = MagicMock()
        page.extract_words.return_value = words
        mock_pages.append(page)

    mock_pdf = MagicMock()
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    mock_open = MagicMock(return_value=mock_pdf)
    return mock_open


def _sample_words() -> list[dict]:
    """Return a minimal list of word dicts for a two-line document.

    Line 1 (top=10): "Contract" in large font → heading candidate.
    Line 2 (top=50): "This" "is" "body" "text." in normal font.
    """
    return [
        # Line 1: "Contract" at large font → heading
        {"text": "Contract", "size": 18.0, "fontname": "Arial-Bold",
         "top": 10.0, "bottom": 20.0, "x0": 72.0},
        # Line 2: body words at normal font size
        {"text": "This", "size": 12.0, "fontname": "Arial",
         "top": 50.0, "bottom": 60.0, "x0": 72.0},
        {"text": "is", "size": 12.0, "fontname": "Arial",
         "top": 50.0, "bottom": 60.0, "x0": 96.0},
        {"text": "body", "size": 12.0, "fontname": "Arial",
         "top": 50.0, "bottom": 60.0, "x0": 108.0},
        {"text": "text.", "size": 12.0, "fontname": "Arial",
         "top": 50.0, "bottom": 60.0, "x0": 126.0},
    ]


# ── DOCX tests ────────────────────────────────────────────────────────────────


class TestParseDocxCanonicalText:
    def test_non_empty_canonical_text(self) -> None:
        docx_bytes = _build_docx([
            ("Introduction", "Heading 1"),
            ("This is the body of the document.", "Normal"),
        ])
        result = parse(docx_bytes, "docx")
        assert isinstance(result, ParsedDocument)
        assert len(result.canonical_text) > 0
        assert "Introduction" in result.canonical_text
        assert "body of the document" in result.canonical_text

    def test_empty_paragraphs_skipped(self) -> None:
        """Empty paragraphs should not appear as signals or in canonical_text."""
        doc = Document()
        doc.add_paragraph("First paragraph", style="Normal")
        doc.add_paragraph("")  # empty — should be skipped
        doc.add_paragraph("Third paragraph", style="Normal")
        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        result = parse(docx_bytes, "docx")
        # No double-blank should appear from the empty para
        assert "First paragraph" in result.canonical_text
        assert "Third paragraph" in result.canonical_text
        # All signals should have non-empty raw_text
        for sig in result.structure_signals:
            assert sig.raw_text.strip() != ""


class TestParseDocxStructureSignalsOffsets:
    def test_offsets_index_canonical_text(self) -> None:
        docx_bytes = _build_docx([
            ("Article 1. Definitions", "Heading 1"),
            ("The term 'Party' means any signatory hereto.", "Normal"),
            ("Termination clause text goes here.", "Normal"),
        ])
        result = parse(docx_bytes, "docx")
        assert len(result.structure_signals) >= 1
        for sig in result.structure_signals:
            extracted = result.canonical_text[sig.char_start:sig.char_end]
            assert extracted == sig.raw_text, (
                f"Offset mismatch: canonical_text[{sig.char_start}:{sig.char_end}]="
                f"{extracted!r} != raw_text={sig.raw_text!r}"
            )

    def test_signals_cover_full_text(self) -> None:
        """canonical_text reconstructed from signals should equal the full text."""
        docx_bytes = _build_docx([
            ("Preamble", "Heading 1"),
            ("Body paragraph one.", "Normal"),
            ("Body paragraph two.", "Normal"),
        ])
        result = parse(docx_bytes, "docx")
        # Signals ordered; their raw_text joined by \n\n should reproduce canonical_text
        reconstructed = "\n\n".join(sig.raw_text for sig in result.structure_signals)
        assert reconstructed == result.canonical_text


class TestParseDocxHeadingDetection:
    def test_heading_1_style_detected(self) -> None:
        docx_bytes = _build_docx([
            ("Section 1", "Heading 1"),
            ("Some body text.", "Normal"),
        ])
        result = parse(docx_bytes, "docx")
        heading_signals = [s for s in result.structure_signals if s.is_heading]
        assert len(heading_signals) >= 1
        h1 = heading_signals[0]
        assert h1.heading_level == 1
        assert h1.raw_text == "Section 1"

    def test_heading_level_2(self) -> None:
        docx_bytes = _build_docx([
            ("Main Title", "Heading 1"),
            ("Sub Section", "Heading 2"),
            ("Body text.", "Normal"),
        ])
        result = parse(docx_bytes, "docx")
        levels = {s.raw_text: s.heading_level for s in result.structure_signals if s.is_heading}
        assert levels.get("Main Title") == 1
        assert levels.get("Sub Section") == 2

    def test_normal_paragraph_not_heading(self) -> None:
        docx_bytes = _build_docx([("Just body text.", "Normal")])
        result = parse(docx_bytes, "docx")
        for sig in result.structure_signals:
            if sig.raw_text == "Just body text.":
                assert not sig.is_heading
                assert sig.heading_level is None


class TestParseDocxDeterminism:
    def test_same_input_same_output(self) -> None:
        docx_bytes = _build_docx([
            ("Clause 1", "Heading 1"),
            ("The parties agree to the following terms and conditions.", "Normal"),
            ("Clause 2", "Heading 2"),
            ("Additional provisions apply.", "Normal"),
        ])
        result_a = parse(docx_bytes, "docx")
        result_b = parse(docx_bytes, "docx")
        assert result_a.canonical_text == result_b.canonical_text
        assert len(result_a.structure_signals) == len(result_b.structure_signals)
        for a, b in zip(result_a.structure_signals, result_b.structure_signals, strict=True):
            assert a == b


# ── PDF tests ─────────────────────────────────────────────────────────────────


class TestParsePdfStructureSignalsOffsets:
    def test_offsets_index_canonical_text(self) -> None:
        mock_open = _make_pdf_mock([_sample_words()])
        with patch.object(parsers.pdfplumber, "open", mock_open):
            result = parse(b"fake-pdf-bytes", "pdf")

        assert len(result.structure_signals) >= 1
        for sig in result.structure_signals:
            extracted = result.canonical_text[sig.char_start:sig.char_end]
            assert extracted == sig.raw_text, (
                f"Offset mismatch: canonical_text[{sig.char_start}:{sig.char_end}]="
                f"{extracted!r} != raw_text={sig.raw_text!r}"
            )

    def test_heading_heuristic_applied(self) -> None:
        """The large-font word should be detected as a heading."""
        mock_open = _make_pdf_mock([_sample_words()])
        with patch.object(parsers.pdfplumber, "open", mock_open):
            result = parse(b"fake-pdf-bytes", "pdf")

        heading_signals = [s for s in result.structure_signals if s.is_heading]
        assert len(heading_signals) >= 1
        # "Contract" at font size 18 vs body 12 → 18/12 = 1.5 > 1.2
        assert any("Contract" in s.raw_text for s in heading_signals)

    def test_bold_detected_in_fontname(self) -> None:
        """Words with bold-indicator fontnames should yield is_bold=True signals."""
        mock_open = _make_pdf_mock([_sample_words()])
        with patch.object(parsers.pdfplumber, "open", mock_open):
            result = parse(b"fake-pdf-bytes", "pdf")

        # "Contract" is in fontname "Arial-Bold"
        contract_sigs = [s for s in result.structure_signals if "Contract" in s.raw_text]
        assert len(contract_sigs) >= 1
        assert contract_sigs[0].is_bold

    def test_canonical_text_reconstructed_from_signals(self) -> None:
        mock_open = _make_pdf_mock([_sample_words()])
        with patch.object(parsers.pdfplumber, "open", mock_open):
            result = parse(b"fake-pdf-bytes", "pdf")

        reconstructed = "\n\n".join(s.raw_text for s in result.structure_signals)
        assert reconstructed == result.canonical_text

    def test_empty_pdf_returns_empty_document(self) -> None:
        mock_open = _make_pdf_mock([[]])  # one page, no words
        with patch.object(parsers.pdfplumber, "open", mock_open):
            result = parse(b"fake-pdf-bytes", "pdf")
        assert result.canonical_text == ""
        assert result.structure_signals == []


class TestParsePdfDeterminism:
    def test_same_input_same_output(self) -> None:
        # Each call to parse will invoke mock; provide same data twice
        mock_open = _make_pdf_mock([_sample_words()])
        with patch.object(parsers.pdfplumber, "open", mock_open):
            result_a = parse(b"fake-pdf-bytes", "pdf")

        mock_open2 = _make_pdf_mock([_sample_words()])
        with patch.object(parsers.pdfplumber, "open", mock_open2):
            result_b = parse(b"fake-pdf-bytes", "pdf")

        assert result_a.canonical_text == result_b.canonical_text
        assert len(result_a.structure_signals) == len(result_b.structure_signals)
        for a, b in zip(result_a.structure_signals, result_b.structure_signals, strict=True):
            assert a == b


# ── Format dispatcher ─────────────────────────────────────────────────────────


class TestParseUnsupportedFormat:
    def test_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unsupported format"):
            parse(b"", "txt")  # type: ignore[arg-type]

    def test_error_message_includes_format(self) -> None:
        with pytest.raises(ValueError, match="'xml'"):
            parse(b"", "xml")  # type: ignore[arg-type]
