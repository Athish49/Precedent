"""Clause segmenter for the Precedent document-processing pipeline.

Takes a ``ParsedDocument`` (output of T-020 parsers) and returns a flat list of
``SegmentedClause`` objects, each capturing a heading and its associated body text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.document_processing.parsers import ParsedDocument, StructureSignal

# ── Heading-detection regexes (applied to the first line of raw_text) ──────────

# Scheme 2: decimal numbering — e.g. "1.", "1.1", "2.3.4"
_RE_DECIMAL = re.compile(r"^\s*\d+(\.\d+)*\.?\s+")

# Scheme 3: alpha numbering — e.g. "(a) Term" or "b. Term"
_RE_ALPHA = re.compile(r"^\s*(\([a-z]\)|[a-z]\.)\s+")

# Scheme 4: roman numeral numbering — e.g. "iv.", "(ii)", "(iv)"
# \(? makes the opening paren optional; \)? makes the closing paren optional so
# dot-style romans like "iv." also match.
_RE_ROMAN = re.compile(
    r"^\s*\(?(?:i{1,3}|iv|vi{0,3}|ix|x{0,3}(?:i{1,3}|iv|vi{0,3}|ix)?)\)?\.?\s+",
    re.IGNORECASE,
)


def _first_line(text: str) -> str:
    """Return the first line of *text*."""
    return text.split("\n", 1)[0]


# A heading is a short title, not a sentence. Numbered sub-clauses are near-
# universal in real contracts ("4.1 The initial term is ... months.") and
# conspicuous ALL-CAPS disclaimer paragraphs are common too (warranty
# disclaimers, liability caps) — both can be long, full sentences that
# happen to start with a number or be fully capitalized, or that a document's
# own paragraph style mis-marks as a heading (e.g. a DOCX "Heading 2" style
# applied to a numbered clause body rather than a real sub-heading). None of
# that makes them headings. Gating every scheme on word count keeps genuine
# short titles ("4. TERM AND TERMINATION", "9. AUDIT") working while stopping
# long numbered/ALL-CAPS/styled sentences from being sliced out as their own
# heading-only clause.
_MAX_HEADING_WORDS = 8


def _looks_like_heading_shape(first_line: str) -> bool:
    """Return True when *first_line* is short enough to plausibly be a title."""
    stripped = first_line.strip()
    if not stripped:
        return False
    return len(stripped.split()) <= _MAX_HEADING_WORDS


def _is_heading_signal(sig: StructureSignal) -> bool:
    """Return True when any heading scheme 1-6 matches the signal.

    Priority order (1=highest) — but the result is a plain OR because the
    output does not record which scheme fired.

    Every scheme additionally requires the line to be heading-shaped (short —
    see ``_looks_like_heading_shape``); a long sentence is body text even
    when it is numbered, bold, ALL CAPS, or carries an explicit heading style.
    """
    first = _first_line(sig.raw_text)

    if not _looks_like_heading_shape(first):
        return False

    # Scheme 1: structural flag from parser
    if sig.is_heading:
        return True

    # Scheme 2: decimal numbering
    if _RE_DECIMAL.match(first):
        return True

    # Scheme 3: alpha numbering
    if _RE_ALPHA.match(first):
        return True

    # Scheme 4: roman numerals
    if _RE_ROMAN.match(first):
        return True

    # Scheme 5: ALL CAPS line (min 4 chars, after stripping)
    stripped = first.strip()
    if stripped.isupper() and len(stripped) >= 4:
        return True

    # Scheme 6: bold signal from parser
    if sig.is_bold:
        return True

    return False


def _is_numbered_subclause_signal(sig: StructureSignal) -> bool:
    """Return True for a long, decimal-numbered paragraph ("4.2 Following the ...").

    Such a paragraph is not a heading (it fails the heading-shape gate, so its
    sentence must never become ``heading_text`` — that is what used to send
    most corpus clauses to ``clause_type="other"``), but its numbering still
    marks a genuine clause boundary. Treating it as body instead would fold
    every sub-clause of a section into one multi-topic clause (e.g. "4. TERM
    AND TERMINATION" swallowing 4.1-4.4), so it starts its own clause and
    inherits the enclosing section's heading (see :func:`segment`).

    Only decimal numbering qualifies: long ALL-CAPS, bold or heading-styled
    sentences without numbering stay body text.
    """
    first = _first_line(sig.raw_text)
    return not _looks_like_heading_shape(first) and bool(_RE_DECIMAL.match(first))


# ── Output data structure ───────────────────────────────────────────────────────


@dataclass
class SegmentedClause:
    """A single segmented clause extracted from a ``ParsedDocument``."""

    clause_id: str  # deterministic: f"c{ordinal:04d}"
    ordinal: int  # 0-based position in document
    heading_text: str | None  # raw heading as found; None for unstructured fallback
    text: str  # full clause body (heading + body text together)
    char_start: int  # offset into canonical_text
    char_end: int  # offset into canonical_text


# ── Segmentation logic ──────────────────────────────────────────────────────────


def segment(doc: ParsedDocument) -> list[SegmentedClause]:
    """Segment *doc* into a list of :class:`SegmentedClause` objects.

    Algorithm
    ---------
    1. Classify every ``StructureSignal`` as heading or body (schemes 1-6).
    2. If zero signals matched any heading scheme → unstructured fallback:
       emit one clause per signal with ``heading_text=None``.
    3. Otherwise, group consecutive body spans under the preceding heading,
       deriving ``text`` by slicing ``canonical_text`` directly so the
       ``canonical_text[char_start:char_end] == clause.text`` invariant holds
       trivially.
    4. A long decimal-numbered paragraph (a sub-clause such as "4.2 Following
       the Initial Term, ...") also starts a new clause, but it is not a
       heading: its ``heading_text`` is the most recent real heading's text
       (e.g. "4. TERM AND TERMINATION"), or its own first line when no heading
       precedes it. This keeps sub-clauses as separate clauses while giving
       them a classifiable section title rather than a sentence.
    """
    signals = doc.structure_signals
    canonical = doc.canonical_text

    if not signals:
        return []

    # ── Classify each signal ───────────────────────────────────────────────
    is_heading: list[bool] = [_is_heading_signal(s) for s in signals]
    is_subclause: list[bool] = [
        not h and _is_numbered_subclause_signal(s) for s, h in zip(signals, is_heading, strict=True)
    ]

    # ── Unstructured fallback ──────────────────────────────────────────────
    if not any(is_heading):
        clauses: list[SegmentedClause] = []
        for ordinal, sig in enumerate(signals):
            text = canonical[sig.char_start : sig.char_end]
            clauses.append(
                SegmentedClause(
                    clause_id=f"c{ordinal:04d}",
                    ordinal=ordinal,
                    heading_text=None,
                    text=text,
                    char_start=sig.char_start,
                    char_end=sig.char_end,
                )
            )
        return clauses

    # ── Group body spans under preceding heading ───────────────────────────
    # Collect (heading_text | None, [signals]) groups. For a real heading the
    # heading signal is the first entry of its group; for a numbered
    # sub-clause the group starts at the sub-clause paragraph itself and the
    # heading text is inherited from the enclosing section.
    groups: list[tuple[str | None, list[StructureSignal]]] = []

    current_heading_text: str | None = None
    current_sigs: list[StructureSignal] = []
    section_heading_text: str | None = None

    for sig, heading_flag, subclause_flag in zip(signals, is_heading, is_subclause, strict=True):
        if heading_flag:
            # Flush the current group before starting a new one.
            groups.append((current_heading_text, current_sigs))
            current_heading_text = sig.raw_text
            section_heading_text = sig.raw_text
            current_sigs = [sig]
        elif subclause_flag:
            groups.append((current_heading_text, current_sigs))
            current_heading_text = (
                section_heading_text
                if section_heading_text is not None
                else _first_line(sig.raw_text)
            )
            current_sigs = [sig]
        else:
            current_sigs.append(sig)

    # Flush final group.
    groups.append((current_heading_text, current_sigs))

    # ── Build SegmentedClause objects ──────────────────────────────────────
    clauses = []
    ordinal = 0

    for heading_text, all_sigs in groups:
        # A leading group with no heading and no body is empty — skip it.
        if not all_sigs:
            continue

        # Determine the character span for this clause.
        char_start = all_sigs[0].char_start
        char_end = all_sigs[-1].char_end

        # Derive text by slicing; invariant holds by construction.
        text = canonical[char_start:char_end]

        clauses.append(
            SegmentedClause(
                clause_id=f"c{ordinal:04d}",
                ordinal=ordinal,
                heading_text=heading_text,
                text=text,
                char_start=char_start,
                char_end=char_end,
            )
        )
        ordinal += 1

    return clauses
