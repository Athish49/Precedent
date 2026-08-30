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
    # Core parties & dates
    parties: list[dict[str, Any]]  # [{name, role}]
    effective_date: date | None
    expiry_date: date | None
    # Term
    initial_term_days: int | None
    renewal_term_days: int | None
    # Governing law & dispute resolution
    governing_law: str | None
    dispute_resolution: str | None  # "arbitration" | "litigation" | "mediation"
    arbitration_venue: str | None
    # Financial
    liability_cap: dict[str, Any] | None  # {value: float, currency: str}
    indemnification_cap: dict[str, Any] | None  # {value: float, currency: str}
    total_contract_value: dict[str, Any] | None  # {value: float, currency: str}
    currency: str | None
    payment_terms: str | None
    financial_fields: dict[str, Any]  # all dollar-amount mentions
    # Renewal & termination
    auto_renewal: bool | None
    termination_for_convenience: bool | None
    termination_notice_days: int | None
    # Obligations
    notice_period_days: int | None
    notice_address: str | None
    milestone_dates: list[date]
    warranty_period_days: int | None
    # IP & confidentiality
    confidentiality_period_years: int | None
    ip_ownership: str | None  # "client" | "vendor" | "joint" | "background"
    # Restrictions
    assignment_allowed: bool | None
    non_compete_months: int | None
    non_solicitation_months: int | None
    # SLA
    sla_uptime_percent: float | None
    sla_response_time_hours: int | None
    # Compliance
    data_processing_agreement: bool | None
    gdpr_applicable: bool | None
    # Boilerplate presence flags
    force_majeure: bool | None
    entire_agreement: bool | None
    amendments_require_writing: bool | None
    limitation_of_liability_exclusions: list[str]
    survival_clauses: list[str]
    # Catch-all
    extracted: dict[str, Any]


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


# ── Additional field extractors ────────────────────────────────────────────────


def _extract_initial_term(text: str) -> int | None:
    m = re.search(
        r"(?:initial\s+term|term\s+of\s+(?:this\s+)?agreement)\s+(?:shall\s+be\s+|of\s+)?(\d+)\s*(year|month|day)",
        text, re.IGNORECASE,
    )
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith("year"):
            return n * 365
        if unit.startswith("month"):
            return n * 30
        return n
    return None


def _extract_renewal_term(text: str) -> int | None:
    m = re.search(
        r"renew(?:al|s)?\s+(?:for\s+)?(?:successive\s+)?(?:period[s]?\s+of\s+)?"
        r"(\d+)[- ](year|month|day)",
        text, re.IGNORECASE,
    )
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith("year"):
            return n * 365
        if unit.startswith("month"):
            return n * 30
        return n
    return None


def _extract_dispute_resolution(text: str) -> str | None:
    if re.search(r"\barbitrat", text, re.IGNORECASE):
        return "arbitration"
    if re.search(r"\bmediat", text, re.IGNORECASE):
        return "mediation"
    if re.search(r"\blitigation\b|\bcourt[s]?\b|\bjurisdiction\b", text, re.IGNORECASE):
        return "litigation"
    return None


