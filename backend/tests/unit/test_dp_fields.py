"""Snapshot and unit tests for the field registry and Extract schema builder."""
from __future__ import annotations

import datetime
import json
import os

import pytest

from app.services.document_processing.fields import (
    REGISTRY,
    FieldDef,
    build_extract_schema,
    validate_value,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGREEMENT_TYPE_KEYS = ["nda", "saas_msa", "dpa", "vendor_msa"]

CLAUSE_FAMILY_KEYS = [
    "term_and_termination",
    "payment",
    "liability",
    "indemnification",
    "confidentiality",
    "ip_ownership",
    "governing_law",
    "dispute_resolution",
    "assignment",
    "non_compete",
    "non_solicitation",
    "sla",
    "warranty",
    "data_protection",
    "insurance",
    "audit_rights",
    "exclusivity",
    "most_favoured_customer",
    "change_of_control",
    "survival",
    "notices",
    "force_majeure",
    "amendment",
    "entire_agreement",
    "severability",
    "waiver",
    "counterparts",
    "representations",
    "definitions",
    "other",
    "scope_of_services",
]

assert len(CLAUSE_FAMILY_KEYS) == 31, "Exactly 31 clause family keys required"

SNAPSHOT_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "fixtures",
    "ingest",
    "extract_schema_snapshot.json",
)

