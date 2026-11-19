"""document processing schema B: new tables and metadata columns (task 1.2)

Creates the four new tables that round out the document-processing data
model (plan section 7.3) and adds the typed projection columns and small
fixes that go with them.

**New tables**
  - ``contract_field``: one row per extracted field value, the source of
    truth fields read from. Unique on (contract_version_id, field_key,
    source); indexed on (field_key, contract_id).
  - ``contract_party``: links ``contract`` to ``party`` with a role, role
    label and entity facts. Unique on (contract_id, party_id).
  - ``contract_signatory``: one row per signature block entry.
  - ``ingest_run``: one row per ingest attempt against a contract version.

**Column additions**
  - ``party.is_own_org``: boolean, not null, default false.
  - ``clause_embedding``: unique on ``clause_id``; new ``model`` text column.
  - ``contract_metadata``: new ``contract_version_id`` plus the typed
    projection columns listed in plan section 7.3. The old untyped columns
    (``parties``, ``financial_fields``, ``milestone_dates``,
    ``liability_cap``, ``notice_period_days``, ``payment_terms``,
    ``extracted``) are **not** dropped here; task 5.2 drops them once the
    new ingest pipeline is the only writer.
  - ``contract_metadata.contract_version_id`` is backfilled immediately
    after being added, from the version 016 creates for every contract (see
    016's docstring) — same reasoning as 016's own clause backfill.

**Fixed after this migration was first written, before ever being applied
for real:** ``ingest_run`` is now created FIRST, before ``contract_field``
-- ``contract_field.ingest_run_id`` has a foreign key to ``ingest_run.id``,
so the table it references must exist first. The original ordering created
``contract_field`` before ``ingest_run`` and failed with "relation
ingest_run does not exist" the first time this migration ran against a
real database; an offline ``--sql`` render never catches this, since
Postgres only checks a ``CREATE TABLE``'s FK target at execution time.
Downgrade now drops in the exact reverse order (``contract_field`` before
``ingest_run``) for the same reason.

Nothing in ``op.*`` calls names the project schema; ``migrations/env.py``
puts it first on the search path for the duration of each migration
transaction.

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-11-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "q7r8s9t0u1v2"
down_revision: str | None = "p6q7r8s9t0u1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. ingest_run ─────────────────────────────────────────────────────
    # Created first: contract_field's ingest_run_id FK (step 2, below) needs
    # this table to already exist. (Fixed after this migration was first
    # written, before ever being applied for real: the original ordering
    # created contract_field before ingest_run, which Postgres rejected with
    # "relation ingest_run does not exist" the first time this ran against a
    # real database -- CREATE TABLE's own FK target is checked at execution
    # time, which an offline --sql render never catches.)
    op.create_table(
        "ingest_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "contract_version.id", name="fk_ingest_run_contract_version", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("processor", sa.Text(), nullable=True),
        sa.Column("processor_version", sa.Text(), nullable=True),
        sa.Column("parse_engine_version", sa.Text(), nullable=True),
        sa.Column("extend_file_id", sa.Text(), nullable=True),
        sa.Column("extend_extract_run_id", sa.Text(), nullable=True),
        sa.Column("extend_parse_run_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("credits_used", sa.Float(), nullable=True),
        sa.Column("raw_extract_key", sa.Text(), nullable=True),
        sa.Column("raw_parse_key", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="ck_ingest_run_status"
        ),
    )

    # ── 2. contract_field ─────────────────────────────────────────────────
    op.create_table(
        "contract_field",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_contract_field_contract", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contract_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "contract_version.id",
                name="fk_contract_field_contract_version",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("field_key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column(
            "clause_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clause.id", name="fk_contract_field_clause", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ingest_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "ingest_run.id", name="fk_contract_field_ingest_run", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('extract', 'derived', 'user')", name="ck_contract_field_source"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'low')",
            name="ck_contract_field_confidence",
        ),
        sa.UniqueConstraint(
            "contract_version_id",
            "field_key",
            "source",
            name="uq_contract_field_version_key_source",
        ),
    )
    op.create_index(
        "ix_contract_field_key_contract", "contract_field", ["field_key", "contract_id"]
    )

    # ── 3. contract_party ────────────────────────────────────────────────
    op.create_table(
        "contract_party",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract.id", name="fk_contract_party_contract", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "party_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("party.id", name="fk_contract_party_party", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("role_label", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("jurisdiction", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('own', 'counterparty', 'other')", name="ck_contract_party_role"
        ),
        sa.UniqueConstraint(
            "contract_id", "party_id", name="uq_contract_party_contract_party"
        ),
    )

    # ── 4. contract_signatory ────────────────────────────────────────────
    op.create_table(
        "contract_signatory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contract_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "contract_version.id",
                name="fk_contract_signatory_contract_version",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "contract_party_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "contract_party.id",
                name="fk_contract_signatory_contract_party",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("printed_name", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("is_signed", sa.Boolean(), nullable=True),
        sa.Column("signed_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── 5. party.is_own_org ──────────────────────────────────────────────
    op.add_column(
        "party",
        sa.Column("is_own_org", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ── 6. clause_embedding: unique on clause_id, new model column ───────
    op.create_unique_constraint(
        "uq_clause_embedding_clause_id", "clause_embedding", ["clause_id"]
    )
    op.add_column("clause_embedding", sa.Column("model", sa.Text(), nullable=True))

    # ── 7. contract_metadata: contract_version_id + projection columns ───
    op.add_column(
        "contract_metadata",
        sa.Column(
            "contract_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "contract_version.id",
                name="fk_contract_metadata_contract_version",
                ondelete="CASCADE",
            ),
            nullable=True,
        ),
    )
    # Backfill from the version 016 created for every contract (see that
    # migration's docstring: every contract had zero contract_version rows
    # before 016 ran, which would otherwise make 019's NULL-contract_version_id
    # deletion wipe every contract_metadata row, not just orphaned ones).
    op.execute(
        sa.text(
            "UPDATE contract_metadata cm SET contract_version_id = cv.id "
            "FROM contract_version cv "
            "WHERE cv.contract_id = cm.contract_id AND cv.version_number = 1 "
            "AND cm.contract_version_id IS NULL"
        )
    )
    op.add_column(
        "contract_metadata", sa.Column("expiry_is_derived", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "contract_metadata", sa.Column("initial_term_months", sa.Integer(), nullable=True)
    )
    op.add_column(
        "contract_metadata", sa.Column("renewal_term_months", sa.Integer(), nullable=True)
    )
    op.add_column(
        "contract_metadata", sa.Column("renewal_notice_days", sa.Integer(), nullable=True)
    )
    op.add_column(
        "contract_metadata", sa.Column("dispute_resolution", sa.Text(), nullable=True)
    )
    op.add_column(
        "contract_metadata", sa.Column("total_value_amount", sa.Numeric(), nullable=True)
    )
    op.add_column("contract_metadata", sa.Column("currency", sa.Text(), nullable=True))
    op.add_column(
        "contract_metadata", sa.Column("liability_cap_amount", sa.Numeric(), nullable=True)
    )
    op.add_column(
        "contract_metadata", sa.Column("liability_cap_basis", sa.Text(), nullable=True)
    )
    op.add_column(
        "contract_metadata", sa.Column("payment_terms_days", sa.Integer(), nullable=True)
    )
    op.add_column(
        "contract_metadata",
        sa.Column("termination_for_convenience", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "contract_metadata", sa.Column("termination_notice_days", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    # ── 7. Drop contract_metadata projection columns ─────────────────────
    op.drop_column("contract_metadata", "termination_notice_days")
    op.drop_column("contract_metadata", "termination_for_convenience")
    op.drop_column("contract_metadata", "payment_terms_days")
    op.drop_column("contract_metadata", "liability_cap_basis")
    op.drop_column("contract_metadata", "liability_cap_amount")
    op.drop_column("contract_metadata", "currency")
    op.drop_column("contract_metadata", "total_value_amount")
    op.drop_column("contract_metadata", "dispute_resolution")
    op.drop_column("contract_metadata", "renewal_notice_days")
    op.drop_column("contract_metadata", "renewal_term_months")
    op.drop_column("contract_metadata", "initial_term_months")
    op.drop_column("contract_metadata", "expiry_is_derived")
    op.drop_constraint(
        "fk_contract_metadata_contract_version", "contract_metadata", type_="foreignkey"
    )
    op.drop_column("contract_metadata", "contract_version_id")

    # ── 6. Revert clause_embedding changes ────────────────────────────────
    op.drop_column("clause_embedding", "model")
    op.drop_constraint(
        "uq_clause_embedding_clause_id", "clause_embedding", type_="unique"
    )

    # ── 5. Drop party.is_own_org ──────────────────────────────────────────
    op.drop_column("party", "is_own_org")

    # ── 4. Drop contract_signatory ──────────────────────────────────────
    op.drop_table("contract_signatory")

    # ── 3. Drop contract_party ────────────────────────────────────────────
    op.drop_table("contract_party")

    # ── 2. Drop contract_field ────────────────────────────────────────────
    # Must be dropped before ingest_run (next): contract_field's
    # ingest_run_id FK still references it. Same ordering constraint as
    # upgrade's step 1/2, in reverse (see that comment).
    op.drop_index("ix_contract_field_key_contract", table_name="contract_field")
    op.drop_table("contract_field")

    # ── 1. Drop ingest_run ─────────────────────────────────────────────────
    op.drop_table("ingest_run")
