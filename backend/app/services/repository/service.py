"""Repository service — contract version store and retrieval (T-032)."""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.config import get_settings
from app.core.storage import get_storage
from app.db.models.contract import ContractVersion
from app.db.repositories.contract_repo import get_contract
from app.services.document_processing.parsers import parse

# ── Helpers ───────────────────────────────────────────────────────────────────

_EXTENSION_TO_FORMAT: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
}


def _source_format_from_filename(filename: str) -> str:
    """Derive source_format from the filename extension."""
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()
    fmt = _EXTENSION_TO_FORMAT.get(suffix)
    if fmt is None:
        raise ValueError(f"Unsupported file format: {filename!r}")
    return fmt


# ── Service functions ─────────────────────────────────────────────────────────


async def store_version(
    session: AsyncSession,
    contract_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    relation: Literal["version", "amendment", "addendum"],
) -> ContractVersion:
    """Store a new version of a contract.

    Steps:
    1. Verify the contract exists — raise AppError(404, "not_found", "Contract not found") if not.
    2. Find the latest version_number for this contract (SELECT MAX(version_number)).
       If none exists, start at 1. New version_number = max + 1.
    3. Get parent: the current contract_version with the highest version_number (before this one).
       parent_version_id = that version's id, or None if this is the first.
    4. Put bytes to object storage:
       key = f"contracts/{contract_id}/versions/{version_number}/{filename}"
    5. Insert ContractVersion row.
    6. Update contract.current_version_id to new version id; flush.
    7. Commit and return the new ContractVersion row.
    """
    # 1. Verify contract exists
    contract = await get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "not_found", "Contract not found")

    # 2. Find the latest version_number
    result = await session.execute(
        select(func.max(ContractVersion.version_number)).where(
            ContractVersion.contract_id == contract_id
        )
    )
    max_ver = result.scalar_one_or_none() or 0
    new_ver = max_ver + 1

    # 3. Get parent version id (last version before this new one)
    if max_ver > 0:
        parent_result = await session.execute(
            select(ContractVersion).where(
                ContractVersion.contract_id == contract_id,
                ContractVersion.version_number == max_ver,
            )
        )
        parent = parent_result.scalar_one_or_none()
        parent_version_id = parent.id if parent else None
    else:
        parent_version_id = None

    # 4. Parse file to get canonical_text
    source_format = _source_format_from_filename(filename)
    parsed = parse(file_bytes, source_format)  # type: ignore[arg-type]

    # 5. Put bytes to object storage
    object_key = f"contracts/{contract_id}/versions/{new_ver}/{filename}"
    settings = get_settings()
    storage = get_storage(settings)
    storage.put(object_key, file_bytes)

    # 6. Insert ContractVersion row
    version = ContractVersion(
        id=uuid.uuid4(),
        contract_id=contract_id,
        version_number=new_ver,
        parent_version_id=parent_version_id,
        object_key=object_key,
        canonical_text=parsed.canonical_text,
        relation=relation,
    )
    session.add(version)
    await session.flush()

    # 7. Update contract.current_version_id
    contract.current_version_id = version.id
    await session.flush()

    await session.commit()
    return version


async def list_versions(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> list[ContractVersion]:
    """Return all versions for a contract, ordered by version_number ascending.

    Raise AppError(404, "not_found", "Contract not found") if contract doesn't exist.
    """
    contract = await get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "not_found", "Contract not found")

    result = await session.execute(
        select(ContractVersion)
        .where(ContractVersion.contract_id == contract_id)
        .order_by(ContractVersion.version_number)
    )
    return list(result.scalars().all())
