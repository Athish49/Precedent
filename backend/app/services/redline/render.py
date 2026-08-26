"""S3 render step — turn LLM replacement_text into tracked changes and
run non-interference check (T-048).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.diff.differ import Change, diff
from app.schemas.analysis import FlagDTO


class NonInterferenceError(Exception):
    pass


@dataclass
class RenderResult:
    tracked_changes: list[Change]
    interference_detected: bool  # True when a change falls outside the flagged span


def render(
    original_text: str,
    replacement_text: str,
    flag: FlagDTO,
    strict: bool = False,
) -> RenderResult:
    tracked_changes = diff(original_text, replacement_text)

    if flag.char_start is None or flag.char_end is None:
        return RenderResult(tracked_changes=tracked_changes, interference_detected=False)

    char_start = flag.char_start
    char_end = flag.char_end

    interference_detected = False
    old_cursor = 0  # tracks position in old text as we walk the change list

    for change in tracked_changes:
        if change.op == "equal":
            old_cursor = change.old_end
        elif change.op == "delete":
            if change.old_start < char_start or change.old_end > char_end:
                interference_detected = True
                break
            old_cursor = change.old_end
        else:  # insert — locate it in old coordinates by current cursor
            insert_pos = old_cursor
            if insert_pos < char_start or insert_pos > char_end:
                interference_detected = True
                break
            # inserts don't advance old_cursor

    if interference_detected and strict:
        raise NonInterferenceError(
            f"Redline change falls outside flagged region [{char_start}, {char_end}]"
        )

    return RenderResult(
        tracked_changes=tracked_changes, interference_detected=interference_detected
    )
