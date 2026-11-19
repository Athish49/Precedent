from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DecisionEvent(Base):
    """Append-only log of negotiation decisions.

    Patterns are computed at read time via the ``counterparty_pattern`` SQL view
    (not a maintained table).  Do not UPDATE rows — append new events instead
    (the view uses ORDER BY created_at DESC to pick the latest final_text).
    """

    __tablename__ = "decision_event"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('pending','accepted','rejected','countered')",
            name="ck_decision_event_outcome",
        ),
        Index("ix_decision_event_counterparty_clause", "counterparty_id", "clause_type"),
        Index("ix_decision_event_contract_id", "contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contract.id", name="fk_decision_event_contract", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable (task 4.6): a redline can be generated before a counterparty
    # is known (e.g. drafting from a template). Writing a zero/nil UUID
    # placeholder here was the bug task 1.3's agent flagged; the column is
    # widened to actually allow NULL (migration 013) instead.
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("party.id", name="fk_decision_event_party"),
        nullable=True,
    )
    clause_type: Mapped[str] = mapped_column(Text, nullable=False)
    position_offered: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_stance: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # New columns (task 1.3; plan section 4). Nullable; nothing populates
    # them yet — the redline/negotiation features (task 4.6 and later) do.
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_decision_event_rule"),
        nullable=True,
    )
    rule_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rule_position.id", name="fk_decision_event_position"),
        nullable=True,
    )
    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_version.id", name="fk_decision_event_playbook_version"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
