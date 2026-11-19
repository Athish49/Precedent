from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Block:
    index: int            # position in the parse output, 0-based
    type: str             # Extend block type
    text: str             # cleaned text as it appears in canonical text
    page: int             # 1-based
    char_start: int       # offsets into canonical text; -1 if the block was dropped
    char_end: int
    dropped: bool = False # header, footer, page number, repeated header


@dataclass(frozen=True)
class CanonicalDocument:
    text: str
    blocks: tuple[Block, ...]   # all blocks, dropped ones included
    page_count: int


@dataclass(frozen=True)
class SectionHint:               # one entry of Extract's clause list
    section_number: str | None
    title: str | None
    family: str | None


@dataclass(frozen=True)
class ClauseDraft:
    ordinal: int                 # document order, 0-based, parents before children
    level: int                   # 1 = section, 2+ = sub-clause
    parent_ordinal: int | None
    section_number: str | None
    title: str | None            # clean title, no numbering
    heading_text: str | None     # raw heading as written
    text: str
    char_start: int
    char_end: int
    page_start: int
    page_end: int
    clause_type: str = "other"
    type_source: str = "none"    # extract | dictionary | none
    issue_keys: tuple[str, ...] = ()
    anchored: bool = True        # False if found by the fallback rule


@dataclass(frozen=True)
class FieldValue:
    field_key: str
    value: Any                   # JSON-serialisable, typed per the registry
    source: str                  # extract | derived
    confidence: str | None       # high | low
    quote: str | None
    page: int | None
    char_start: int | None
    char_end: int | None
    clause_ordinal: int | None


@dataclass(frozen=True)
class PartyDraft:
    name: str
    role_label: str | None
    entity_type: str | None
    jurisdiction: str | None
    address: str | None
    role: str = "other"          # own | counterparty | other


@dataclass(frozen=True)
class SignatoryDraft:
    printed_name: str | None
    title: str | None
    party_name: str | None
    is_signed: bool | None
    signed_date: date | None


@dataclass(frozen=True)
class IngestResult:
    document: CanonicalDocument
    title: str | None
    contract_type: str | None
    clauses: tuple[ClauseDraft, ...]
    fields: tuple[FieldValue, ...]
    parties: tuple[PartyDraft, ...]
    signatories: tuple[SignatoryDraft, ...]
    warnings: tuple[str, ...]

    def level1(self) -> tuple["ClauseDraft", ...]:
        """Return level 1 clauses in document order (sorted by ordinal)."""
        return tuple(
            sorted(
                (c for c in self.clauses if c.level == 1),
                key=lambda c: c.ordinal,
            )
        )