# Known column names that will exist in ContractMetadata after task 1.2.
KNOWN_PROJECTION_COLUMNS = {
    "effective_date",
    "expiry_date",
    "expiry_is_derived",
    "initial_term_months",
    "auto_renewal",
    "renewal_term_months",
    "renewal_notice_days",
    "governing_law",
    "dispute_resolution",
    "total_value_amount",
    "currency",
    "liability_cap_amount",
    "liability_cap_basis",
    "payment_terms_days",
    "termination_for_convenience",
    "termination_notice_days",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_scalar_types(schema: dict, path: str = "") -> list[tuple[str, object]]:
    """Recursively collect (path, type_value) for every scalar 'type' field."""
    results = []
    if isinstance(schema, dict):
        if "type" in schema:
            t = schema["type"]
            # Recurse into array items / object properties even if we found 'type'
            results.append((path, t))
        for key, value in schema.items():
            if key in ("properties", "items"):
                sub_path = f"{path}.{key}" if path else key
                results.extend(_collect_scalar_types(value, sub_path))
            elif key == "properties" or isinstance(value, dict):
                sub_path = f"{path}.{key}" if path else key
                if isinstance(value, dict):
                    results.extend(_collect_scalar_types(value, sub_path))
    return results


def _is_nullable_type(t: object) -> bool:
    """Return True if *t* is a nullable type declaration."""
    if isinstance(t, list):
        return None in t or "null" in t
    return False


# ---------------------------------------------------------------------------
# Snapshot test
# ---------------------------------------------------------------------------

class TestExtractSchemaSnapshot:
    def test_snapshot(self, tmp_path):
        """Build schema, write snapshot if missing, compare if present."""
        schema = build_extract_schema(AGREEMENT_TYPE_KEYS, CLAUSE_FAMILY_KEYS)

        snapshot_path = os.path.abspath(SNAPSHOT_PATH)
        os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)

        if not os.path.exists(snapshot_path):
            with open(snapshot_path, "w", encoding="utf-8") as fh:
                json.dump(schema, fh, indent=2, default=str)
        else:
            with open(snapshot_path, encoding="utf-8") as fh:
                saved = json.load(fh)
            assert schema == saved, (
                "Extract schema changed. If intentional, delete "
                f"{snapshot_path} and re-run."
            )

    def test_every_primitive_is_nullable(self):
        """Every scalar (non-array, non-object) property in the schema must
        have a nullable type list. Arrays are a bare "array" type and are
        never nullable -- Extend rejects both ["array", "null"] and
        "nullable": true (see fields.py's _field_schema docstring context /
        document_processing_verification.md section 1)."""
        schema = build_extract_schema(AGREEMENT_TYPE_KEYS, CLAUSE_FAMILY_KEYS)
        props = schema["properties"]

        for key, prop in props.items():
            if not isinstance(prop, dict):
                continue
            t = prop.get("type")
            if t is None:
                continue
            # Skip object and bare array types -- object schemas don't carry
            # a nullable "type", and arrays are intentionally non-nullable.
            if t in ("object", "array"):
                continue
            assert _is_nullable_type(t), (
                f"Property '{key}' has non-nullable type: {t!r}"
            )
            assert "nullable" not in prop, (
                f"Property '{key}' uses unsupported 'nullable' keyword"
            )

    def test_arrays_are_bare_array_type_with_primitive_items(self):
        """Array properties must be a bare "array" type (not nullable), and
        string_list items must be a bare primitive type (not nullable) --
        see document_processing_verification.md section 1, defects 2 and 3."""
        schema = build_extract_schema(AGREEMENT_TYPE_KEYS, CLAUSE_FAMILY_KEYS)
        props = schema["properties"]

        for key in ("parties", "signatories", "clauses"):
            prop = props[key]
            assert prop["type"] == "array", f"'{key}' type should be bare 'array': {prop['type']!r}"
            assert "nullable" not in prop

        for field in REGISTRY.values():
            if field.kind != "string_list":
                continue
            prop = props[field.key]
            assert prop["type"] == "array", f"'{field.key}' type should be bare 'array'"
            assert prop["items"] == {"type": "string"}, (
                f"'{field.key}' items should be a bare primitive type: {prop['items']!r}"
            )

    def test_every_enum_contains_null(self):
        """Every enum-typed property must declare its values in a separate
        "enum" list (never mixed into "type") and that list must include
        null, with "type" kept to ["string", "null"]."""
        schema = build_extract_schema(AGREEMENT_TYPE_KEYS, CLAUSE_FAMILY_KEYS)
        props = schema["properties"]

        enum_like_keys = ["contract_type"] + [
            f.key for f in REGISTRY.values() if f.kind == "enum"
        ]
        for key in enum_like_keys:
            prop = props[key]
            assert prop["type"] == ["string", "null"], (
                f"Property '{key}' enum-backed type should be ['string', 'null']: {prop['type']!r}"
            )
            assert None in prop["enum"], (
                f"Property '{key}' enum does not contain null: {prop['enum']!r}"
            )
            assert all(
                v is None or isinstance(v, str) for v in prop["enum"]
            ), f"Property '{key}' enum contains non-string, non-null values: {prop['enum']!r}"

        # Also check nested family enum inside clauses.items.properties
        clauses = props.get("clauses", {})
        items = clauses.get("items", {})
        family = items.get("properties", {}).get("family", {})
        assert family["type"] == ["string", "null"]
        assert None in family["enum"], (
            f"clauses[].family enum does not contain null: {family['enum']!r}"
        )

    def test_clauses_description_asks_for_exhibits_and_schedules(self):
        """See document_processing_verification.md section 9 item 3:
        Extract's clauses[] hint list systematically omitted
        exhibits/schedules/annexes because the description only mentioned
        'numbered sections'. The description must now ask for them too."""
        schema = build_extract_schema(AGREEMENT_TYPE_KEYS, CLAUSE_FAMILY_KEYS)
        desc = schema["properties"]["clauses"]["description"].lower()
        assert "exhibit" in desc
        assert "schedule" in desc
        assert "annex" in desc

    def test_field_registry_fields_in_schema(self):
        """Every registry field appears in the schema."""
        schema = build_extract_schema(AGREEMENT_TYPE_KEYS, CLAUSE_FAMILY_KEYS)
        props = schema["properties"]
        for key in REGISTRY:
            assert key in props, f"Registry field '{key}' missing from schema"


# ---------------------------------------------------------------------------
# Projection column tests
# ---------------------------------------------------------------------------

