"""
Parties and own-organisation matching for document processing.

No database or network imports.
"""
from __future__ import annotations

import re
from dataclasses import replace

from app.services.document_processing.types import PartyDraft, SignatoryDraft

# Corporate suffixes that must be preserved after punctuation stripping.
_CORPORATE_SUFFIXES = frozenset(
    ["inc", "llc", "ltd", "corp", "co", "lp", "llp", "plc", "gmbh", "bv", "nv", "ag"]
)

# Bare role words that do not count as a real party name (used by callers, not here).
_ROLE_WORDS = frozenset(
    [
        "customer",
        "supplier",
        "vendor",
        "company",
        "licensor",
        "licensee",
        "party",
        "buyer",
        "seller",
        "client",
        "contractor",
        "provider",
    ]
)


def normalize_party_name(name: str) -> str:
    """
    Normalise a party name for comparison.

    Steps:
    1. Lower-case.
    2. Strip punctuation (commas, periods, etc.) — but keep corporate suffixes.
    3. Collapse whitespace.
    4. Drop a leading "the ".

    Corporate suffixes (inc, llc, ltd, corp, co, …) are preserved even
    though they follow a period in forms like "Halcyon Care, Inc.".

    Examples:
        "Halcyon Care, Inc."  → "halcyon care inc"
        "The Acme Corporation" → "acme corporation"
        "BETA LLC"            → "beta llc"
        "Supplier"            → "supplier"
    """
    if not name:
        return ""

    # Lower-case first so suffix detection is case-insensitive.
    result = name.lower()

    # Remove punctuation characters but keep alphanumerics and whitespace.
    # This turns "Halcyon Care, Inc." → "halcyon care inc".
    result = re.sub(r"[^\w\s]", " ", result)

    # Collapse multiple whitespace into one and strip edges.
    result = re.sub(r"\s+", " ", result).strip()

    # Drop a leading "the " (with a space after, so "theory" is left alone).
    result = re.sub(r"^the\s+", "", result)

    # Final strip in case the leading-the removal left nothing.
    return result.strip()


def assign_roles(
    parties: list[PartyDraft],
    own_org_names: list[str],
) -> tuple[list[PartyDraft], list[str]]:
    """
    Assign ``own``, ``counterparty`` or ``other`` roles to *parties*.

    Returns ``(parties_with_roles, warnings)``.

    Logic
    -----
    1. If *own_org_names* is **empty** → warning ``own_org_not_configured``;
       all parties stay ``other``; no roles are assigned.
    2. For each party: if ``normalize_party_name(party.name)`` equals or
       **starts with** ``normalize_party_name(n)`` for any *n* in
       *own_org_names* → role ``own``.
    3. If *own_org_names* is non-empty but nothing matched → warning
       ``own_org_not_found``; no counterparty is assigned; all stay ``other``.
    4. The first remaining (non-``own``) party → role ``counterparty``.
    5. The rest → role ``other``.
    6. If only own-org parties are present → warning ``no_counterparty``.
    """
    warnings: list[str] = []

    if not own_org_names:
        warnings.append("own_org_not_configured")
        # All roles stay at their default "other" — return as-is.
        return list(parties), warnings

    # Pre-compute normalised own-org names.
    normalised_own = [normalize_party_name(n) for n in own_org_names]

    def _is_own(party: PartyDraft) -> bool:
        norm = normalize_party_name(party.name)
        return any(
            norm == own or norm.startswith(own)
            for own in normalised_own
        )

    # First pass: mark own-org parties.
    tagged: list[PartyDraft] = []
    found_own = False
    for p in parties:
        if _is_own(p):
            tagged.append(replace(p, role="own"))
            found_own = True
        else:
            tagged.append(p)

    if not found_own:
        warnings.append("own_org_not_found")
        # Leave all as "other" — no counterparty.
        return tagged, warnings

    # Second pass: assign counterparty / other among non-own parties.
    result: list[PartyDraft] = []
    counterparty_assigned = False
    for p in tagged:
        if p.role == "own":
            result.append(p)
        elif not counterparty_assigned:
            result.append(replace(p, role="counterparty"))
            counterparty_assigned = True
        else:
            result.append(replace(p, role="other"))

    if not counterparty_assigned:
        warnings.append("no_counterparty")

    return result, warnings


def link_signatory(
    signatory: SignatoryDraft,
    parties: list[PartyDraft],
) -> int | None:
    """
    Return the index in *parties* whose normalised name matches
    ``normalize_party_name(signatory.party_name)``, or ``None`` if
    *party_name* is ``None`` or no match is found.
    """
    if signatory.party_name is None:
        return None

    target = normalize_party_name(signatory.party_name)
    for i, party in enumerate(parties):
        if normalize_party_name(party.name) == target:
            return i

    return None
