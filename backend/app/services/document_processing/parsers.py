"""Document parsers for PDF and DOCX formats.

Produces a common ``ParsedDocument`` intermediate representation consumed
by downstream pipeline stages (segmenter, etc.).
"""

from __future__ import annotations

import io
import statistics
from dataclasses import dataclass, field
from typing import Literal

import pdfplumber
from docx import Document

# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class StructureSignal:
    """Per-span structural metadata aligned to offsets within ``canonical_text``."""

    char_start: int
    char_end: int
    is_bold: bool
    font_size: float | None  # None for DOCX (not easily available at paragraph level)
    is_heading: bool  # explicit heading style (DOCX) or font-size heuristic (PDF)
    heading_level: int | None  # 1=H1, 2=H2, … (from DOCX style; None for PDF)
    raw_text: str  # the span text; guaranteed: canonical_text[char_start:char_end] == raw_text


@dataclass
class ParsedDocument:
    """Common intermediate output produced by all format parsers."""

    canonical_text: str
    structure_signals: list[StructureSignal] = field(default_factory=list)


# ── PDF parser ────────────────────────────────────────────────────────────────

_BOLD_MARKERS = ("Bold", "bold", "-B", "BD")


def _is_bold_font(fontname: str) -> bool:
    return any(marker in fontname for marker in _BOLD_MARKERS)


def _parse_pdf(file_bytes: bytes) -> ParsedDocument:
    """Parse a digital PDF using pdfplumber.

    Words are grouped into lines by comparing their ``top`` coordinate.
    Each line becomes one block.  Blocks are joined with ``\\n\\n`` to form
    ``canonical_text``.  Heading detection uses a font-size heuristic:
    blocks whose max font size is ≥ 1.2× the document-wide median are
    flagged as headings.
    """
    blocks: list[tuple[str, bool, float | None]] = []  # (text, is_bold, font_size)

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        all_words: list[dict] = []
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["size", "fontname", "top", "bottom"])
            all_words.extend(words)

        # ── Collect all font sizes for median calculation ─────────────────
        all_sizes: list[float] = [
            float(w["size"]) for w in all_words if w.get("size") is not None
        ]
        median_size: float | None = statistics.median(all_sizes) if all_sizes else None

        # ── Group words into lines by page order then top coordinate ──────
        # Re-iterate pages in order to preserve reading sequence.
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["size", "fontname", "top", "bottom"])
            if not words:
                continue

            # Sort by (top, x0) so words read left-to-right within a line
            words_sorted = sorted(
                words, key=lambda w: (float(w.get("top", 0)), float(w.get("x0", 0)))
            )

            # Group into lines: words whose ``top`` values are within 2pt of each other
            lines: list[list[dict]] = []
            current_line: list[dict] = [words_sorted[0]]
            current_top = float(words_sorted[0].get("top", 0))

            for w in words_sorted[1:]:
                w_top = float(w.get("top", 0))
                if abs(w_top - current_top) <= 2.0:
                    current_line.append(w)
                else:
                    lines.append(current_line)
                    current_line = [w]
                    current_top = w_top
            lines.append(current_line)

            # Build one block per line
            for line_words in lines:
                line_text = " ".join(w["text"] for w in line_words)
                if not line_text.strip():
                    continue

                bold = any(_is_bold_font(str(w.get("fontname", ""))) for w in line_words)
                sizes = [float(w["size"]) for w in line_words if w.get("size") is not None]
                line_font_size = max(sizes) if sizes else None

                blocks.append((line_text, bold, line_font_size))

    # ── Build canonical_text and signals ──────────────────────────────────
    texts = [b[0] for b in blocks]
    canonical_text = "\n\n".join(texts)

    signals: list[StructureSignal] = []
    cursor = 0
    for text, is_bold, font_size in blocks:
        char_start = cursor
        char_end = cursor + len(text)

        # Heading heuristic: font size ≥ 1.2× document median
        is_heading = bool(
            font_size is not None and median_size is not None and font_size >= 1.2 * median_size
        )

        signals.append(
            StructureSignal(
                char_start=char_start,
                char_end=char_end,
                is_bold=is_bold,
                font_size=font_size,
                is_heading=is_heading,
                heading_level=None,
                raw_text=text,
            )
        )
        # Advance past this block + the "\n\n" separator (last block has no separator)
        cursor = char_end + 2  # len("\n\n") == 2

    return ParsedDocument(canonical_text=canonical_text, structure_signals=signals)


# ── DOCX parser ───────────────────────────────────────────────────────────────

_HEADING_PREFIX = "Heading "


def _heading_level_from_style(style_name: str) -> int | None:
    """Return the heading level (1-based) for styles like ``"Heading 1"``, else None."""
    if style_name.startswith(_HEADING_PREFIX):
        suffix = style_name[len(_HEADING_PREFIX):]
        if suffix.isdigit():
            return int(suffix)
    return None


def _parse_docx(file_bytes: bytes) -> ParsedDocument:
    """Parse a DOCX file using python-docx.

    Each non-empty paragraph becomes one block.  Heading detection is based
    on paragraph style name.  Bold detection checks each run's bold attribute.
    """
    doc = Document(io.BytesIO(file_bytes))

    blocks: list[tuple[str, bool, int | None]] = []  # (text, is_bold, heading_level)

    for para in doc.paragraphs:
        text = para.text  # raw, unstripped — used directly as raw_text
        if text.strip() == "":
            continue  # skip empty paragraphs

        heading_level = _heading_level_from_style(para.style.name)

        # Bold: any run is bold (or style has bold set)
        is_bold = any(run.bold for run in para.runs if run.bold is not None)

        blocks.append((text, is_bold, heading_level))

    # ── Build canonical_text and signals ──────────────────────────────────
    texts = [b[0] for b in blocks]
    canonical_text = "\n\n".join(texts)

    signals: list[StructureSignal] = []
    cursor = 0
    for text, is_bold, heading_level in blocks:
        char_start = cursor
        char_end = cursor + len(text)

        is_heading = heading_level is not None

        signals.append(
            StructureSignal(
                char_start=char_start,
                char_end=char_end,
                is_bold=is_bold,
                font_size=None,  # not easily available at paragraph level in DOCX
                is_heading=is_heading,
                heading_level=heading_level,
                raw_text=text,
            )
        )
        cursor = char_end + 2  # advance past "\n\n"

    return ParsedDocument(canonical_text=canonical_text, structure_signals=signals)


# ── Top-level dispatcher ──────────────────────────────────────────────────────


def parse(file_bytes: bytes, source_format: Literal["pdf", "docx"]) -> ParsedDocument:
    """Dispatch to the appropriate parser based on *source_format*.

    Args:
        file_bytes: Raw file content as bytes.
        source_format: Either ``"pdf"`` or ``"docx"``.

    Returns:
        A :class:`ParsedDocument` with ``canonical_text`` and
        ``structure_signals`` populated.

    Raises:
        ValueError: If *source_format* is not supported.
    """
    if source_format == "pdf":
        return _parse_pdf(file_bytes)
    elif source_format == "docx":
        return _parse_docx(file_bytes)
    raise ValueError(f"Unsupported format: {source_format!r}")
