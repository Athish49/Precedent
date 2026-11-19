"""Segmentation (plan section 5.3).

Pure function: segment(document, hints) -> (clauses, warnings).
No database, no network, no storage imports.
"""

from __future__ import annotations

import re
import string

from app.services.document_processing.types import Block, CanonicalDocument, ClauseDraft, SectionHint

_ALPHA_RE = re.compile(r"^\(([a-zA-Z])\)\s*")
_ROMAN_RE = re.compile(r"^\(([ivxlcdmIVXLCDM]{2,})\)\s*")
_NUMERIC_EXT_RE = re.compile(r"^(\d+(?:\.\d+)+)[.\-):]*\s*")
_WITNESS_RE = re.compile(r"^\s*IN WITNESS WHEREOF", re.IGNORECASE)
_NO_NUMBER_FALLBACK_RE = re.compile(
    r"^(\d+(?:\.\d+)*)[.\-):]\s*([^.\n:]{1,80}?)[.:]"
)

_HEADING_TYPES = {"heading", "section_heading"}

# Appendix/exhibit/schedule/annex headings that Extract's own `clauses[]`
# hints systematically omit (verification doc section 5/5.1a, proposed
# change #3). Matched only when the ENTIRE block is heading-shaped: a
# label (Exhibit/Schedule/Annex/Appendix), a single letter/number/roman
# label, then nothing or a short title running to the end of the block.
# This is deliberately strict (end-anchored, single-token label) so an
# ordinary body paragraph that happens to start with "Schedule 1 sets out
# ..." does not match -- only an actual heading line does. A mid-sentence
# cross-reference like "see Exhibit A" never reaches this regex at all
# since it isn't the start of its own block.
_APPENDIX_RE = re.compile(
    r"^\s*(Exhibit|Schedule|Annex|Appendix)\s+([A-Za-z]|\d+|[IVXLCDM]+)\b"
    r"(?:\s*[:\-–—.]\s*(.{1,80}))?\s*$",
    re.IGNORECASE,
)


def _words(text: str) -> list[str]:
    return text.split()


def _is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c in string.ascii_uppercase for c in letters)


def _kept_blocks(document: CanonicalDocument) -> list[Block]:
    return [b for b in document.blocks if not b.dropped]


def _build_anchor_regex(hint: SectionHint) -> re.Pattern | None:
    title_words = _words(hint.title) if hint.title else []
    title_pattern = (
        r"[^A-Za-z0-9]*".join(re.escape(w) for w in title_words) if title_words else None
    )
    if hint.section_number:
        num = re.escape(hint.section_number)
        prefix = rf"(?:(?:article|section)\s+)?{num}(?!\.?\d)\s*[.\-):]*\s*"
        if title_pattern is None:
            return re.compile(r"^\s*" + prefix, re.IGNORECASE)
        return re.compile(r"^\s*" + prefix + "(" + title_pattern + ")", re.IGNORECASE)
    if title_pattern is None:
        return None
    return re.compile(r"^\s*(" + title_pattern + ")", re.IGNORECASE)


def _anchor_matches(hint: SectionHint, block: Block) -> re.Match | None:
    pattern = _build_anchor_regex(hint)
    if pattern is None:
        return None
    m = pattern.match(block.text)
    if m is None:
        return None
    if hint.section_number is None:
        # No number: match title at the start of a block of at most 12 words.
        if len(_words(block.text)) > 12:
            return None
    return m


