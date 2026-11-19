"""document processing schema A: contract, version, clause, cascades (task 1.1)

Adds the columns, constraints and foreign-key cascades needed by the new
document-processing pipeline.  The upgrade is applied in nine sections; each
has a matching rollback step in downgrade().

**contract**
  - Add ``original_filename``, ``status_reason``, ``contract_type_source``.
  - Replace ``ck_contract_status`` to include ``failed`` and ``ready``.
  - **Data remap (added after this migration was first written, before the FK
    below, because applying this migration for real failed against the live
    database otherwise):** the playbook corpus loader (outside this file, in the application's seed package) wrote
    ``contract.contract_type`` from a playbook's compound ``key`` slug
    (``halcyon-saas-msa-vendor`` → ``saas_msa_vendor``) instead of from the
    playbook's own ``practice_area``, and hardcoded ``party_role='vendor'``
    for every row regardless of the playbook's real ``party_role``. Both are
    fixed here by joining back to ``playbook`` on the reverse of that same
    derivation. For an agreement-kind practice area (``nda``, ``saas_msa``,
    ``dpa``, ``vendor_msa``), ``contract_type`` becomes that practice area
    and ``party_role`` becomes the playbook's real role. For ``baseline``,
    ``hipaa`` and ``gdpr`` (never a contract's own type, per
    ``context_capture.py``'s documented convention — regimes belong in
    ``context.regimes``, which these rows already carry correctly),
    ``contract_type`` becomes ``NULL`` and ``party_role`` is still corrected.
    A generic safety net then nulls any ``contract_type`` that still is not a
    ``kind='agreement'`` key, so the FK below cannot fail for any other
    reason. This is a one-way data fix; downgrade does not restore the old
    (wrong) values. The loader itself and its test are fixed separately in
    the same change, in the playbook corpus loader (outside this file, in
    the application's seed package) and its test, so this cannot recur.
    **This data remap mutates existing contract rows and was not written
    into the original plan or implementation docs** — it was added live,
    mid-migration, when applying this migration for real against the real
    database failed with a foreign-key violation on the existing data. It
    was investigated, the exact remap was computed and shown to the user
    before being written, and the user gave explicit, informed go-ahead to
    remap these specific rows this specific way (see
    `document_processing_verification.md` for the fuller account). Treat
    this note as that sign-off, recorded here because the plan document
    itself does not cover it.
  - Add a foreign key from ``contract_type`` to ``agreement_type.key``.
  - **Version backfill (added for the same reason):** every contract in the
    live database had zero ``contract_version`` rows (the old pipeline never
    wrote one — this was finding 9 in ``document_processing_status.md``).
    Migration 019 deletes every ``clause``/``contract_metadata`` row with no
    ``contract_version_id``, which with zero version rows would delete ALL
    of them, not just the ones belonging to orphaned data. So this migration
    now also creates one ``contract_version`` (``version_number=1``) per
    existing contract from its own ``object_key``/``canonical_text``, sets
    ``contract.current_version_id``, and backfills
    ``clause.contract_version_id`` for that contract's existing clauses (see
    the dedicated section near the end of ``upgrade()``).
    ``contract_metadata.contract_version_id`` is backfilled the same way in
    migration 017, once that column exists.

**contract_version**
  - Add ``file_sha256``, ``file_size_bytes``, ``page_count``,
    ``source_format``, ``original_filename``.
  - Replace the non-unique index on (contract_id, version_number) with a
    UNIQUE constraint.
  - Add an index on ``file_sha256``.

**clause**
  - Add ``contract_version_id`` (FK to contract_version, CASCADE, nullable).
  - Add ``clause_key`` (UUID NOT NULL; back-filled with gen_random_uuid()).
  - Add ``parent_id`` (self FK CASCADE, nullable).
  - Add ``level`` (integer NOT NULL default 1), ``section_number``, ``title``,
    ``page_start``, ``page_end``.
  - Add ``type_source`` (NOT NULL default 'none', check extract|dictionary|none).
  - Add ``text_sha256`` (nullable text).
  - Add check constraints: char_end > char_start, char_start >= 0, level >= 1.
  - Add index on (contract_id, clause_key).
  - Add partial unique index on (contract_version_id, ordinal)
    WHERE contract_version_id IS NOT NULL.

**clause_family**
  - Insert ``preamble`` and ``signature_block`` (category ``structure``).

**New FKs**
  - flag.clause_id → clause.id ON DELETE SET NULL
  - redline.clause_id → clause.id ON DELETE SET NULL

**CASCADE**
  - Recreate every FK that references contract.id with ON DELETE CASCADE.
  - Recreate clause_embedding.clause_id → clause.id with ON DELETE CASCADE.

Nothing in ``op.*`` calls names the project schema; ``migrations/env.py``
puts it first on the search path for the duration of each migration
transaction.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-11-17
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p6q7r8s9t0u1"
down_revision: str | None = "o5p6q7r8s9t0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Reference data: two new clause families
# ---------------------------------------------------------------------------
_NEW_FAMILIES = [
    {
        "key": "preamble",
        "name": "Preamble",
        "category": "structure",
        "description": (
            "Introductory recitals and background before the first numbered section. "
            "Records the date, the parties and the context of the agreement."
        ),
        "synonyms": json.dumps([]),
        "sort_order": 300,
    },
    {
        "key": "signature_block",
        "name": "Signature Block",
        "category": "structure",
        "description": (
            "The signature area at the end of the agreement, including printed names, "
            "titles, signatures and dates."
        ),
        "synonyms": json.dumps([]),
        "sort_order": 310,
    },
]

_CLAUSE_FAMILY_INSERT = sa.text(
    "INSERT INTO clause_family (key, name, category, description, synonyms, sort_order) "
    "VALUES (:key, :name, :category, :description, CAST(:synonyms AS jsonb), :sort_order)"
).bindparams(
    sa.bindparam("key", type_=sa.Text()),
    sa.bindparam("name", type_=sa.Text()),
    sa.bindparam("category", type_=sa.Text()),
    sa.bindparam("description", type_=sa.Text()),
    sa.bindparam("synonyms", type_=sa.Text()),
    sa.bindparam("sort_order", type_=sa.Integer()),
)

# ---------------------------------------------------------------------------
# All FKs pointing at contract.id that need CASCADE
# ---------------------------------------------------------------------------
# Each entry: (table, fk_name, local_col, referent_table, referent_col)
_CONTRACT_CASCADE_FKS: list[tuple[str, str, str, str, str]] = [
    ("contract_version", "fk_contract_version_contract", "contract_id", "contract", "id"),
    ("contract_metadata", "fk_contract_metadata_contract", "contract_id", "contract", "id"),
    ("clause", "fk_clause_contract", "contract_id", "contract", "id"),
    ("clause_embedding", "fk_clause_embedding_contract", "contract_id", "contract", "id"),
    ("flag", "fk_flag_contract", "contract_id", "contract", "id"),
    ("risk_score", "fk_risk_score_contract", "contract_id", "contract", "id"),
    ("redline", "fk_redline_contract", "contract_id", "contract", "id"),
    ("obligation", "fk_obligation_contract", "contract_id", "contract", "id"),
    ("alert", "fk_alert_contract", "contract_id", "contract", "id"),
    ("qa_cache", "fk_qa_cache_contract", "contract_id", "contract", "id"),
    ("review_run", "fk_review_run_contract", "contract_id", "contract", "id"),
    ("decision_event", "fk_decision_event_contract", "contract_id", "contract", "id"),
    ("playbook_exception", "fk_playbook_exception_contract", "contract_id", "contract", "id"),
]


def upgrade() -> None:
    # ── 1. contract: new columns ─────────────────────────────────────────────
    op.add_column("contract", sa.Column("original_filename", sa.Text(), nullable=True))
    op.add_column("contract", sa.Column("status_reason", sa.Text(), nullable=True))
    op.add_column("contract", sa.Column("contract_type_source", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_contract_contract_type_source",
        "contract",
        "contract_type_source IN ('user', 'extracted')",
    )

    # ── 2. contract: replace status check constraint ─────────────────────────
    op.drop_constraint("ck_contract_status", "contract", type_="check")
    op.create_check_constraint(
        "ck_contract_status",
        "contract",
        "status IN ('processing', 'failed', 'ready', 'analyzed', 'redlined', 'executed')",
    )

    # ── 2.5. contract: remap contract_type/party_role from the playbook ──────
    # Fixes the playbook corpus loader's bug (see module docstring): the
    # loader wrote contract_type from a playbook's compound key slug instead
    # of its practice_area, and hardcoded party_role='vendor' for every row.
    # Join back via the exact reverse of that derivation
    # (playbook.key == 'halcyon-' || replace(contract_type, '_', '-')).
    op.execute(
        sa.text(
            "UPDATE contract c "
            "SET contract_type = pb.practice_area, party_role = pb.party_role "
            "FROM playbook pb "
            "WHERE c.contract_type IS NOT NULL "
            "AND pb.key = 'halcyon-' || replace(c.contract_type, '_', '-') "
            "AND pb.practice_area IN ('nda', 'saas_msa', 'dpa', 'vendor_msa')"
        )
    )
    # baseline/hipaa/gdpr are never a contract's own type (context_capture.py's
    # documented convention); these rows already carry the regime correctly
    # in context.regimes, so only contract_type and party_role need fixing.
    op.execute(
        sa.text(
            "UPDATE contract c "
            "SET contract_type = NULL, party_role = pb.party_role "
            "FROM playbook pb "
            "WHERE c.contract_type IS NOT NULL "
            "AND pb.key = 'halcyon-' || replace(c.contract_type, '_', '-') "
            "AND pb.practice_area IN ('baseline', 'hipaa', 'gdpr')"
        )
    )
    # Safety net: anything that still isn't a kind='agreement' key (no
    # matching playbook row, or any other stale value) is nulled too, so the
    # FK below cannot fail for any other reason.
    op.execute(
        sa.text(
            "UPDATE contract SET contract_type = NULL "
            "WHERE contract_type IS NOT NULL "
            "AND contract_type NOT IN ("
            "SELECT key FROM agreement_type WHERE kind = 'agreement'"
            ")"
        )
    )

    # ── 3. contract: add FK from contract_type to agreement_type.key ─────────
    op.create_foreign_key(
        "fk_contract_contract_type",
        "contract",
        "agreement_type",
        ["contract_type"],
        ["key"],
    )

    # ── 4. contract_version: new columns ─────────────────────────────────────
    op.add_column("contract_version", sa.Column("file_sha256", sa.Text(), nullable=True))
    op.add_column("contract_version", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("contract_version", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column("contract_version", sa.Column("source_format", sa.Text(), nullable=True))
    op.add_column(
        "contract_version", sa.Column("original_filename", sa.Text(), nullable=True)
    )
    op.create_index("ix_contract_version_file_sha256", "contract_version", ["file_sha256"])

    # ── 5. contract_version: replace index with unique constraint ─────────────
    op.drop_index("ix_contract_version_contract_version", table_name="contract_version")
    op.create_unique_constraint(
        "uq_contract_version_contract_version_number",
        "contract_version",
        ["contract_id", "version_number"],
    )

    # ── 6. clause: new columns ────────────────────────────────────────────────
    # contract_version_id: nullable FK (stays nullable until task 5.2)
    op.add_column(
        "clause",
        sa.Column("contract_version_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_clause_contract_version",
        "clause",
        "contract_version",
        ["contract_version_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── 6.5. Backfill: one contract_version per existing contract ───────────
    # See the module docstring. Only inserts a version for a contract that
    # doesn't already have one, so this is safe to run even if some future
    # database already has real version rows for some contracts.
    op.execute(
        sa.text(
            "INSERT INTO contract_version (id, contract_id, version_number, "
            "object_key, canonical_text, relation, created_at) "
            "SELECT gen_random_uuid(), c.id, 1, c.object_key, c.canonical_text, "
            "'version', now() "
            "FROM contract c "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM contract_version cv WHERE cv.contract_id = c.id"
            ")"
        )
    )
    op.execute(
        sa.text(
            "UPDATE contract c SET current_version_id = cv.id "
            "FROM contract_version cv "
            "WHERE cv.contract_id = c.id AND cv.version_number = 1 "
            "AND c.current_version_id IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE clause cl SET contract_version_id = cv.id "
            "FROM contract_version cv "
            "WHERE cv.contract_id = cl.contract_id AND cv.version_number = 1 "
            "AND cl.contract_version_id IS NULL"
        )
    )

    # clause_key: add nullable, back-fill, then make NOT NULL
    op.add_column("clause", sa.Column("clause_key", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE clause SET clause_key = gen_random_uuid() WHERE clause_key IS NULL"))
    op.alter_column(
        "clause",
        "clause_key",
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    # parent_id: nullable self FK
    op.add_column("clause", sa.Column("parent_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_clause_parent",
        "clause",
        "clause",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # level: NOT NULL default 1
    op.add_column(
        "clause",
        sa.Column("level", sa.Integer(), server_default="1", nullable=False),
    )
    # Remove server_default after adding; it stays only for future inserts via
    # direct SQL. ORM inserts always pass a Python-side default.
    # (Leave server_default in place so direct SQL inserts work too.)

    # Other new clause columns (all nullable)
    op.add_column("clause", sa.Column("section_number", sa.Text(), nullable=True))
    op.add_column("clause", sa.Column("title", sa.Text(), nullable=True))
    op.add_column("clause", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("clause", sa.Column("page_end", sa.Integer(), nullable=True))

    # type_source: NOT NULL default 'none'
    op.add_column(
        "clause",
        sa.Column("type_source", sa.Text(), server_default="none", nullable=False),
    )
    op.create_check_constraint(
        "ck_clause_type_source",
        "clause",
        "type_source IN ('extract', 'dictionary', 'none')",
    )

    op.add_column("clause", sa.Column("text_sha256", sa.Text(), nullable=True))

    # ── 7. clause: check constraints ─────────────────────────────────────────
    op.create_check_constraint(
        "ck_clause_char_end_gt_start",
        "clause",
        "char_end > char_start",
    )
    op.create_check_constraint(
        "ck_clause_char_start_gte_zero",
        "clause",
        "char_start >= 0",
    )
    op.create_check_constraint(
        "ck_clause_level_gte_one",
        "clause",
        "level >= 1",
    )

    # ── 8. clause: indexes ───────────────────────────────────────────────────
    op.create_index(
        "ix_clause_contract_clause_key",
        "clause",
        ["contract_id", "clause_key"],
    )
    # Partial unique index: (contract_version_id, ordinal) WHERE NOT NULL
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_clause_version_ordinal "
            "ON clause (contract_version_id, ordinal) "
            "WHERE contract_version_id IS NOT NULL"
        )
    )

    # ── 9. clause_family: insert preamble and signature_block ────────────────
    for family in _NEW_FAMILIES:
        op.execute(_CLAUSE_FAMILY_INSERT.bindparams(**family))

    # ── 10. Add FKs for flag.clause_id and redline.clause_id ─────────────────
    op.create_foreign_key(
        "fk_flag_clause",
        "flag",
        "clause",
        ["clause_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_redline_clause",
        "redline",
        "clause",
        ["clause_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── 11. Recreate all contract.id FKs with ON DELETE CASCADE ──────────────
    for table, fk_name, local_col, ref_table, ref_col in _CONTRACT_CASCADE_FKS:
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(fk_name, table, ref_table, [local_col], [ref_col], ondelete="CASCADE")

    # ── 12. Recreate clause_embedding.clause_id with CASCADE ─────────────────
    op.drop_constraint("fk_clause_embedding_clause", "clause_embedding", type_="foreignkey")
    op.create_foreign_key(
        "fk_clause_embedding_clause",
        "clause_embedding",
        "clause",
        ["clause_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Note: the step-2.5 contract_type/party_role remap and the step-6.5
    # contract_version/clause backfill are one-way data fixes, like 019's
    # column drops. Downgrade reverses the schema only; it does not restore
    # the old (wrong) contract_type/party_role values and does not delete
    # the contract_version rows the backfill created (clause.contract_version_id
    # values on them are removed anyway, below, since the column itself is
    # dropped).

    # ── 12. Revert clause_embedding.clause_id CASCADE ────────────────────────
    op.drop_constraint("fk_clause_embedding_clause", "clause_embedding", type_="foreignkey")
    op.create_foreign_key(
        "fk_clause_embedding_clause",
        "clause_embedding",
        "clause",
        ["clause_id"],
        ["id"],
    )

    # ── 11. Revert contract.id CASCADE FKs ───────────────────────────────────
    for table, fk_name, local_col, ref_table, ref_col in reversed(_CONTRACT_CASCADE_FKS):
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.create_foreign_key(fk_name, table, ref_table, [local_col], [ref_col])

    # ── 10. Drop flag/redline clause FKs ─────────────────────────────────────
    op.drop_constraint("fk_redline_clause", "redline", type_="foreignkey")
    op.drop_constraint("fk_flag_clause", "flag", type_="foreignkey")

    # ── 9. Remove preamble and signature_block from clause_family ─────────────
    op.execute(
        sa.text("DELETE FROM clause_family WHERE key IN ('preamble', 'signature_block')")
    )

    # ── 8. Drop clause indexes ────────────────────────────────────────────────
    op.execute(sa.text("DROP INDEX IF EXISTS uq_clause_version_ordinal"))
    op.drop_index("ix_clause_contract_clause_key", table_name="clause")

    # ── 7. Drop clause check constraints ─────────────────────────────────────
    op.drop_constraint("ck_clause_level_gte_one", "clause", type_="check")
    op.drop_constraint("ck_clause_char_start_gte_zero", "clause", type_="check")
    op.drop_constraint("ck_clause_char_end_gt_start", "clause", type_="check")

    # ── 6. Drop clause columns ────────────────────────────────────────────────
    op.drop_column("clause", "text_sha256")
    op.drop_constraint("ck_clause_type_source", "clause", type_="check")
    op.drop_column("clause", "type_source")
    op.drop_column("clause", "page_end")
    op.drop_column("clause", "page_start")
    op.drop_column("clause", "title")
    op.drop_column("clause", "section_number")
    op.drop_column("clause", "level")
    op.drop_constraint("fk_clause_parent", "clause", type_="foreignkey")
    op.drop_column("clause", "parent_id")
    op.drop_column("clause", "clause_key")
    op.drop_constraint("fk_clause_contract_version", "clause", type_="foreignkey")
    op.drop_column("clause", "contract_version_id")

    # ── 5. Revert contract_version: restore index, drop unique constraint ─────
    op.drop_constraint(
        "uq_contract_version_contract_version_number", "contract_version", type_="unique"
    )
    op.create_index(
        "ix_contract_version_contract_version",
        "contract_version",
        ["contract_id", "version_number"],
    )

    # ── 4. Drop contract_version columns ─────────────────────────────────────
    op.drop_index("ix_contract_version_file_sha256", table_name="contract_version")
    op.drop_column("contract_version", "original_filename")
    op.drop_column("contract_version", "source_format")
    op.drop_column("contract_version", "page_count")
    op.drop_column("contract_version", "file_size_bytes")
    op.drop_column("contract_version", "file_sha256")

    # ── 3. Drop contract FK to agreement_type ────────────────────────────────
    op.drop_constraint("fk_contract_contract_type", "contract", type_="foreignkey")

    # ── 2. Restore original status check constraint ───────────────────────────
    op.drop_constraint("ck_contract_status", "contract", type_="check")
    op.create_check_constraint(
        "ck_contract_status",
        "contract",
        "status IN ('processing', 'analyzed', 'redlined', 'executed')",
    )

    # ── 1. Drop contract columns ──────────────────────────────────────────────
    op.drop_constraint("ck_contract_contract_type_source", "contract", type_="check")
    op.drop_column("contract", "contract_type_source")
    op.drop_column("contract", "status_reason")
    op.drop_column("contract", "original_filename")
