"""Character-level diff engine backed by diff-match-patch.

Produces a list of :class:`Change` objects with absolute character offsets
into both the old and new text strings. Diffs are post-processed with
``diff_cleanupSemantic`` so that a small edit in one clause yields a
localized delta rather than a giant spanning operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from diff_match_patch import diff_match_patch

# diff-match-patch operation constants
_DELETE = -1
_INSERT = 1
_EQUAL = 0

_OP_MAP: dict[int, Literal["equal", "insert", "delete"]] = {
    _EQUAL: "equal",
    _INSERT: "insert",
    _DELETE: "delete",
}


@dataclass
class Change:
    """One contiguous run of equal, inserted, or deleted characters."""

    op: Literal["equal", "insert", "delete"]
    text: str
    # Offsets in the *old* string (-1 for pure inserts).
    old_start: int
    old_end: int
    # Offsets in the *new* string (-1 for pure deletes).
    new_start: int
    new_end: int


def diff(old_text: str, new_text: str) -> list[Change]:
    """Compute a character-level diff between *old_text* and *new_text*.

    The diff is semantically cleaned up so that changes are aligned on
    word/sentence boundaries where possible, keeping deltas localised.

    Parameters
    ----------
    old_text:
        The original text.
    new_text:
        The revised text.

    Returns
    -------
    list[Change]
        Ordered sequence of :class:`Change` objects covering the full span
        of both strings. ``old_start``/``old_end`` are ``-1`` for ``"insert"``
        operations; ``new_start``/``new_end`` are ``-1`` for ``"delete"``
        operations.
    """
    dmp = diff_match_patch()
    raw_diffs = dmp.diff_main(old_text, new_text)
    dmp.diff_cleanupSemantic(raw_diffs)

    changes: list[Change] = []
    old_cursor = 0
    new_cursor = 0

    for op_code, text in raw_diffs:
        length = len(text)
        op = _OP_MAP[op_code]

        if op == "equal":
            changes.append(
                Change(
                    op="equal",
                    text=text,
                    old_start=old_cursor,
                    old_end=old_cursor + length,
                    new_start=new_cursor,
                    new_end=new_cursor + length,
                )
            )
            old_cursor += length
            new_cursor += length

        elif op == "delete":
            changes.append(
                Change(
                    op="delete",
                    text=text,
                    old_start=old_cursor,
                    old_end=old_cursor + length,
                    new_start=-1,
                    new_end=-1,
                )
            )
            old_cursor += length

        else:  # insert
            changes.append(
                Change(
                    op="insert",
                    text=text,
                    old_start=-1,
                    old_end=-1,
                    new_start=new_cursor,
                    new_end=new_cursor + length,
                )
            )
            new_cursor += length

    return changes
