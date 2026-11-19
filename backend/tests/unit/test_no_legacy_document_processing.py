"""Removal guard for the old document-processing pipeline (doc_proc task 5.1).

Encodes the checks from ``document_processing_plan.md`` section 11.3 so a
later change that brings any of the old pipeline back fails CI:

1. The five deleted files do not exist.
2. The four greps from section 11.3 find nothing *unexpected* — each comes
   with a small, literal allowlist of lines already in the tree on the day
   this guard was written, each one justified below. A real regression
   (a new import of the deleted modules, a revived old DTO, a live read of
   a removed column) shows up as a *new* hit this allowlist does not cover,
   and fails the test.

The allowlists are intentionally exact-line matches, not path or keyword
exclusions: anything added later to an allowlisted file that is not one of
these exact lines still fails the test.

None of these searches scan the seed package: a test in this directory
must not read a file belonging to that package at all (seed isolation,
``playbook_implementation.md`` section 3.0 rule 1, enforced by
``test_seed_isolation.py``) — not even to grep it for a stale import. The
equivalent check for the seed package — that nothing in it imports a
deleted module — was run by hand for doc_proc task 5.3 and is covered by
the seed package's own corpus test, which imports nothing from the old
pipeline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_BACKEND = Path(__file__).parent.parent.parent
_FRONTEND = _BACKEND.parent / "frontend"

_DELETED_FILES = (
    "app/services/document_processing/parsers.py",
    "app/services/document_processing/extraction.py",
    "app/services/document_processing/service.py",
    "app/services/document_processing/segmentation.py",
    "app/services/document_processing/clause_types.py",
)


def test_deleted_files_do_not_exist() -> None:
    for relative in _DELETED_FILES:
        path = _BACKEND / relative
        assert not path.exists(), f"deleted file still exists: {path}"


_SELF = Path(__file__).resolve()


def _grep(pattern: str, paths: tuple[Path, ...]) -> list[str]:
    """Run ``grep -rnE pattern`` over the given paths (skipping any that
    don't exist, e.g. an optional frontend checkout) and return each hit's
    line content, trimmed, with the ``file:line:`` prefix stripped.

    Excludes this guard file itself: it necessarily names every pattern it
    searches for (in the pattern strings, the allowlists, and this
    docstring), so it would otherwise always match its own scan.
    """
    existing = [str(p) for p in paths if p.exists()]
    if not existing:
        return []
    result = subprocess.run(
        ["grep", "-rnIE", "--exclude-dir=__pycache__", pattern, *existing],
        capture_output=True,
        text=True,
    )
    hits: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        file_part, _, rest = line.partition(":")
        if Path(file_part).resolve() == _SELF:
            continue
        # Strip the "lineno:" prefix grep -n adds, keeping only the
        # matched line's own text for allowlist comparison.
        _, _, content = rest.partition(":")
        hits.append(content.strip())
    return hits


# ---------------------------------------------------------------------------
# Search 1: pdfplumber|spacy|en_core_web|dateutil
#
# Removed outright in task 5.1 (pdfplumber, spacy) or never a dependency
# here (en_core_web, dateutil). No legitimate hit exists anywhere in the
# scope, so this allowlist is empty.
# ---------------------------------------------------------------------------

_SEARCH_1_PATTERN = r"pdfplumber|spacy|en_core_web|dateutil"
_SEARCH_1_PATHS = (
    _BACKEND / "app",
    _BACKEND / "tests",
    _BACKEND / "scripts",
    _BACKEND / "pyproject.toml",
)
_SEARCH_1_ALLOWED: frozenset[str] = frozenset()


def test_search_1_no_pdfplumber_spacy_en_core_web_dateutil() -> None:
    hits = _grep(_SEARCH_1_PATTERN, _SEARCH_1_PATHS)
    violations = [h for h in hits if h not in _SEARCH_1_ALLOWED]
    assert not violations, "search 1 found unexpected hits:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Search 2: old DTOs/types/functions from the deleted modules.
#
# Every allowed hit below is one of:
#   (a) a guard-style assertion that the name is *absent* (the deleted
#       name appears only as a string literal being checked for);
#   (b) a comment/docstring explaining what was removed and why;
#   (c) ``extract_metadata`` used as a plain parameter/variable name in the
#       *new* pipeline (mapping.py, pipeline.py) for the Extract API's own
#       metadata dict — a different concept from the deleted
#       ``extraction.extract_metadata()`` function, which happens to share
#       the name.
# ---------------------------------------------------------------------------

_SEARCH_2_PATTERN = (
    r"ParsedDocument|StructureSignal|SegmentedClause|ContractMetadataDTO|PartyDTO|"
    r"ProcessedContract|extract_metadata|_try_parse_date|_source_format_from_filename|"
    r"_SYNONYMS|normalize_clause_type|classify_contract_type|contract_type_classify"
)
_SEARCH_2_PATHS = (
    _BACKEND / "app",
    _BACKEND / "tests",
    _BACKEND / "scripts",
)
_SEARCH_2_ALLOWED: frozenset[str] = frozenset(
    {
        # app/schemas/documents.py — explains why the new response models
        # don't reuse the old DTO.
        "re-using any old-pipeline DTO (``ProcessedContract`` et al., which belong to",
        # app/services/repository/service.py — explains what replaced the
        # deleted parsers.parse / _source_format_from_filename call.
        "#    parsers.parse / _source_format_from_filename.",
        # app/services/document_processing/mapping.py and pipeline.py —
        # ``extract_metadata`` as a parameter/variable name for the new
        # pipeline's Extract-API metadata dict (see docstring above).
        "extract_metadata: dict,",
        "extract_value, extract_metadata, document, typed_clauses",
        "def _metadata_get(extract_metadata: dict, key: str) -> dict:",
        "if key in extract_metadata:",
        "return extract_metadata.get(key) or {}",
        "return extract_metadata.get(alias) or {}",
        "meta = _metadata_get(extract_metadata, field_key)",
        # tests/unit/test_documents_api.py — asserts ProcessedContract is
        # NOT in the route source.
        'assert "ProcessedContract" not in source',
        # tests/unit/test_context_capture.py — asserts classify_contract_type
        # was removed.
        "def test_classify_contract_type_removed() -> None:",
        'assert not hasattr(cc, "classify_contract_type")',
        # tests/integration/test_determinism.py — explains what was removed
        # from this file and points at its replacement.
        "# The old pipeline's segmentation-determinism case (same ParsedDocument ->",
        "# identical SegmentedClause list) was removed with parsers.py and",
    }
)


def test_search_2_no_old_dtos_or_functions() -> None:
    hits = _grep(_SEARCH_2_PATTERN, _SEARCH_2_PATHS)
    violations = [h for h in hits if h not in _SEARCH_2_ALLOWED]
    assert not violations, "search 2 found unexpected hits:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Search 3: document_processing.(parsers|extraction|service|segmentation|clause_types)
#
# Both allowed hits are guard/explanatory text naming the deleted dotted
# path, not an import of it.
# ---------------------------------------------------------------------------

_SEARCH_3_PATTERN = r"document_processing\.(parsers|extraction|service|segmentation|clause_types)"
_SEARCH_3_PATHS = (
    _BACKEND / "app",
    _BACKEND / "tests",
    _BACKEND / "scripts",
)
_SEARCH_3_ALLOWED: frozenset[str] = frozenset(
    {
        # tests/unit/test_dp_clause_typing.py — asserts the old module was
        # never imported.
        'assert "document_processing.clause_types" not in sys.modules',
    }
)


def test_search_3_no_import_of_deleted_modules() -> None:
    hits = _grep(_SEARCH_3_PATTERN, _SEARCH_3_PATHS)
    violations = [h for h in hits if h not in _SEARCH_3_ALLOWED]
    assert not violations, "search 3 found unexpected hits:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Search 4: financial_fields|milestone_dates|notice_period_days
#
# ``notice_period_days`` is also the name of a legitimate *new* Tier-1
# field (fields.py), a smart-search filter (core/llm/schemas/search.py and
# its prompt) and a still-live ``contract_metadata`` column read by nothing
# but the migration-downgrade SQL tests below — none of that is the deleted
# ``ContractMetadata.notice_period_days`` *Python attribute* this task
# removed. ``financial_fields``/``milestone_dates`` only appear in: the ORM
# model's own explanatory comment, the new removal-guard assertions in
# test_dp_schema_b_models.py, and migration-018 SQL-text tests that
# legitimately exercise the *downgrade* path (which still writes the old,
# not-yet-dropped column names as raw SQL — task 5.2 drops the columns).
# ---------------------------------------------------------------------------

_SEARCH_4_PATTERN = r"financial_fields|milestone_dates|notice_period_days"
_SEARCH_4_PATHS = (
    _BACKEND / "app",
    _BACKEND / "db",
    _BACKEND / "tests",
    _FRONTEND / "lib",
    _FRONTEND / "components",
    _FRONTEND / "app",
)
_SEARCH_4_ALLOWED: frozenset[str] = frozenset(
    {
        # app/core/llm/schemas/search.py — SmartSearchFilters field.
        "notice_period_days: int | None = Field(",
        # app/core/llm/prompts/smart_search_filters.md — the same filter,
        # documented for the model.
        '"notice_period_days": "<integer or null>",',
        "- **Metadata fields** (`contract_type`, `status`, `auto_renewal`, "
        "`notice_period_days`, `governing_law`, `effective_date_from`, "
        "`effective_date_to`): Use when the user mentions facts about the "
        "contract structure, dates, or administrative properties.",
        '"notice_period_days": 30,',
        '"notice_period_days": null,',
        # app/db/models/contract.py — explanatory comment on the removal.
        "# ``parties``, ``liability_cap``, ``notice_period_days``, ``payment_terms``,",
        "# ``financial_fields``, ``milestone_dates`` and ``extracted`` (the old",
        # app/api/routes/documents.py — explanatory comment.
        "# legacy columns (parties/liability_cap/financial_fields/... — those belong",
        # app/services/document_processing/fields.py — Tier-1 field registry.
        '"notice_period_days": FieldDef(',
        'key="notice_period_days",',
        # tests/unit/test_analytics_views_sql.py — migration 018's upgrade
        # (checks these are GONE) and downgrade (checks the old, still
        # physically present columns come back) paths.
        '"""The point of 018: no more financial_fields / liability_cap (JSON) /',
        "notice_period_days / payment_terms — only the typed projection columns.",
        '"""',
        'assert "financial_fields" not in combined',
        'assert "milestone_dates" not in combined',
        'assert "cm.notice_period_days" not in combined',
        'assert "cm.financial_fields" in combined',
        'assert "cm.notice_period_days" in combined',
        # tests/unit/test_smart_search.py — the SmartSearchFilters field,
        # not the ORM attribute.
        "FAKE_FILTERS_METADATA = SmartSearchFilters(auto_renewal=True, notice_period_days=30)",
        "assert result.filters_used.notice_period_days == 30",
        # tests/unit/test_dp_schema_b_models.py — this task's own removal
        # guard, naming the removed attributes to assert they're gone.
        "# The old untyped columns (parties, financial_fields, milestone_dates,",
        "# liability_cap, notice_period_days, payment_terms, extracted) were",
        '"financial_fields",',
        '"milestone_dates",',
        '"notice_period_days",',
        # tests/fixtures/ingest/extract_schema_snapshot.json — the Extract
        # schema's own field name, unrelated to the ORM column.
        '"notice_period_days": {',
        # tests/unit/test_dp_drop_legacy_columns_models.py and
        # test_doc_proc_drop_legacy_columns_migration.py — doc_proc task
        # 5.2's own removal guard and migration-019 render test, naming the
        # now-dropped column names to assert they're gone (model side) or
        # that the downgrade recreates them, empty (migration-render SQL
        # side; migration 019 physically drops these columns for real, so
        # these are the last legitimate hits for this search).
        'assert "ALTER TABLE contract_metadata ADD COLUMN financial_fields JSONB" in down_sql',
        'assert "ALTER TABLE contract_metadata ADD COLUMN milestone_dates JSONB" in down_sql',
        'assert "ALTER TABLE contract_metadata ADD COLUMN notice_period_days INTEGER" in down_sql',
    }
)


def test_search_4_no_legacy_metadata_field_reads() -> None:
    hits = _grep(_SEARCH_4_PATTERN, _SEARCH_4_PATHS)
    violations = [h for h in hits if h not in _SEARCH_4_ALLOWED]
    assert not violations, "search 4 found unexpected hits:\n" + "\n".join(violations)
