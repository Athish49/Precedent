"""Clause typing (task 2.4; plan section 5.4).

Types each clause draft against the ``clause_family`` taxonomy: Extract's
hint wins when it names a valid, non-``other`` family; otherwise the
dictionary (exact synonym match, then a fuzzy match at 80) decides; otherwise
the clause is ``other``. A compound title such as "Governing Law and
Disputes" keeps one primary family and records the others in ``issue_keys``.

No import of the old ``document_processing/clause_types.py`` module: this
file replaces it (plan section 3.4, 5.9).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_processing.types import ClauseDraft

_FUZZY_CUTOFF = 80

# Clause families that keep the type set by the segmenter, never retyped.
_FIXED_FAMILIES = ("preamble", "signature_block")

# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------

# "Article 7 - ", "Section 9. ", case-insensitive.
_ARTICLE_SECTION_RE = re.compile(r"^(?:article|section)\s+\d+[a-z]?\s*[-:.)]*\s*", re.IGNORECASE)
# "7. ", "7.1.2 ", "12 ".
_NUMERIC_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*\s*[-:.)]*\s*")
# "(a) ", "(iv) ", case-insensitive. Requires both parens so ordinary words
# starting with "a" or a roman-numeral-looking letter are never touched.
_PAREN_PREFIX_RE = re.compile(r"^\((?:[a-z]{1,3}|[ivxlcdm]+)\)\s*", re.IGNORECASE)
_TRAILING_PUNCT_RE = re.compile(r"[\s.,;:\-]+$")

# Compound title split points: " and ", ";", ",", "/".
_COMPOUND_SPLIT_RE = re.compile(r"\s+and\s+|[;,/]")


def clean_title(title: str | None) -> str:
    """Strip numbering, "Article N"/"Section N" prefixes and trailing
    punctuation from a heading, then lower-case it.
    """
    if not title:
        return ""
    text = title.strip()
    text = _ARTICLE_SECTION_RE.sub("", text)
    text = _NUMERIC_PREFIX_RE.sub("", text)
    text = _PAREN_PREFIX_RE.sub("", text)
    text = _TRAILING_PUNCT_RE.sub("", text)
    return text.strip().lower()


def _split_compound(cleaned: str) -> list[str]:
    if not cleaned:
        return []
    parts = [p.strip() for p in _COMPOUND_SPLIT_RE.split(cleaned) if p.strip()]
    return parts or [cleaned]


# ---------------------------------------------------------------------------
# Family index
# ---------------------------------------------------------------------------


@dataclass
class FamilyIndex:
    """The clause_family taxonomy, as needed to type clauses.

    ``keys`` is every valid ``clause_family.key``. ``synonyms`` maps a
    lower-cased synonym phrase to the family key that owns it.
    """

    keys: set[str]
    synonyms: dict[str, str]

    @classmethod
    def from_rows(cls, rows: Any) -> "FamilyIndex":
        """Build an index from ``clause_family`` rows.

        Each row may be an ORM ``ClauseFamily`` instance (``.key``,
        ``.synonyms``) or a mapping with the same two keys.
        """
        keys: set[str] = set()
        synonyms: dict[str, str] = {}
        for row in rows:
            if isinstance(row, dict):
                key = row["key"]
                row_synonyms = row.get("synonyms") or ()
            else:
                key = row.key
                row_synonyms = row.synonyms or ()
            keys.add(key)
            for synonym in row_synonyms:
                synonyms[synonym.strip().lower()] = key
        return cls(keys=keys, synonyms=synonyms)


_family_index_cache: FamilyIndex | None = None


async def load_family_index(session: AsyncSession) -> FamilyIndex:
    """Load the ``FamilyIndex`` from the ``clause_family`` table.

    Cached per process. Call ``clear_family_index_cache()`` to force a
    reload (e.g. in tests, or after the table changes).
    """
    global _family_index_cache
    if _family_index_cache is not None:
        return _family_index_cache

    # Imported lazily so this module has no hard dependency on the ORM at
    # import time beyond what SQLAlchemy itself needs.
    from app.db.models.taxonomy import ClauseFamily

    result = await session.execute(select(ClauseFamily))
    rows = result.scalars().all()
    _family_index_cache = FamilyIndex.from_rows(rows)
    return _family_index_cache


def clear_family_index_cache() -> None:
    global _family_index_cache
    _family_index_cache = None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _match_single(text: str, index: FamilyIndex) -> str | None:
    """Exact synonym match, then fuzzy at the cutoff. ``None`` on no match."""
    if not text:
        return None
    exact = index.synonyms.get(text)
    if exact is not None:
        return exact
    best_family: str | None = None
    best_score = -1.0
    for synonym, family in index.synonyms.items():
        score = fuzz.token_sort_ratio(text, synonym)
        if score >= _FUZZY_CUTOFF and score > best_score:
            best_score = score
            best_family = family
    return best_family


def _dictionary_family(cleaned: str, parts: list[str], index: FamilyIndex) -> str | None:
    """The family the dictionary would choose for this cleaned title.

    Tries the whole cleaned title first (so a synonym that is itself a
    compound phrase, e.g. "fees and payment", matches directly); otherwise
    the first compound part that matches anything.
    """
    whole = _match_single(cleaned, index)
    if whole is not None:
        return whole
    for part in parts:
        match = _match_single(part, index)
        if match is not None:
            return match
    return None


def type_clause(
    draft: ClauseDraft,
    hint_family: str | None,
    index: FamilyIndex,
    *,
    parent: ClauseDraft | None = None,
) -> ClauseDraft:
    """Type one clause draft.

    ``hint_family`` is the family Extract's section list gave this clause
    (looked up by section number, then title), or ``None``. ``parent`` is
    the already-typed parent clause when ``draft.level >= 2``; sub-clauses
    inherit the parent's type and type_source unless their own title maps
    to a family.
    """
    if draft.clause_type in _FIXED_FAMILIES:
        return draft

    title = draft.title if draft.title is not None else draft.heading_text
    cleaned = clean_title(title)
    parts = _split_compound(cleaned)
    dict_family = _dictionary_family(cleaned, parts, index)

    if draft.level >= 2 and parent is not None:
        if dict_family is not None:
            chosen, type_source = dict_family, "dictionary"
        else:
            chosen, type_source = parent.clause_type, parent.type_source
    else:
        if hint_family is not None and hint_family in index.keys and hint_family != "other":
            chosen, type_source = hint_family, "extract"
        elif dict_family is not None:
            chosen, type_source = dict_family, "dictionary"
        else:
            chosen, type_source = "other", "none"

    part_matches = (_match_single(part, index) for part in parts)
    issue_keys = tuple(
        dict.fromkeys(family for family in part_matches if family is not None and family != chosen)
    )

    return replace(draft, clause_type=chosen, type_source=type_source, issue_keys=issue_keys)
