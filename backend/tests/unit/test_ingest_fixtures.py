"""Unit tests for the ingest fixture loader (task 0.3)."""

from __future__ import annotations

import pytest

from tests.ingest_fixtures import all_cases, load_case


def test_all_cases_returns_at_least_seven():
    cases = all_cases()
    assert len(cases) >= 7, f"Expected at least 7 cases, got {len(cases)}: {cases}"


def test_load_case_returns_three_tuple_for_all_cases():
    for name in all_cases():
        result = load_case(name)
        assert isinstance(result, tuple), f"{name}: expected tuple, got {type(result)}"
        assert len(result) == 3, f"{name}: expected 3-tuple, got length {len(result)}"
        extract_dict, parse_blocks, answers = result
        assert isinstance(extract_dict, dict), f"{name}: extract_dict is not a dict"
        assert isinstance(parse_blocks, list), f"{name}: parse_blocks is not a list"
        assert isinstance(answers, dict), f"{name}: answers is not a dict"


def test_blank_case_has_zero_parse_blocks():
    _, parse_blocks, _ = load_case("blank")
    assert parse_blocks == [], f"blank case should have 0 parse blocks, got {len(parse_blocks)}"


def test_contract_cases_have_assignment_requires_consent():
    contract_cases = ["msa_styled_docx", "msa_runin_docx", "msa_runin_pdf", "msa_scanned_pdf"]
    for name in contract_cases:
        _, _, answers = load_case(name)
        assert "assignment_requires_consent" in answers, (
            f"{name}: answers missing 'assignment_requires_consent'"
        )
        assert "assignment_allowed_without_consent" not in answers, (
            f"{name}: answers still has deprecated 'assignment_allowed_without_consent'"
        )
