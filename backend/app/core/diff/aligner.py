"""Clause aligner: match old and new clause lists by stable clause_id.

Robust to insert, delete, and reorder operations. A clause that moves
position but retains its clause_id is matched — not treated as delete+insert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class Clause:
    """Minimal clause representation used by the diff engine."""

    clause_id: str
    text: str


@dataclass
class AlignedPair:
    """One aligned slot produced by :func:`align`."""

    old: Clause | None
    new: Clause | None
    change: Literal["unchanged", "modified", "inserted", "deleted"]


def align(old_clauses: list[Clause], new_clauses: list[Clause]) -> list[AlignedPair]:
    """Align *old_clauses* and *new_clauses* by ``clause_id``.

    Matching strategy
    -----------------
    1. Build an index of old clauses keyed by ``clause_id``.
    2. Walk *new_clauses* in order:
       - If a matching old clause exists, emit ``"unchanged"`` or ``"modified"``.
       - Otherwise emit ``"inserted"``.
    3. Any old clause whose id was never consumed is emitted as ``"deleted"``.

    Deleted clauses are appended after all matched/inserted clauses so the
    output stays deterministic regardless of where deletions occurred.

    Parameters
    ----------
    old_clauses:
        Clauses from the prior version of the document.
    new_clauses:
        Clauses from the new version of the document.

    Returns
    -------
    list[AlignedPair]
        One entry per unique clause, in new-document order (deletions last).
    """
    old_index: dict[str, Clause] = {c.clause_id: c for c in old_clauses}
    consumed: set[str] = set()

    pairs: list[AlignedPair] = []

    for new_clause in new_clauses:
        cid = new_clause.clause_id
        if cid in old_index:
            old_clause = old_index[cid]
            consumed.add(cid)
            change: Literal["unchanged", "modified"] = (
                "unchanged" if old_clause.text == new_clause.text else "modified"
            )
            pairs.append(AlignedPair(old=old_clause, new=new_clause, change=change))
        else:
            pairs.append(AlignedPair(old=None, new=new_clause, change="inserted"))

    # Emit deletions in the original order for determinism.
    for old_clause in old_clauses:
        if old_clause.clause_id not in consumed:
            pairs.append(AlignedPair(old=old_clause, new=None, change="deleted"))

    return pairs
