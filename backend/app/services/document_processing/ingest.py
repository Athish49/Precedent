"""Ingest orchestrator (task 3.1; plan section 5.1).

Owns the whole path from a validated upload to a ``ready``/``failed``
contract: ``create_contract`` writes the contract + version 1 rows and the
original file, then ``run_ingest`` drives Extend (upload, Extract, Parse),
runs the pure pipeline (``pipeline.build_result``) and writes every
downstream table in one transaction.

No other module writes ``contract.status``, ``contract_version`` file facts
or ``ingest_run`` rows; everything downstream of upload goes through here.

Known open items (see the task's final report for detail — these are gaps
in modules this task does not own, not bugs introduced here):

* ``app/core/config.py`` declares ``extend_api_key``, ``extend_base_url``,
  ``extend_extract_processor``, ``extend_extract_version``,
  ``extend_parse_engine``, ``extend_parse_version``,
  ``extend_poll_interval_seconds``, ``extend_timeout_seconds``,
  ``own_org_names`` and ``max_upload_mb``. Everything here still reads them
  with ``getattr(..., default)`` so it degrades to documented defaults
  instead of raising if a field were ever missing, and tests patch
  ``get_extend_client``/``get_storage`` directly. A real (non-test) run
  reads these settings normally; there is no gap left here.
* :class:`~app.core.extend.client.ExtractRun` and
  ``ExtendClient.parse_output`` do not retain the literal raw HTTP response
  bodies (only the fields they parsed out). The ``extract.json``/
  ``parse.json`` objects written here are therefore a faithful
  reconstruction of the meaningful fields (``value``, ``metadata``,
  ``parseRunId``, ``usage``, flattened ``blocks``), not byte-identical
  copies of what Extend returned.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.config import get_settings
from app.core.extend.client import get_extend_client
from app.core.extend.errors import ExtendRunFailed, ExtendTimeout, ExtendUnavailable
from app.core.storage import get_storage
from app.db.models.contract import Contract, ContractVersion
from app.db.repositories import clause_repo, contract_repo, field_repo, ingest_repo
from app.services.document_processing.clause_typing import load_family_index
from app.services.document_processing.context_capture import (
    derive_deal_value_band,
    derive_regimes,
    list_classifiable_agreement_types,
)
from app.services.document_processing.fields import REGISTRY, build_extract_schema
from app.services.document_processing.parties import link_signatory, normalize_party_name
from app.services.document_processing.pipeline import NoTextError, build_result
from app.services.document_processing.upload_validation import ValidatedUpload, validate_upload
from app.services.repository import vector

# Level 1 clause families that are never embedded (task 3.2; plan section 5.8).
_NO_EMBED_FAMILIES = frozenset({"preamble", "signature_block"})

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

_MIN_TEXT_CHARS = 200

# Extend failure reasons -> contract.status_reason (section 4.3's table).
_EXTEND_FAILURE_REASON_MAP: dict[str, str] = {
    "PASSWORD_PROTECTED_FILE": "password_protected",
    "FILE_TYPE_NOT_SUPPORTED": "unsupported_format",
    "FILE_SIZE_TOO_LARGE": "too_large",
    "CORRUPT_FILE": "unreadable",
    "PARSING_ERROR": "unreadable",
}


def _map_failure_reason(exc: Exception) -> str:
    """Map an exception raised during ingest to a ``status_reason`` value."""
    if isinstance(exc, NoTextError):
        return "no_text"
    if isinstance(exc, ExtendRunFailed):
        return _EXTEND_FAILURE_REASON_MAP.get(exc.failure_reason, "extraction_failed")
    if isinstance(exc, ExtendTimeout):
        return "timeout"
    if isinstance(exc, ExtendUnavailable):
        return "provider_unavailable"
    return "extraction_failed"


# ---------------------------------------------------------------------------
# create_contract
# ---------------------------------------------------------------------------


async def create_contract(
    session: AsyncSession,
    *,
    validated: ValidatedUpload,
    data: bytes,
    paper_origin: str,
    contract_type: str | None,
    party_role: str | None,
    context: dict | None,
    force: bool = False,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create the ``contract`` + ``contract_version`` (number 1) rows and
    store the original file. Returns ``(contract_id, version_id)``.

    Duplicate check: a ``contract_version.file_sha256`` match raises
    ``AppError(409, "duplicate_file", ...)`` with the existing contract id
    in ``detail``, unless ``force`` is true.

    The rows are committed before the file is stored (plan section 5.1:
    "order of writes"). If ``storage.put`` fails, the contract is marked
    ``failed``/``storage_failed`` in a fresh transaction and the original
    exception is re-raised.
    """
    if not force:
        existing_version = await contract_repo.find_by_sha256(session, validated.sha256)
        if existing_version is not None:
            raise AppError(
                409,
                "duplicate_file",
                "A contract with this file already exists.",
                {"existing_contract_id": str(existing_version.contract_id)},
            )

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    object_key = f"contracts/{contract_id}/v1/{validated.safe_filename}"

    contract = Contract(
        id=contract_id,
        title=validated.safe_filename,
        original_filename=validated.safe_filename,
        object_key=object_key,
        source_format=validated.source_format,
        canonical_text="",
        paper_origin=paper_origin,
        contract_type=contract_type,
        contract_type_source="user" if contract_type else None,
        party_role=party_role,
        context=context,
        status="processing",
    )
    session.add(contract)

    version = ContractVersion(
        id=version_id,
        contract_id=contract_id,
        version_number=1,
        object_key=object_key,
        canonical_text="",
        relation="version",
        file_sha256=validated.sha256,
        file_size_bytes=validated.size_bytes,
        source_format=validated.source_format,
        original_filename=validated.safe_filename,
    )
    session.add(version)
    await session.flush()

    contract.current_version_id = version_id
    await session.flush()
    await session.commit()

    settings = get_settings()
    storage = get_storage(settings)
    try:
        await asyncio.to_thread(storage.put, object_key, data)
    except Exception:
        contract.status = "failed"
        contract.status_reason = "storage_failed"
        await session.commit()
        raise

    return contract_id, version_id


