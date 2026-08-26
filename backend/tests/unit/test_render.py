"""Unit tests for redline render step (T-048)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.schemas.analysis import FlagDTO
from app.services.redline.render import NonInterferenceError, RenderResult, render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(char_start: int | None, char_end: int | None) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        clause_id=None,
        flag_type="unfavorable",
        severity="medium",
        source="rule",
        char_start=char_start,
        char_end=char_end,
        detail={},
        matched_rule_id=None,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# 1. Basic render — tracked_changes are produced with correct op types and text
# ---------------------------------------------------------------------------


def test_basic_render_produces_tracked_changes() -> None:
    original = "The liability shall be unlimited."
    replacement = "The liability shall be limited to direct damages."
    flag = _flag(char_start=0, char_end=len(original))

    result = render(original, replacement, flag)

    assert isinstance(result, RenderResult)
    ops = [c.op for c in result.tracked_changes]
    # Must contain at least one delete and one insert (something changed)
    assert "delete" in ops
    assert "insert" in ops

    # Reconstructed old text from equal+delete spans must equal original
    reconstructed_old = "".join(
        c.text for c in result.tracked_changes if c.op in ("equal", "delete")
    )
    assert reconstructed_old == original

    # Reconstructed new text from equal+insert spans must equal replacement
    reconstructed_new = "".join(
        c.text for c in result.tracked_changes if c.op in ("equal", "insert")
    )
    assert reconstructed_new == replacement


# ---------------------------------------------------------------------------
# 2. No change — all ops are "equal", interference_detected=False
# ---------------------------------------------------------------------------


def test_no_change_produces_equal_ops() -> None:
    text = "Governing law shall be New York."
    flag = _flag(char_start=0, char_end=len(text))

    result = render(text, text, flag)

    assert all(c.op == "equal" for c in result.tracked_changes)
    assert result.interference_detected is False


# ---------------------------------------------------------------------------
# 3. Non-interference passes — change fully within flagged region
# ---------------------------------------------------------------------------


def test_non_interference_passes_when_change_inside_region() -> None:
    # Original: "AAAA [target word] AAAA"
    # We flag only the middle portion and replace a word inside it
    prefix = "Preamble text. "
    flagged_region = "liability is unlimited in all cases"
    suffix = ". End of clause."
    original = prefix + flagged_region + suffix
    replacement = prefix + "liability is limited to direct damages" + suffix

    char_start = len(prefix)
    char_end = len(prefix) + len(flagged_region)
    flag = _flag(char_start=char_start, char_end=char_end)

    result = render(original, replacement, flag)

    assert result.interference_detected is False


# ---------------------------------------------------------------------------
# 4. Non-interference fails — change outside flagged region
# ---------------------------------------------------------------------------


def test_non_interference_fails_when_change_outside_region() -> None:
    # Flag covers only the middle; we change the prefix (outside)
    prefix = "Modified preamble. "
    flagged = "liability is unlimited"
    suffix = ". End of clause."
    original = "Original preamble. " + flagged + suffix
    replacement = prefix + flagged + suffix

    # Flag only the middle (flagged) portion — char positions in original
    char_start = len("Original preamble. ")
    char_end = char_start + len(flagged)
    flag = _flag(char_start=char_start, char_end=char_end)

    result = render(original, replacement, flag)

    assert result.interference_detected is True


def test_strict_mode_raises_non_interference_error() -> None:
    original = "Original preamble. liability is unlimited. End of clause."
    replacement = "Changed preamble. liability is unlimited. End of clause."

    char_start = len("Original preamble. ")
    char_end = char_start + len("liability is unlimited")
    flag = _flag(char_start=char_start, char_end=char_end)

    with pytest.raises(NonInterferenceError):
        render(original, replacement, flag, strict=True)


def test_strict_mode_does_not_raise_when_change_inside() -> None:
    prefix = "Preamble text. "
    flagged = "liability is unlimited in all cases"
    suffix = ". End of clause."
    original = prefix + flagged + suffix
    replacement = prefix + "liability is limited to direct damages" + suffix

    char_start = len(prefix)
    char_end = len(prefix) + len(flagged)
    flag = _flag(char_start=char_start, char_end=char_end)

    # Should not raise
    result = render(original, replacement, flag, strict=True)
    assert result.interference_detected is False


# ---------------------------------------------------------------------------
# 5. None char_start/char_end — non-interference check skipped
# ---------------------------------------------------------------------------


def test_none_char_start_skips_interference_check() -> None:
    original = "The quick brown fox"
    replacement = "The slow red fox"
    flag = _flag(char_start=None, char_end=None)

    result = render(original, replacement, flag)

    # tracked_changes are still produced
    assert len(result.tracked_changes) > 0
    # No interference detected (check skipped)
    assert result.interference_detected is False


def test_none_char_start_strict_does_not_raise() -> None:
    original = "Some clause text here."
    replacement = "Completely different text here."
    flag = _flag(char_start=None, char_end=None)

    # strict=True must not raise when there is no region to check against
    result = render(original, replacement, flag, strict=True)
    assert result.interference_detected is False


# ---------------------------------------------------------------------------
# 6. Determinism — same inputs always produce same output
# ---------------------------------------------------------------------------


def test_determinism() -> None:
    original = "The indemnifying party shall bear all costs and expenses."
    replacement = "The indemnifying party shall bear reasonable costs."
    flag = _flag(char_start=0, char_end=len(original))

    result_a = render(original, replacement, flag)
    result_b = render(original, replacement, flag)

    assert len(result_a.tracked_changes) == len(result_b.tracked_changes)
    for a, b in zip(result_a.tracked_changes, result_b.tracked_changes, strict=True):
        assert a.op == b.op
        assert a.text == b.text
        assert a.old_start == b.old_start
        assert a.old_end == b.old_end
        assert a.new_start == b.new_start
        assert a.new_end == b.new_end

    assert result_a.interference_detected == result_b.interference_detected