class TestProjectionColumns:
    def test_all_projections_are_known_columns(self):
        """Every non-None projection must be in the known column list."""
        for field in REGISTRY.values():
            if field.projection is not None:
                assert field.projection in KNOWN_PROJECTION_COLUMNS, (
                    f"Field '{field.key}' has projection '{field.projection}' "
                    f"which is not in KNOWN_PROJECTION_COLUMNS"
                )

    def test_projection_is_string_or_none(self):
        """Projection must be a string or None."""
        for field in REGISTRY.values():
            assert field.projection is None or isinstance(field.projection, str)


# ---------------------------------------------------------------------------
# validate_value tests
# ---------------------------------------------------------------------------

class TestValidateValueBoolean:
    def setup_method(self):
        self.fd = REGISTRY["auto_renewal"]  # boolean field

    def test_valid_true(self):
        assert validate_value(self.fd, True) is True

    def test_valid_false(self):
        assert validate_value(self.fd, False) is False

    def test_null_input(self):
        assert validate_value(self.fd, None) is None

    def test_wrong_type_string(self):
        assert validate_value(self.fd, "true") is None

    def test_wrong_type_int(self):
        assert validate_value(self.fd, 1) is None


class TestValidateValueInteger:
    def setup_method(self):
        self.fd = REGISTRY["initial_term_months"]

    def test_valid_int(self):
        assert validate_value(self.fd, 12) == 12

    def test_valid_string_int(self):
        assert validate_value(self.fd, "24") == 24

    def test_null_input(self):
        assert validate_value(self.fd, None) is None

    def test_wrong_type_bool(self):
        # booleans are ints in Python but should be rejected
        assert validate_value(self.fd, True) is None

    def test_wrong_type_string(self):
        assert validate_value(self.fd, "twelve") is None


class TestValidateValueNumber:
    def setup_method(self):
        self.fd = REGISTRY["liability_cap_amount"]

    def test_valid_float(self):
        assert validate_value(self.fd, 1000000.0) == 1000000.0

    def test_valid_int_coerced(self):
        assert validate_value(self.fd, 500) == 500.0

    def test_valid_string_number(self):
        assert validate_value(self.fd, "99.5") == 99.5

    def test_null_input(self):
        assert validate_value(self.fd, None) is None

    def test_wrong_type_bool(self):
        assert validate_value(self.fd, True) is None

    def test_wrong_type_string(self):
        assert validate_value(self.fd, "one million") is None


class TestValidateValueDate:
    def setup_method(self):
        self.fd = REGISTRY["effective_date"]

    def test_valid_date_object(self):
        d = datetime.date(2024, 1, 15)
        assert validate_value(self.fd, d) == d

    def test_valid_iso_string(self):
        result = validate_value(self.fd, "2024-01-15")
        assert result == datetime.date(2024, 1, 15)

    def test_valid_datetime_object(self):
        dt = datetime.datetime(2024, 1, 15, 10, 30)
        assert validate_value(self.fd, dt) == datetime.date(2024, 1, 15)

    def test_null_input(self):
        assert validate_value(self.fd, None) is None

    def test_wrong_type_string(self):
        assert validate_value(self.fd, "January 15 2024") is None

    def test_wrong_type_int(self):
        assert validate_value(self.fd, 20240115) is None


class TestValidateValueString:
    def setup_method(self):
        self.fd = REGISTRY["governing_law"]

    def test_valid_string(self):
        assert validate_value(self.fd, "New York") == "New York"

    def test_null_input(self):
        assert validate_value(self.fd, None) is None

    def test_empty_string(self):
        assert validate_value(self.fd, "") is None

    def test_coerces_int(self):
        # str(42) = "42" which is non-empty → valid
        assert validate_value(self.fd, 42) == "42"