# ---------------------------------------------------------------------------
# run_ingest
# ---------------------------------------------------------------------------


async def run_ingest(
    session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession],
    contract_id: uuid.UUID,
    version_id: uuid.UUID,
) -> None:
    """Run the Extend pipeline for one contract version and write every
    downstream row in one transaction.

    Opens its own sessions from *session_factory* (never the caller's).
    Never leaves the contract in ``processing``: any exception marks it
    ``failed`` with a mapped ``status_reason`` in a fresh session, and fails
    the ``ingest_run`` row when one was started.
    """
    settings = get_settings()
    run_id: uuid.UUID | None = None

    try:
        # 1. Start the run, and read the file facts we need (own short session).
        async with session_factory() as session:
            run = await ingest_repo.start_run(
                session,
                version_id,
                provider="extend",
                processor=getattr(settings, "extend_extract_processor", "extraction_light"),
                processor_version=getattr(settings, "extend_extract_version", "3.8.0"),
                parse_engine_version=getattr(settings, "extend_parse_version", "1.0.0"),
            )
            run_id = run.id
            version_row = await session.get(ContractVersion, version_id)
            if version_row is None:
                raise AppError(404, "not_found", "Contract version not found")
            object_key = version_row.object_key
            safe_filename = version_row.original_filename or "upload"
            await session.commit()

        # 2. Read the stored file and the taxonomy needed to build the
        #    Extract schema (own short, read-only session).
        storage = get_storage(settings)
        file_bytes = await asyncio.to_thread(storage.get, object_key)

        async with session_factory() as session:
            agreement_types = await list_classifiable_agreement_types(session)
            agreement_type_keys = [a.key for a in agreement_types]
            family_index = await load_family_index(session)

        schema = build_extract_schema(agreement_type_keys, sorted(family_index.keys))

        # 3. Talk to Extend: upload, Extract, fetch Parse blocks.
        client = get_extend_client(settings)
        async with client:
            file_id = await client.upload(safe_filename, file_bytes)
            extract_run = await client.extract(file_id, schema)
            parse_blocks = await client.parse_output(extract_run.parse_run_id)

        # 4. Store the raw responses (section 3.1, item 2).
        raw_extract_key = f"contracts/{contract_id}/v1/extract.json"
        raw_parse_key = f"contracts/{contract_id}/v1/parse.json"
        extract_payload = json.dumps(
            {
                "output": {"value": extract_run.value, "metadata": extract_run.metadata},
                "parseRunId": extract_run.parse_run_id,
                "usage": extract_run.usage,
                "baseVersion": extract_run.processor_version,
            }
        ).encode("utf-8")
        parse_payload = json.dumps(
            {"output": {"chunks": [{"blocks": parse_blocks}]}}
        ).encode("utf-8")
        await asyncio.to_thread(storage.put, raw_extract_key, extract_payload)
        await asyncio.to_thread(storage.put, raw_parse_key, parse_payload)

        # 5. Run the pure pipeline.
        own_org_names = list(getattr(settings, "own_org_names", None) or [])
        result = build_result(
            extract_run.value,
            extract_run.metadata,
            parse_blocks,
            family_index=family_index,
            agreement_type_keys=agreement_type_keys,
            own_org_names=own_org_names,
        )

        # 6. One transaction: every downstream table, then the run and the
        #    contract/version rows.
        async with session_factory() as session:
            contract = await session.get(Contract, contract_id)
            version_row = await session.get(ContractVersion, version_id)
            if contract is None or version_row is None:
                raise AppError(404, "not_found", "Contract or version not found")

            clause_rows = await clause_repo.replace_clauses(
                session, contract_id, version_id, result.clauses
            )
            clause_ids_by_ordinal = {row.ordinal: row.id for row in clause_rows}

            resolved_parties: list[tuple[uuid.UUID, object]] = []
            for draft in result.parties:
                party_row = await contract_repo.upsert_party(
                    session, normalize_party_name(draft.name), draft.name
                )
                resolved_parties.append((party_row.id, draft))
            contract_party_rows = await contract_repo.replace_contract_parties(
                session, contract_id, resolved_parties
            )

            parties_list = list(result.parties)
            signatory_entries = []
            for signatory in result.signatories:
                idx = link_signatory(signatory, parties_list)
                contract_party_id = (
                    contract_party_rows[idx].id
                    if idx is not None and idx < len(contract_party_rows)
                    else None
                )
                signatory_entries.append((signatory, contract_party_id))
            await contract_repo.replace_signatories(session, version_id, signatory_entries)

            await field_repo.replace_extracted(
                session,
                contract_id,
                version_id,
                run_id,
                result.fields,
                clause_ids_by_ordinal=clause_ids_by_ordinal,
            )

            values_in_force = await field_repo.values_in_force(session, version_id)
            registry_projection = {
                key: field_def.projection
                for key, field_def in REGISTRY.items()
                if field_def.projection
            }
            await contract_repo.write_metadata_projection(
                session, contract_id, version_id, values_in_force, registry_projection
            )

            counterparty_party_id = next(
                (pid for pid, draft in resolved_parties if draft.role == "counterparty"),
                None,
            )

            # Contract type: a user-supplied value at upload wins outright.
            if contract.contract_type_source != "user":
                if result.contract_type:
                    contract.contract_type = result.contract_type
                    contract.contract_type_source = "extracted"
                else:
                    contract.contract_type = None
                    contract.contract_type_source = None

            if result.title:
                contract.title = result.title

            contract.canonical_text = result.document.text
            contract.counterparty_id = counterparty_party_id
            contract.status = "ready"
            contract.status_reason = None

            resolved_context: dict = dict(contract.context) if contract.context else {}
            if "regimes" not in resolved_context:
                regimes = derive_regimes(result.document.text)
                if regimes:
                    resolved_context["regimes"] = regimes
            if (
                "deal_value_band" not in resolved_context
                and resolved_context.get("deal_value") is not None
            ):
                band = await derive_deal_value_band(session, resolved_context["deal_value"])
                if band is not None:
                    resolved_context["deal_value_band"] = band
            contract.context = resolved_context or None

            version_row.canonical_text = result.document.text
            version_row.page_count = result.document.page_count

            credits_used = None
            if isinstance(extract_run.usage, dict):
                credits_used = extract_run.usage.get("credits") or extract_run.usage.get(
                    "creditsUsed"
                )

            await ingest_repo.finish_run(
                session,
                run_id,
                warnings=list(result.warnings),
                credits_used=credits_used,
                extend_file_id=file_id,
                extend_parse_run_id=extract_run.parse_run_id,
                raw_extract_key=raw_extract_key,
                raw_parse_key=raw_parse_key,
            )

            await session.commit()

        # 7. Embeddings (task 3.2; plan section 5.8): level 1 clauses, except
        #    preamble/signature_block. Runs in its own session/transaction,
        #    after the main commit above, so an embedding failure never rolls
        #    back or fails the contract -- it only adds a warning to the
        #    ingest run, which has already finished "succeeded".
        embed_clauses = [
            SimpleNamespace(
                id=clause_ids_by_ordinal[draft.ordinal],
                text=draft.text,
                clause_type=draft.clause_type,
            )
            for draft in result.clauses
            if draft.level == 1
            and draft.clause_type not in _NO_EMBED_FAMILIES
            and draft.ordinal in clause_ids_by_ordinal
        ]
        if embed_clauses:
            try:
                async with session_factory() as embed_session:
                    await vector.embed_and_store_clauses(
                        contract_id, embed_clauses, embed_session
                    )
                    await embed_session.commit()
            except Exception:  # noqa: BLE001 — downgrade to a warning, never fail the contract
                async with session_factory() as warn_session:
                    warnings = list(result.warnings)
                    if "embedding_failed" not in warnings:
                        warnings.append("embedding_failed")
                    await ingest_repo.finish_run(warn_session, run_id, warnings=warnings)
                    await warn_session.commit()

    except Exception as exc:  # noqa: BLE001 — must never leave a contract "processing"
        reason = _map_failure_reason(exc)
        logger.exception(
            "ingest failed for contract %s version %s, mapped to status_reason=%s",
            contract_id,
            version_id,
            reason,
        )
        async with session_factory() as session:
            contract = await session.get(Contract, contract_id)
            if contract is not None:
                contract.status = "failed"
                contract.status_reason = reason
            if run_id is not None:
                await ingest_repo.fail_run(session, run_id, reason)
            await session.commit()


