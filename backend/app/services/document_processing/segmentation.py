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


def _is_heading_signal(sig: StructureSignal) -> bool:
    """Return True when any heading scheme 1-6 matches the signal.

    Priority order (1=highest) — but the result is a plain OR because the
    output does not record which scheme fired.
    """
    first = _first_line(sig.raw_text)

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
    """
    signals = doc.structure_signals
    canonical = doc.canonical_text

    if not signals:
        return []

    # ── Classify each signal ───────────────────────────────────────────────
    is_heading: list[bool] = [_is_heading_signal(s) for s in signals]

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
    # Collect (heading_signal | None, [body_signals]) groups.
    groups: list[tuple[StructureSignal | None, list[StructureSignal]]] = []

    current_heading: StructureSignal | None = None
    current_body: list[StructureSignal] = []

    for sig, heading_flag in zip(signals, is_heading, strict=True):
        if heading_flag:
            # Flush the current group before starting a new one.
            groups.append((current_heading, current_body))
            current_heading = sig
            current_body = []
        else:
            current_body.append(sig)

    # Flush final group.
    groups.append((current_heading, current_body))

    # ── Build SegmentedClause objects ──────────────────────────────────────
    clauses = []
    ordinal = 0

    for heading_sig, body_sigs in groups:
        # A leading group with no heading and no body is empty — skip it.
        if heading_sig is None and not body_sigs:
            continue

        # Determine the character span for this clause.
        all_sigs = ([heading_sig] if heading_sig is not None else []) + body_sigs
        char_start = all_sigs[0].char_start
        char_end = all_sigs[-1].char_end

        # Derive text by slicing; invariant holds by construction.
        text = canonical[char_start:char_end]
        heading_text = heading_sig.raw_text if heading_sig is not None else None

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
