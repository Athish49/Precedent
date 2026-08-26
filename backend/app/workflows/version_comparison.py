from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.diff import differ as differ_mod
from app.db.models.contract import ContractVersion
from app.db.repositories import clause_repo, contract_repo


@dataclass
class ClauseDiff:
    clause_id: uuid.UUID
    clause_type: str
    heading_text: str | None
    ordinal: int
    char_start: int
    char_end: int
    change_type: str  # "unchanged" | "modified"
    changes: list[dict]  # serialized Change objects within this clause's span


@dataclass
class VersionDiffResult:
    contract_id: uuid.UUID
    v_a: uuid.UUID
    v_b: uuid.UUID
    v_a_number: int
    v_b_number: int
    clause_diffs: list[ClauseDiff]
    global_changes: list[dict]  # full document change set, serialized


def _insert_old_positions(raw_changes: list) -> list[int]:
    """Return the old-text cursor position at the time of each insert op."""
    positions: list[int] = []
    old_cur = 0
    for ch in raw_changes:
        if ch.op == "insert":
            positions.append(old_cur)
        else:
            old_cur = ch.old_end
    return positions


async def compare_versions(
    session: AsyncSession,
    contract_id: uuid.UUID,
    v_a: uuid.UUID,
    v_b: uuid.UUID,
) -> VersionDiffResult:
    """Compare two contract versions. Returns clause-aligned change set."""
    contract = await contract_repo.get_contract(session, contract_id)
    if contract is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    result_a = await session.execute(
        select(ContractVersion).where(
            ContractVersion.id == v_a,
            ContractVersion.contract_id == contract_id,
        )
    )
    version_a = result_a.scalar_one_or_none()
    if version_a is None:
        msg = f"Version {v_a} not found for contract {contract_id}"
        raise AppError(404, "version_not_found", msg)

    result_b = await session.execute(
        select(ContractVersion).where(
            ContractVersion.id == v_b,
            ContractVersion.contract_id == contract_id,
        )
    )
    version_b = result_b.scalar_one_or_none()
    if version_b is None:
        msg = f"Version {v_b} not found for contract {contract_id}"
        raise AppError(404, "version_not_found", msg)

    clauses = await clause_repo.get_clauses_for_contract(session, contract_id)

    raw_changes = differ_mod.diff(version_a.canonical_text, version_b.canonical_text)
    global_changes = [dataclasses.asdict(c) for c in raw_changes]

    # Pre-compute old-text position for each insert to enable clause attribution.
    ipos = _insert_old_positions(raw_changes)

    clause_diffs: list[ClauseDiff] = []
    for clause in clauses:
        cs = clause.char_start
        ce = clause.char_end

        clause_changes: list[dict] = []
        has_modification = False
        insert_counter = 0

        for ch in raw_changes:
            if ch.op == "equal":
                if ch.old_start < ce and ch.old_end > cs:
                    clause_changes.append(dataclasses.asdict(ch))
            elif ch.op == "delete":
                if ch.old_start < ce and ch.old_end > cs:
                    clause_changes.append(dataclasses.asdict(ch))
                    has_modification = True
            else:  # insert
                old_pos = ipos[insert_counter]
                insert_counter += 1
                if cs <= old_pos <= ce:
                    clause_changes.append(dataclasses.asdict(ch))
                    has_modification = True

        if has_modification:
            change_type = "modified"
        elif not clause_changes:
            change_type = "unchanged"
        else:
            all_equal = all(c["op"] == "equal" for c in clause_changes)
            change_type = "unchanged" if all_equal else "modified"

        clause_diffs.append(
            ClauseDiff(
                clause_id=clause.id,
                clause_type=clause.clause_type,
                heading_text=clause.heading_text,
                ordinal=clause.ordinal,
                char_start=cs,
                char_end=ce,
                change_type=change_type,
                changes=clause_changes,
            )
        )

    return VersionDiffResult(
        contract_id=contract_id,
        v_a=v_a,
        v_b=v_b,
        v_a_number=version_a.version_number,
        v_b_number=version_b.version_number,
        clause_diffs=clause_diffs,
        global_changes=global_changes,
    )
