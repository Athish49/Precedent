"""Tests for document_processing/clause_typing.py (task 2.4).

The ``FamilyIndex`` under test is built directly from the real reference
data in migrations 010 and 016 (29 + 2 = 31 clause families), loaded here
with no database and no network, per the task's ground rules.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from app.services.document_processing.clause_typing import (
    FamilyIndex,
    clean_title,
    clear_family_index_cache,
    load_family_index,
    type_clause,
)
from app.services.document_processing.types import ClauseDraft

_BACKEND = Path(__file__).resolve().parents[2]


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
        import json

        rows.append({"key": fam["key"], "synonyms": json.loads(fam["synonyms"])})
    return rows


@pytest.fixture(scope="module")
def real_index() -> FamilyIndex:
    rows = _real_family_rows()
    assert len(rows) == 31
    return FamilyIndex.from_rows(rows)


def make_draft(
    *,
    ordinal: int = 0,
    level: int = 1,
    parent_ordinal: int | None = None,
    title: str | None = "Indemnification",
    heading_text: str | None = None,
    clause_type: str = "other",
    type_source: str = "none",
) -> ClauseDraft:
    return ClauseDraft(
        ordinal=ordinal,
        level=level,
        parent_ordinal=parent_ordinal,
        section_number=None,
        title=title,
        heading_text=heading_text if heading_text is not None else title,
        text="placeholder text",
        char_start=0,
        char_end=len("placeholder text"),
        page_start=1,
        page_end=1,
        clause_type=clause_type,
        type_source=type_source,
    )


# ---------------------------------------------------------------------------
# FamilyIndex.from_rows
# ---------------------------------------------------------------------------


def test_from_rows_builds_keys_and_synonyms():
    rows = [
        {"key": "indemnification", "synonyms": ["indemnification", "indemnity"]},
        {"key": "other", "synonyms": []},
    ]
    index = FamilyIndex.from_rows(rows)
    assert index.keys == {"indemnification", "other"}
    assert index.synonyms == {"indemnification": "indemnification", "indemnity": "indemnification"}


def test_from_rows_accepts_orm_like_objects():
    class Row:
        def __init__(self, key, synonyms):
            self.key = key
            self.synonyms = synonyms

    rows = [Row("security", ["security", "data security"])]
    index = FamilyIndex.from_rows(rows)
    assert index.keys == {"security"}
    assert index.synonyms["data security"] == "security"


def test_real_index_has_31_keys(real_index: FamilyIndex):
    assert len(real_index.keys) == 31
    assert "other" in real_index.keys
    assert "preamble" in real_index.keys
    assert "signature_block" in real_index.keys


# ---------------------------------------------------------------------------
# clean_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ARTICLE 7 - INDEMNIFICATION", "indemnification"),
        ("Section 9. Confidentiality", "confidentiality"),
        ("Data Security", "data security"),
        ("Service Levels", "service levels"),
        ("7. Indemnification", "indemnification"),
        ("6.1 Audit Rights", "audit rights"),
        ("(a) Supplier Obligations", "supplier obligations"),
        ("(iv) Remedies", "remedies"),
        ("Governing Law and Disputes", "governing law and disputes"),
        (None, ""),
        ("", ""),
        ("   ", ""),
    ],
)
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


# ---------------------------------------------------------------------------
# type_clause: the implementation doc's "Done when" cases
# ---------------------------------------------------------------------------


def test_article_prefix_types_correctly(real_index: FamilyIndex):
    draft = make_draft(title="ARTICLE 7 - INDEMNIFICATION")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "indemnification"
    assert result.type_source == "dictionary"


def test_section_prefix_types_correctly(real_index: FamilyIndex):
    draft = make_draft(title="Section 9. Confidentiality")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "confidentiality"
    assert result.type_source == "dictionary"


def test_data_security_types_to_security(real_index: FamilyIndex):
    draft = make_draft(title="Data Security")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "security"
    assert result.type_source == "dictionary"


def test_service_levels_types_correctly(real_index: FamilyIndex):
    draft = make_draft(title="Service Levels")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "service_levels"
    assert result.type_source == "dictionary"


def test_hint_wins_when_valid_and_not_other(real_index: FamilyIndex):
    draft = make_draft(title="General")  # matches nothing in the dictionary
    result = type_clause(draft, "security", real_index)
    assert result.clause_type == "security"
    assert result.type_source == "extract"


def test_hint_ignored_when_unknown_key(real_index: FamilyIndex):
    draft = make_draft(title="Indemnification")
    result = type_clause(draft, "not_a_real_family", real_index)
    assert result.clause_type == "indemnification"
    assert result.type_source == "dictionary"


def test_hint_ignored_when_other(real_index: FamilyIndex):
    draft = make_draft(title="Indemnification")
    result = type_clause(draft, "other", real_index)
    assert result.clause_type == "indemnification"
    assert result.type_source == "dictionary"


def test_hint_ignored_when_none_falls_back_to_dictionary(real_index: FamilyIndex):
    draft = make_draft(title="Confidentiality")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "confidentiality"
    assert result.type_source == "dictionary"


def test_no_match_falls_back_to_other(real_index: FamilyIndex):
    draft = make_draft(title="Flibbertigibbet Provisions")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "other"
    assert result.type_source == "none"


def test_compound_title_governing_law_and_disputes(real_index: FamilyIndex):
    draft = make_draft(title="Governing Law and Disputes")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "governing_law"
    assert result.type_source == "dictionary"
    assert "dispute_resolution" in result.issue_keys


def test_compound_title_no_spurious_issue_when_both_parts_same_family(real_index: FamilyIndex):
    # "Fees and Payment" -- both halves belong to the payment family.
    draft = make_draft(title="Fees and Payment")
    result = type_clause(draft, None, real_index)
    assert result.clause_type == "payment"
    assert result.issue_keys == ()


def test_fuzzy_match_above_cutoff(real_index: FamilyIndex):
    # Not an exact synonym, but close enough (token_sort_ratio >= 80).
    draft = make_draft(title="Limitation of Liability and Disclaimer of Warranties")
    result = type_clause(draft, None, real_index)
    # Either a direct fuzzy hit on the whole title, or a compound split that
    # resolves to limitation_of_liability with warranties as an issue.
    assert result.clause_type in ("limitation_of_liability", "warranties")
    assert result.type_source in ("dictionary",)


def test_preamble_kept_as_is(real_index: FamilyIndex):
    draft = make_draft(title=None, clause_type="preamble", type_source="none")
    result = type_clause(draft, "indemnification", real_index)
    assert result is draft
    assert result.clause_type == "preamble"
    assert result.type_source == "none"


def test_signature_block_kept_as_is(real_index: FamilyIndex):
    draft = make_draft(title=None, clause_type="signature_block", type_source="none")
    result = type_clause(draft, "security", real_index)
    assert result.clause_type == "signature_block"


# ---------------------------------------------------------------------------
# Sub-clause inheritance (spec item 5)
# ---------------------------------------------------------------------------


def test_subclause_inherits_parent_type_when_own_title_unmatched(real_index: FamilyIndex):
    parent = make_draft(
        ordinal=0, level=1, title="Indemnification", clause_type="indemnification",
        type_source="extract",
    )
    child = make_draft(
        ordinal=1, level=2, parent_ordinal=0, title="(a) Supplier shall defend Customer",
    )
    result = type_clause(child, None, real_index, parent=parent)
    assert result.clause_type == "indemnification"
    assert result.type_source == "extract"


def test_subclause_overrides_when_own_title_maps_to_family(real_index: FamilyIndex):
    parent = make_draft(
        ordinal=0, level=1, title="General", clause_type="other", type_source="none",
    )
    child = make_draft(
        ordinal=1, level=2, parent_ordinal=0, title="Confidentiality",
    )
    result = type_clause(child, None, real_index, parent=parent)
    assert result.clause_type == "confidentiality"
    assert result.type_source == "dictionary"


# ---------------------------------------------------------------------------
# load_family_index / clear_family_index_cache
# ---------------------------------------------------------------------------


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.execute_count = 0

    async def execute(self, _stmt):
        self.execute_count += 1
        return _FakeResult(self._rows)


class _FakeFamilyRow:
    def __init__(self, key, synonyms):
        self.key = key
        self.synonyms = synonyms


@pytest.mark.asyncio
async def test_load_family_index_reads_once_and_caches():
    clear_family_index_cache()
    rows = [_FakeFamilyRow("indemnification", ["indemnification", "indemnity"])]
    session = _FakeSession(rows)

    first = await load_family_index(session)
    second = await load_family_index(session)

    assert first is second
    assert session.execute_count == 1
    assert first.keys == {"indemnification"}
    clear_family_index_cache()


@pytest.mark.asyncio
async def test_clear_family_index_cache_forces_reload():
    clear_family_index_cache()
    rows_a = [_FakeFamilyRow("indemnification", [])]
    session_a = _FakeSession(rows_a)
    first = await load_family_index(session_a)
    assert first.keys == {"indemnification"}

    clear_family_index_cache()
    rows_b = [_FakeFamilyRow("security", [])]
    session_b = _FakeSession(rows_b)
    second = await load_family_index(session_b)

    assert second.keys == {"security"}
    assert first is not second
    clear_family_index_cache()


def test_no_import_of_old_clause_types_module():
    import re as _re

    import app.services.document_processing.clause_typing as mod

    source = Path(mod.__file__).read_text()
    assert not _re.search(r"^\s*(import|from)\s+\S*clause_types", source, _re.MULTILINE)
    assert "document_processing.clause_types" not in sys.modules
