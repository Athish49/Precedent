"""Field registry and Extract schema builder for document processing.

No database or network imports.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldDef:
    key: str
    kind: str          # string | integer | number | boolean | date | enum | string_list
    tier: int          # 1 or 2
    description: str   # question text for Extract — must say "leave null if not stated"
    enum: tuple[str, ...] | None = None   # allowed values when kind == "enum"
    projection: str | None = None          # contract_metadata column name, or None
    derived_from: tuple[str, ...] | None = None  # field keys this is derived from


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, FieldDef] = {
    # --- Tier 1 ---
    "effective_date": FieldDef(
        key="effective_date",
        kind="date",
        tier=1,
        description="The date on which the agreement becomes effective or was entered into. Leave null if not stated.",
        projection="effective_date",
    ),
    "expiry_date": FieldDef(
        key="expiry_date",
        kind="date",
        tier=1,
        description="The explicit end date of the agreement. Leave null if not stated. Only if an explicit end date is written; do not compute from the term.",
        projection="expiry_date",
    ),
    "initial_term_months": FieldDef(
        key="initial_term_months",
        kind="integer",
        tier=1,
        description="The initial term of the agreement in months (convert years to months). Leave null if not stated.",
        projection="initial_term_months",
    ),
    "auto_renewal": FieldDef(
        key="auto_renewal",
        kind="boolean",
        tier=1,
        description=(
            "Whether the agreement automatically renews. If the document "
            "has a term/renewal clause or section but it does not grant an "
            "automatic-renewal right (e.g. it states only a fixed term with "
            "no renewal clause, or renewal requires an affirmative new "
            "agreement), answer false, not null. Leave null only when the "
            "document has no clause addressing the term or renewal at all."
        ),
        projection="auto_renewal",
    ),
    "renewal_term_months": FieldDef(
        key="renewal_term_months",
        kind="integer",
        tier=1,
        description="The renewal term in months. Leave null if not stated.",
        projection="renewal_term_months",
    ),
    "renewal_notice_days": FieldDef(
        key="renewal_notice_days",
        kind="integer",
        tier=1,
        description="The number of days' notice required to prevent auto-renewal. Leave null if not stated.",
        projection="renewal_notice_days",
    ),
    "governing_law": FieldDef(
        key="governing_law",
        kind="string",
        tier=1,
        description="The state or jurisdiction whose laws govern this agreement. Leave null if not stated.",
        projection="governing_law",
    ),
    "dispute_resolution": FieldDef(
        key="dispute_resolution",
        kind="enum",
        tier=1,
        description=(
            "The dispute resolution mechanism that applies. If arbitration is "
            "excluded, do not answer arbitration. Use 'escalation' when the "
            "contract requires an informal internal escalation or negotiation "
            "step (e.g. senior-management negotiation) before formal "
            "proceedings, distinct from litigation/arbitration/mediation "
            "themselves. Leave null if not stated."
        ),
        enum=("litigation", "arbitration", "mediation", "escalation"),
        projection="dispute_resolution",
    ),
    "dispute_venue": FieldDef(
        key="dispute_venue",
        kind="string",
        tier=1,
        description="The specific court or forum designated for disputes. Leave null if not stated.",
        projection=None,
    ),
    "liability_cap_amount": FieldDef(
        key="liability_cap_amount",
        kind="number",
        tier=1,
        description="The maximum aggregate liability amount in the contract currency as a numeric value. Leave null if stated as a multiple of fees or not stated.",
        projection="liability_cap_amount",
    ),
    "liability_cap_basis": FieldDef(
        key="liability_cap_basis",
        kind="string",
        tier=1,
        description=(
            "The basis or description of the liability cap (e.g., '12 months "
            "of fees', '$1,000,000'). If liability is expressly stated as "
            "uncapped or unlimited, state that (e.g. 'uncapped' / 'no limit') "
            "rather than leaving this null. If the cap is defined by "
            "reference to another document or agreement (e.g. 'subject to "
            "the Agreement's limitation of liability') rather than restated "
            "here, describe that cross-reference rather than leaving this "
            "null. Leave null only if liability/cap is not addressed at all."
        ),
        projection="liability_cap_basis",
    ),
    "total_value_amount": FieldDef(
        key="total_value_amount",
        kind="number",
        tier=1,
        description=(
            "The total contract value as a numeric amount. If the contract "
            "states multiple fee components (e.g. a recurring subscription "
            "fee plus a one-time implementation fee), sum them into a single "
            "total figure, or state the clearly primary/largest recurring "
            "figure if the components are not additive — do not decline to "
            "answer merely because the figure is composite. Leave null only "
            "when no numeric figure is stated at all; do not guess."
        ),
        projection="total_value_amount",
    ),
    "currency": FieldDef(
        key="currency",
        kind="string",
        tier=1,
        description="The currency of monetary amounts in the contract (e.g., 'USD'). Leave null if not stated.",
        projection="currency",
    ),
    "payment_terms_days": FieldDef(
        key="payment_terms_days",
        kind="integer",
        tier=1,
        description="Payment due in this many days (net-30 = 30). Leave null if not stated.",
        projection="payment_terms_days",
    ),
    "termination_for_convenience": FieldDef(
        key="termination_for_convenience",
        kind="boolean",
        tier=1,
        description=(
            "Whether either party may terminate for convenience (without "
            "cause). A right to terminate ongoing discussions or "
            "negotiations without cause (not just a signed agreement's "
            "ongoing obligations) also counts as termination for "
            "convenience. If the document has a termination/renewal-type "
            "clause or section but it does not grant this right (e.g. it "
            "only allows termination for cause), answer false, not null. "
            "Leave null only when the document has no clause addressing "
            "termination at all."
        ),
        projection="termination_for_convenience",
    ),
    "termination_for_convenience_party": FieldDef(
        key="termination_for_convenience_party",
        kind="enum",
        tier=1,
        description=(
            "Which party may terminate for convenience, if any. Answer this "
            "only when termination_for_convenience is true (the document "
            "grants a right to terminate without cause, including a right "
            "to terminate ongoing discussions/negotiations without cause). "
            "If the document has a termination clause but it does not "
            "grant a convenience-termination right (termination_for_"
            "convenience is false), or if there is no termination clause at "
            "all, leave null."
        ),
        enum=("either", "customer", "vendor"),
        projection=None,
    ),
    "termination_notice_days": FieldDef(
        key="termination_notice_days",
        kind="integer",
        tier=1,
        description=(
            "The number of days' advance notice required before a "
            "termination takes effect, for a termination NOT conditioned on "
            "curing a breach (e.g. a convenience or fixed-notice "
            "termination). Do not use this field for a cure period — see "
            "cure_period_days for that. Leave null if not stated."
        ),
        projection="termination_notice_days",
    ),
    # --- Tier 2 ---
    "cure_period_days": FieldDef(
        key="cure_period_days",
        kind="integer",
        tier=2,
        description=(
            "The number of days a party has to FIX/CURE a breach before the "
            "other party may terminate because of it — this is distinct "
            "from a general termination notice period (see "
            "termination_notice_days for that). Leave null if not stated."
        ),
        projection=None,
    ),
    "notice_period_days": FieldDef(
        key="notice_period_days",
        kind="integer",
        tier=2,
        description="General notice period in days. Leave null if not stated.",
        projection=None,
    ),
    "indemnification_cap_amount": FieldDef(
        key="indemnification_cap_amount",
        kind="number",
        tier=2,
        description="Maximum indemnification liability amount. Leave null if not stated.",
        projection=None,
    ),
    "liability_exclusions": FieldDef(
        key="liability_exclusions",
        kind="string_list",
        tier=2,
        description="List of liability carve-outs or exclusions from the cap. Leave null if not stated.",
        projection=None,
    ),
    "assignment_requires_consent": FieldDef(
        key="assignment_requires_consent",
        kind="boolean",
        tier=2,
        description="Whether assignment requires the other party's prior written consent. Leave null if not stated.",
        projection=None,
    ),
    "assignment_exceptions": FieldDef(
        key="assignment_exceptions",
        kind="string_list",
        tier=2,
        description="List of exceptions where assignment is permitted without consent. Leave null if not stated.",
        projection=None,
    ),
    "confidentiality_period_years": FieldDef(
        key="confidentiality_period_years",
        kind="integer",
        tier=2,
        description="Confidentiality obligation duration in years after termination. Leave null if not stated.",
        projection=None,
    ),
    "ip_ownership": FieldDef(
        key="ip_ownership",
        kind="enum",
        tier=2,
        description="Who owns intellectual property created under this agreement. Leave null if not stated.",
        enum=("customer", "vendor", "joint"),
        projection=None,
    ),
    "non_compete_months": FieldDef(
        key="non_compete_months",
        kind="integer",
        tier=2,
        description="Non-compete restriction duration in months. Leave null if not stated.",
        projection=None,
    ),
    "non_solicitation_months": FieldDef(
        key="non_solicitation_months",
        kind="integer",
        tier=2,
        description="Non-solicitation restriction duration in months. Leave null if not stated.",
        projection=None,
    ),
    "sla_uptime_percent": FieldDef(
        key="sla_uptime_percent",
        kind="number",
        tier=2,
        description="Service level uptime percentage commitment. Leave null if not stated.",
        projection=None,
    ),
    "sla_response_time_hours": FieldDef(
        key="sla_response_time_hours",
        kind="integer",
        tier=2,
        description="Service level response time commitment in hours. Leave null if not stated.",
        projection=None,
    ),
    "warranty_period_days": FieldDef(
        key="warranty_period_days",
        kind="integer",
        tier=2,
        description="Warranty period in days. Leave null if not stated.",
        projection=None,
    ),
    "breach_notification_hours": FieldDef(
        key="breach_notification_hours",
        kind="integer",
        tier=2,
        description="Hours within which a security breach must be notified. Leave null if not stated.",
        projection=None,
    ),
    "data_processing_agreement": FieldDef(
        key="data_processing_agreement",
        kind="boolean",
        tier=2,
        description="Whether a data processing agreement or addendum is in place. Leave null if not stated.",
        projection=None,
    ),
    "gdpr_applicable": FieldDef(
        key="gdpr_applicable",
        kind="boolean",
        tier=2,
        description="Whether GDPR applies to this agreement. Leave null if not stated.",
        projection=None,
    ),
    "survival_clauses": FieldDef(
        key="survival_clauses",
        kind="string_list",
        tier=2,
        description="Clause titles or descriptions that survive termination. Leave null if not stated.",
        projection=None,
    ),
    "insurance_required": FieldDef(
        key="insurance_required",
        kind="boolean",
        tier=2,
        description="Whether the agreement requires insurance. Leave null if not stated.",
        projection=None,
    ),
    "exclusivity": FieldDef(
        key="exclusivity",
        kind="boolean",
        tier=2,
        description="Whether the agreement contains exclusivity provisions. Leave null if not stated.",
        projection=None,
    ),
    "most_favoured_customer": FieldDef(
        key="most_favoured_customer",
        kind="boolean",
        tier=2,
        description="Whether most-favoured-customer pricing applies. Leave null if not stated.",
        projection=None,
    ),
    "audit_rights": FieldDef(
        key="audit_rights",
        kind="boolean",
        tier=2,
        description="Whether the agreement grants audit rights. Leave null if not stated.",
        projection=None,
    ),
    "change_of_control_restriction": FieldDef(
        key="change_of_control_restriction",
        kind="boolean",
        tier=2,
        description="Whether change of control triggers restrictions or termination rights. Leave null if not stated.",
        projection=None,
    ),
}


# ---------------------------------------------------------------------------
# Schema builder
# ---------------------------------------------------------------------------

def _field_schema(field: FieldDef) -> dict:
    """Return the JSON schema fragment for a single registry field."""
    kind = field.kind
    desc = field.description

    if kind == "date":
        return {"type": ["string", "null"], "extend:type": "date", "description": desc}
    if kind == "boolean":
        return {"type": ["boolean", "null"], "description": desc}
    if kind == "integer":
        return {"type": ["integer", "null"], "description": desc}
    if kind == "number":
        return {"type": ["number", "null"], "description": desc}
    if kind == "string":
        return {"type": ["string", "null"], "description": desc}
    if kind == "enum":
        assert field.enum is not None
        return {
            "type": ["string", "null"],
            "enum": [*field.enum, None],
            "description": desc,
        }
    if kind == "string_list":
        return {
            "type": "array",
            "items": {"type": "string"},
            "description": desc,
        }
    raise ValueError(f"Unknown kind: {kind!r}")


def build_extract_schema(
    agreement_type_keys: list[str],
    clause_family_keys: list[str],
) -> dict:
    """Build the Extend JSON schema dict for an Extract run.

    Parameters
    ----------
    agreement_type_keys:
        The agreement type enum values (e.g. ["nda", "saas_msa", ...]).
    clause_family_keys:
        The clause family enum values.

    Returns
    -------
    dict
        A JSON-serialisable schema dict ready to pass as ``config.schema``
        in an Extend Extract run.
    """
    properties: dict[str, Any] = {
        "title": {
            "type": ["string", "null"],
            "description": "The title of the agreement.",
        },
        "contract_type": {
            "type": ["string", "null"],
            "enum": [*agreement_type_keys, None],
            "description": "The type of agreement.",
        },
        "parties": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "role_label": {
                        "type": ["string", "null"],
                        "description": "The name used for this party in the document, e.g. 'Supplier' or 'Customer'.",
                    },
                    "entity_type": {
                        "type": ["string", "null"],
                        "description": "Legal entity type, e.g. 'corporation', 'LLC'.",
                    },
                    "jurisdiction": {
                        "type": ["string", "null"],
                        "description": "State or country of incorporation.",
                    },
                    "address": {"type": ["string", "null"]},
                },
            },
        },
        "signatories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "printed_name": {"type": ["string", "null"]},
                    "title": {"type": ["string", "null"]},
                    "party_name": {
                        "type": ["string", "null"],
                        "description": "The party this signatory represents.",
                    },
                    "is_signed": {"type": ["boolean", "null"]},
                    "signed_date": {
                        "type": ["string", "null"],
                        "extend:type": "date",
                    },
                },
            },
        },
        "clauses": {
            "type": "array",
            "description": (
                "Every top-level numbered section in order. Do not include "
                "sub-clauses. Also include exhibit/schedule/annex/appendix-style "
                "sections (e.g. 'Exhibit A', 'Schedule 1', 'Annex 2') as their own "
                "top-level entries in this list, using whatever label is actually "
                "printed — including non-numeric labels — as section_number."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "section_number": {
                        "type": ["string", "null"],
                        "description": "The section number as written, e.g. '1', '2.1', 'ARTICLE IV', 'Exhibit A', 'Schedule 1'.",
                    },
                    "title": {
                        "type": ["string", "null"],
                        "description": "The section title without the number.",
                    },
                    "family": {
                        "type": ["string", "null"],
                        "enum": [*clause_family_keys, None],
                        "description": "The clause family this section belongs to.",
                    },
                },
            },
        },
    }

    # Add one property per registry field
    for field in REGISTRY.values():
        properties[field.key] = _field_schema(field)

    return {"type": "object", "properties": properties}


# ---------------------------------------------------------------------------
# Value validator / coercer
# ---------------------------------------------------------------------------

def validate_value(field_def: FieldDef, raw: Any) -> Any | None:
    """Coerce *raw* to the type declared in *field_def*.

    Returns ``None`` for null/missing input or when the value cannot be
    coerced to the expected type.
    """
    if raw is None:
        return None

    kind = field_def.kind

    if kind == "boolean":
        if isinstance(raw, bool):
            return raw
        return None

    if kind == "integer":
        if isinstance(raw, bool):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    if kind == "number":
        if isinstance(raw, bool):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    if kind == "date":
        if isinstance(raw, datetime.date) and not isinstance(raw, datetime.datetime):
            return raw
        if isinstance(raw, datetime.datetime):
            return raw.date()
        if isinstance(raw, str):
            try:
                return datetime.date.fromisoformat(raw)
            except ValueError:
                return None
        return None

    if kind == "string":
        s = str(raw)
        return s if s else None

    if kind == "enum":
        assert field_def.enum is not None
        if raw in field_def.enum:
            return raw
        return None

    if kind == "string_list":
        if not isinstance(raw, list):
            return None
        result = [str(item) for item in raw if item is not None and str(item)]
        return result  # may be empty list; callers may treat [] as None if desired

    raise ValueError(f"Unknown kind: {kind!r}")
