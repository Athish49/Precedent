"""Mapping, evidence, sanity checks and derived values (plan section 5.5).

Pure functions: Extract output + canonical document -> FieldValue / PartyDraft /
SignatoryDraft / SectionHint rows. No database, no network, no storage imports.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any

from app.services.document_processing.fields import REGISTRY, validate_value
from app.services.document_processing.types import (
    CanonicalDocument,
    ClauseDraft,
    FieldValue,
    PartyDraft,
    SectionHint,
    SignatoryDraft,
)

# ---------------------------------------------------------------------------
# Backward-compat aliases: some recorded fixtures (and live responses taken
# before a registry rename) use an older Extract field name. Mapping bridges
# the gap here, in code we own, rather than touching the registry or the
# fixtures.
# ---------------------------------------------------------------------------
_ALIASES: dict[str, str] = {
    "total_value_amount": "total_contract_value",
}

_BARE_ROLE_WORDS = {
    "customer",
    "supplier",
    "vendor",
    "company",
    "licensor",
    "licensee",
    "party",
}

_DATE_MIN = date(1990, 1, 1)
_DATE_MAX = date(2100, 12, 31)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str | None) -> str:
    return re.sub(r"\s+", " ", name or "").strip().lower()


def _extract_get(extract_value: dict, key: str) -> Any:
    if key in extract_value:
        return extract_value.get(key)
    alias = _ALIASES.get(key)
    if alias is not None:
        return extract_value.get(alias)
    return None


def _metadata_get(extract_metadata: dict, key: str) -> dict:
    if key in extract_metadata:
        return extract_metadata.get(key) or {}
    alias = _ALIASES.get(key)
    if alias is not None:
        return extract_metadata.get(alias) or {}
    return {}


def _page_for_offset(document: CanonicalDocument, offset: int) -> int | None:
    for block in document.blocks:
        if not block.dropped and block.char_start <= offset < block.char_end:
            return block.page
    return None


def _clause_ordinal_for_offset(
    level1_clauses: list[ClauseDraft], offset: int
) -> int | None:
    for clause in level1_clauses:
        if clause.char_start <= offset < clause.char_end:
            return clause.ordinal
    return None


def _exact_occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    occurrences = []
    start = 0
    while True:
        idx = text.find(quote, start)
        if idx == -1:
            break
        occurrences.append((idx, idx + len(quote)))
        start = idx + 1
    return occurrences


def _normalize_ws(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to a single space, keeping a map back to the
    original character offset of each normalised character."""
    norm_chars: list[str] = []
    orig_pos: list[int] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            norm_chars.append(" ")
            orig_pos.append(i)
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            i = j
        else:
            norm_chars.append(c)
            orig_pos.append(i)
            i += 1
    orig_pos.append(n)
    return "".join(norm_chars), orig_pos


def _ws_insensitive_occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    norm_text, orig_pos = _normalize_ws(text)
    norm_quote, _ = _normalize_ws(quote.strip())
    if not norm_quote:
        return []
    occurrences = []
    start = 0
    while True:
        idx = norm_text.find(norm_quote, start)
        if idx == -1:
            break
        orig_start = orig_pos[idx]
        last_char_idx = idx + len(norm_quote) - 1
        orig_end = orig_pos[last_char_idx] + 1
        occurrences.append((orig_start, orig_end))
        start = idx + 1
    return occurrences


def _pick_occurrence(
    document: CanonicalDocument,
    occurrences: list[tuple[int, int]],
    cited_page: int | None,
) -> tuple[int, int] | None:
    if not occurrences:
        return None
    if cited_page is not None:
        for start, end in occurrences:
            if _page_for_offset(document, start) == cited_page:
                return start, end
    return occurrences[0]


def _locate_quote(
    document: CanonicalDocument,
    quote: str,
    cited_page: int | None,
    level1_clauses: list[ClauseDraft],
) -> tuple[int, int, int | None] | None:
    if not quote:
        return None
    occurrences = _exact_occurrences(document.text, quote)
    if not occurrences:
        occurrences = _ws_insensitive_occurrences(document.text, quote)
    picked = _pick_occurrence(document, occurrences, cited_page)
    if picked is None:
        return None
    start, end = picked
    ordinal = _clause_ordinal_for_offset(level1_clauses, start)
    return start, end, ordinal


# ---------------------------------------------------------------------------
# 1 & 2: map_fields, evidence
# ---------------------------------------------------------------------------

def map_fields(
    extract_value: dict,
    extract_metadata: dict,
    document: CanonicalDocument,
    clauses: list[ClauseDraft],
) -> tuple[list[FieldValue], list[str]]:
    """Map Extract's output to FieldValue rows with evidence, sanity checks
    and derived values applied."""
    level1_clauses = [c for c in clauses if c.level == 1]
    results: list[FieldValue] = []

    for field_key, field_def in REGISTRY.items():
        raw = _extract_get(extract_value, field_key)
        if raw is None:
            continue
        if field_def.kind == "string_list" and raw == []:
            # Extend's array properties cannot be null (see fields.py's
            # schema builder); for a string_list field with nothing stated,
            # Extend returns [] rather than null. Treat an empty list the
            # same as absent -- do not store an empty FieldValue.
            continue
        if field_def.kind == "enum" and isinstance(raw, str):
            raw = raw.lower()
        value = validate_value(field_def, raw)
        if value is None:
            continue

        meta = _metadata_get(extract_metadata, field_key)
        citations = meta.get("citations") or []

        quote: str | None = None
        page: int | None = None
        char_start: int | None = None
        char_end: int | None = None
        clause_ordinal: int | None = None
        confidence = "low"

        if citations:
            citation = citations[0]
            cited_quote = citation.get("referenceText")
            cited_page = ((citation.get("page") or {}).get("number"))
            quote = cited_quote
            page = cited_page
            if cited_quote:
                located = _locate_quote(document, cited_quote, cited_page, level1_clauses)
                if located is not None:
                    char_start, char_end, clause_ordinal = located
                    quote = document.text[char_start:char_end]
                    page = _page_for_offset(document, char_start) or cited_page
                    confidence = "high"

        results.append(
            FieldValue(
                field_key=field_key,
                value=value,
                source="extract",
                confidence=confidence,
                quote=quote,
                page=page,
                char_start=char_start,
                char_end=char_end,
                clause_ordinal=clause_ordinal,
            )
        )

    results, warnings = _apply_sanity_checks(results)
    results = _add_derived(results)
    return results, warnings


