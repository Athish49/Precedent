"""Replay accuracy test for app/services/document_processing/pipeline.py
(task 2.9).

Runs ``build_result`` over the recorded fixture cases in
``tests/fixtures/ingest/`` and asserts the "good enough" marks from
``document_processing_plan.md`` section 2:

- Tier 1 field accuracy >= 85% per field across the four contract cases.
- At least 90% of expected sections found (anchored).
- At most one false split per document.
- Clause typing accuracy >= 85% (over clauses whose expected family exists
  in the taxonomy).
- ``blank`` and ``corrupt_docx_processed`` raise ``NoTextError``.

The ``FamilyIndex`` is built directly from the real migration 010 + 016
clause_family data, the same technique used in
``tests/unit/test_dp_clause_typing.py`` (import the migration files via
``importlib`` and pull their literal family-list structures) -- no database,
no network.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from app.services.document_processing.clause_typing import FamilyIndex
from app.services.document_processing.fields import REGISTRY
from app.services.document_processing.pipeline import NoTextError, build_result
from app.services.document_processing.invariants import InvariantError
from tests.ingest_fixtures import load_case

_BACKEND = Path(__file__).resolve().parents[2]

CONTRACT_CASES = ["msa_styled_docx", "msa_runin_docx", "msa_runin_pdf", "msa_scanned_pdf"]

AGREEMENT_TYPE_KEYS = ["nda", "saas_msa", "dpa", "vendor_msa"]
OWN_ORG_NAMES = ["Halcyon Care"]

# answers.json uses the pre-rename Extract field name for this one.
_ANSWER_ALIASES = {"total_value_amount": "total_contract_value"}


# ---------------------------------------------------------------------------
# FamilyIndex from the real migrations (same pattern as test_dp_clause_typing)
# ---------------------------------------------------------------------------


def _load_migration_module(filename: str):
    path = _BACKEND / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(f"_migration_{filename}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _real_family_rows() -> list[dict[str, object]]:
    """The 29 clause families from migration 010 plus the 2 from 016."""
    m010 = _load_migration_module("010_playbook_lookups.py")
    m016 = _load_migration_module("016_doc_proc_schema_a.py")
    rows: list[dict[str, object]] = [
        {"key": fam["key"], "synonyms": fam["synonyms"]} for fam in m010._CLAUSE_FAMILIES
    ]
    for fam in m016._NEW_FAMILIES:
        rows.append({"key": fam["key"], "synonyms": json.loads(fam["synonyms"])})
    return rows


@pytest.fixture(scope="module")
def family_index() -> FamilyIndex:
    rows = _real_family_rows()
    assert len(rows) == 31
    return FamilyIndex.from_rows(rows)


# ---------------------------------------------------------------------------
# Free-text matching, same style as test_dp_mapping.py
# ---------------------------------------------------------------------------


def _free_text_matches(value: object, answer: object) -> bool:
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


def _field_matches(field_def, fv_value, answer) -> bool:
    if field_def.kind in ("integer", "number"):
        return fv_value == answer
    if field_def.kind == "boolean":
        return fv_value is answer
    if field_def.kind == "date":
        return str(fv_value) == answer
    return _free_text_matches(fv_value, answer)


# ---------------------------------------------------------------------------
# Build results for all four contract cases once per module.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_cases(family_index: FamilyIndex) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for case_name in CONTRACT_CASES:
        extract_dict, parse_blocks, answers = load_case(case_name)
        value = extract_dict["output"]["value"]
        metadata = extract_dict["output"]["metadata"]
        result = build_result(
            value,
            metadata,
            parse_blocks,
            family_index=family_index,
            agreement_type_keys=AGREEMENT_TYPE_KEYS,
            own_org_names=OWN_ORG_NAMES,
        )
        out[case_name] = {"result": result, "answers": answers}
    return out


# ---------------------------------------------------------------------------
# Tier 1 field accuracy >= 85% per field across the four cases.
# ---------------------------------------------------------------------------


def _print_field_accuracy_table(per_field: dict[str, list[bool]]) -> None:
    print("\nTier 1 field accuracy (per field, across contract cases):")
    print(f"{'field':35s} {'matched':>8s} {'total':>6s} {'pct':>7s}")
    for key, outcomes in sorted(per_field.items()):
        matched = sum(1 for o in outcomes if o)
        total = len(outcomes)
        pct = (matched / total * 100) if total else 0.0
        print(f"{key:35s} {matched:8d} {total:6d} {pct:6.1f}%")


def test_tier1_field_accuracy_at_least_85_percent(built_cases: dict[str, dict]) -> None:
    tier1_keys = [k for k, fd in REGISTRY.items() if fd.tier == 1]
    assert tier1_keys, "registry must have tier 1 fields"

    per_field: dict[str, list[bool]] = {k: [] for k in tier1_keys}

    for case_name, data in built_cases.items():
        result = data["result"]
        answers = data["answers"]
        by_key = {fv.field_key: fv for fv in result.fields}

        for key in tier1_keys:
            field_def = REGISTRY[key]
            answer_key = _ANSWER_ALIASES.get(key, key)
            if answer_key not in answers:
                continue  # this fixture's answer file does not assert this field

            if key == "expiry_date":
                answer_raw = str(answers[answer_key])
                expected_date = answer_raw.split(" ")[0]
                fv = by_key.get("expiry_date")
                matched = (
                    fv is not None
                    and fv.source == "derived"
                    and str(fv.value) == expected_date
                )
                per_field[key].append(matched)
                continue

            fv = by_key.get(key)
            answer = answers[answer_key]
            matched = fv is not None and _field_matches(field_def, fv.value, answer)
            per_field[key].append(matched)

    # Drop fields no fixture asserted (nothing to score).
    scored = {k: v for k, v in per_field.items() if v}

    failures = []
    for key, outcomes in scored.items():
        pct = sum(1 for o in outcomes if o) / len(outcomes)
        if pct < 0.85:
            failures.append((key, pct, outcomes))

    if failures:
        _print_field_accuracy_table(scored)
        details = ", ".join(f"{k}={pct:.0%}" for k, pct, _ in failures)
        pytest.fail(f"Tier 1 fields below the 85% mark: {details}")


# ---------------------------------------------------------------------------
# At least 90% of expected sections found (anchored); at most one false
# split per document.
# ---------------------------------------------------------------------------


def test_sections_found_and_false_splits(built_cases: dict[str, dict]) -> None:
    for case_name, data in built_cases.items():
        result = data["result"]
        answers = data["answers"]
        expected_sections = answers["sections"]

        anchored = [
            c for c in result.clauses if c.level == 1 and c.section_number is not None
        ]
        expected_pairs = {(s["number"], s["title"]) for s in expected_sections}
        found_pairs = {(c.section_number, c.title) for c in anchored}

        found_count = len(expected_pairs & found_pairs)
        found_rate = found_count / len(expected_pairs) if expected_pairs else 1.0
        assert found_rate >= 0.90, (
            f"{case_name}: only {found_rate:.0%} of expected sections found "
            f"({found_count}/{len(expected_pairs)})"
        )

        # False splits: level-1 clauses beyond the expected sections, preamble
        # and signature_block (i.e. sections anchored that are not among the
        # expected pairs).
        false_splits = [p for p in found_pairs if p not in expected_pairs]
        assert len(false_splits) <= 1, (
            f"{case_name}: {len(false_splits)} false split(s): {false_splits}"
        )


# ---------------------------------------------------------------------------
# Clause typing accuracy >= 85% of clauses whose expected family exists in
# the taxonomy.
# ---------------------------------------------------------------------------


def test_clause_typing_accuracy_at_least_85_percent(
    built_cases: dict[str, dict], family_index: FamilyIndex
) -> None:
    total = 0
    correct = 0
    for case_name, data in built_cases.items():
        result = data["result"]
        answers = data["answers"]
        by_number = {c.section_number: c for c in result.clauses if c.level == 1}

        for section in answers["sections"]:
            expected_family = section.get("family")
            if not expected_family or expected_family not in family_index.keys:
                continue  # family not in the taxonomy; excluded from the mark
            clause = by_number.get(section["number"])
            total += 1
            if clause is not None and clause.clause_type == expected_family:
                correct += 1

    assert total > 0, "no clauses with a taxonomy family to score"
    accuracy = correct / total
    assert accuracy >= 0.85, (
        f"clause typing accuracy {accuracy:.0%} ({correct}/{total}) below the 85% mark"
    )


# ---------------------------------------------------------------------------
# blank and corrupt_docx_processed raise NoTextError.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_name", ["blank", "corrupt_docx_processed"])
def test_no_text_cases_raise_no_text_error(
    case_name: str, family_index: FamilyIndex
) -> None:
    extract_dict, parse_blocks, _answers = load_case(case_name)
    value = extract_dict["output"]["value"]
    metadata = extract_dict["output"]["metadata"]

    with pytest.raises(NoTextError):
        build_result(
            value,
            metadata,
            parse_blocks,
            family_index=family_index,
            agreement_type_keys=AGREEMENT_TYPE_KEYS,
            own_org_names=OWN_ORG_NAMES,
        )


# ---------------------------------------------------------------------------
# Sanity: build_result does not raise InvariantError on the real fixtures.
# ---------------------------------------------------------------------------


def test_build_result_does_not_raise_invariant_error(built_cases: dict[str, dict]) -> None:
    # built_cases already succeeded in constructing results (build_result
    # would have raised InvariantError during fixture setup otherwise), but
    # assert explicitly for clarity and to document the "Done when" item.
    for case_name, data in built_cases.items():
        assert data["result"] is not None, case_name
