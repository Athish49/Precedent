"""Unit tests for the ingest orchestrator (task 3.1).

No real network or database. Extend is replaced by ``FakeExtendClient``
(fed the real recorded fixtures under ``tests/fixtures/ingest/``), storage
by ``InMemoryStorage``, and every repository call is mocked so this file
tests orchestration (call order, status transitions, failure mapping, the
plan section 7.5 point 7/8 invariants on the data ingest.py computes)
rather than re-proving what task 1.3's own repository tests already cover.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.errors import AppError
from app.core.extend.errors import (
    ExtendRunFailed,
    ExtendTimeout,
    ExtendUnavailable,
)
from app.db.models.contract import Contract, ContractVersion
from app.services.document_processing import ingest
from app.services.document_processing.clause_typing import FamilyIndex
from app.services.document_processing.pipeline import NoTextError
from app.services.document_processing.upload_validation import ValidatedUpload
from tests.fake_extend import FakeExtendClient
from tests.in_memory_storage import InMemoryStorage

_BACKEND = Path(__file__).resolve().parents[2]
_FIXTURES = _BACKEND / "tests" / "fixtures" / "ingest"

AGREEMENT_TYPE_KEYS = ["nda", "saas_msa", "dpa", "vendor_msa"]
# The "msa_styled_docx" fixture (and its sibling contract cases) is the
# synthetic test MSA from the live Extend evaluation (document_processing_
# plan.md section 3.5), whose own-side party is "Halcyon Systems, Inc." —
# distinct from the seed corpus's "Halcyon Care" used by seed/contracts/
# evaluate_ingest.py. This file uses the fixture's own org name.
OWN_ORG_NAMES = ["Halcyon Systems"]


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _load_migration_module(filename: str):
    path = _BACKEND / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(f"_migration_{filename}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def family_index() -> FamilyIndex:
    """The real 31-key FamilyIndex, built from the migrations (no DB)."""
    m010 = _load_migration_module("010_playbook_lookups.py")
    m016 = _load_migration_module("016_doc_proc_schema_a.py")
    rows: list[dict[str, object]] = [
        {"key": fam["key"], "synonyms": fam["synonyms"]} for fam in m010._CLAUSE_FAMILIES
    ]
    for fam in m016._NEW_FAMILIES:
        rows.append({"key": fam["key"], "synonyms": json.loads(fam["synonyms"])})
    assert len(rows) == 31
    return FamilyIndex.from_rows(rows)


def _load_raw_case(name: str) -> tuple[dict, dict]:
    """Load the raw extract.json / parse.json dicts for a fixture case
    (full response shape, as FakeExtendClient expects -- not the flattened
    blocks that ``tests.ingest_fixtures.load_case`` returns)."""
    case_dir = _FIXTURES / name
    with open(case_dir / "extract.json") as f:
        extract = json.load(f)
    with open(case_dir / "parse.json") as f:
        parse = json.load(f)
    return extract, parse


class _FakeSettings:
    """Minimal settings double: enough attributes for ingest.py's own
    direct reads (own_org_names, max_upload_mb). get_storage/get_extend_client
    themselves are monkeypatched away in these tests, so the Extend-specific
    fields are not exercised here.
    """

    own_org_names = OWN_ORG_NAMES
    max_upload_mb = 25
    extend_api_key = "sk-test"
    extend_base_url = "https://api.extend.invalid"
    extend_extract_processor = "extraction_light"
    extend_extract_version = "3.8.0"
    extend_parse_engine = "parse_light"
    extend_parse_version = "1.0.0"
    extend_poll_interval_seconds = 0
    extend_timeout_seconds = 5


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


class _RepoPatches:
    """Patches every repository call ``ingest.py`` makes, recording calls
    and returning realistic objects so orchestration-level assertions can
    be made without a real database.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.clause_rows: list[SimpleNamespace] = []
        self.upsert_party_calls: list[tuple[str, str]] = []
        self.party_ids_by_name: dict[str, uuid.UUID] = {}
        self.replace_contract_parties_calls: list[tuple] = []
        self.replace_signatories_calls: list[tuple] = []
        self.replace_extracted_calls: list[tuple] = []
        self.values_in_force_result: dict = {}
        self.write_metadata_projection_calls: list[tuple] = []
        self.finish_run_calls: list[dict] = []
        self.fail_run_calls: list[tuple] = []
        self.find_by_sha256_result = None

        self.replace_clauses_mock = AsyncMock(side_effect=self._replace_clauses)
        self.upsert_party_mock = AsyncMock(side_effect=self._upsert_party)
        self.replace_contract_parties_mock = AsyncMock(
            side_effect=self._replace_contract_parties
        )
        self.replace_signatories_mock = AsyncMock(side_effect=self._replace_signatories)
        self.replace_extracted_mock = AsyncMock(side_effect=self._replace_extracted)
        self.values_in_force_mock = AsyncMock(side_effect=self._values_in_force)
        self.write_metadata_projection_mock = AsyncMock(
            side_effect=self._write_metadata_projection
        )
        self.find_by_sha256_mock = AsyncMock(side_effect=self._find_by_sha256)

        run_counter = {"n": 0}

        async def _start_run(session, version_id, **kwargs):
            run_counter["n"] += 1
            return SimpleNamespace(id=uuid.uuid4(), contract_version_id=version_id, **kwargs)

        async def _finish_run(session, run_id, **kwargs):
            self.finish_run_calls.append((run_id, kwargs))
            return SimpleNamespace(id=run_id, status="succeeded", **kwargs)

        async def _fail_run(session, run_id, failure_reason, **kwargs):
            self.fail_run_calls.append((run_id, failure_reason, kwargs))
            return SimpleNamespace(id=run_id, status="failed", failure_reason=failure_reason)

        self.start_run_mock = AsyncMock(side_effect=_start_run)
        self.finish_run_mock = AsyncMock(side_effect=_finish_run)
        self.fail_run_mock = AsyncMock(side_effect=_fail_run)

        monkeypatch.setattr(ingest.clause_repo, "replace_clauses", self.replace_clauses_mock)
        monkeypatch.setattr(ingest.contract_repo, "upsert_party", self.upsert_party_mock)
        monkeypatch.setattr(
            ingest.contract_repo, "replace_contract_parties", self.replace_contract_parties_mock
        )
        monkeypatch.setattr(
            ingest.contract_repo, "replace_signatories", self.replace_signatories_mock
        )
        monkeypatch.setattr(ingest.field_repo, "replace_extracted", self.replace_extracted_mock)
        monkeypatch.setattr(ingest.field_repo, "values_in_force", self.values_in_force_mock)
        monkeypatch.setattr(
            ingest.contract_repo, "write_metadata_projection", self.write_metadata_projection_mock
        )
        monkeypatch.setattr(ingest.contract_repo, "find_by_sha256", self.find_by_sha256_mock)
        monkeypatch.setattr(ingest.ingest_repo, "start_run", self.start_run_mock)
        monkeypatch.setattr(ingest.ingest_repo, "finish_run", self.finish_run_mock)
        monkeypatch.setattr(ingest.ingest_repo, "fail_run", self.fail_run_mock)

    async def _replace_clauses(self, session, contract_id, version_id, drafts):
        self.clause_rows = [
            SimpleNamespace(ordinal=d.ordinal, id=uuid.uuid4(), contract_version_id=version_id)
            for d in drafts
        ]
        return self.clause_rows

    async def _upsert_party(self, session, normalized_name, display_name):
        if normalized_name not in self.party_ids_by_name:
            self.party_ids_by_name[normalized_name] = uuid.uuid4()
        self.upsert_party_calls.append((normalized_name, display_name))
        return SimpleNamespace(
            id=self.party_ids_by_name[normalized_name],
            normalized_name=normalized_name,
            display_name=display_name,
        )

    async def _replace_contract_parties(self, session, contract_id, entries):
        self.replace_contract_parties_calls.append((contract_id, entries))
        return [SimpleNamespace(id=pid, role=draft.role) for pid, draft in entries]

    async def _replace_signatories(self, session, version_id, entries):
        self.replace_signatories_calls.append((version_id, entries))
        return [SimpleNamespace(id=uuid.uuid4()) for _ in entries]

    async def _replace_extracted(
        self, session, contract_id, version_id, run_id, values, *, clause_ids_by_ordinal=None
    ):
        self.replace_extracted_calls.append(
            (contract_id, version_id, run_id, list(values), clause_ids_by_ordinal)
        )
        return []

    async def _values_in_force(self, session, version_id):
        return self.values_in_force_result

    async def _write_metadata_projection(
        self, session, contract_id, version_id, values_in_force, registry_projection
    ):
        self.write_metadata_projection_calls.append(
            (contract_id, version_id, values_in_force, registry_projection)
        )
        return SimpleNamespace(contract_id=contract_id)

    async def _find_by_sha256(self, session, sha256):
        return self.find_by_sha256_result


