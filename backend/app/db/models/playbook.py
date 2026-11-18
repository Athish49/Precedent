"""Playbook header, versions, rules and rule children (task 1.2).

``Playbook`` and ``PlaybookRule`` are the existing tables, extended per
``playbook_plan.md`` sections 3.2 and 3.4. Every other class here is new:
``PlaybookVersion`` and ``PlaybookChangeLog`` (section 3.3), and the six rule
children — ``RulePosition``, ``RuleParameter``, ``RedLine``, ``RuleObjection``,
``RuleDependency`` and ``RuleTestCase`` (sections 3.5 to 3.10).

``PlaybookRule`` once carried five legacy flat columns for its negotiating
language. Migration ``011`` backfilled them into ``rule_position`` /
``red_line`` rows, and migration ``015`` (task 5.5) dropped them. Positions
and red lines are now the only source for that content.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Playbook(Base):
    """A playbook header (``playbook_plan.md`` section 3.2).

    ``practice_area`` keeps its existing name but is now backed by a foreign
    key to ``agreement_type`` instead of the five-value check constraint
    (``ck_playbook_practice_area``, dropped by migration ``011``).
    """

    __tablename__ = "playbook"
    __table_args__ = (UniqueConstraint("key", name="uq_playbook_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    practice_area: Mapped[str] = mapped_column(
        Text,
        ForeignKey("agreement_type.key", name="fk_playbook_agreement_type"),
        nullable=False,
    )
    precedence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # New columns (task 1.2). ``key`` is left nullable at the database: the
    # plan marks it "unique", not "required", and the repository function
    # that creates a Playbook does not supply it yet (task 1.4 wires that
    # up). The backfill in migration 011 still gives every existing row a
    # slug, and the unique constraint above is added only after that backfill.
    key: Mapped[str | None] = mapped_column(Text, nullable=True)
    layer: Mapped[str] = mapped_column(
        Text, nullable=False, default="agreement", server_default="agreement"
    )
    party_role: Mapped[str] = mapped_column(
        Text, nullable=False, default="vendor", server_default="vendor"
    )
    paper_scope: Mapped[str] = mapped_column(
        Text, nullable=False, default="both", server_default="both"
    )
    jurisdiction: Mapped[str] = mapped_column(
        Text, nullable=False, default="global", server_default="global"
    )
    business_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approver_role.id", name="fk_playbook_owner_role"),
        nullable=True,
    )
    parent_playbook_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook.id", name="fk_playbook_parent"),
        nullable=True,
    )
    applies_when: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default="active"
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        # `use_alter=True`: `playbook` and `playbook_version` reference each
        # other (a version's `playbook_id` and a playbook's
        # `current_version_id`). This tells SQLAlchemy's table sorter the
        # cycle is fine to resolve with a deferred ALTER, matching how the
        # migration itself adds this FK only after `playbook_version` exists.
        ForeignKey("playbook_version.id", name="fk_playbook_current_version", use_alter=True),
        nullable=True,
    )
    review_cadence_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_review_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # `onupdate` added per task 1.2 item 8: a model-level touch on update,
    # not a DB trigger (matches the pattern in app/db/models/taxonomy.py and
    # app/db/models/authority.py).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlaybookVersion(Base):
    """A snapshot of a playbook's rules (``playbook_plan.md`` section 3.3).

    Only a ``draft`` version is editable. Publishing freezes its rules and
    children, sets ``playbook.current_version_id``, and marks the previous
    version ``superseded``. A new draft is created by copying the current
    version. None of that lifecycle is implemented here; this task only
    creates the table and backfills one ``1.0`` / ``published`` version per
    existing playbook.
    """

    __tablename__ = "playbook_version"
    __table_args__ = (
        UniqueConstraint("playbook_id", "version", name="uq_playbook_version_playbook_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook.id", name="fk_playbook_version_playbook", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlaybookChangeLog(Base):
    """One row per rule-level change between versions (section 3.3)."""

    __tablename__ = "playbook_change_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playbook_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_version.id", name="fk_playbook_change_log_version", ondelete="CASCADE"),
        nullable=False,
    )
    rule_key: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(Text, nullable=False)
    field_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlaybookRule(Base):
    """One rule per issue per playbook version (``playbook_plan.md`` section 3.4).

    Negotiating language does not live on this row. The preferred position,
    fallbacks and acceptable variants are ``rule_position`` rows, and
    prohibited phrasing is rule-scoped ``red_line`` rows. Migration ``015``
    dropped the legacy flat columns that used to hold them.
    """

    __tablename__ = "playbook_rule"
    __table_args__ = (
        Index("ix_playbook_rule_playbook_clause", "playbook_id", "clause_type"),
        UniqueConstraint(
            "playbook_version_id", "rule_key", name="uq_playbook_rule_version_rule_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook.id", name="fk_playbook_rule_playbook", ondelete="CASCADE"),
        nullable=False,
    )
    clause_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clause_family.key", name="fk_playbook_rule_clause_family"),
        nullable=False,
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_weight: Mapped[float] = mapped_column(Numeric, nullable=False, default=1.0)

    # New columns (task 1.2). Nullable here: they are not required yet.
    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_version.id", name="fk_playbook_rule_version"),
        nullable=True,
    )
    issue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clause_issue.id", name="fk_playbook_rule_issue"),
        nullable=True,
    )
    rule_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    negotiable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    default_zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_human_judgment: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    judgment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_when: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    detection_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    authored_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class RulePosition(Base):
    """The ladder: preferred, fallback and acceptable-variant language
    (``playbook_plan.md`` section 3.5)."""

    __tablename__ = "rule_position"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_rule_position_rule", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    rung: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    zone: Mapped[str] = mapped_column(Text, nullable=False)
    approver_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approver_role.id", name="fk_rule_position_approver_role"),
        nullable=True,
    )
    conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    give_get: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RuleParameter(Base):
    """A structured, comparable value extracted from the clause (section 3.6)."""

    __tablename__ = "rule_parameter"
    __table_args__ = (UniqueConstraint("rule_id", "key", name="uq_rule_parameter_rule_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_rule_parameter_rule", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_value: Mapped[dict | list | str | float | int | bool | None] = mapped_column(
        JSONB, nullable=True
    )
    green_limit: Mapped[dict | list | str | float | int | bool | None] = mapped_column(
        JSONB, nullable=True
    )
    yellow_limit: Mapped[dict | list | str | float | int | bool | None] = mapped_column(
        JSONB, nullable=True
    )
    allowed_values: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extraction_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_overrides: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RedLine(Base):
    """Something never accepted without the named approval, or never at all
    (section 3.7). ``scope`` is ``rule``, ``playbook`` or ``global``; only the
    matching one of ``rule_id`` / ``playbook_id`` is set."""

    __tablename__ = "red_line"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_red_line_rule", ondelete="CASCADE"),
        nullable=True,
    )
    playbook_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook.id", name="fk_red_line_playbook"),
        nullable=True,
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition_type: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    approver_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approver_role.id", name="fk_red_line_approver_role"),
        nullable=True,
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RuleObjection(Base):
    """What the counterparty says, and how we answer (section 3.8)."""

    __tablename__ = "rule_objection"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_rule_objection_rule", ondelete="CASCADE"),
        nullable=False,
    )
    objection: Mapped[str] = mapped_column(Text, nullable=False)
    their_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    talking_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    recommended_position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rule_position.id", name="fk_rule_objection_recommended_position"),
        nullable=True,
    )
    frequency: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterparty_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RuleDependency(Base):
    """Which other rules move with this one (section 3.9)."""

    __tablename__ = "rule_dependency"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_rule_dependency_rule", ondelete="CASCADE"),
        nullable=False,
    )
    related_rule_key: Mapped[str] = mapped_column(Text, nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RuleTestCase(Base):
    """How we know the rule works (section 3.10)."""

    __tablename__ = "rule_test_case"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_rule.id", name="fk_rule_test_case_rule", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sample_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    expected_zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_position_rung: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_red_line_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_trap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
