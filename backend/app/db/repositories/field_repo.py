from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence
from typing import Any, TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.field import ContractField

if TYPE_CHECKING:
    from app.services.document_processing.types import FieldValue

# Priority order for "value in force": user over extract over derived.
_SOURCE_PRIORITY = {"user": 0, "extract": 1, "derived": 2}


def _json_safe(value: Any) -> Any:
    """Coerce a FieldValue.value to something the JSONB column can store.

    ``fields.validate_value`` returns a real ``datetime.date`` for a
    ``date``-kind field; psycopg has no default JSON encoder for it, so an
    uncoerced date crashes the whole ingest transaction (found live: every
    real contract has at least one date field, so this crashed every real
    upload). Every other registry kind (string/enum/string_list/int/float/
    bool) is already JSON-safe.
    """
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


async def replace_extracted(
    session: AsyncSession,
    contract_id: uuid.UUID,
    version_id: uuid.UUID,
    run_id: uuid.UUID | None,
    values: Sequence["FieldValue"],
    *,
    clause_ids_by_ordinal: dict[int, uuid.UUID] | None = None,
) -> list[ContractField]:
    """Replace the version's ``extract`` and ``derived`` rows. Never touches
    ``user`` rows (plan section 7.3: a user correction is a new row, never
    overwritten by re-processing).

    ``clause_ids_by_ordinal`` maps a ``FieldValue.clause_ordinal`` to the
    clause row id it falls in, resolved by the caller after
    ``clause_repo.replace_clauses`` has run in the same transaction.
    """
    clause_ids_by_ordinal = clause_ids_by_ordinal or {}
    await session.execute(
        delete(ContractField).where(
            ContractField.contract_version_id == version_id,
            ContractField.source.in_(("extract", "derived")),
        )
    )
    rows: list[ContractField] = []
    for value in values:
        clause_id = (
            clause_ids_by_ordinal.get(value.clause_ordinal)
            if value.clause_ordinal is not None
            else None
        )
        row = ContractField(
            id=uuid.uuid4(),
            contract_id=contract_id,
            contract_version_id=version_id,
            field_key=value.field_key,
            value=_json_safe(value.value),
            source=value.source,
            confidence=value.confidence,
            quote=value.quote,
            page=value.page,
            char_start=value.char_start,
            char_end=value.char_end,
            clause_id=clause_id,
            ingest_run_id=run_id,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


async def values_in_force(
    session: AsyncSession, version_id: uuid.UUID
) -> dict[str, ContractField]:
    """Return the value in force per ``field_key``: ``user`` over ``extract``
    over ``derived`` (plan section 7.3).
    """
    result = await session.execute(
        select(ContractField).where(ContractField.contract_version_id == version_id)
    )
    rows = list(result.scalars().all())
    by_key: dict[str, ContractField] = {}
    for row in rows:
        existing = by_key.get(row.field_key)
        if existing is None or _SOURCE_PRIORITY[row.source] < _SOURCE_PRIORITY[existing.source]:
            by_key[row.field_key] = row
    return by_key


async def set_user_value(
    session: AsyncSession,
    contract_id: uuid.UUID,
    version_id: uuid.UUID,
    field_key: str,
    value: object,
) -> ContractField:
    """Set (or replace) the ``user`` row for *field_key* on this version.

    The unique key is (contract_version_id, field_key, source), so there is
    at most one ``user`` row per field per version; this updates it in
    place if present, otherwise inserts it.
    """
    result = await session.execute(
        select(ContractField).where(
            ContractField.contract_version_id == version_id,
            ContractField.field_key == field_key,
            ContractField.source == "user",
        )
    )
    value = _json_safe(value)
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.value = value
        existing.confidence = None
        await session.flush()
        return existing

    row = ContractField(
        id=uuid.uuid4(),
        contract_id=contract_id,
        contract_version_id=version_id,
        field_key=field_key,
        value=value,
        source="user",
        confidence=None,
    )
    session.add(row)
    await session.flush()
    return row
