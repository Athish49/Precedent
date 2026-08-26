"""Unit tests for the shared diff engine (T-014).

Covers both the clause aligner (app.core.diff.aligner) and the character-level
differ (app.core.diff.differ).
"""

from __future__ import annotations

from app.core.diff.aligner import Clause, align
from app.core.diff.differ import Change, diff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clause(clause_id: str, text: str) -> Clause:
    return Clause(clause_id=clause_id, text=text)


def _changes_by_op(changes: list[Change], op: str) -> list[Change]:
    return [c for c in changes if c.op == op]


# ---------------------------------------------------------------------------
# Aligner tests
# ---------------------------------------------------------------------------


def test_align_unchanged() -> None:
    """Identical clause lists produce all 'unchanged' pairs."""
    old = [_clause("c1", "Alpha"), _clause("c2", "Beta")]
    new = [_clause("c1", "Alpha"), _clause("c2", "Beta")]
    pairs = align(old, new)
    assert len(pairs) == 2
    assert all(p.change == "unchanged" for p in pairs)
    assert all(p.old is not None and p.new is not None for p in pairs)


def test_align_inserted() -> None:
    """A clause in *new* with a fresh id is marked 'inserted'."""
    old = [_clause("c1", "Alpha")]
    new = [_clause("c1", "Alpha"), _clause("c2", "New clause")]
    pairs = align(old, new)
    inserted = [p for p in pairs if p.change == "inserted"]
    assert len(inserted) == 1
    assert inserted[0].new is not None
    assert inserted[0].new.clause_id == "c2"
    assert inserted[0].old is None


def test_align_deleted() -> None:
    """A clause present in *old* but absent from *new* is marked 'deleted'."""
    old = [_clause("c1", "Alpha"), _clause("c2", "Beta")]
    new = [_clause("c1", "Alpha")]
    pairs = align(old, new)
    deleted = [p for p in pairs if p.change == "deleted"]
    assert len(deleted) == 1
    assert deleted[0].old is not None
    assert deleted[0].old.clause_id == "c2"
    assert deleted[0].new is None


def test_align_modified() -> None:
    """Same clause_id but different text → 'modified'."""
    old = [_clause("c1", "Original text")]
    new = [_clause("c1", "Modified text")]
    pairs = align(old, new)
    assert len(pairs) == 1
    assert pairs[0].change == "modified"
    assert pairs[0].old is not None
    assert pairs[0].new is not None
    assert pairs[0].old.clause_id == pairs[0].new.clause_id == "c1"


def test_align_reorder() -> None:
    """Reordered clauses are matched by clause_id, not treated as delete+insert."""
    old = [_clause("c1", "Alpha"), _clause("c2", "Beta"), _clause("c3", "Gamma")]
    # Reverse order in new document.
    new = [_clause("c3", "Gamma"), _clause("c2", "Beta"), _clause("c1", "Alpha")]
    pairs = align(old, new)

    # No inserts or deletes — all three clauses must be matched unchanged.
    assert len(pairs) == 3
    assert all(p.change == "unchanged" for p in pairs)

    # Output follows *new* order.
    new_ids = [p.new.clause_id for p in pairs if p.new is not None]  # type: ignore[union-attr]
    assert new_ids == ["c3", "c2", "c1"]


def test_align_mixed() -> None:
    """Combination: one unchanged, one modified, one deleted, one inserted."""
    old = [_clause("c1", "Keep"), _clause("c2", "Old text"), _clause("c3", "Remove")]
    new = [_clause("c1", "Keep"), _clause("c2", "New text"), _clause("c4", "Added")]
    pairs = align(old, new)

    by_change = {p.change: p for p in pairs}
    assert by_change["unchanged"].old.clause_id == "c1"  # type: ignore[union-attr]
    assert by_change["modified"].old.clause_id == "c2"  # type: ignore[union-attr]
    assert by_change["inserted"].new.clause_id == "c4"  # type: ignore[union-attr]
    assert by_change["deleted"].old.clause_id == "c3"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Differ tests
# ---------------------------------------------------------------------------


def test_differ_equal() -> None:
    """Identical strings produce a single 'equal' change covering the full text."""
    text = "The quick brown fox"
    changes = diff(text, text)
    assert len(changes) == 1
    assert changes[0].op == "equal"
    assert changes[0].text == text
    assert changes[0].old_start == 0
    assert changes[0].old_end == len(text)
    assert changes[0].new_start == 0
    assert changes[0].new_end == len(text)


def test_differ_insert() -> None:
    """Appending text produces a localized 'insert' change."""
    old = "Hello world"
    new = "Hello world, friend"
    changes = diff(old, new)

    inserts = _changes_by_op(changes, "insert")
    assert len(inserts) >= 1
    # The inserted text must be present somewhere in the change set.
    inserted_text = "".join(c.text for c in inserts)
    assert ", friend" in inserted_text

    # Insert ops must have -1 old offsets.
    for c in inserts:
        assert c.old_start == -1
        assert c.old_end == -1

    # New offsets must be valid (>= 0 and new_start < new_end).
    for c in inserts:
        assert c.new_start >= 0
        assert c.new_end > c.new_start


def test_differ_delete() -> None:
    """Removing text produces a localized 'delete' change."""
    old = "Hello beautiful world"
    new = "Hello world"
    changes = diff(old, new)

    deletes = _changes_by_op(changes, "delete")
    assert len(deletes) >= 1
    deleted_text = "".join(c.text for c in deletes)
    assert "beautiful" in deleted_text

    # Delete ops must have -1 new offsets.
    for c in deletes:
        assert c.new_start == -1
        assert c.new_end == -1

    # Old offsets must be valid.
    for c in deletes:
        assert c.old_start >= 0
        assert c.old_end > c.old_start


def test_differ_replace() -> None:
    """Replacing a word produces delete + insert, not one giant equal span."""
    old = "The cat sat on the mat"
    new = "The dog sat on the mat"
    changes = diff(old, new)

    ops = [c.op for c in changes]
    assert "delete" in ops
    assert "insert" in ops

    # "cat" must appear in deleted text.
    deleted_text = "".join(c.text for c in _changes_by_op(changes, "delete"))
    inserted_text = "".join(c.text for c in _changes_by_op(changes, "insert"))
    assert "cat" in deleted_text
    assert "dog" in inserted_text


def test_differ_determinism() -> None:
    """Same input → identical output on two successive calls."""
    old = "Clause one with some content."
    new = "Clause one with modified content and extra words."
    result_a = diff(old, new)
    result_b = diff(old, new)

    assert len(result_a) == len(result_b)
    for a, b in zip(result_a, result_b, strict=True):
        assert a.op == b.op
        assert a.text == b.text
        assert a.old_start == b.old_start
        assert a.old_end == b.old_end
        assert a.new_start == b.new_start
        assert a.new_end == b.new_end


def test_differ_offset_coverage() -> None:
    """Equal + delete changes must cover every character of old_text exactly once."""
    old = "Section 1: Parties. Section 2: Obligations."
    new = "Section 1: Parties. Section 2: Revised obligations and extra terms."
    changes = diff(old, new)

    # Reconstruct old_text from equal + delete spans (in order).
    reconstructed_old = ""
    for c in changes:
        if c.op in ("equal", "delete"):
            reconstructed_old += c.text
    assert reconstructed_old == old

    # Reconstruct new_text from equal + insert spans (in order).
    reconstructed_new = ""
    for c in changes:
        if c.op in ("equal", "insert"):
            reconstructed_new += c.text
    assert reconstructed_new == new
