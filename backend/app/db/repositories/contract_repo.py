from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.contract import Contract, ContractMetadata, ContractVersion, Party
from app.db.models.party_link import ContractParty, ContractSignatory

if TYPE_CHECKING:
    from app.db.models.field import ContractField
    from app.services.document_processing.types import PartyDraft, SignatoryDraft


async def get_contract(session: AsyncSession, contract_id: uuid.UUID) -> Contract | None:
    """Fetch a Contract by id, or None if not found."""
    result = await session.execute(select(Contract).where(Contract.id == contract_id))
    return result.scalar_one_or_none()


async def get_contract_with_metadata(
    session: AsyncSession, contract_id: uuid.UUID
) -> tuple[Contract, ContractMetadata | None] | None:
    """Fetch Contract + its ContractMetadata in one query (LEFT OUTER JOIN).
    Returns None if contract doesn't exist.
    """
    stmt = (
        select(Contract, ContractMetadata)
        .outerjoin(ContractMetadata, Contract.id == ContractMetadata.contract_id)
        .where(Contract.id == contract_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    contract, metadata = row
    return (contract, metadata)


def _build_contract_filters(
    stmt,
    *,
    contract_type: str | None,
    counterparty_id: uuid.UUID | None,
    status: str | None,
    effective_date_from: date | None,
    effective_date_to: date | None,
):
    """Apply optional WHERE clauses to a statement (shared by list + count queries)."""
    if contract_type is not None:
        stmt = stmt.where(Contract.contract_type == contract_type)
    if counterparty_id is not None:
        stmt = stmt.where(Contract.counterparty_id == counterparty_id)
    if status is not None:
        stmt = stmt.where(Contract.status == status)
    if effective_date_from is not None:
        stmt = stmt.where(ContractMetadata.effective_date >= effective_date_from)
    if effective_date_to is not None:
        stmt = stmt.where(ContractMetadata.effective_date <= effective_date_to)
    return stmt


async def list_contracts(
    session: AsyncSession,
    *,
    contract_type: str | None = None,
    counterparty_id: uuid.UUID | None = None,
    status: str | None = None,
    effective_date_from: date | None = None,
    effective_date_to: date | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Contract], int]:
    """Faceted list with optional filters. Returns (items, total_count).
    Filters on contract columns + contract_metadata date columns.
    total_count is the count with same filters applied (without pagination).
    """
    base = select(Contract).outerjoin(ContractMetadata, Contract.id == ContractMetadata.contract_id)
    base = _build_contract_filters(
        base,
        contract_type=contract_type,
        counterparty_id=counterparty_id,
        status=status,
        effective_date_from=effective_date_from,
        effective_date_to=effective_date_to,
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    list_stmt = base.limit(limit).offset(offset)
    list_result = await session.execute(list_stmt)
    items = list(list_result.scalars().all())

    return items, total


async def update_contract(session: AsyncSession, contract_id: uuid.UUID, **kwargs: object) -> Contract | None:
    """Partially update a Contract row (task 4.1, item 5: PATCH
    /api/repository/contracts/{id}). Returns None if the contract does not
    exist; does not commit (caller's responsibility).
    """
    contract = await get_contract(session, contract_id)
    if contract is None:
        return None
    for field, value in kwargs.items():
        setattr(contract, field, value)
    await session.flush()
    return contract


async def upsert_party(
    session: AsyncSession, normalized_name: str, display_name: str
) -> Party:
    """Insert the party if it does not already exist, else return the
    existing row. Uses ``INSERT ... ON CONFLICT (normalized_name) DO
    NOTHING`` (plan section 5.6) so two concurrent uploads of the same
    counterparty do not race on the unique constraint — the old
    select-then-insert this replaces could raise an integrity error under
    that race.
    """
    insert_stmt = (
        pg_insert(Party)
        .values(id=uuid.uuid4(), normalized_name=normalized_name, display_name=display_name)
        .on_conflict_do_nothing(index_elements=["normalized_name"])
    )
    await session.execute(insert_stmt)
    result = await session.execute(
        select(Party).where(Party.normalized_name == normalized_name)
    )
    return result.scalar_one()


async def replace_contract_parties(
    session: AsyncSession,
    contract_id: uuid.UUID,
    entries: list[tuple[uuid.UUID, "PartyDraft"]],
) -> list[ContractParty]:
    """Delete a contract's ``contract_party`` rows and insert *entries* in
    their place, in order. Each entry pairs a resolved ``party.id`` with
    the draft carrying its role and the facts Extract gave it.
    """
    await session.execute(delete(ContractParty).where(ContractParty.contract_id == contract_id))
    rows: list[ContractParty] = []
    for ordinal, (party_id, draft) in enumerate(entries):
        row = ContractParty(
            id=uuid.uuid4(),
            contract_id=contract_id,
            party_id=party_id,
            role=draft.role,
            role_label=draft.role_label,
            entity_type=draft.entity_type,
            jurisdiction=draft.jurisdiction,
            address=draft.address,
            ordinal=ordinal,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def replace_signatories(
    session: AsyncSession,
    version_id: uuid.UUID,
    entries: list[tuple["SignatoryDraft", uuid.UUID | None]],
) -> list[ContractSignatory]:
    """Delete a version's ``contract_signatory`` rows and insert *entries*
    in their place. Each entry pairs a draft with the ``contract_party.id``
    it was linked to (``parties.link_signatory``), or None if it could not
    be linked.
    """
    await session.execute(
        delete(ContractSignatory).where(ContractSignatory.contract_version_id == version_id)
    )
    rows: list[ContractSignatory] = []
    for draft, contract_party_id in entries:
        row = ContractSignatory(
            id=uuid.uuid4(),
            contract_version_id=version_id,
            contract_party_id=contract_party_id,
            printed_name=draft.printed_name,
            title=draft.title,
            is_signed=draft.is_signed,
            signed_date=draft.signed_date,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def write_metadata_projection(
    session: AsyncSession,
    contract_id: uuid.UUID,
    version_id: uuid.UUID,
    values_in_force: dict[str, "ContractField"],
    registry_projection: dict[str, str],
) -> ContractMetadata:
    """Write the typed ``contract_metadata`` columns from the values in
    force in ``contract_field`` (plan section 7.3: ``contract_metadata``
    "is written by one function from ``contract_field``, in the same
    transaction, and by nothing else").

    ``registry_projection`` maps a field key to the ``contract_metadata``
    column it projects to (``fields.FieldDef.projection``). A field with no
    value in force clears its column to null.
    """
    result = await session.execute(
        select(ContractMetadata).where(ContractMetadata.contract_id == contract_id)
    )
    metadata = result.scalar_one_or_none()
    if metadata is None:
        metadata = ContractMetadata(contract_id=contract_id)
        session.add(metadata)
    metadata.contract_version_id = version_id
    for field_key, column_name in registry_projection.items():
        field_row = values_in_force.get(field_key)
        setattr(metadata, column_name, field_row.value if field_row is not None else None)
    await session.flush()
    return metadata


async def find_by_sha256(session: AsyncSession, sha256: str) -> ContractVersion | None:
    """Return the first ``contract_version`` row with this file hash, for
    duplicate-upload detection (plan section 5.1), or None.
    """
    result = await session.execute(
        select(ContractVersion).where(ContractVersion.file_sha256 == sha256)
    )
    return result.scalars().first()