def _extract_arbitration_venue(text: str) -> str | None:
    m = re.search(
        r"arbitration\s+(?:shall\s+be\s+)?(?:conducted\s+)?in\s+([A-Z][a-zA-Z ,]+?)(?:\s*\.|,|\n)",
        text, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _extract_indemnification_cap(text: str) -> dict[str, Any] | None:
    m = re.search(
        r"indemnif\w+\s+(?:obligation[s]?\s+)?(?:shall\s+not\s+exceed|cap(?:ped\s+at)?)\s*"
        r"\$?([\d,]+(?:\.\d+)?)(?:\s*(million|thousand|USD|EUR|GBP))?",
        text, re.IGNORECASE,
    )
    if m:
        try:
            value = _parse_amount(m.group(1), m.group(2))
            token = (m.group(2) or "").upper()
            currency = token if token in ("USD", "EUR", "GBP") else "USD"
            return {"value": value, "currency": currency}
        except Exception:
            pass
    return None


def _extract_total_contract_value(text: str) -> dict[str, Any] | None:
    m = re.search(
        r"(?:total\s+contract\s+value|total\s+fees?|aggregate\s+fees?)\s*(?:of|:)?\s*"
        r"\$?([\d,]+(?:\.\d+)?)(?:\s*(million|thousand|USD|EUR|GBP))?",
        text, re.IGNORECASE,
    )
    if m:
        try:
            value = _parse_amount(m.group(1), m.group(2))
            token = (m.group(2) or "").upper()
            currency = token if token in ("USD", "EUR", "GBP") else "USD"
            return {"value": value, "currency": currency}
        except Exception:
            pass
    return None


def _extract_currency(text: str) -> str | None:
    for code in ("USD", "EUR", "GBP", "CAD", "AUD", "SGD"):
        if re.search(rf"\b{code}\b", text):
            return code
    if re.search(r"\$", text):
        return "USD"
    return None


def _extract_termination_for_convenience(text: str) -> bool | None:
    if re.search(r"terminat\w+\s+for\s+convenience", text, re.IGNORECASE):
        return True
    return None


def _extract_termination_notice(text: str) -> int | None:
    m = re.search(
        r"terminat\w+\s+(?:upon|with|by\s+providing)\s+(\d+)[- ]"
        r"(?:calendar\s+)?days?\s+(?:written\s+)?notice",
        text, re.IGNORECASE,
    )
    return int(m.group(1)) if m else None


def _extract_notice_address(text: str) -> str | None:
    m = re.search(
        r"Notices?\s+(?:shall\s+be\s+)?(?:sent\s+to|delivered\s+to|addressed\s+to)[:\s]+(.+?)(?:\n\n|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        snippet = m.group(1).strip()[:200]
        return snippet if snippet else None
    return None


def _extract_warranty_period(text: str) -> int | None:
    m = re.search(
        r"warrant[yi]\s+(?:period\s+of\s+|for\s+)?(\d+)\s*(year|month|day)",
        text, re.IGNORECASE,
    )
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith("year"):
            return n * 365
        if unit.startswith("month"):
            return n * 30
        return n
    return None


def _extract_confidentiality_period(text: str) -> int | None:
    m = re.search(
        r"confidentiality\s+obligation[s]?\s+(?:shall\s+)?(?:survive|last|continue)\s+for\s+(\d+)\s*year",
        text, re.IGNORECASE,
    )
    return int(m.group(1)) if m else None


def _extract_ip_ownership(text: str) -> str | None:
    if re.search(
        r"(?:client|customer)\s+(?:shall\s+)?own[s]?\s+all\s+(?:intellectual property|IP)",
        text, re.IGNORECASE,
    ):
        return "client"
    if re.search(
        r"(?:vendor|supplier|company)\s+(?:shall\s+)?retain[s]?\s+all\s+"
        r"(?:intellectual property|IP)",
        text, re.IGNORECASE,
    ):
        return "vendor"
    if re.search(r"jointly\s+own", text, re.IGNORECASE):
        return "joint"
    if re.search(r"background\s+(?:intellectual property|IP)", text, re.IGNORECASE):
        return "background"
    return None


def _extract_assignment_allowed(text: str) -> bool | None:
    if re.search(
        r"may\s+not\s+assign|shall\s+not\s+assign|without\s+(?:prior\s+)?written\s+consent",
        text, re.IGNORECASE,
    ):
        return False
    if re.search(r"may\s+assign\s+(?:this\s+agreement|its\s+rights)", text, re.IGNORECASE):
        return True
    return None


def _extract_non_compete(text: str) -> int | None:
    m = re.search(
        r"non[- ]compete\b.{0,60}?(\d+)\s*month", text, re.IGNORECASE | re.DOTALL,
    )
    return int(m.group(1)) if m else None


def _extract_non_solicitation(text: str) -> int | None:
    m = re.search(
        r"non[- ]solicit\w+\b.{0,60}?(\d+)\s*month", text, re.IGNORECASE | re.DOTALL,
    )
    return int(m.group(1)) if m else None


def _extract_sla_uptime(text: str) -> float | None:
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*%\s*uptime", text, re.IGNORECASE)
    return float(m.group(1)) if m else None


def _extract_sla_response_time(text: str) -> int | None:
    m = re.search(r"respond\s+within\s+(\d+)\s*hour", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _extract_dpa(text: str) -> bool | None:
    if re.search(r"data\s+processing\s+agreement|DPA\b", text, re.IGNORECASE):
        return True
    return None


def _extract_gdpr(text: str) -> bool | None:
    if re.search(r"\bGDPR\b|General\s+Data\s+Protection\s+Regulation", text, re.IGNORECASE):
        return True
    return None


def _extract_force_majeure(text: str) -> bool | None:
    return True if re.search(r"force\s+majeure", text, re.IGNORECASE) else None


def _extract_entire_agreement(text: str) -> bool | None:
    m = re.search(r"entire\s+agreement|merger\s+clause|integration\s+clause", text, re.IGNORECASE)
    return True if m else None


def _extract_amendments_require_writing(text: str) -> bool | None:
    if re.search(
        r"amend\w+\s+(?:must\s+be|shall\s+be|only\s+(?:be\s+)?)?in\s+writing",
        text, re.IGNORECASE,
    ):
        return True
    return None


def _extract_lol_exclusions(text: str) -> list[str]:
    exclusions: list[str] = []
    carve_outs = [
        ("gross negligence", r"gross\s+negligence"),
        ("wilful misconduct", r"wilful\s+misconduct|willful\s+misconduct"),
        ("fraud", r"\bfraud\b"),
        ("death or personal injury", r"death\s+or\s+personal\s+injury"),
        ("IP infringement", r"intellectual\s+property\s+infring"),
        ("data breach", r"data\s+breach"),
        ("confidentiality breach", r"breach\s+of\s+confidentiality"),
    ]
    for label, pat in carve_outs:
        if re.search(pat, text, re.IGNORECASE):
            exclusions.append(label)
    return exclusions


def _extract_survival_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    m = re.search(
        r"(?:following\s+)?(?:provisions?\s+)?(?:shall\s+)?survive\s+(?:termination|expiration)[^.]*?:?\s*(.+?)(?:\.|$)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        raw = m.group(1)
        items = re.split(r",\s*|\band\b", raw)
        clauses = [i.strip().strip("()") for i in items if 2 < len(i.strip()) < 60]
    return clauses[:10]


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

    # Extract all fields
    effective_date = _extract_effective_date(text)
    expiry_date = _extract_expiry_date(text)
    initial_term_days = _extract_initial_term(text)
    renewal_term_days = _extract_renewal_term(text)
    governing_law = _extract_governing_law(text)
    dispute_resolution = _extract_dispute_resolution(text)
    arbitration_venue = _extract_arbitration_venue(text)
    liability_cap = _extract_liability_cap(text)
    indemnification_cap = _extract_indemnification_cap(text)
    total_contract_value = _extract_total_contract_value(text)
    currency = _extract_currency(text)
    notice_period_days = _extract_notice_period(text)
    notice_address = _extract_notice_address(text)
    auto_renewal = _extract_auto_renewal(text)
    termination_for_convenience = _extract_termination_for_convenience(text)
    termination_notice_days = _extract_termination_notice(text)
    payment_terms = _extract_payment_terms(text)
    financial_fields = _extract_financial_fields(text)
    milestone_dates = _extract_milestone_dates(text)
    warranty_period_days = _extract_warranty_period(text)
    confidentiality_period_years = _extract_confidentiality_period(text)
    ip_ownership = _extract_ip_ownership(text)
    assignment_allowed = _extract_assignment_allowed(text)
    non_compete_months = _extract_non_compete(text)
    non_solicitation_months = _extract_non_solicitation(text)
    sla_uptime_percent = _extract_sla_uptime(text)
    sla_response_time_hours = _extract_sla_response_time(text)
    data_processing_agreement = _extract_dpa(text)
    gdpr_applicable = _extract_gdpr(text)
    force_majeure = _extract_force_majeure(text)
    entire_agreement = _extract_entire_agreement(text)
    amendments_require_writing = _extract_amendments_require_writing(text)
    limitation_of_liability_exclusions = _extract_lol_exclusions(text)
    survival_clauses = _extract_survival_clauses(text)

    metadata = ContractMetadataDTO(
        parties=parties_list,
        effective_date=effective_date,
        expiry_date=expiry_date,
        initial_term_days=initial_term_days,
        renewal_term_days=renewal_term_days,
        governing_law=governing_law,
        dispute_resolution=dispute_resolution,
        arbitration_venue=arbitration_venue,
        liability_cap=liability_cap,
        indemnification_cap=indemnification_cap,
        total_contract_value=total_contract_value,
        currency=currency,
        notice_period_days=notice_period_days,
        notice_address=notice_address,
        auto_renewal=auto_renewal,
        termination_for_convenience=termination_for_convenience,
        termination_notice_days=termination_notice_days,
        payment_terms=payment_terms,
        financial_fields=financial_fields,
        milestone_dates=milestone_dates,
        warranty_period_days=warranty_period_days,
        confidentiality_period_years=confidentiality_period_years,
        ip_ownership=ip_ownership,
        assignment_allowed=assignment_allowed,
        non_compete_months=non_compete_months,
        non_solicitation_months=non_solicitation_months,
        sla_uptime_percent=sla_uptime_percent,
        sla_response_time_hours=sla_response_time_hours,
        data_processing_agreement=data_processing_agreement,
        gdpr_applicable=gdpr_applicable,
        force_majeure=force_majeure,
        entire_agreement=entire_agreement,
        amendments_require_writing=amendments_require_writing,
        limitation_of_liability_exclusions=limitation_of_liability_exclusions,
        survival_clauses=survival_clauses,
        extracted={},
    )
    return metadata, parties_dtos