def _anchor_hints(
    kept: list[Block], hints: list[SectionHint]
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    anchors: list[dict] = []
    search_start = 0
    for hint in hints:
        found = None
        for i in range(search_start, len(kept)):
            block = kept[i]
            m = _anchor_matches(hint, block)
            if m is not None:
                found = (i, m)
                break
        if found is None:
            label = f"{hint.section_number or ''} {hint.title or ''}".strip()
            warnings.append(f"section_not_anchored:{label}")
            continue
        i, m = found
        anchors.append(
            {
                "block_idx": i,
                "hint": hint,
                "char_start": block_char_start(kept[i]),
                "heading_text": kept[i].text[: m.end()],
            }
        )
        search_start = i + 1

    if hints:
        anchored_rate = len(anchors) / len(hints)
        if anchored_rate < 0.8:
            warnings.append("low_anchor_rate")

    return anchors, warnings


def block_char_start(block: Block) -> int:
    return block.char_start


def _fallback_sections(kept: list[Block]) -> list[dict]:
    """No hints (or none anchored): find section starts by rule."""
    sections: list[dict] = []
    for i, block in enumerate(kept):
        m = _NO_NUMBER_FALLBACK_RE.match(block.text)
        if m is not None:
            number = m.group(1)
            title = m.group(2).strip()
            sections.append(
                {
                    "block_idx": i,
                    "hint": SectionHint(section_number=number, title=title, family=None),
                    "char_start": block.char_start,
                    "heading_text": block.text[: m.end()],
                }
            )
            continue
        if block.type in _HEADING_TYPES:
            words = _words(block.text)
            if len(words) <= 12 and not (_is_all_caps(block.text) and len(words) > 8):
                sections.append(
                    {
                        "block_idx": i,
                        "hint": SectionHint(section_number=None, title=block.text.strip(), family=None),
                        "char_start": block.char_start,
                        "heading_text": block.text,
                    }
                )
    return sections


def _detect_appendix_sections(
    kept: list[Block],
    scan_start: int,
    scan_end: int,
    exclude_block_idxs: set[int],
) -> list[dict]:
    """Fallback detection of unhinted exhibit/schedule/annex/appendix
    headings (verification doc section 5.1a, proposed change #3). Only
    scans blocks within [scan_start, scan_end) that were not already used
    as a hint's own anchor block, so this never fires inside an anchored
    section's own heading and never widens an already-anchored section's
    boundaries beyond what the hint itself claimed.
    """
    found: list[dict] = []
    for i, block in enumerate(kept):
        if i in exclude_block_idxs:
            continue
        if block.char_start < scan_start or block.char_start >= scan_end:
            continue
        m = _APPENDIX_RE.match(block.text)
        if m is None:
            continue
        if len(_words(block.text)) > 12:
            # Heading-shaped per the regex but still too long to be a
            # real heading line (extra defense-in-depth alongside the
            # end-anchored regex above).
            continue
        label = m.group(1)
        num = m.group(2)
        title_raw = m.group(3)
        title = title_raw.strip() or None if title_raw else None
        section_number = f"{label.capitalize()} {num}"
        found.append(
            {
                "block_idx": i,
                "hint": SectionHint(section_number=section_number, title=title, family=None),
                "char_start": block.char_start,
                "heading_text": block.text[: m.end()],
                "anchored": False,
            }
        )
    return found


def _find_signature_start(kept: list[Block], after_char: int) -> int | None:
    for block in kept:
        if block.char_start < after_char:
            continue
        if block.type == "key_value" or _WITNESS_RE.match(block.text):
            return block.char_start
    return None


def _classify_break(
    block: Block, section_number: str | None, stack: list[dict]
) -> tuple[int, str, str, int] | None:
    """Return (depth, kind, label, match_end) if `block` opens a sub-clause."""
    m = _NUMERIC_EXT_RE.match(block.text)
    if m is not None and section_number:
        child_num = m.group(1)
        parent_parts = section_number.split(".")
        child_parts = child_num.split(".")
        if child_parts[: len(parent_parts)] == parent_parts and len(child_parts) > len(parent_parts):
            depth = 1 + (len(child_parts) - len(parent_parts))
            return depth, "numeric", child_num, m.end()

    m = _ALPHA_RE.match(block.text)
    if m is not None:
        last_number_depth = max(
            (n["depth"] for n in stack if n["kind"] in ("section", "numeric")),
            default=1,
        )
        return last_number_depth + 1, "alpha", m.group(1), m.end()

    m = _ROMAN_RE.match(block.text)
    if m is not None:
        depth = stack[-1]["depth"] + 1 if stack else 2
        return depth, "roman", m.group(1), m.end()

    return None


def _page_range(blocks: list[Block], char_start: int, char_end: int) -> tuple[int, int]:
    pages = [
        b.page
        for b in blocks
        if not b.dropped and b.char_start < char_end and b.char_end > char_start
    ]
    if not pages:
        return 1, 1
    return min(pages), max(pages)


def segment(
    document: CanonicalDocument, hints: list[SectionHint]
) -> tuple[list[ClauseDraft], list[str]]:
    text = document.text
    kept = _kept_blocks(document)
    all_blocks = list(document.blocks)

    used_hint_anchors = False
    if hints:
        sections, warnings = _anchor_hints(kept, hints)
        anchored_flag = True
        if not sections:
            sections = _fallback_sections(kept)
            anchored_flag = False
        else:
            used_hint_anchors = True
    else:
        sections = _fallback_sections(kept)
        warnings = []
        anchored_flag = False

    if not sections:
        # Nothing matched at all: one clause covering the whole text.
        clause = ClauseDraft(
            ordinal=0,
            level=1,
            parent_ordinal=None,
            section_number=None,
            title=None,
            heading_text=None,
            text=text,
            char_start=0,
            char_end=len(text),
            page_start=1,
            page_end=max(document.page_count, 1),
            clause_type="other",
            type_source="none",
            anchored=False,
        )
        return [clause], warnings

    sections.sort(key=lambda s: s["char_start"])

    if used_hint_anchors:
        exclude_block_idxs = {s["block_idx"] for s in sections}
        hint_last_char_start = sections[-1]["char_start"]
        appendix_boundary = _find_signature_start(kept, hint_last_char_start + 1)
        scan_end = appendix_boundary if appendix_boundary is not None else len(text)
        scan_start = sections[0]["char_start"]
        appendix_sections = _detect_appendix_sections(
            kept, scan_start, scan_end, exclude_block_idxs
        )
        if appendix_sections:
            sections = sections + appendix_sections
            sections.sort(key=lambda s: s["char_start"])

    last_section_char_start = sections[-1]["char_start"]
    signature_start = _find_signature_start(kept, last_section_char_start + 1)

    # Build the list of top-level section nodes (dict form, not yet ClauseDraft).
    nodes: list[dict] = []

    preamble_end = sections[0]["char_start"]
    if preamble_end > 0:
        nodes.append(
            {
                "level": 1,
                "parent": None,
                "section_number": None,
                "title": None,
                "heading_text": None,
                "char_start": 0,
                "char_end": preamble_end,
                "clause_type": "preamble",
                "type_source": "none",
                "anchored": True,
            }
        )

    section_end_points = []
    for idx in range(len(sections)):
        start = sections[idx]["char_start"]
        if idx + 1 < len(sections):
            end = sections[idx + 1]["char_start"]
        elif signature_start is not None:
            end = signature_start
        else:
            end = len(text)
        section_end_points.append((start, end))

    for idx, sec in enumerate(sections):
        start, end = section_end_points[idx]
        hint = sec["hint"]
        section_node = {
            "level": 1,
            "parent": None,
            "section_number": hint.section_number,
            "title": hint.title,
            "heading_text": sec["heading_text"],
            "char_start": start,
            "char_end": end,
            "clause_type": "other",
            "type_source": "none",
            "anchored": sec.get("anchored", anchored_flag),
        }
        nodes.append(section_node)

        # Sub-clauses: find blocks in [start, end) that open a child.
        blocks_in_range = [
            b for b in kept if b.char_start >= start and b.char_start < end
        ]
        # Skip the section's own anchor block (first one), since its own
        # opening is the section heading, not a sub-clause marker.
        rest_blocks = blocks_in_range[1:] if blocks_in_range else []

        stack = [{"depth": 1, "node": section_node, "kind": "section"}]

        # Build child nodes, applying a depth-stack to assign parents and
        # close out ranges as deeper/sibling breaks occur. Classification
        # and the stack update happen in the same pass, since alpha/roman
        # depth depends on the stack state at the point of the break.
        for block in rest_blocks:
            classified = _classify_break(block, hint.section_number, stack)
            if classified is None:
                continue
            depth, kind, label, _match_end = classified
            char_pos = block.char_start
            while len(stack) >= depth:
                popped = stack.pop()
                if popped["node"]["char_end"] is None or popped["node"]["char_end"] == end:
                    popped["node"]["char_end"] = char_pos
            parent_node = stack[-1]["node"]
            child_node = {
                "level": depth,
                "parent": parent_node,
                "section_number": None,
                "title": None,
                "heading_text": None,
                "char_start": char_pos,
                "char_end": end,
                "clause_type": None,  # inherits parent's type later
                "type_source": None,
                "anchored": sec.get("anchored", anchored_flag),
                "_break_kind": kind,
                "_break_label": label,
            }
            nodes.append(child_node)
            stack.append({"depth": depth, "node": child_node, "kind": kind})

        # Close any still-open children at the section's end.
        while len(stack) > 1:
            popped = stack.pop()
            popped["node"]["char_end"] = end

    if signature_start is not None:
        nodes.append(
            {
                "level": 1,
                "parent": None,
                "section_number": None,
                "title": None,
                "heading_text": None,
                "char_start": signature_start,
                "char_end": len(text),
                "clause_type": "signature_block",
                "type_source": "none",
                "anchored": True,
            }
        )

    # Order depth-first: sorting by char_start gives pre-order since a
    # parent always starts at or before its children.
    nodes.sort(key=lambda n: n["char_start"])

    ordinal_of: dict[int, int] = {}
    for ordinal, node in enumerate(nodes):
        ordinal_of[id(node)] = ordinal

    clauses: list[ClauseDraft] = []
    for node in nodes:
        ordinal = ordinal_of[id(node)]
        parent_ordinal = (
            ordinal_of[id(node["parent"])] if node["parent"] is not None else None
        )
        char_start = node["char_start"]
        char_end = node["char_end"]
        page_start, page_end = _page_range(all_blocks, char_start, char_end)
        clause_type = node["clause_type"] or "other"
        type_source = node["type_source"] or "none"
        clauses.append(
            ClauseDraft(
                ordinal=ordinal,
                level=node["level"],
                parent_ordinal=parent_ordinal,
                section_number=node["section_number"],
                title=node["title"],
                heading_text=node["heading_text"],
                text=text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                page_start=page_start,
                page_end=page_end,
                clause_type=clause_type,
                type_source=type_source,
                anchored=node["anchored"],
            )
        )

    return clauses, warnings
