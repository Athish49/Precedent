from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.contract import Contract, ContractMetadata
from app.db.models.obligation import Alert, Obligation
from app.db.repositories import obligation_repo


@dataclass
class MonitorResult:
    deadline_alerts: list[Alert]
    renewal_alerts: list[Alert]

    @property
    def total(self) -> int:
        return len(self.deadline_alerts) + len(self.renewal_alerts)


async def run_monitor(
    session: AsyncSession,
    *,
    today: date | None = None,
    deadline_days: int = 30,
    renewal_window_min: int = 30,
    renewal_window_max: int = 90,
) -> MonitorResult:
    """Run one deterministic monitoring pass. Fires deadline + renewal alerts.

    Args:
        session: Async DB session (caller commits).
        today: Reference date; defaults to date.today().
        deadline_days: Days ahead to check for upcoming deadlines.
        renewal_window_min: Minimum days ahead for renewal alerts (default 30).
        renewal_window_max: Maximum days ahead for renewal alerts (default 90).
    """
    today = today or date.today()
    deadline_alerts = await _check_deadlines(session, today, deadline_days)
    renewal_alerts = await _check_renewals(session, today, renewal_window_min, renewal_window_max)
    return MonitorResult(deadline_alerts=deadline_alerts, renewal_alerts=renewal_alerts)


async def _check_deadlines(
    session: AsyncSession,
    today: date,
    deadline_days: int,
) -> list[Alert]:
    """Fire deadline alerts for open obligations due within deadline_days."""
    cutoff = today + timedelta(days=deadline_days)

    result = await session.execute(
        select(Obligation).where(
            Obligation.status == "open",
            Obligation.deadline.is_not(None),
            Obligation.deadline >= today,
            Obligation.deadline <= cutoff,
        )
    )
    obligations = list(result.scalars().all())

    alerts: list[Alert] = []
    for ob in obligations:
        days = (ob.deadline - today).days
        alert = Alert(
            contract_id=ob.contract_id,
            alert_type="deadline",
            payload={
                "obligation_id": str(ob.id),
                "commitment": ob.commitment,
                "owner": ob.owner,
                "deadline": ob.deadline.isoformat(),
                "days_until_deadline": days,
            },
        )
        alert = await obligation_repo.create_alert(session, alert)
        alerts.append(alert)
    return alerts


async def _check_renewals(
    session: AsyncSession,
    today: date,
    window_min: int,
    window_max: int,
) -> list[Alert]:
    """Fire renewal alerts for contracts expiring within [window_min, window_max] days."""
    min_date = today + timedelta(days=window_min)
    max_date = today + timedelta(days=window_max)

    stmt = (
        select(Contract, ContractMetadata)
        .join(ContractMetadata, Contract.id == ContractMetadata.contract_id)
        .where(
            ContractMetadata.expiry_date.is_not(None),
            ContractMetadata.expiry_date >= min_date,
            ContractMetadata.expiry_date <= max_date,
            # auto_renewal True or None — not explicitly False
            ContractMetadata.auto_renewal.is_not(False),
        )
    )
    rows = await session.execute(stmt)
    pairs = rows.all()

    alerts: list[Alert] = []
    for contract, meta in pairs:
        days = (meta.expiry_date - today).days
        alert = Alert(
            contract_id=contract.id,
            alert_type="renewal",
            payload={
                "expiry_date": meta.expiry_date.isoformat(),
                "auto_renewal": meta.auto_renewal,
                "days_until_expiry": days,
                "contract_title": contract.title,
            },
        )
        alert = await obligation_repo.create_alert(session, alert)
        alerts.append(alert)
    return alerts
