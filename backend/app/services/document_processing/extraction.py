"""Metadata extraction from canonical contract text.

Uses spaCy NER for entity recognition and regex for structured field extraction.
No LLM calls — pure deterministic extraction.
"""

from __future__ import annotations

import re
import string
from datetime import date, datetime
from typing import Any

import spacy
from pydantic import BaseModel

# ── spaCy singleton ────────────────────────────────────────────────────────────

_nlp: spacy.language.Language | None = None


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


# ── Data-transfer objects ──────────────────────────────────────────────────────


class PartyDTO(BaseModel):
    display_name: str  # e.g. "Acme, Inc."
    normalized_name: str  # lowercased, punctuation-stripped: "acme inc"


class ContractMetadataDTO(BaseModel):
    parties: list[dict[str, Any]]  # [{name, role}]
    effective_date: date | None
    expiry_date: date | None
    governing_law: str | None
    liability_cap: dict[str, Any] | None  # {value: float, currency: str} or None
    notice_period_days: int | None
    auto_renewal: bool | None
    payment_terms: str | None
    financial_fields: dict[str, Any]  # dict of any extracted financial values
    milestone_dates: list[date]
    extracted: dict[str, Any]  # catch-all for remaining fields


# ── Helpers ────────────────────────────────────────────────────────────────────

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _normalize_name(name: str) -> str:
    """Lowercase and strip punctuation, collapse whitespace."""
    return " ".join(name.translate(_PUNCT_TABLE).lower().split())


