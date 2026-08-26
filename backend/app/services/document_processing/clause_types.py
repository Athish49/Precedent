"""Clause-type normalizer (T-022).

Maps raw heading text → canonical clause_type string using an exact-match
synonym dictionary, with rapidfuzz fuzzy fallback.  Purely deterministic —
no LLM involved.
"""

from __future__ import annotations

from rapidfuzz import fuzz, process

# ---------------------------------------------------------------------------
# Synonym dictionary: lowercased synonym → canonical clause type
# ---------------------------------------------------------------------------
_SYNONYMS: dict[str, str] = {
    # indemnification
    "indemnification": "indemnification",
    "indemnity": "indemnification",
    "hold harmless": "indemnification",
    "indemnification and hold harmless": "indemnification",
    "indemnity and hold harmless": "indemnification",
    # limitation_of_liability
    "limitation of liability": "limitation_of_liability",
    "liability cap": "limitation_of_liability",
    "liability limitation": "limitation_of_liability",
    "limitation on liability": "limitation_of_liability",
    "cap on liability": "limitation_of_liability",
    # termination
    "termination": "termination",
    "termination for cause": "termination",
    "termination for convenience": "termination",
    "term and termination": "termination",
    "termination rights": "termination",
    # confidentiality
    "confidentiality": "confidentiality",
    "non-disclosure": "confidentiality",
    "nondisclosure": "confidentiality",
    "confidential information": "confidentiality",
    "nda": "confidentiality",
    "non disclosure": "confidentiality",
    "confidentiality and non-disclosure": "confidentiality",
    # intellectual_property
    "intellectual property": "intellectual_property",
    "ip ownership": "intellectual_property",
    "ip rights": "intellectual_property",
    "ownership of ip": "intellectual_property",
    "work product": "intellectual_property",
    "intellectual property rights": "intellectual_property",
    "ownership of intellectual property": "intellectual_property",
    # governing_law
    "governing law": "governing_law",
    "choice of law": "governing_law",
    "jurisdiction": "governing_law",
    "applicable law": "governing_law",
    "governing law and jurisdiction": "governing_law",
    "choice of law and jurisdiction": "governing_law",
    # dispute_resolution
    "dispute resolution": "dispute_resolution",
    "arbitration": "dispute_resolution",
    "mediation": "dispute_resolution",
    "disputes": "dispute_resolution",
    "resolution of disputes": "dispute_resolution",
    "dispute resolution and arbitration": "dispute_resolution",
    # payment
    "payment": "payment",
    "fees": "payment",
    "compensation": "payment",
    "payment terms": "payment",
    "pricing": "payment",
    "invoicing": "payment",
    "fees and payment": "payment",
    "payment and invoicing": "payment",
    # warranties
    "warranties": "warranties",
    "representations and warranties": "warranties",
    "representations": "warranties",
    "warranty": "warranties",
    "warranties and representations": "warranties",
    # force_majeure
    "force majeure": "force_majeure",
    "acts of god": "force_majeure",
    "force majeure events": "force_majeure",
    "force majeure and acts of god": "force_majeure",
    # assignment
    "assignment": "assignment",
    "assignment and delegation": "assignment",
    "transfer of rights": "assignment",
    "assignment of rights": "assignment",
    # entire_agreement
    "entire agreement": "entire_agreement",
    "integration": "entire_agreement",
    "merger clause": "entire_agreement",
    "entire understanding": "entire_agreement",
    "entire agreement and integration": "entire_agreement",
    # amendment
    "amendment": "amendment",
    "modification": "amendment",
    "changes to agreement": "amendment",
    "amendments and modifications": "amendment",
    "modifications to agreement": "amendment",
    # notices
    "notices": "notices",
    "notice requirements": "notices",
    "notice": "notices",
    "notice provisions": "notices",
    "notices and communications": "notices",
    # definitions
    "definitions": "definitions",
    "defined terms": "definitions",
    "interpretation": "definitions",
    "definitions and interpretation": "definitions",
    # term
    "term": "term",
    "duration": "term",
    "agreement term": "term",
    "term of agreement": "term",
    # compliance
    "compliance": "compliance",
    "compliance with laws": "compliance",
    "regulatory compliance": "compliance",
    "compliance with applicable laws": "compliance",
    # data_protection
    "data protection": "data_protection",
    "data processing": "data_protection",
    "privacy": "data_protection",
    "data privacy": "data_protection",
    "gdpr": "data_protection",
    "hipaa": "data_protection",
    "data protection and privacy": "data_protection",
    "data processing agreement": "data_protection",
    # audit
    "audit": "audit",
    "audit rights": "audit",
    "inspection": "audit",
    "audit and inspection": "audit",
    "right to audit": "audit",
    # insurance
    "insurance": "insurance",
    "insurance requirements": "insurance",
    "insurance coverage": "insurance",
}

# Pre-compute the keys list once so fuzzy matching doesn't rebuild it each call.
_SYNONYM_KEYS: list[str] = list(_SYNONYMS.keys())

_FUZZY_CUTOFF = 80


def normalize_clause_type(heading_text: str | None) -> str:
    """Map *heading_text* to a canonical clause type string.

    Returns ``"other"`` for unknown headings or ``None`` input.

    Resolution order:
    1. ``None`` → ``"other"``
    2. Exact match in synonym dictionary → canonical type
    3. Fuzzy match (token_sort_ratio ≥ 80) → canonical type of best match
    4. No match → ``"other"``
    """
    if heading_text is None:
        return "other"

    normalized = heading_text.strip().lower()
    if not normalized:
        return "other"

    # Exact match
    if normalized in _SYNONYMS:
        return _SYNONYMS[normalized]

    # Fuzzy match
    result = process.extractOne(
        normalized,
        _SYNONYM_KEYS,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=_FUZZY_CUTOFF,
    )
    if result is not None:
        matched_key = result[0]
        return _SYNONYMS[matched_key]

    return "other"
