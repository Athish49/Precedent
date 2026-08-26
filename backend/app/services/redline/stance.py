"""Deterministic stance-mode filter and NMS context builder for S3 redline generation.

Stance semantics (business rule — no doc source defines per-severity thresholds,
so these are baked in as authoritative constants):
  light    → redline high-severity flags only (minimal intervention)
  balanced → redline medium + high severity flags
  firm     → redline all flagged clauses (low + medium + high)
"""

from __future__ import annotations

import uuid

from app.db.repositories.nms_repo import CounterpartyPattern
from app.schemas.analysis import FlagDTO

# Severity sets per stance mode.
_STANCE_SEVERITIES: dict[str, frozenset[str]] = {
    "light": frozenset({"high"}),
    "balanced": frozenset({"medium", "high"}),
    "firm": frozenset({"low", "medium", "high"}),
}

_SEVERITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3}

# Injected at the end of every non-empty NMS context string.
_STANCE_GUIDANCE: dict[str, str] = {
    "light": (
        "Apply minimal revisions; accept counterparty language unless it creates clear legal risk."
    ),
    "balanced": (
        "Target a balanced outcome; "
        "move toward playbook position where counterparty has shown flexibility."
    ),
    "firm": (
        "Maintain the preferred playbook position; "
        "do not accept deviations without escalation."
    ),
}

# Returned when there is no prior history (pattern is None or both fields are None).
_NO_HISTORY_CONTEXT: dict[str, str] = {
    "light": (
        "No prior negotiation history with this counterparty for this clause type. "
        "Apply light-touch revisions."
    ),
    "balanced": (
        "No prior negotiation history with this counterparty for this clause type. "
        "Apply balanced revisions."
    ),
    "firm": (
        "No prior negotiation history with this counterparty for this clause type. "
        "Maintain firm preferred position."
    ),
}


def queue_clauses(flags: list[FlagDTO], stance_mode: str) -> list[FlagDTO]:
    """Return one representative flag per clause that clears the stance severity threshold.

    The representative is the highest-severity qualifying flag for that clause;
    ties preserve the original list order.  Flags with ``clause_id=None``
    (missing-clause flags) are excluded — no existing text to redline.

    Raises ``ValueError`` for unrecognised ``stance_mode`` values.
    """
    allowed = _STANCE_SEVERITIES.get(stance_mode)
    if allowed is None:
        raise ValueError(
            f"Unknown stance_mode {stance_mode!r}; expected light|balanced|firm"
        )

    eligible = [f for f in flags if f.clause_id is not None and f.severity in allowed]

    best: dict[uuid.UUID, FlagDTO] = {}
    for flag in eligible:
        cid: uuid.UUID = flag.clause_id  # type: ignore[assignment]  # clause_id is not None here
        existing = best.get(cid)
        if existing is None or (
            _SEVERITY_RANK.get(flag.severity, 0) > _SEVERITY_RANK.get(existing.severity, 0)
        ):
            best[cid] = flag

    seen: set[uuid.UUID] = set()
    result: list[FlagDTO] = []
    for flag in eligible:
        cid = flag.clause_id  # type: ignore[assignment]
        if cid not in seen:
            seen.add(cid)
            result.append(best[cid])

    return result


def build_nms_context(pattern: CounterpartyPattern | None, stance_mode: str) -> str:
    """Return a deterministic NMS context string for injection into the T-047 LLM prompt.

    Describes historical negotiation outcomes with this counterparty for this
    clause type, framed relative to the current stance.

    Raises ``ValueError`` for unrecognised ``stance_mode`` values.
    """
    if stance_mode not in _STANCE_SEVERITIES:
        raise ValueError(
            f"Unknown stance_mode {stance_mode!r}; expected light|balanced|firm"
        )

    if pattern is None or (pattern.accept_rate is None and pattern.last_closed_text is None):
        return _NO_HISTORY_CONTEXT[stance_mode]

    parts: list[str] = []
    if pattern.accept_rate is not None:
        pct = round(pattern.accept_rate * 100)
        parts.append(f"Historical acceptance rate for this clause type: {pct}%.")
    if pattern.last_closed_text:
        parts.append(f'Last closed language: "{pattern.last_closed_text}".')
    parts.append(_STANCE_GUIDANCE[stance_mode])

    return " ".join(parts)