def _try_parse_date(text: str) -> date | None:
    """Attempt to parse a date string, returning None on failure."""
    text = text.strip().rstrip(".,;")
    # Try dateutil first
    try:
        from dateutil import parser as dateutil_parser  # type: ignore[import]

        return dateutil_parser.parse(text, fuzzy=True).date()
    except Exception:
        pass
    # Fallback: common formats
    for fmt in ("%B %d, %Y", "%d %B %Y", "%Y-%m-%d", "%B %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value_str: str, multiplier_str: str | None) -> float:
    """Parse a numeric string (with possible commas) and apply multiplier."""
    amount = float(value_str.replace(",", ""))
    if multiplier_str:
        m = multiplier_str.lower()
        if m == "million":
            amount *= 1_000_000
        elif m == "thousand":
            amount *= 1_000
    return amount


# ── Field extractors ───────────────────────────────────────────────────────────


def _extract_effective_date(text: str) -> date | None:
    # Patterns that allow commas within the date (e.g. "January 1, 2024")
    # Terminated by newline or by comma-then-whitespace-then-newline/word.
    patterns = [
        r"effective\s+as\s+of\s+(.+?)(?:\s*\n)",
        r"dated\s+(.+?)(?:\s*\n)",
        r"entered\s+into\s+(?:as\s+of\s+)?(.+?)(?:\s*\n)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result = _try_parse_date(m.group(1))
            if result is not None:
                return result
    return None


def _extract_expiry_date(text: str) -> date | None:
    patterns = [
        r"expir(?:es?|ation\s+date)\s*(?:on|:)?\s*(.+?)(?:\s*\n|\s*\.)",
        r"terminat(?:es?|ion\s+date)\s*(?:on|:)?\s*(.+?)(?:\s*\n|\s*\.)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result = _try_parse_date(m.group(1))
            if result is not None:
                return result
    return None


def _extract_governing_law(text: str) -> str | None:
    patterns = [
        r"governed\s+by\s+(?:the\s+laws?\s+of\s+)?(.+?)(?:\s*\.|,|\n)",
        r"laws?\s+of\s+(?:the\s+[Ss]tate\s+of\s+)?(.+?)(?:\s*\.|,|\n)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            value = m.group(1).strip().rstrip(".,;")
            if value:
                return value
    return None


def _extract_liability_cap(text: str) -> dict[str, Any] | None:
    patterns = [
        (
            r"(?:aggregate\s+)?liabilit[yi]\s+(?:cap|limit(?:ation)?)\s*"
            r"(?:of|shall\s+not\s+exceed)\s*\$?([\d,]+(?:\.\d+)?)"
            r"(?:\s*(million|thousand|USD|EUR|GBP))?"
        ),
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                value = _parse_amount(m.group(1), m.group(2))
                # Determine currency from multiplier token or default USD
                currency_token = (m.group(2) or "").upper()
                currency = currency_token if currency_token in ("USD", "EUR", "GBP") else "USD"
                return {"value": value, "currency": currency}
            except Exception:
                pass
    return None


def _extract_notice_period(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(?:calendar\s+)?days?\s+(?:prior\s+)?notice", text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def _extract_auto_renewal(text: str) -> bool | None:
    patterns = [
        r"auto(?:matically)?\s*renew",
        r"shall\s+automatically\s+renew",
    ]
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return None


def _extract_payment_terms(text: str) -> str | None:
    # "Net N" shorthand
    m = re.search(r"\bnet\s+(\d+)\b", text, re.IGNORECASE)
    if m:
        return f"Net {m.group(1)}"
    # Longer patterns
    m = re.search(
        r"(?:payment|invoice)s?\s+(?:are\s+)?due\s+(?:within\s+)?(.+?)(?:\s*\.|,|\n)",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip().rstrip(".,;")
    return None


def _extract_financial_fields(text: str) -> dict[str, str]:
    """Extract all dollar-amount mentions with surrounding context as key."""
    results: dict[str, str] = {}
    pattern = r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|thousand))?"
    for m in re.finditer(pattern, text, re.IGNORECASE):
        start = max(0, m.start() - 10)
        context = text[start : m.start()].strip()
        key = re.sub(r"\s+", "_", context[-20:].strip()) or f"amount_{m.start()}"
        results[key] = m.group(0)
    return results


def _extract_milestone_dates(text: str) -> list[date]:
    """Extract dates associated with milestone/deadline keywords."""
    milestone_dates: list[date] = []
    pattern = r"(?:milestone|deliverable|deadline|due\s+by)\s*[:–-]?\s*(.+?)(?:\s*\.|,|\n)"
    for m in re.finditer(pattern, text, re.IGNORECASE):
        parsed = _try_parse_date(m.group(1))
        if parsed is not None:
            milestone_dates.append(parsed)
    return milestone_dates


# ── Party extraction ───────────────────────────────────────────────────────────


def _extract_parties(text: str) -> list[PartyDTO]:
    """Run spaCy NER to extract PERSON and ORG entities as deduplicated parties."""
    nlp = _get_nlp()
    doc = nlp(text[:50000])
    seen: dict[str, PartyDTO] = {}
    for ent in doc.ents:
        if ent.label_ in ("PERSON", "ORG"):
            display = ent.text.strip()
            normalized = _normalize_name(display)
            if normalized and normalized not in seen:
                seen[normalized] = PartyDTO(display_name=display, normalized_name=normalized)
    return list(seen.values())


# ── Public API ─────────────────────────────────────────────────────────────────


def extract_metadata(canonical_text: str) -> tuple[ContractMetadataDTO, list[PartyDTO]]:
    """Extract metadata and party list from canonical_text.

    Returns (metadata_dto, parties).
    """
    text = canonical_text

    # Extract parties via NER
    parties_dtos = _extract_parties(text)
    parties_list = [{"name": p.display_name, "role": "unknown"} for p in parties_dtos]

    # Extract individual fields
    effective_date = _extract_effective_date(text)
    expiry_date = _extract_expiry_date(text)
    governing_law = _extract_governing_law(text)
    liability_cap = _extract_liability_cap(text)
    notice_period_days = _extract_notice_period(text)
    auto_renewal = _extract_auto_renewal(text)
    payment_terms = _extract_payment_terms(text)
    financial_fields = _extract_financial_fields(text)
    milestone_dates = _extract_milestone_dates(text)

    metadata = ContractMetadataDTO(
        parties=parties_list,
        effective_date=effective_date,
        expiry_date=expiry_date,
        governing_law=governing_law,
        liability_cap=liability_cap,
        notice_period_days=notice_period_days,
        auto_renewal=auto_renewal,
        payment_terms=payment_terms,
        financial_fields=financial_fields,
        milestone_dates=milestone_dates,
        extracted={},
    )
    return metadata, parties_dtos
