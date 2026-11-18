"""playbook lookups: agreement types, clause taxonomy, context and authority (task 1.1)

Creates the lookup and authority tables the playbook data model depends on:
``agreement_type``, ``clause_family``, ``clause_issue``, ``context_dimension``,
``approver_role`` and ``escalation_policy`` (``playbook_plan.md`` sections 3.1,
3.2, 3.11, 3.12).

Only ``agreement_type`` (7 rows) and ``clause_family`` (29 rows) get literal
data here: they are reference data the document pipeline depends on, so they
must never depend on the seed folder (``playbook_implementation.md`` section
3.0 rule 5). ``clause_issue``, ``context_dimension``, ``approver_role`` and
``escalation_policy`` are company content; their rows are loaded later by the
seed loader (task 2.1) from ``taxonomy.yaml`` and ``authority.yaml``.

Like every migration, this one does not name the project schema in
``op.create_table`` / ``op.bulk_insert`` calls: the migration environment
puts the project schema first on the search path for the duration of the
migration transaction (``migrations/env.py``), so unqualified names resolve
there.

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-11-16
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j0k1l2m3n4o5"
down_revision: str | None = "i9j0k1l2m3n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Literal reference data
# ---------------------------------------------------------------------------
# The seven agreement types (``playbook_plan.md`` section 3.2; headers table
# in ``playbook_implementation.md`` section 3.3-3.12).
_AGREEMENT_TYPES: list[dict[str, str]] = [
    {"key": "baseline", "name": "Baseline", "kind": "baseline"},
    {"key": "nda", "name": "Mutual NDA", "kind": "agreement"},
    {"key": "saas_msa", "name": "SaaS Master Subscription Agreement", "kind": "agreement"},
    {"key": "dpa", "name": "Data Processing Agreement", "kind": "agreement"},
    {"key": "vendor_msa", "name": "Vendor Master Services Agreement", "kind": "agreement"},
    {"key": "hipaa", "name": "HIPAA Overlay", "kind": "regime"},
    {"key": "gdpr", "name": "GDPR Overlay", "kind": "regime"},
]

# The 29 clause families: the 20 canonical types carried over from
# ``_SYNONYMS`` in ``app/services/document_processing/clause_types.py``
# (that module is not changed here; task 5.5 retires it), plus ``other``,
# plus the eight new families named in task 1.1. Every family has at least
# four heading synonyms and no synonym is reused across two families.
_CLAUSE_FAMILIES: list[dict[str, object]] = [
    {
        "key": "indemnification",
        "name": "Indemnification",
        "category": "risk_allocation",
        "description": (
            "Indemnification obligations under which one party compensates the other for "
            "specified third-party claims, losses or damages. Covers which claims are covered, "
            "the indemnification procedure and any limits on the obligation."
        ),
        "synonyms": [
            "indemnification",
            "indemnity",
            "hold harmless",
            "indemnification and hold harmless",
            "indemnity and hold harmless",
        ],
        "sort_order": 10,
    },
    {
        "key": "limitation_of_liability",
        "name": "Limitation of Liability",
        "category": "risk_allocation",
        "description": (
            "Caps each party's maximum financial exposure under the agreement, usually "
            "expressed as a multiple or period of fees. Covers the cap amount, carve-outs from "
            "the cap and treatment of consequential damages."
        ),
        "synonyms": [
            "limitation of liability",
            "liability cap",
            "liability limitation",
            "limitation on liability",
            "cap on liability",
        ],
        "sort_order": 20,
    },
    {
        "key": "termination",
        "name": "Termination",
        "category": "term_and_exit",
        "description": (
            "Sets out when and how either party may end the agreement, whether for cause, "
            "convenience or at the end of the term. Covers notice periods, cure periods and the "
            "effect of termination on the parties' obligations."
        ),
        "synonyms": [
            "termination",
            "termination for cause",
            "termination for convenience",
            "term and termination",
            "termination rights",
        ],
        "sort_order": 30,
    },
    {
        "key": "confidentiality",
        "name": "Confidentiality",
        "category": "boilerplate",
        "description": (
            "Obligates each party to protect the other's confidential information and "
            "restrict its use and disclosure. Covers the standard of care, permitted "
            "disclosures, exceptions and survival after termination."
        ),
        "synonyms": [
            "confidentiality",
            "non-disclosure",
            "nondisclosure",
            "confidential information",
            "nda",
            "non disclosure",
            "confidentiality and non-disclosure",
        ],
        "sort_order": 40,
    },
    {
        "key": "intellectual_property",
        "name": "Intellectual Property",
        "category": "risk_allocation",
        "description": (
            "Establishes which party owns intellectual property created or used under the "
            "agreement and what rights the other receives. Covers pre-existing IP, work "
            "product, licenses and feedback."
        ),
        "synonyms": [
            "intellectual property",
            "ip ownership",
            "ip rights",
            "ownership of ip",
            "work product",
            "intellectual property rights",
            "ownership of intellectual property",
        ],
        "sort_order": 50,
    },
    {
        "key": "governing_law",
        "name": "Governing Law",
        "category": "boilerplate",
        "description": (
            "Fixes which jurisdiction's law governs the agreement and where disputes may be "
            "brought. Covers the choice of law and the venue for litigation or other "
            "proceedings."
        ),
        "synonyms": [
            "governing law",
            "choice of law",
            "jurisdiction",
            "applicable law",
            "governing law and jurisdiction",
            "choice of law and jurisdiction",
        ],
        "sort_order": 60,
    },
    {
        "key": "dispute_resolution",
        "name": "Dispute Resolution",
        "category": "boilerplate",
        "description": (
            "Describes the process the parties must follow to resolve a dispute before or "
            "instead of litigation. Covers escalation steps, negotiation periods and any "
            "arbitration or mediation requirement."
        ),
        "synonyms": [
            "dispute resolution",
            "arbitration",
            "mediation",
            "disputes",
            "resolution of disputes",
            "dispute resolution and arbitration",
        ],
        "sort_order": 70,
    },
    {
        "key": "payment",
        "name": "Payment",
        "category": "commercial",
        "description": (
            "Sets the fees payable under the agreement and the terms on which they are "
            "invoiced and paid. Covers payment timing, late fees, price increases and taxes."
        ),
        "synonyms": [
            "payment",
            "fees",
            "compensation",
            "payment terms",
            "pricing",
            "invoicing",
            "fees and payment",
            "payment and invoicing",
        ],
        "sort_order": 80,
    },
    {
        "key": "warranties",
        "name": "Warranties",
        "category": "risk_allocation",
        "description": (
            "States the promises each party makes about its performance, authority or the "
            "condition of what it provides. Covers the scope of the warranty, disclaimers and "
            "the remedy for a breach of warranty."
        ),
        "synonyms": [
            "warranties",
            "representations and warranties",
            "representations",
            "warranty",
            "warranties and representations",
        ],
        "sort_order": 90,
    },
    {
        "key": "force_majeure",
        "name": "Force Majeure",
        "category": "boilerplate",
        "description": (
            "Excuses a party's performance when prevented by events beyond its reasonable "
            "control. Covers which events qualify, the notice required and the effect on the "
            "agreement if the event continues."
        ),
        "synonyms": [
            "force majeure",
            "acts of god",
            "force majeure events",
            "force majeure and acts of god",
        ],
        "sort_order": 100,
    },
    {
        "key": "assignment",
        "name": "Assignment",
        "category": "boilerplate",
        "description": (
            "Restricts a party's ability to transfer its rights or obligations under the "
            "agreement to a third party. Covers consent requirements and any exception for a "
            "change of control or corporate reorganization."
        ),
        "synonyms": [
            "assignment",
            "assignment and delegation",
            "transfer of rights",
            "assignment of rights",
        ],
        "sort_order": 110,
    },
    {
        "key": "entire_agreement",
        "name": "Entire Agreement",
        "category": "boilerplate",
        "description": (
            "States that the written agreement is the parties' complete understanding and "
            "supersedes prior discussions. Covers integration of referenced documents and the "
            "order of precedence between them."
        ),
        "synonyms": [
            "entire agreement",
            "integration",
            "merger clause",
            "entire understanding",
            "entire agreement and integration",
        ],
        "sort_order": 120,
    },
    {
        "key": "amendment",
        "name": "Amendment",
        "category": "boilerplate",
        "description": (
            "Sets the process required to change the agreement after signing. Covers the form "
            "an amendment must take and who must approve it."
        ),
        "synonyms": [
            "amendment",
            "modification",
            "changes to agreement",
            "amendments and modifications",
            "modifications to agreement",
        ],
        "sort_order": 130,
    },
    {
        "key": "notices",
        "name": "Notices",
        "category": "boilerplate",
        "description": (
            "Specifies how formal notices between the parties must be delivered and when they "
            "are deemed received. Covers permitted delivery methods, addresses and timing."
        ),
        "synonyms": [
            "notices",
            "notice requirements",
            "notice",
            "notice provisions",
            "notices and communications",
        ],
        "sort_order": 140,
    },
    {
        "key": "definitions",
        "name": "Definitions",
        "category": "boilerplate",
        "description": (
            "Defines the key terms used throughout the agreement so they carry a fixed, agreed "
            "meaning. Covers how defined terms are interpreted and cross-referenced."
        ),
        "synonyms": [
            "definitions",
            "defined terms",
            "interpretation",
            "definitions and interpretation",
        ],
        "sort_order": 150,
    },
    {
        "key": "term",
        "name": "Term",
        "category": "term_and_exit",
        "description": (
            "Sets the length of the agreement and the conditions, if any, for renewal. Covers "
            "the initial term, renewal terms and any notice needed to prevent renewal."
        ),
        "synonyms": [
            "term",
            "duration",
            "agreement term",
            "term of agreement",
        ],
        "sort_order": 160,
    },
    {
        "key": "compliance",
        "name": "Compliance",
        "category": "boilerplate",
        "description": (
            "Requires each party to comply with applicable laws and regulations in performing "
            "the agreement. Covers the scope of the compliance obligation and any specific "
            "regulatory regime referenced."
        ),
        "synonyms": [
            "compliance",
            "compliance with laws",
            "regulatory compliance",
            "compliance with applicable laws",
        ],
        "sort_order": 170,
    },
    {
        "key": "data_protection",
        "name": "Data Protection",
        "category": "data_and_security",
        "description": (
            "Governs how personal data or protected health information is processed under the "
            "agreement. Covers processing instructions, data subject rights and data handling "
            "obligations such as return or deletion."
        ),
        "synonyms": [
            "data protection",
            "data processing",
            "privacy",
            "data privacy",
            "gdpr",
            "hipaa",
            "data protection and privacy",
            "data processing agreement",
        ],
        "sort_order": 180,
    },
    {
        "key": "audit",
        "name": "Audit",
        "category": "data_and_security",
        "description": (
            "Gives one party the right to verify the other's compliance with the agreement "
            "through inspection or audit. Covers audit frequency, notice, scope and who bears "
            "the cost."
        ),
        "synonyms": [
            "audit",
            "audit rights",
            "inspection",
            "audit and inspection",
            "right to audit",
        ],
        "sort_order": 190,
    },
    {
        "key": "insurance",
        "name": "Insurance",
        "category": "risk_allocation",
        "description": (
            "Requires a party to maintain specified types and levels of insurance during the "
            "agreement. Covers coverage requirements, evidence of insurance and any requirement "
            "to name the other party as an additional insured."
        ),
        "synonyms": [
            "insurance",
            "insurance requirements",
            "insurance coverage",
            "certificate of insurance",
            "insurance evidence",
        ],
        "sort_order": 200,
    },
    {
        "key": "other",
        "name": "Other",
        "category": "boilerplate",
        "description": (
            "Catches headings that do not match any other defined clause family. Used when a "
            "clause's content does not correspond to a recognized canonical type."
        ),
        "synonyms": [
            "miscellaneous",
            "general provisions",
            "other terms",
            "additional provisions",
        ],
        "sort_order": 210,
    },
    # Eight new families (task 1.1).
    {
        "key": "service_levels",
        "name": "Service Levels",
        "category": "commercial",
        "description": (
            "Governs the vendor's commitments on system availability, performance and service "
            "credits for shortfalls. Covers uptime percentages, measurement windows and the "
            "customer's remedy when commitments are missed."
        ),
        "synonyms": [
            "service level agreement",
            "service levels",
            "sla",
            "uptime commitment",
            "service credits",
            "availability commitment",
        ],
        "sort_order": 220,
    },
    {
        "key": "security",
        "name": "Security",
        "category": "data_and_security",
        "description": (
            "Describes the technical and organizational security measures the vendor maintains "
            "to protect systems and data, including relevant certifications. Covers security "
            "program scope, control standards and evidence provided to the customer."
        ),
        "synonyms": [
            "security",
            "information security",
            "security program",
            "security measures",
            "data security",
            "security requirements",
        ],
        "sort_order": 230,
    },
    {
        "key": "subprocessors",
        "name": "Subprocessors",
        "category": "data_and_security",
        "description": (
            "Covers the processor's use of subprocessors to handle personal data or PHI on its "
            "behalf, including notice, objection rights and flow-down obligations. Addresses "
            "how subprocessor changes are authorized and communicated."
        ),
        "synonyms": [
            "subprocessors",
            "sub-processors",
            "subcontractors",
            "third-party processors",
            "subprocessor authorization",
            "use of subprocessors",
        ],
        "sort_order": 240,
    },
    {
        "key": "breach_notification",
        "name": "Breach Notification",
        "category": "data_and_security",
        "description": (
            "Sets the timeline and content required when a party must notify the other of a "
            "security incident or data breach. Covers the trigger for notice, the deadline and "
            "what information the notice must contain."
        ),
        "synonyms": [
            "breach notification",
            "security breach notification",
            "incident notification",
            "data breach notification",
            "notification of breach",
            "security incident reporting",
        ],
        "sort_order": 250,
    },
    {
        "key": "data_transfers",
        "name": "Data Transfers",
        "category": "data_and_security",
        "description": (
            "Addresses the mechanism used to transfer personal data across borders and any "
            "requirement to keep data within a named region. Covers transfer safeguards such as "
            "standard contractual clauses and data residency commitments."
        ),
        "synonyms": [
            "data transfers",
            "cross-border data transfers",
            "international data transfers",
            "transfer mechanism",
            "data residency",
            "data localization",
        ],
        "sort_order": 260,
    },
    {
        "key": "publicity",
        "name": "Publicity",
        "category": "commercial",
        "description": (
            "Governs whether and how a party may refer to the other publicly, including use of "
            "name, logo and performance data in marketing. Covers consent requirements and any "
            "restriction on publicizing the relationship."
        ),
        "synonyms": [
            "publicity",
            "external announcements",
            "use of name and logo",
            "press releases",
            "marketing references",
            "customer references",
        ],
        "sort_order": 270,
    },
    {
        "key": "non_solicitation",
        "name": "Non-Solicitation",
        "category": "boilerplate",
        "description": (
            "Restricts a party from soliciting or hiring the other party's employees during "
            "and after the relationship. Covers the scope of the restriction, its duration and "
            "any carve-outs for general advertising or unsolicited applications."
        ),
        "synonyms": [
            "non-solicitation",
            "non solicitation",
            "employee non-solicit",
            "no-hire",
            "non-solicitation of employees",
            "solicitation restrictions",
        ],
        "sort_order": 280,
    },
    {
        "key": "suspension",
        "name": "Suspension",
        "category": "term_and_exit",
        "description": (
            "Covers the vendor's right to suspend the customer's access to the service, "
            "typically for non-payment or security risk, short of full termination. Addresses "
            "the grounds for suspension, notice and restoration of service."
        ),
        "synonyms": [
            "suspension",
            "suspension of services",
            "right to suspend",
            "service suspension",
            "suspension rights",
            "temporary suspension",
        ],
        "sort_order": 290,
    },
]

assert len(_AGREEMENT_TYPES) == 7
assert len(_CLAUSE_FAMILIES) == 29

# No synonym may map to two families (checked here as well as by hand; a
# second check also guards the data if this file is ever edited).
_seen_synonyms: dict[str, str] = {}
for _family in _CLAUSE_FAMILIES:
    assert len(_family["synonyms"]) >= 4, f"{_family['key']} needs at least 4 synonyms"
    for _syn in _family["synonyms"]:
        _owner = _seen_synonyms.get(_syn)
        assert _owner is None, f"synonym {_syn!r} used by both {_owner!r} and {_family['key']!r}"
        _seen_synonyms[_syn] = _family["key"]


def upgrade() -> None:
    op.create_table(
        "agreement_type",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_agreement_type"),
    )

    op.create_table(
        "clause_family",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("synonyms", postgresql.JSONB(), nullable=False),
        sa.Column("external_refs", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_clause_family"),
    )

    op.create_table(
        "clause_issue",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("family_key", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("detection_hints", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["family_key"], ["clause_family.key"], name="fk_clause_issue_family"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clause_issue"),
        sa.UniqueConstraint("family_key", "key", name="uq_clause_issue_family_key"),
    )

    op.create_table(
        "context_dimension",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("values", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_context_dimension"),
    )

    op.create_table(
        "approver_role",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("function", sa.Text(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("default_sla_hours", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approver_role"),
        sa.UniqueConstraint("key", name="uq_approver_role_key"),
    )

    op.create_table(
        "escalation_policy",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=True),
        sa.Column("clause_type", sa.Text(), nullable=True),
        sa.Column("zone", sa.Text(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), nullable=True),
        sa.Column("approver_role_id", sa.UUID(), nullable=False),
        sa.Column("consult_role_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("sla_hours", sa.Integer(), nullable=False),
        sa.Column("required_info", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["playbook_id"], ["playbook.id"], name="fk_escalation_policy_playbook"
        ),
        sa.ForeignKeyConstraint(
            ["clause_type"], ["clause_family.key"], name="fk_escalation_policy_clause_family"
        ),
        sa.ForeignKeyConstraint(
            ["approver_role_id"], ["approver_role.id"], name="fk_escalation_policy_approver_role"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_escalation_policy"),
    )

    # ── Literal reference data ────────────────────────────────────────────
    # Inserted directly as literals (never read from backend/seed/): the
    # document pipeline depends on these rows existing.
    agreement_type_table = sa.table(
        "agreement_type",
        sa.column("key", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("kind", sa.Text()),
    )
    op.bulk_insert(agreement_type_table, _AGREEMENT_TYPES)

    # ``synonyms`` is a JSONB column. Alembic's offline literal renderer has
    # no renderer for a JSONB bind value, so ``op.bulk_insert`` needs its
    # shadow column declared ``sa.Text()`` and fed an already-dumped JSON
    # string to render offline at all. But a bare ``sa.Text()``-typed bind
    # sent through a real (online) connection carries an explicit varchar
    # OID, and Postgres will not implicitly cast that to jsonb — online
    # execution then fails with ``DatatypeMismatch`` even though the exact
    # same statement rendered fine offline (unknown-typed literals coerce
    # freely). Issuing the insert as raw SQL with an explicit
    # ``CAST(:synonyms AS jsonb)`` fixes both: the cast still renders as
    # plain literal SQL offline, and overrides the implicit varchar typing
    # online so Postgres accepts it directly. The real table, created
    # above, still has a JSONB column.
    clause_family_insert = sa.text(
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
    for family in _CLAUSE_FAMILIES:
        op.execute(
            clause_family_insert.bindparams(
                key=family["key"],
                name=family["name"],
                category=family["category"],
                description=family["description"],
                synonyms=json.dumps(family["synonyms"]),
                sort_order=family["sort_order"],
            )
        )


def downgrade() -> None:
    op.drop_table("escalation_policy")
    op.drop_table("approver_role")
    op.drop_table("context_dimension")
    op.drop_table("clause_issue")
    op.drop_table("clause_family")
    op.drop_table("agreement_type")
