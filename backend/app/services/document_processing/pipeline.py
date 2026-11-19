"""Pure pipeline assembly (task 2.9; plan section 5).

``build_result`` wires together the pure stages owned by tasks 2.1-2.7 into
one ``IngestResult``. No database, storage or network import.
"""

from __future__ import annotations

from app.services.document_processing.canonical import build_canonical
from app.services.document_processing.clause_typing import FamilyIndex, type_clause
from app.services.document_processing.fields import REGISTRY
from app.services.document_processing.invariants import InvariantError, check_result
from app.services.document_processing.mapping import (
    map_contract_type,
    map_fields,
    map_hints,
    map_parties,
    map_signatories,
    map_title,
)
from app.services.document_processing.parties import assign_roles
from app.services.document_processing.sections import segment
from app.services.document_processing.types import ClauseDraft, IngestResult

_MIN_TEXT_CHARS = 200


class NoTextError(Exception):
    """Raised when the canonical text has fewer than 200 characters."""


def build_result(
    extract_value: dict,
    extract_metadata: dict,
    parse_blocks: list[dict],
    *,
    family_index: FamilyIndex,
    agreement_type_keys: list[str],
    own_org_names: list[str],
) -> IngestResult:
    """Assemble an ``IngestResult`` from raw Extract/Parse output.

    Order: canonical text -> hints -> segmentation -> clause typing (in
    document order, threading the already-typed parent through for
    sub-clauses) -> field mapping -> party mapping and role assignment ->
    signatory mapping and linking -> title/contract type -> invariant check.

    Raises ``NoTextError`` when the canonical text is under 200 characters,
    and ``InvariantError`` when ``check_result`` reports any violation.
    """
    document = build_canonical(parse_blocks)
    if len(document.text) < _MIN_TEXT_CHARS:
        raise NoTextError(
            f"canonical text has only {len(document.text)} character(s); "
            f"minimum is {_MIN_TEXT_CHARS}"
        )

    warnings: list[str] = []

    hints = map_hints(extract_value)
    clauses, segment_warnings = segment(document, hints)
    warnings.extend(segment_warnings)

    hint_family_by_number = {
        h.section_number: h.family for h in hints if h.section_number
    }
    hint_family_by_title = {
        h.title.strip().lower(): h.family for h in hints if h.title
    }

    typed_by_ordinal: dict[int, ClauseDraft] = {}
    typed_clauses: list[ClauseDraft] = []
    for draft in sorted(clauses, key=lambda c: c.ordinal):
        hint_family: str | None = None
        if draft.section_number is not None and draft.section_number in hint_family_by_number:
            hint_family = hint_family_by_number[draft.section_number]
        elif draft.title is not None and draft.title.strip().lower() in hint_family_by_title:
            hint_family = hint_family_by_title[draft.title.strip().lower()]

        parent = (
            typed_by_ordinal.get(draft.parent_ordinal)
            if draft.parent_ordinal is not None
            else None
        )
        typed = type_clause(draft, hint_family, family_index, parent=parent)
        typed_by_ordinal[typed.ordinal] = typed
        typed_clauses.append(typed)

    typed_clauses.sort(key=lambda c: c.ordinal)

    field_values, field_warnings = map_fields(
        extract_value, extract_metadata, document, typed_clauses
    )
    warnings.extend(field_warnings)

    raw_parties = map_parties(extract_value, document)
    parties, party_warnings = assign_roles(raw_parties, own_org_names)
    warnings.extend(party_warnings)

    signatories = map_signatories(extract_value)

    title = map_title(extract_value)
    contract_type = map_contract_type(extract_value, agreement_type_keys)

    result = IngestResult(
        document=document,
        title=title,
        contract_type=contract_type,
        clauses=tuple(typed_clauses),
        fields=tuple(field_values),
        parties=tuple(parties),
        signatories=tuple(signatories),
        warnings=tuple(warnings),
    )

    violations = check_result(result, family_index.keys, REGISTRY)
    if violations:
        raise InvariantError(violations)

    return result
