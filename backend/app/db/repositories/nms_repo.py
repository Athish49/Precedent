"""NMS (Negotiation Memory Store) repository — append-only writes, pattern reads."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import qualified
from app.db.models.nms import DecisionEvent

# The view lives in the project schema; never rely on the session search path.
_PATTERN_VIEW = qualified("counterparty_pattern")


@dataclass
class CounterpartyPattern:
    """Row returned by the ``counterparty_pattern`` SQL view."""

    counterparty_id: uuid.UUID
    clause_type: str
    accept_rate: float | None
    last_closed_text: str | None


# ---------------------------------------------------------------------------
# NOTE (task 4.6): a zero/nil UUID (``uuid.UUID(int=0)``) was previously used
# throughout ``app/workflows/review_pipeline.py`` and ``app/api/routes/
# redlines.py`` as a placeholder for "unknown counterparty". That has been
# removed in favour of passing ``None`` through, which is why
# ``get_counterparty_pattern`` below accepts ``counterparty_id: uuid.UUID |
# None`` and short-circuits to "no pattern" rather than querying the view
# with a fabricated id.
# ---------------------------------------------------------------------------


async def create_decision_event(
    session: AsyncSession, event: DecisionEvent
) -> DecisionEvent:
    """Append a new decision event.  Never updates an existing row."""
    session.add(event)
    await session.flush()
    return event


async def get_events_for_contract(
    session: AsyncSession, contract_id: uuid.UUID
) -> list[DecisionEvent]:
    """Return all decision events for a contract, oldest first."""
    result = await session.execute(
        select(DecisionEvent)
        .where(DecisionEvent.contract_id == contract_id)
        .order_by(DecisionEvent.created_at)
    )
    return list(result.scalars().all())


async def get_counterparty_pattern(
    session: AsyncSession,
    counterparty_id: uuid.UUID | None,
    clause_type: str,
) -> CounterpartyPattern | None:
    """Return the pattern for a (counterparty, clause_type) pair, or None if no history.

    Queries the ``counterparty_pattern`` SQL view directly. Returns None when
    the GROUP BY emits no row for that combination (no prior decision events),
    and also when ``counterparty_id`` is None (unknown counterparty — there is
    by definition no negotiation history to look up).
    """
    if counterparty_id is None:
        return None

    stmt = text(
        f"""
        SELECT counterparty_id, clause_type, accept_rate, last_closed_text
        FROM {_PATTERN_VIEW}
        WHERE counterparty_id = :counterparty_id
          AND clause_type = :clause_type
        """
    )
    result = await session.execute(
        stmt,
        {"counterparty_id": str(counterparty_id), "clause_type": clause_type},
    )
    row = result.first()
    if row is None:
        return None
    return CounterpartyPattern(
        counterparty_id=uuid.UUID(str(row.counterparty_id)),
        clause_type=row.clause_type,
        accept_rate=row.accept_rate,
        last_closed_text=row.last_closed_text,
    )


async def get_patterns_for_counterparty(
    session: AsyncSession,
    counterparty_id: uuid.UUID,
) -> list[CounterpartyPattern]:
    """Return all patterns for a counterparty across all clause types."""
    stmt = text(
        f"""
        SELECT counterparty_id, clause_type, accept_rate, last_closed_text
        FROM {_PATTERN_VIEW}
        WHERE counterparty_id = :counterparty_id
        ORDER BY clause_type
        """
    )
    result = await session.execute(stmt, {"counterparty_id": str(counterparty_id)})
    return [
        CounterpartyPattern(
            counterparty_id=uuid.UUID(str(row.counterparty_id)),
            clause_type=row.clause_type,
            accept_rate=row.accept_rate,
            last_closed_text=row.last_closed_text,
        )
        for row in result.all()
    ]