class TestValidateValueEnum:
    def setup_method(self):
        self.fd = REGISTRY["dispute_resolution"]

    def test_valid_enum(self):
        assert validate_value(self.fd, "litigation") == "litigation"

    def test_valid_arbitration(self):
        assert validate_value(self.fd, "arbitration") == "arbitration"

    def test_null_input(self):
        assert validate_value(self.fd, None) is None

    def test_wrong_value(self):
        assert validate_value(self.fd, "mediation_plus") is None

    def test_wrong_type(self):
        assert validate_value(self.fd, 123) is None


class TestValidateValueStringList:
    def setup_method(self):
        self.fd = REGISTRY["liability_exclusions"]

    def test_valid_list(self):
        assert validate_value(self.fd, ["fraud", "gross negligence"]) == [
            "fraud",
            "gross negligence",
        ]

    def test_null_input(self):
        assert validate_value(self.fd, None) is None

    def test_empty_list(self):
        result = validate_value(self.fd, [])
        assert result == []

    def test_not_a_list(self):
        assert validate_value(self.fd, "single string") is None

    def test_filters_empty_items(self):
        result = validate_value(self.fd, ["valid", "", None])
        assert result == ["valid"]


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

class TestRegistryIntegrity:
    def test_all_keys_match_field_key(self):
        for key, field in REGISTRY.items():
            assert key == field.key, f"Registry key '{key}' does not match field.key '{field.key}'"

    def test_tiers_are_1_or_2(self):
        for field in REGISTRY.values():
            assert field.tier in (1, 2), f"Field '{field.key}' has invalid tier {field.tier}"

    def test_enum_fields_have_enum_tuple(self):
        for field in REGISTRY.values():
            if field.kind == "enum":
                assert field.enum is not None and len(field.enum) > 0, (
                    f"Enum field '{field.key}' has no enum values"
                )

    def test_non_enum_fields_have_no_enum(self):
        for field in REGISTRY.values():
            if field.kind != "enum":
                assert field.enum is None, (
                    f"Non-enum field '{field.key}' has unexpected enum values"
                )

    def test_descriptions_contain_leave_null(self):
        for field in REGISTRY.values():
            assert "leave null" in field.description.lower(), (
                f"Field '{field.key}' description missing 'leave null' guidance"
            )

    def test_dispute_resolution_enum_includes_escalation(self):
        field = REGISTRY["dispute_resolution"]
        assert field.enum == ("litigation", "arbitration", "mediation", "escalation")
        assert "escalation" in field.description.lower()

    def test_convention_fields_instruct_infer_false(self):
        """termination_for_convenience and auto_renewal must instruct the
        model to answer false (not null) when the relevant clause exists but
        does not grant the right -- see document_processing_verification.md
        section 5/9, proposed change #4."""
        for key in ("termination_for_convenience", "auto_renewal"):
            desc = REGISTRY[key].description.lower()
            assert "false" in desc, f"{key} description should mention answering false"

    def test_termination_for_convenience_mentions_discussions(self):
        """Best-effort mitigation for the contract 10 miss (verification doc
        section 5.1 / 9, proposed change #10): a right to terminate ongoing
        discussions/negotiations without cause also counts."""
        desc = REGISTRY["termination_for_convenience"].description.lower()
        assert "discussion" in desc or "negotiation" in desc

    def test_cure_and_notice_days_are_disambiguated(self):
        cure_desc = REGISTRY["cure_period_days"].description.lower()
        notice_desc = REGISTRY["termination_notice_days"].description.lower()
        assert "cure" in cure_desc
        assert "cure" in notice_desc  # explicitly excludes cure period
        assert "notice" in notice_desc

    def test_liability_cap_basis_covers_uncapped_and_cross_reference(self):
        desc = REGISTRY["liability_cap_basis"].description.lower()
        assert "uncapped" in desc or "unlimited" in desc
        assert "reference" in desc

    def test_total_value_amount_covers_composite_figures(self):
        desc = REGISTRY["total_value_amount"].description.lower()
        assert "sum" in desc or "composite" in desc