def _apply_sanity_checks(
    results: list[FieldValue],
) -> tuple[list[FieldValue], list[str]]:
    warnings: list[str] = []
    dropped: set[str] = set()
    by_key = {fv.field_key: fv for fv in results}

    for fv in results:
        field_def = REGISTRY[fv.field_key]
        value = fv.value

        if fv.field_key.endswith("percent"):
            if not (0 <= value <= 100):
                dropped.add(fv.field_key)
                warnings.append(f"dropped:{fv.field_key}:percent_out_of_range")
            continue

        if field_def.kind == "date":
            if not (_DATE_MIN <= value <= _DATE_MAX):
                dropped.add(fv.field_key)
                warnings.append(f"dropped:{fv.field_key}:date_out_of_range")
            continue

        if field_def.kind in ("integer", "number"):
            if value < 0:
                dropped.add(fv.field_key)
                warnings.append(f"dropped:{fv.field_key}:negative_value")
            continue

    if (
        "expiry_date" in by_key
        and "effective_date" in by_key
        and "expiry_date" not in dropped
        and "effective_date" not in dropped
    ):
        if by_key["expiry_date"].value <= by_key["effective_date"].value:
            dropped.add("expiry_date")
            warnings.append("dropped:expiry_date:expiry_not_after_effective")

    filtered = [fv for fv in results if fv.field_key not in dropped]
    return filtered, warnings


# ---------------------------------------------------------------------------
# 4: derived values
# ---------------------------------------------------------------------------

def _add_months(start: date, months: int) -> date:
    total_month = start.month - 1 + months
    year = start.year + total_month // 12
    month = total_month % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_derived(results: list[FieldValue]) -> list[FieldValue]:
    by_key = {fv.field_key: fv for fv in results}
    if (
        "expiry_date" not in by_key
        and "effective_date" in by_key
        and "initial_term_months" in by_key
    ):
        effective = by_key["effective_date"].value
        months = by_key["initial_term_months"].value
        expiry = _add_months(effective, months)
        results = list(results) + [
            FieldValue(
                field_key="expiry_date",
                value=expiry,
                source="derived",
                confidence=None,
                quote=None,
                page=None,
                char_start=None,
                char_end=None,
                clause_ordinal=None,
            )
        ]
    return results


# ---------------------------------------------------------------------------
# 5: map_parties
# ---------------------------------------------------------------------------

def map_parties(extract_value: dict, document: CanonicalDocument) -> list[PartyDraft]:
    raw_parties = extract_value.get("parties") or []
    seen: set[str] = set()
    result: list[PartyDraft] = []

    for raw in raw_parties:
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        norm_name = _normalize_name(name)
        role_label = raw.get("role_label")
        norm_role = _normalize_name(role_label) if role_label else ""

        if norm_role and norm_name == norm_role:
            continue
        if norm_name in _BARE_ROLE_WORDS:
            continue
        if norm_name in seen:
            continue
        seen.add(norm_name)

        result.append(
            PartyDraft(
                name=name,
                role_label=role_label,
                entity_type=raw.get("entity_type"),
                jurisdiction=raw.get("jurisdiction"),
                address=raw.get("address"),
            )
        )

    return result


# ---------------------------------------------------------------------------
# 6: map_signatories
# ---------------------------------------------------------------------------

def map_signatories(extract_value: dict) -> list[SignatoryDraft]:
    raw_signatories = extract_value.get("signatories") or []
    result: list[SignatoryDraft] = []

    for raw in raw_signatories:
        signed_date: date | None = None
        raw_date = raw.get("signed_date")
        if raw_date:
            try:
                if isinstance(raw_date, date):
                    signed_date = raw_date
                else:
                    signed_date = date.fromisoformat(str(raw_date))
            except ValueError:
                signed_date = None

        is_signed = raw.get("is_signed")
        if not isinstance(is_signed, bool):
            is_signed = None

        result.append(
            SignatoryDraft(
                printed_name=raw.get("printed_name"),
                title=raw.get("title"),
                party_name=raw.get("party_name"),
                is_signed=is_signed,
                signed_date=signed_date,
            )
        )

    return result


# ---------------------------------------------------------------------------
# 7: map_hints, map_title, map_contract_type
# ---------------------------------------------------------------------------

def map_hints(extract_value: dict) -> list[SectionHint]:
    raw_clauses = extract_value.get("clauses") or []
    return [
        SectionHint(
            section_number=raw.get("section_number"),
            title=raw.get("title"),
            family=raw.get("family"),
        )
        for raw in raw_clauses
    ]


def map_title(extract_value: dict) -> str | None:
    title = extract_value.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def map_contract_type(extract_value: dict, allowed_keys: list[str]) -> str | None:
    contract_type = extract_value.get("contract_type")
    if isinstance(contract_type, str) and contract_type in allowed_keys:
        return contract_type
    return None
