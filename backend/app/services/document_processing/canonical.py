"""Blocks to canonical text (plan section 5.2).

Pure function: build_canonical(parse_blocks) -> CanonicalDocument.
No database, no network, no storage imports.
"""

from __future__ import annotations

import re
from collections import Counter

from app.services.document_processing.types import Block, CanonicalDocument

_DROPPED_TYPES = {"footer", "page_number"}

_PRIVATE_USE_LEADING_RE = re.compile(r"^[--]+\s*")
_HEADING_MARK_RE = re.compile(r"^#{1,6}\s*")
_BOLD_MARK_RE = re.compile(r"\*\*")
_LINE_BREAK_HYPHEN_RE = re.compile(r"(\w)- (\w)")
_SEPARATOR_ROW_RE = re.compile(r"^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$")
_WHITESPACE_RUN_RE = re.compile(r"[ \t]+")


def _page_of(raw_block: dict) -> int:
    page = ((raw_block.get("metadata") or {}).get("page") or {}).get("number")
    return int(page) if page is not None else 1


def _raw_text(raw_block: dict) -> str:
    return raw_block.get("content") or ""


def _normalize(text: str) -> str:
    """Normalise text for comparison: strip markdown marks, case, whitespace."""
    stripped = _HEADING_MARK_RE.sub("", text)
    stripped = _BOLD_MARK_RE.sub("", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip().lower()
    return stripped


def _clean_text(text: str, *, is_table: bool) -> str:
    """Clean markdown marks, line-break hyphens and stray bullet characters."""
    cleaned = text
    if not is_table:
        cleaned = _HEADING_MARK_RE.sub("", cleaned)
        cleaned = _BOLD_MARK_RE.sub("", cleaned)
    cleaned = _PRIVATE_USE_LEADING_RE.sub("- ", cleaned)
    cleaned = _LINE_BREAK_HYPHEN_RE.sub(r"\1-\2", cleaned)
    if is_table:
        # Collapse horizontal whitespace within each line, but keep line
        # breaks (table rows) intact.
        lines = cleaned.split("\n")
        lines = [_WHITESPACE_RUN_RE.sub(" ", line).strip() for line in lines]
        cleaned = "\n".join(lines)
    else:
        cleaned = _WHITESPACE_RUN_RE.sub(" ", cleaned)
        cleaned = cleaned.strip()
    return cleaned


def _strip_separator_rows(table_text: str) -> str:
    """Drop markdown table separator rows (e.g. '| --- | --- |') from a table block."""
    lines = table_text.split("\n")
    kept = [line for line in lines if not _SEPARATOR_ROW_RE.match(line)]
    return "\n".join(kept)


def build_canonical(parse_blocks: list[dict]) -> CanonicalDocument:
    """Build a CanonicalDocument from Extend Parse blocks, per plan section 5.2.

    Steps:
      1. Drop footer and page_number blocks.
      2. Drop running headers: any block whose normalised text equals a
         `header` block's text, and any block that repeats as the first
         kept block on at least half the pages (minimum two pages).
      3. Clean kept blocks: strip markdown marks, close up line-break
         hyphens, replace stray private-use bullet characters.
      4. Join a table block to the previous one when it crosses a page
         break, appending its data rows and dropping its separator row.
      5. Join kept blocks with a blank line, recording exact offsets.
    """
    if not parse_blocks:
        return CanonicalDocument(text="", blocks=(), page_count=0)

    page_count = max((_page_of(b) for b in parse_blocks), default=0)

    # Normalised text of every explicit `header` block.
    header_texts = {
        _normalize(_raw_text(b)) for b in parse_blocks if b.get("type") == "header"
    }

    # First pass: drop footer/page_number and explicit header matches.
    # (index, raw_block, page, type)
    stage1: list[tuple[int, dict, int, str]] = []
    for idx, raw in enumerate(parse_blocks):
        btype = raw.get("type")
        if btype in _DROPPED_TYPES:
            continue
        norm = _normalize(_raw_text(raw))
        if norm and norm in header_texts:
            continue
        stage1.append((idx, raw, _page_of(raw), btype))

    # Second pass: drop blocks that repeat as the first kept block on at
    # least half the pages (minimum two pages), even if untagged.
    first_kept_per_page: dict[int, str] = {}
    for _idx, raw, page, _btype in stage1:
        if page not in first_kept_per_page:
            first_kept_per_page[page] = _normalize(_raw_text(raw))

    counts = Counter(first_kept_per_page.values())
    num_pages = max(len(first_kept_per_page), 1)
    repeated_header_texts = {
        text
        for text, count in counts.items()
        if text and count >= 2 and count >= num_pages / 2
    }

    kept: list[tuple[int, dict, int, str]] = []
    for idx, raw, page, btype in stage1:
        norm = _normalize(_raw_text(raw))
        if norm and norm in repeated_header_texts:
            continue
        kept.append((idx, raw, page, btype))

    # Clean kept blocks' text.
    cleaned_kept: list[dict] = []
    for idx, raw, page, btype in kept:
        is_table = btype == "table"
        text = _clean_text(_raw_text(raw), is_table=is_table)
        cleaned_kept.append(
            {"index": idx, "type": btype, "text": text, "page": page}
        )

    # Merge tables that cross a page break.
    merged: list[dict] = []
    for entry in cleaned_kept:
        if (
            merged
            and entry["type"] == "table"
            and merged[-1]["type"] == "table"
            and merged[-1]["page"] != entry["page"]
            and _is_first_on_its_page(cleaned_kept, entry)
        ):
            appended = _strip_separator_rows(entry["text"])
            if appended:
                merged[-1]["text"] = merged[-1]["text"] + "\n" + appended
            continue
        merged.append(dict(entry))

    # Join with blank lines, recording offsets.
    pieces: list[str] = []
    offsets: dict[int, tuple[int, int]] = {}
    pos = 0
    for i, entry in enumerate(merged):
        if i > 0:
            pieces.append("\n\n")
            pos += 2
        start = pos
        pieces.append(entry["text"])
        pos += len(entry["text"])
        offsets[entry["index"]] = (start, pos)

    text = "".join(pieces)

    # Build the full Block list, in original order, dropped ones included.
    blocks: list[Block] = []
    for idx, raw in enumerate(parse_blocks):
        btype = raw.get("type")
        page = _page_of(raw)
        if idx in offsets:
            char_start, char_end = offsets[idx]
            block_text = text[char_start:char_end]
            blocks.append(
                Block(
                    index=idx,
                    type=btype,
                    text=block_text,
                    page=page,
                    char_start=char_start,
                    char_end=char_end,
                    dropped=False,
                )
            )
        else:
            blocks.append(
                Block(
                    index=idx,
                    type=btype,
                    text=_raw_text(raw),
                    page=page,
                    char_start=-1,
                    char_end=-1,
                    dropped=True,
                )
            )

    return CanonicalDocument(text=text, blocks=tuple(blocks), page_count=page_count)


def _is_first_on_its_page(cleaned_kept: list[dict], entry: dict) -> bool:
    """True if `entry` is the first kept block on its page within `cleaned_kept`."""
    for other in cleaned_kept:
        if other["page"] == entry["page"]:
            return other["index"] == entry["index"]
    return False