# ---------------------------------------------------------------------------
# extract_canonical_text
# ---------------------------------------------------------------------------


async def extract_canonical_text(data: bytes, filename: str) -> str:
    """Text-only entry point (plan section 5.7): validate, upload, run a
    standalone Parse, build canonical text. Raises ``NoTextError`` when the
    result is under 200 characters. Used by ``repository/service.py::
    store_version`` (task 3.5) in place of the deleted ``parsers.parse``.
    """
    from app.services.document_processing.canonical import build_canonical

    settings = get_settings()
    max_mb = int(getattr(settings, "max_upload_mb", 25))
    validated = validate_upload(filename, data, max_mb)

    client = get_extend_client(settings)
    async with client:
        file_id = await client.upload(validated.safe_filename, data)
        parse_blocks = await client.parse(file_id)

    document = build_canonical(parse_blocks)
    if len(document.text) < _MIN_TEXT_CHARS:
        raise NoTextError(
            f"canonical text has only {len(document.text)} character(s); "
            f"minimum is {_MIN_TEXT_CHARS}"
        )
    return document.text


# ---------------------------------------------------------------------------
# sweep_stale
# ---------------------------------------------------------------------------


async def sweep_stale(session: AsyncSession, older_than_minutes: int = 15) -> None:
    """Mark every ``processing`` contract last touched more than
    *older_than_minutes* ago as ``failed``/``timeout`` (plan section 5.1).
    Commits.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    result = await session.execute(
        select(Contract).where(Contract.status == "processing", Contract.updated_at < cutoff)
    )
    stale = result.scalars().all()
    for contract in stale:
        contract.status = "failed"
        contract.status_reason = "timeout"
    if stale:
        await session.commit()
