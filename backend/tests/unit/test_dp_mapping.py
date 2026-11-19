"""Tests for app.services.document_processing.mapping (task 2.5).

Covers: map_fields evidence/confidence, sanity checks, derived expiry_date,
map_parties filtering/dedup, map_signatories, map_hints, map_title,
map_contract_type, and the accuracy mark against the four contract fixtures.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.services.document_processing.canonical import build_canonical
from app.services.document_processing.fields import REGISTRY
from app.services.document_processing.mapping import (
    map_contract_type,
    map_fields,
    map_hints,
    map_parties,
    map_signatories,
    map_title,
)
from app.services.document_processing.types import CanonicalDocument, ClauseDraft
from tests.ingest_fixtures import load_case

CONTRACT_CASES = ["msa_styled_docx", "msa_runin_docx", "msa_runin_pdf", "msa_scanned_pdf"]

# answers.json uses the pre-rename Extract field name for this one.
_ANSWER_ALIASES = {"total_value_amount": "total_contract_value"}


def _whole_document_clauses(document: CanonicalDocument) -> list[ClauseDraft]:
    """A single level-1 clause spanning the whole document -- a stand-in for
    real segmentation (task 2.3), which this task must not depend on."""
    return [
        ClauseDraft(
            ordinal=0,
            level=1,
            parent_ordinal=None,
            section_number=None,
            title=None,
            heading_text=None,
            text=document.text,
            char_start=0,
            char_end=len(document.text),
            page_start=1,
            page_end=max(document.page_count, 1),
        )
    ]


def _free_text_matches(value: object, answer: object) -> bool:
    """Case-insensitive containment, falling back to token overlap for
    paraphrased free text (plan 5.5: free text wording varies between runs
    and is for display only)."""
    v = str(value).strip().lower()
    a = str(answer).strip().lower()
    if not a:
        return not v
    if v in a or a in v:
        return True
    v_tokens = {t for t in re.findall(r"[a-z0-9$,.]+", v) if len(t) > 2}
    a_tokens = {t for t in re.findall(r"[a-z0-9$,.]+", a) if len(t) > 2}
    if not a_tokens:
        return False
    overlap = v_tokens & a_tokens
    return len(overlap) / len(a_tokens) >= 0.3


# ---------------------------------------------------------------------------
# Accuracy mark: every Tier 1 field matches on all four contract cases.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_name", CONTRACT_CASES)
def test_tier1_fields_match_answers(case_name: str) -> None:
    extract_dict, parse_blocks, answers = load_case(case_name)
    value = extract_dict["output"]["value"]
    metadata = extract_dict["output"]["metadata"]
    document = build_canonical(parse_blocks)
    clauses = _whole_document_clauses(document)

    field_values, _warnings = map_fields(value, metadata, document, clauses)
    by_key = {fv.field_key: fv for fv in field_values}

    tier1_keys = [k for k, fd in REGISTRY.items() if fd.tier == 1]
    assert tier1_keys, "registry must have tier 1 fields"

    for key in tier1_keys:
        field_def = REGISTRY[key]
        answer_key = _ANSWER_ALIASES.get(key, key)
        if answer_key not in answers:
            continue  # not asserted by this fixture's answer key

        if key == "expiry_date":
            # This fixture states a term but no explicit end date, so the
            # answer documents the derived value with an annotation.
            answer_raw = str(answers[answer_key])
            expected_date = answer_raw.split(" ")[0]
            fv = by_key.get("expiry_date")
            assert fv is not None, f"{case_name}: expiry_date missing"
            assert fv.source == "derived", f"{case_name}: expiry_date should be derived"
            assert str(fv.value) == expected_date, f"{case_name}: expiry_date value"
            continue

        fv = by_key.get(key)
        assert fv is not None, f"{case_name}: tier 1 field {key!r} missing"
        answer = answers[answer_key]

        if field_def.kind in ("integer", "number"):
            assert fv.value == answer, f"{case_name}: {key} = {fv.value!r} != {answer!r}"
        elif field_def.kind == "boolean":
            assert fv.value is answer, f"{case_name}: {key} = {fv.value!r} != {answer!r}"
        elif field_def.kind == "date":
            assert str(fv.value) == answer, f"{case_name}: {key} = {fv.value!r} != {answer!r}"
        else:
            # enum and free-text string fields
            assert _free_text_matches(fv.value, answer), (
                f"{case_name}: {key} = {fv.value!r} does not match answer {answer!r}"
            )


@pytest.mark.parametrize("case_name", CONTRACT_CASES)
def test_high_confidence_offsets_match_quote(case_name: str) -> None:
    extract_dict, parse_blocks, _answers = load_case(case_name)
    value = extract_dict["output"]["value"]
    metadata = extract_dict["output"]["metadata"]
    document = build_canonical(parse_blocks)
    clauses = _whole_document_clauses(document)

    field_values, _warnings = map_fields(value, metadata, document, clauses)

    high_confidence = [fv for fv in field_values if fv.confidence == "high"]
    assert high_confidence, f"{case_name}: expected at least one high-confidence field"

    for fv in high_confidence:
        assert fv.char_start is not None and fv.char_end is not None
        assert document.text[fv.char_start:fv.char_end] == fv.quote
        assert fv.clause_ordinal is not None


@pytest.mark.parametrize("case_name", CONTRACT_CASES)
def test_no_citation_fields_are_low_confidence(case_name: str) -> None:
    extract_dict, parse_blocks, _answers = load_case(case_name)
    value = extract_dict["output"]["value"]
    metadata = extract_dict["output"]["metadata"]
    document = build_canonical(parse_blocks)
    clauses = _whole_document_clauses(document)

    field_values, _warnings = map_fields(value, metadata, document, clauses)
    by_key = {fv.field_key: fv for fv in field_values}

    # currency has no citations on the Light tier recordings used here.
    fv = by_key.get("currency")
    if fv is not None and not (metadata.get("currency") or {}).get("citations"):
        assert fv.confidence == "low"
        assert fv.char_start is None
        assert fv.char_end is None


# ---------------------------------------------------------------------------
# Sanity checks (point 3)
# ---------------------------------------------------------------------------

def _simple_document(text: str) -> CanonicalDocument:
    return build_canonical(
        [{"type": "text", "content": text, "metadata": {"page": {"number": 1}}}]
    )


def _clauses_for(document: CanonicalDocument) -> list[ClauseDraft]:
    return _whole_document_clauses(document)


def test_sanity_check_drops_date_out_of_range() -> None:
    document = _simple_document("The agreement is effective as of January 1, 1899.")
    clauses = _clauses_for(document)
    value = {"effective_date": "1899-01-01"}
    metadata = {}

    field_values, warnings = map_fields(value, metadata, document, clauses)

    assert not any(fv.field_key == "effective_date" for fv in field_values)
    assert "dropped:effective_date:date_out_of_range" in warnings


def test_sanity_check_drops_negative_amount() -> None:
    document = _simple_document("Liability is capped.")
    clauses = _clauses_for(document)
    value = {"liability_cap_amount": -500000}
    metadata = {}

    field_values, warnings = map_fields(value, metadata, document, clauses)

    assert not any(fv.field_key == "liability_cap_amount" for fv in field_values)
    assert "dropped:liability_cap_amount:negative_value" in warnings


def test_sanity_check_drops_negative_duration() -> None:
    document = _simple_document("Notice period applies.")
    clauses = _clauses_for(document)
    value = {"renewal_notice_days": -30}
    metadata = {}

    field_values, warnings = map_fields(value, metadata, document, clauses)

    assert not any(fv.field_key == "renewal_notice_days" for fv in field_values)
    assert "dropped:renewal_notice_days:negative_value" in warnings


def test_sanity_check_drops_expiry_not_after_effective() -> None:
    document = _simple_document("Term dates stated.")
    clauses = _clauses_for(document)
    value = {"effective_date": "2025-01-01", "expiry_date": "2024-01-01"}
    metadata = {}

    field_values, warnings = map_fields(value, metadata, document, clauses)

    by_key = {fv.field_key: fv for fv in field_values}
    assert "expiry_date" not in by_key
    assert "effective_date" in by_key  # unrelated value survives
    assert "dropped:expiry_date:expiry_not_after_effective" in warnings


def test_sanity_check_drops_percent_out_of_range() -> None:
    document = _simple_document("Uptime is guaranteed.")
    clauses = _clauses_for(document)
    value = {"sla_uptime_percent": 150}
    metadata = {}

    field_values, warnings = map_fields(value, metadata, document, clauses)

    assert not any(fv.field_key == "sla_uptime_percent" for fv in field_values)
    assert "dropped:sla_uptime_percent:percent_out_of_range" in warnings


def test_string_list_empty_list_is_treated_as_absent() -> None:
    """Extend cannot return null for an array property (see fields.py's
    schema builder), so an unstated string_list field comes back as []
    rather than null. map_fields must treat that the same as absent."""
    document = _simple_document("No carve-outs mentioned.")
    clauses = _clauses_for(document)
    value = {"liability_exclusions": []}
    metadata = {}

    field_values, warnings = map_fields(value, metadata, document, clauses)

    assert not any(fv.field_key == "liability_exclusions" for fv in field_values)
    assert warnings == []


def test_string_list_non_empty_list_is_still_stored() -> None:
    document = _simple_document("Fraud and gross negligence are excluded.")
    clauses = _clauses_for(document)
    value = {"liability_exclusions": ["fraud", "gross negligence"]}
    metadata = {}

    field_values, _warnings = map_fields(value, metadata, document, clauses)
    by_key = {fv.field_key: fv for fv in field_values}

    assert by_key["liability_exclusions"].value == ["fraud", "gross negligence"]


def test_sanity_check_allows_valid_percent() -> None:
    document = _simple_document("Uptime is guaranteed.")
    clauses = _clauses_for(document)
    value = {"sla_uptime_percent": 99.9}
    metadata = {}

    field_values, warnings = map_fields(value, metadata, document, clauses)

    by_key = {fv.field_key: fv for fv in field_values}
    assert by_key["sla_uptime_percent"].value == 99.9
    assert not warnings


# ---------------------------------------------------------------------------
# Derived values (point 4)
# ---------------------------------------------------------------------------

def test_derived_expiry_date_from_term() -> None:
    document = _simple_document("The term is stated but no end date is given.")
    clauses = _clauses_for(document)
    value = {"effective_date": "2025-03-03", "initial_term_months": 36}
    metadata = {}

    field_values, _warnings = map_fields(value, metadata, document, clauses)
    by_key = {fv.field_key: fv for fv in field_values}

    assert by_key["expiry_date"].value == date(2028, 3, 3)
    assert by_key["expiry_date"].source == "derived"
    assert by_key["expiry_date"].quote is None


def test_no_derived_expiry_date_when_already_present() -> None:
    document = _simple_document("The agreement expires on a stated date.")
    clauses = _clauses_for(document)
    value = {
        "effective_date": "2025-03-03",
        "initial_term_months": 36,
        "expiry_date": "2030-01-01",
    }
    metadata = {}

    field_values, _warnings = map_fields(value, metadata, document, clauses)
    by_key = {fv.field_key: fv for fv in field_values}

    assert by_key["expiry_date"].value == date(2030, 1, 1)
    assert by_key["expiry_date"].source == "extract"


def test_derived_expiry_date_handles_month_end_overflow() -> None:
    document = _simple_document("Term stated, no end date.")
    clauses = _clauses_for(document)
    value = {"effective_date": "2025-01-31", "initial_term_months": 1}
    metadata = {}

    field_values, _warnings = map_fields(value, metadata, document, clauses)
    by_key = {fv.field_key: fv for fv in field_values}

    # January 31 + 1 month: February has no 31st, so it clamps to Feb 28.
    assert by_key["expiry_date"].value == date(2025, 2, 28)


# ---------------------------------------------------------------------------
# map_parties (point 5)
# ---------------------------------------------------------------------------

def test_map_parties_drops_empty_name() -> None:
    document = _simple_document("doc")
    value = {"parties": [{"name": "", "role_label": "Customer"}]}
    assert map_parties(value, document) == []


def test_map_parties_drops_name_equal_to_role_label() -> None:
    document = _simple_document("doc")
    value = {"parties": [{"name": "Customer", "role_label": "Customer"}]}
    assert map_parties(value, document) == []


def test_map_parties_drops_bare_role_words() -> None:
    document = _simple_document("doc")
    value = {
        "parties": [
            {"name": "Vendor", "role_label": None},
            {"name": "Supplier", "role_label": None},
            {"name": "Company", "role_label": None},
        ]
    }
    assert map_parties(value, document) == []


def test_map_parties_dedupes_on_normalised_name() -> None:
    document = _simple_document("doc")
    value = {
        "parties": [
            {"name": "Halcyon Systems, Inc.", "role_label": "Supplier"},
            {"name": "  halcyon systems, inc.  ", "role_label": "Supplier"},
        ]
    }
    parties = map_parties(value, document)
    assert len(parties) == 1
    assert parties[0].name == "Halcyon Systems, Inc."


def test_map_parties_keeps_real_parties() -> None:
    document = _simple_document("doc")
    value = {
        "parties": [
            {
                "name": "Acme, Inc.",
                "role_label": "Customer",
                "entity_type": "corporation",
                "jurisdiction": "Delaware",
                "address": "1 Main St",
            }
        ]
    }
    parties = map_parties(value, document)
    assert len(parties) == 1
    assert parties[0].name == "Acme, Inc."
    assert parties[0].entity_type == "corporation"
    assert parties[0].jurisdiction == "Delaware"
    assert parties[0].address == "1 Main St"


# ---------------------------------------------------------------------------
# map_signatories (point 6)
# ---------------------------------------------------------------------------

def test_map_signatories_basic() -> None:
    value = {
        "signatories": [
            {
                "printed_name": "Dana Whitfield",
                "title": "CRO",
                "party_name": "Halcyon Systems, Inc.",
                "is_signed": True,
                "signed_date": "2025-03-01",
            }
        ]
    }
    signatories = map_signatories(value)
    assert len(signatories) == 1
    sig = signatories[0]
    assert sig.printed_name == "Dana Whitfield"
    assert sig.is_signed is True
    assert sig.signed_date == date(2025, 3, 1)


def test_map_signatories_handles_missing_and_bad_date() -> None:
    value = {
        "signatories": [
            {"printed_name": None, "title": None, "party_name": None, "is_signed": None, "signed_date": None},
            {"printed_name": "X", "signed_date": "not-a-date"},
        ]
    }
    signatories = map_signatories(value)
    assert signatories[0].is_signed is None
    assert signatories[0].signed_date is None
    assert signatories[1].signed_date is None


def test_map_signatories_empty() -> None:
    assert map_signatories({}) == []


# ---------------------------------------------------------------------------
# map_hints, map_title, map_contract_type (point 7)
# ---------------------------------------------------------------------------

def test_map_hints() -> None:
    value = {
        "clauses": [
            {"section_number": "1", "title": "Definitions", "family": "definitions"},
            {"section_number": "2", "title": "Services", "family": None},
        ]
    }
    hints = map_hints(value)
    assert len(hints) == 2
    assert hints[0].section_number == "1"
    assert hints[0].title == "Definitions"
    assert hints[0].family == "definitions"
    assert hints[1].family is None


def test_map_hints_empty() -> None:
    assert map_hints({}) == []


def test_map_title() -> None:
    assert map_title({"title": "  Master Services Agreement  "}) == "Master Services Agreement"
    assert map_title({"title": None}) is None
    assert map_title({"title": ""}) is None
    assert map_title({}) is None


def test_map_contract_type_allowed() -> None:
    assert map_contract_type({"contract_type": "saas_msa"}, ["nda", "saas_msa"]) == "saas_msa"


def test_map_contract_type_not_allowed_is_null() -> None:
    assert map_contract_type({"contract_type": "MSA"}, ["nda", "saas_msa"]) is None


def test_map_contract_type_missing() -> None:
    assert map_contract_type({}, ["nda"]) is None