@pytest.fixture
def repo_patches(monkeypatch: pytest.MonkeyPatch) -> _RepoPatches:
    return _RepoPatches(monkeypatch)


class _EmbedCalls:
    """Records every ``embed_and_store_clauses`` call so tests can assert on
    which clauses were embedded, without touching the real model (task 3.2).
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def __call__(self, contract_id, clauses, session) -> None:
        self.calls.append((contract_id, list(clauses)))


@pytest.fixture(autouse=True)
def embed_patch(monkeypatch: pytest.MonkeyPatch) -> _EmbedCalls:
    """Autouse so no test in this file ever calls the real embedding model
    (``app.core.embeddings.embed`` loads a real sentence-transformers model).
    Individual tests can still override ``ingest.vector.embed_and_store_clauses``
    themselves (e.g. to simulate a failure) after pulling this fixture.
    """
    recorder = _EmbedCalls()
    monkeypatch.setattr(ingest.vector, "embed_and_store_clauses", recorder)
    return recorder


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> InMemoryStorage:
    double = InMemoryStorage()
    monkeypatch.setattr(ingest, "get_storage", lambda settings=None: double)
    return double


@pytest.fixture
def fake_settings(monkeypatch: pytest.MonkeyPatch) -> _FakeSettings:
    settings = _FakeSettings()
    monkeypatch.setattr(ingest, "get_settings", lambda: settings)
    return settings


def _patch_extend_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    extract_response: dict | None = None,
    parse_response: dict | None = None,
    raise_on_extract=None,
    raise_on_parse=None,
    raise_on_upload=None,
) -> FakeExtendClient:
    client = FakeExtendClient(
        extract_response or {"output": {"value": {}, "metadata": {}}, "parseRunId": "pr_x"},
        parse_response or {"output": {"chunks": []}},
        raise_on_extract=raise_on_extract,
        raise_on_parse=raise_on_parse,
        raise_on_upload=raise_on_upload,
    )
    monkeypatch.setattr(ingest, "get_extend_client", lambda settings=None: client)
    return client


class _SessionFactory:
    """A ``session_factory`` whose ``()`` call yields a fresh async-context
    session. Every produced session shares the same ``AsyncMock`` so the
    test can assert on it, and ``session.get`` resolves ``Contract``/
    ``ContractVersion`` by id from the dicts given at construction.
    """

    def __init__(self, contracts: dict, versions: dict) -> None:
        self.contracts = contracts
        self.versions = versions
        self.sessions: list[AsyncMock] = []

    def __call__(self) -> AsyncMock:
        session = _make_session()

        async def _get(model, pk):
            if model is Contract:
                return self.contracts.get(pk)
            if model is ContractVersion:
                return self.versions.get(pk)
            return None

        session.get = AsyncMock(side_effect=_get)
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        self.sessions.append(session)
        return session


def _validated_upload(sha256: str = "a" * 64) -> ValidatedUpload:
    return ValidatedUpload(
        source_format="docx", sha256=sha256, size_bytes=100, safe_filename="contract.docx"
    )


# ---------------------------------------------------------------------------
# create_contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_contract_writes_rows_and_stores_file(
    storage: InMemoryStorage, repo_patches: _RepoPatches, fake_settings: _FakeSettings
) -> None:
    session = _make_session()
    validated = _validated_upload()

    contract_id, version_id = await ingest.create_contract(
        session,
        validated=validated,
        data=b"file bytes",
        paper_origin="own",
        contract_type=None,
        party_role=None,
        context=None,
    )

    assert session.add.call_count == 2
    added = [call.args[0] for call in session.add.call_args_list]
    contract = next(a for a in added if isinstance(a, Contract))
    version = next(a for a in added if isinstance(a, ContractVersion))

    assert contract.id == contract_id
    assert contract.status == "processing"
    assert contract.title == validated.safe_filename
    assert contract.original_filename == validated.safe_filename
    assert contract.current_version_id == version_id
    assert version.id == version_id
    assert version.version_number == 1
    assert version.relation == "version"
    assert version.file_sha256 == validated.sha256
    assert session.commit.await_count >= 1

    key = f"contracts/{contract_id}/v1/{validated.safe_filename}"
    assert storage.get(key) == b"file bytes"


@pytest.mark.asyncio
async def test_create_contract_duplicate_without_force_raises_409(
    storage: InMemoryStorage, repo_patches: _RepoPatches, fake_settings: _FakeSettings
) -> None:
    existing_id = uuid.uuid4()
    repo_patches.find_by_sha256_result = SimpleNamespace(contract_id=existing_id)
    session = _make_session()

    with pytest.raises(AppError) as exc_info:
        await ingest.create_contract(
            session,
            validated=_validated_upload(),
            data=b"bytes",
            paper_origin="own",
            contract_type=None,
            party_role=None,
            context=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "duplicate_file"
    assert exc_info.value.detail == {"existing_contract_id": str(existing_id)}
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_contract_force_bypasses_duplicate_check(
    storage: InMemoryStorage, repo_patches: _RepoPatches, fake_settings: _FakeSettings
) -> None:
    repo_patches.find_by_sha256_result = SimpleNamespace(contract_id=uuid.uuid4())
    session = _make_session()

    contract_id, version_id = await ingest.create_contract(
        session,
        validated=_validated_upload(),
        data=b"bytes",
        paper_origin="own",
        contract_type=None,
        party_role=None,
        context=None,
        force=True,
    )

    assert contract_id is not None
    assert version_id is not None
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_create_contract_storage_failure_marks_failed_and_reraises(
    repo_patches: _RepoPatches, fake_settings: _FakeSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _BrokenStorage(InMemoryStorage):
        def put(self, key, data):
            raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(ingest, "get_storage", lambda settings=None: _BrokenStorage())
    session = _make_session()

    with pytest.raises(RuntimeError):
        await ingest.create_contract(
            session,
            validated=_validated_upload(),
            data=b"bytes",
            paper_origin="own",
            contract_type=None,
            party_role=None,
            context=None,
        )

    added = [call.args[0] for call in session.add.call_args_list]
    contract = next(a for a in added if isinstance(a, Contract))
    assert contract.status == "failed"
    assert contract.status_reason == "storage_failed"


@pytest.mark.asyncio
async def test_create_contract_user_contract_type_source(
    storage: InMemoryStorage, repo_patches: _RepoPatches, fake_settings: _FakeSettings
) -> None:
    session = _make_session()
    await ingest.create_contract(
        session,
        validated=_validated_upload(),
        data=b"bytes",
        paper_origin="own",
        contract_type="saas_msa",
        party_role="vendor",
        context={"region": "us"},
    )
    added = [call.args[0] for call in session.add.call_args_list]
    contract = next(a for a in added if isinstance(a, Contract))
    assert contract.contract_type == "saas_msa"
    assert contract.contract_type_source == "user"
    assert contract.party_role == "vendor"
    assert contract.context == {"region": "us"}


# ---------------------------------------------------------------------------
# run_ingest — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_ingest_happy_path_ready(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
) -> None:
    extract_resp, parse_resp = _load_raw_case("msa_styled_docx")
    _patch_extend_client(monkeypatch, extract_response=extract_resp, parse_response=parse_resp)

    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))
    monkeypatch.setattr(ingest, "derive_regimes", lambda text: [])
    monkeypatch.setattr(ingest, "derive_deal_value_band", AsyncMock(return_value=None))

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    object_key = f"contracts/{contract_id}/v1/contract.docx"
    storage.put(object_key, b"original file bytes")

    contract = Contract(
        id=contract_id,
        title="contract.docx",
        original_filename="contract.docx",
        object_key=object_key,
        source_format="docx",
        canonical_text="",
        paper_origin="own",
        status="processing",
        current_version_id=version_id,
    )
    version = ContractVersion(
        id=version_id,
        contract_id=contract_id,
        version_number=1,
        object_key=object_key,
        canonical_text="",
        relation="version",
        original_filename="contract.docx",
    )

    factory = _SessionFactory({contract_id: contract}, {version_id: version})

    await ingest.run_ingest(factory, contract_id, version_id)

    # Status.
    assert contract.status == "ready"
    assert contract.status_reason is None

    # Point 8: contract.canonical_text equals the version's text.
    assert contract.canonical_text == version.canonical_text
    assert contract.canonical_text != ""
    assert version.page_count is not None and version.page_count > 0

    # Point 8: counterparty_id matches the party resolved to role "counterparty".
    # The fixture has Halcyon Care (own) plus a real counterparty, so a
    # counterparty must have been resolved.
    assert contract.counterparty_id is not None
    counterparty_names = [
        name
        for name, pid in repo_patches.party_ids_by_name.items()
        if pid == contract.counterparty_id
    ]
    assert len(counterparty_names) == 1

    # Every table was written to.
    repo_patches.replace_clauses_mock.assert_awaited_once()
    assert len(repo_patches.clause_rows) > 0
    repo_patches.replace_extracted_mock.assert_awaited_once()
    repo_patches.write_metadata_projection_mock.assert_awaited_once()
    assert repo_patches.upsert_party_calls  # at least one party resolved
    repo_patches.replace_contract_parties_mock.assert_awaited_once()
    repo_patches.replace_signatories_mock.assert_awaited_once()

    # ingest_run finished, not failed.
    assert len(repo_patches.finish_run_calls) == 1
    assert len(repo_patches.fail_run_calls) == 0

    # Raw responses are in storage.
    raw_extract = json.loads(storage.get(f"contracts/{contract_id}/v1/extract.json"))
    raw_parse = json.loads(storage.get(f"contracts/{contract_id}/v1/parse.json"))
    assert raw_extract["output"]["value"]
    assert raw_parse["output"]["chunks"]


@pytest.mark.asyncio
async def test_run_ingest_embeds_level1_clauses_except_structure(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
    embed_patch: _EmbedCalls,
) -> None:
    """Task 3.2: embeddings are written for level 1 clauses, excluding
    preamble and signature_block, and the contract still ends `ready`."""
    extract_resp, parse_resp = _load_raw_case("msa_styled_docx")
    _patch_extend_client(monkeypatch, extract_response=extract_resp, parse_response=parse_resp)
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))
    monkeypatch.setattr(ingest, "derive_regimes", lambda text: [])
    monkeypatch.setattr(ingest, "derive_deal_value_band", AsyncMock(return_value=None))

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    object_key = f"contracts/{contract_id}/v1/contract.docx"
    storage.put(object_key, b"original file bytes")
    contract, _version, factory, _ = _fresh_contract_and_factory(contract_id, version_id)
    storage.put(object_key, b"original file bytes")

    await ingest.run_ingest(factory, contract_id, version_id)

    assert contract.status == "ready"
    assert len(embed_patch.calls) == 1
    embedded_contract_id, embedded_clauses = embed_patch.calls[0]
    assert embedded_contract_id == contract_id
    assert embedded_clauses, "expected at least one level 1 clause to be embedded"

    embedded_types = {c.clause_type for c in embedded_clauses}
    assert "preamble" not in embedded_types
    assert "signature_block" not in embedded_types

    # Every embedded clause id must be a real clause row id (task 3.2
    # requires embedding the clauses just written, not re-derived ones).
    written_ids = {row.id for row in repo_patches.clause_rows}
    for clause in embedded_clauses:
        assert clause.id in written_ids
        assert clause.text
        assert clause.clause_type


@pytest.mark.asyncio
async def test_run_ingest_embedding_failure_downgrades_to_warning(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
    embed_patch: _EmbedCalls,
) -> None:
    """Task 3.2: an embedding failure must not fail the contract -- it adds
    `embedding_failed` to the ingest run's warnings, and the contract stays
    `ready`."""
    extract_resp, parse_resp = _load_raw_case("msa_styled_docx")
    _patch_extend_client(monkeypatch, extract_response=extract_resp, parse_response=parse_resp)
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))
    monkeypatch.setattr(ingest, "derive_regimes", lambda text: [])
    monkeypatch.setattr(ingest, "derive_deal_value_band", AsyncMock(return_value=None))

    async def _boom(contract_id, clauses, session) -> None:
        raise RuntimeError("embedding model unavailable")

    monkeypatch.setattr(ingest.vector, "embed_and_store_clauses", _boom)

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    object_key = f"contracts/{contract_id}/v1/contract.docx"
    contract, _version, factory, _ = _fresh_contract_and_factory(contract_id, version_id)
    storage.put(object_key, b"original file bytes")

    await ingest.run_ingest(factory, contract_id, version_id)

    # The contract reaches `ready` despite the embedding failure.
    assert contract.status == "ready"
    assert contract.status_reason is None
    assert len(repo_patches.fail_run_calls) == 0

    # finish_run was called twice: once by the main transaction, once more
    # to add the warning after the embedding step failed.
    assert len(repo_patches.finish_run_calls) == 2
    _first_run_id, first_kwargs = repo_patches.finish_run_calls[0]
    assert "embedding_failed" not in first_kwargs["warnings"]
    second_run_id, second_kwargs = repo_patches.finish_run_calls[1]
    assert second_run_id == _first_run_id
    assert "embedding_failed" in second_kwargs["warnings"]


@pytest.mark.asyncio
async def test_run_ingest_keeps_user_supplied_contract_type(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
) -> None:
    extract_resp, parse_resp = _load_raw_case("msa_styled_docx")
    _patch_extend_client(monkeypatch, extract_response=extract_resp, parse_response=parse_resp)
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))
    monkeypatch.setattr(ingest, "derive_regimes", lambda text: [])
    monkeypatch.setattr(ingest, "derive_deal_value_band", AsyncMock(return_value=None))

    contract_id = uuid.uuid4()
    version_id = uuid.uuid4()
    object_key = f"contracts/{contract_id}/v1/contract.docx"
    storage.put(object_key, b"original file bytes")

    contract = Contract(
        id=contract_id,
        title="contract.docx",
        original_filename="contract.docx",
        object_key=object_key,
        source_format="docx",
        canonical_text="",
        paper_origin="own",
        status="processing",
        current_version_id=version_id,
        contract_type="dpa",
        contract_type_source="user",
    )
    version = ContractVersion(
        id=version_id,
        contract_id=contract_id,
        version_number=1,
        object_key=object_key,
        canonical_text="",
        relation="version",
        original_filename="contract.docx",
    )
    factory = _SessionFactory({contract_id: contract}, {version_id: version})

    await ingest.run_ingest(factory, contract_id, version_id)

    assert contract.status == "ready"
    assert contract.contract_type == "dpa"
    assert contract.contract_type_source == "user"


# ---------------------------------------------------------------------------
# run_ingest — failure modes
# ---------------------------------------------------------------------------


def _fresh_contract_and_factory(contract_id: uuid.UUID, version_id: uuid.UUID):
    object_key = f"contracts/{contract_id}/v1/contract.docx"
    contract = Contract(
        id=contract_id,
        title="contract.docx",
        original_filename="contract.docx",
        object_key=object_key,
        source_format="docx",
        canonical_text="",
        paper_origin="own",
        status="processing",
        current_version_id=version_id,
    )
    version = ContractVersion(
        id=version_id,
        contract_id=contract_id,
        version_number=1,
        object_key=object_key,
        canonical_text="",
        relation="version",
        original_filename="contract.docx",
    )
    factory = _SessionFactory({contract_id: contract}, {version_id: version})
    return contract, version, factory, object_key


@pytest.mark.parametrize(
    "failure_reason,expected_status_reason",
    [
        ("PASSWORD_PROTECTED_FILE", "password_protected"),
        ("FILE_TYPE_NOT_SUPPORTED", "unsupported_format"),
        ("FILE_SIZE_TOO_LARGE", "too_large"),
        ("CORRUPT_FILE", "unreadable"),
        ("PARSING_ERROR", "unreadable"),
        ("SOMETHING_ELSE_ENTIRELY", "extraction_failed"),
    ],
)
@pytest.mark.asyncio
async def test_run_ingest_extend_run_failed_maps_reason(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
    failure_reason: str,
    expected_status_reason: str,
) -> None:
    _patch_extend_client(monkeypatch, raise_on_extract=ExtendRunFailed(failure_reason))
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))

    contract_id, version_id = uuid.uuid4(), uuid.uuid4()
    contract, _version, factory, object_key = _fresh_contract_and_factory(contract_id, version_id)
    storage.put(object_key, b"bytes")

    await ingest.run_ingest(factory, contract_id, version_id)

    assert contract.status == "failed"
    assert contract.status_reason == expected_status_reason
    repo_patches.replace_clauses_mock.assert_not_awaited()
    assert len(repo_patches.fail_run_calls) == 1
    assert repo_patches.fail_run_calls[0][1] == expected_status_reason


@pytest.mark.asyncio
async def test_run_ingest_extend_timeout_maps_to_timeout(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
) -> None:
    _patch_extend_client(monkeypatch, raise_on_extract=ExtendTimeout())
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))

    contract_id, version_id = uuid.uuid4(), uuid.uuid4()
    contract, _version, factory, object_key = _fresh_contract_and_factory(contract_id, version_id)
    storage.put(object_key, b"bytes")

    await ingest.run_ingest(factory, contract_id, version_id)

    assert contract.status == "failed"
    assert contract.status_reason == "timeout"
    repo_patches.replace_clauses_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_ingest_extend_unavailable_maps_to_provider_unavailable(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
) -> None:
    _patch_extend_client(monkeypatch, raise_on_upload=ExtendUnavailable())
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))

    contract_id, version_id = uuid.uuid4(), uuid.uuid4()
    contract, _version, factory, object_key = _fresh_contract_and_factory(contract_id, version_id)
    storage.put(object_key, b"bytes")

    await ingest.run_ingest(factory, contract_id, version_id)

    assert contract.status == "failed"
    assert contract.status_reason == "provider_unavailable"
    repo_patches.replace_clauses_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_ingest_no_text_maps_to_no_text(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
) -> None:
    extract_resp, parse_resp = _load_raw_case("blank")
    _patch_extend_client(monkeypatch, extract_response=extract_resp, parse_response=parse_resp)
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(return_value=[SimpleNamespace(key=k) for k in AGREEMENT_TYPE_KEYS]),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))

    contract_id, version_id = uuid.uuid4(), uuid.uuid4()
    contract, _version, factory, object_key = _fresh_contract_and_factory(contract_id, version_id)
    storage.put(object_key, b"bytes")

    await ingest.run_ingest(factory, contract_id, version_id)

    assert contract.status == "failed"
    assert contract.status_reason == "no_text"
    repo_patches.replace_clauses_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_ingest_never_leaves_contract_processing_on_unexpected_error(
    storage: InMemoryStorage,
    repo_patches: _RepoPatches,
    fake_settings: _FakeSettings,
    monkeypatch: pytest.MonkeyPatch,
    family_index: FamilyIndex,
) -> None:
    """An exception from a step with no specific mapping still ends `failed`,
    never stuck `processing` (section 3.1, item 5)."""
    monkeypatch.setattr(
        ingest,
        "list_classifiable_agreement_types",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    monkeypatch.setattr(ingest, "load_family_index", AsyncMock(return_value=family_index))
    _patch_extend_client(monkeypatch)

    contract_id, version_id = uuid.uuid4(), uuid.uuid4()
    contract, _version, factory, object_key = _fresh_contract_and_factory(contract_id, version_id)
    storage.put(object_key, b"bytes")

    await ingest.run_ingest(factory, contract_id, version_id)

    assert contract.status == "failed"
    assert contract.status_reason == "extraction_failed"


# ---------------------------------------------------------------------------
# extract_canonical_text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_canonical_text_returns_text(
    fake_settings: _FakeSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _extract_resp, parse_resp = _load_raw_case("msa_styled_docx")
    _patch_extend_client(monkeypatch, parse_response=parse_resp)

    text = await ingest.extract_canonical_text(b"%PDF-1.4 fake", "contract.pdf")
    assert isinstance(text, str)
    assert len(text) >= 200


@pytest.mark.asyncio
async def test_extract_canonical_text_raises_no_text_on_blank(
    fake_settings: _FakeSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _extract_resp, parse_resp = _load_raw_case("blank")
    _patch_extend_client(monkeypatch, parse_response=parse_resp)

    with pytest.raises(NoTextError):
        await ingest.extract_canonical_text(b"%PDF-1.4 fake", "contract.pdf")


@pytest.mark.asyncio
async def test_extract_canonical_text_rejects_bad_upload(
    fake_settings: _FakeSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(AppError):
        await ingest.extract_canonical_text(b"", "contract.pdf")


# ---------------------------------------------------------------------------
# sweep_stale
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sweep_stale_marks_old_processing_contracts_failed() -> None:
    from datetime import UTC, datetime, timedelta

    old_contract = Contract(
        id=uuid.uuid4(),
        title="old",
        object_key="k",
        source_format="pdf",
        canonical_text="",
        paper_origin="own",
        status="processing",
    )
    old_contract.updated_at = datetime.now(UTC) - timedelta(minutes=30)

    session = _make_session()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [old_contract]
    session.execute.return_value = scalars_result

    await ingest.sweep_stale(session, older_than_minutes=15)

    assert old_contract.status == "failed"
    assert old_contract.status_reason == "timeout"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_sweep_stale_no_stale_rows_does_not_commit() -> None:
    session = _make_session()
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = []
    session.execute.return_value = scalars_result

    await ingest.sweep_stale(session)

    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# No legacy imports (plan section 11; this task's "Done when")
# ---------------------------------------------------------------------------


def test_ingest_does_not_import_legacy_modules() -> None:
    source = (_BACKEND / "app" / "services" / "document_processing" / "ingest.py").read_text()
    forbidden = ["service", "parsers", "extraction", "segmentation", "clause_types"]
    for name in forbidden:
        pattern = rf"^\s*(import|from)\s+\S*\b{name}\b"
        assert not re.search(pattern, source, re.MULTILINE), f"ingest.py imports {name!r}"
