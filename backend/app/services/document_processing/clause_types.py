"""Clause-type normalizer (T-022, retired to DB-backed synonyms by task 5.5).

Maps raw heading text → canonical clause_type string using an exact-match
synonym lookup, with rapidfuzz fuzzy fallback.  Purely deterministic — no LLM
involved.

The synonym→clause-family-key mapping used to be a hardcoded dict here. It
now comes from the ``clause_family`` table (``app/db/models/taxonomy.py``,
seeded by migration ``010`` + ``014``, never from the seed folder) and is
cached in this module at process startup via :func:`load_synonym_cache`
(called from ``app.main``'s lifespan). ``normalize_clause_type`` itself stays
a fast, synchronous, pure function with no DB round-trip per call — it just
reads the module-level cache populated once.

Tests that need the mapping without a live database call
:func:`set_synonym_cache` directly (see ``tests/conftest.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rapidfuzz import fuzz, process

from app.services.document_processing.segmentation import (
    _RE_ALPHA,
    _RE_DECIMAL,
    _RE_ROMAN,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_FUZZY_CUTOFF = 80

# ---------------------------------------------------------------------------
# Process-wide synonym cache: lowercased synonym → canonical clause-family key.
#
# ``None`` means "not populated yet". ``normalize_clause_type`` fails loudly
# rather than silently falling back to an empty/partial mapping, so a missing
# startup hook is caught immediately instead of quietly returning "other"
# for everything.
# ---------------------------------------------------------------------------
_synonym_map: dict[str, str] | None = None
_synonym_keys: list[str] = []


def set_synonym_cache(mapping: dict[str, str]) -> None:
    """Populate the module-level synonym cache directly.

    Used by :func:`load_synonym_cache` (production, from the DB) and by tests
    that need a known mapping without a live database connection.
    """
    global _synonym_map, _synonym_keys
    _synonym_map = dict(mapping)
    _synonym_keys = list(_synonym_map.keys())


def clear_synonym_cache() -> None:
    """Reset the cache to "not populated". Used by tests for isolation."""
    global _synonym_map, _synonym_keys
    _synonym_map = None
    _synonym_keys = []


async def load_synonym_cache(session: "AsyncSession") -> None:
    """Populate the synonym cache from the ``clause_family`` table.

    Called once at application startup (``app.main``'s lifespan), *not* per
    request and *not* per call to ``normalize_clause_type`` — this is the
    only place clause-type normalization touches the database.
    """
    from app.db.repositories.taxonomy_repo import list_clause_families

    families = await list_clause_families(session)
    mapping: dict[str, str] = {}
    for family in families:
        for synonym in family.synonyms:
            mapping[synonym] = family.key
    set_synonym_cache(mapping)


def _require_cache() -> tuple[dict[str, str], list[str]]:
    if _synonym_map is None:
        raise RuntimeError(
            "clause_types synonym cache not populated. Call "
            "`load_synonym_cache(session)` during app startup (see "
            "app.main's lifespan), or `set_synonym_cache(mapping)` in tests."
        )
    return _synonym_map, _synonym_keys


def _strip_leading_numbering(text: str) -> str:
    """Strip a single leading enumeration marker (e.g. ``"9."``, ``"1.1"``,
    ``"(a)"``, ``"iv."``) from *text*.

    The segmenter (``segmentation.py``) stores ``heading_text`` as the raw
    paragraph text, numbering marker included — it never strips the prefix
    it used to *detect* the heading. Left in place, that prefix drags down
    matching here: an exact match like ``"9. audit"`` no longer equals the
    dictionary key ``"audit"``, and short canonical names (audit, term,
    payment, …) are disproportionately penalized by fuzzy scoring because the
    numbering makes up a large fraction of the overall string. Stripping it
    first — using the same numbering patterns the segmenter itself matches —
    fixes that without weakening the fuzzy threshold.
    """
    for pattern in (_RE_DECIMAL, _RE_ALPHA, _RE_ROMAN):
        match = pattern.match(text)
        if match:
            return text[match.end() :]
    return text


def normalize_clause_type(heading_text: str | None) -> str:
    """Map *heading_text* to a canonical clause type string.

    Returns ``"other"`` for unknown headings or ``None`` input.

    Resolution order:
    1. ``None`` → ``"other"``
    2. Strip a leading numbering marker, if any (see ``_strip_leading_numbering``)
    3. Exact match in synonym dictionary → canonical type
    4. Fuzzy match (token_sort_ratio ≥ 80) → canonical type of best match
    5. No match → ``"other"``
    """
    if heading_text is None:
        return "other"

    stripped_text = _strip_leading_numbering(heading_text.strip())
    normalized = stripped_text.strip().lower()
    if not normalized:
        return "other"

    synonyms, synonym_keys = _require_cache()

    # Exact match
    if normalized in synonyms:
        return synonyms[normalized]

    # Fuzzy match
    result = process.extractOne(
        normalized,
        synonym_keys,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=_FUZZY_CUTOFF,
    )
    if result is not None:
        matched_key = result[0]
        return synonyms[matched_key]

    return "other"
