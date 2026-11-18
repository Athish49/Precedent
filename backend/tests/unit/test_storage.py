"""Unit tests for app.core.storage.

The S3 backend is exercised against a mocked boto3 client: no network, no
credentials. The in-memory double used by the rest of the suite is tested
here too. Nothing in this file touches the filesystem.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import app.core.storage as storage_module
from app.core.config import Settings
from app.core.storage import (
    S3StorageBackend,
    StorageBackend,
    StorageConfigurationError,
    get_storage,
    validate_key,
)
from tests.in_memory_storage import InMemoryStorage

_BUCKET = "test-bucket"

# Keys that must never reach the bucket: absolute, or escaping the prefix.
_BAD_KEYS = [
    "/contracts/x/y.pdf",
    "\\contracts\\x\\y.pdf",
    "../other-project/secret.pdf",
    "contracts/../../other-project/secret.pdf",
    "contracts/x/..",
    "contracts\\..\\..\\secret.pdf",
    "..",
    "",
]


@pytest.fixture()
def s3_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``boto3.client`` with a factory returning one mock client."""
    client = MagicMock(name="s3_client")
    factory = MagicMock(name="boto3.client", return_value=client)
    monkeypatch.setattr("boto3.client", factory)
    client.factory = factory
    return client


@pytest.fixture()
def settings() -> Settings:
    """Settings built from the placeholder environment in conftest."""
    return Settings(_env_file=None)


@pytest.fixture()
def backend(s3_client: MagicMock, settings: Settings) -> S3StorageBackend:
    result = get_storage(settings)
    assert isinstance(result, S3StorageBackend)
    return result


# ── S3 backend: project prefix ────────────────────────────────────────────────


class TestS3Prefix:
    def test_put_reaches_client_with_namespace_prefix(
        self, backend: S3StorageBackend, s3_client: MagicMock
    ) -> None:
        backend.put("contracts/x/y.pdf", b"%PDF")
        s3_client.put_object.assert_called_once_with(
            Bucket=_BUCKET, Key="precedent/contracts/x/y.pdf", Body=b"%PDF"
        )

    def test_get_reads_prefixed_key(self, backend: S3StorageBackend, s3_client: MagicMock) -> None:
        s3_client.get_object.return_value = {"Body": MagicMock(read=lambda: b"payload")}
        assert backend.get("contracts/x/y.pdf") == b"payload"
        s3_client.get_object.assert_called_once_with(
            Bucket=_BUCKET, Key="precedent/contracts/x/y.pdf"
        )

    def test_presign_signs_prefixed_key(
        self, backend: S3StorageBackend, s3_client: MagicMock
    ) -> None:
        s3_client.generate_presigned_url.return_value = "https://signed.example/url"
        assert backend.presign("contracts/x/y.pdf", expires_in=120) == "https://signed.example/url"
        s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": _BUCKET, "Key": "precedent/contracts/x/y.pdf"},
            ExpiresIn=120,
        )

    def test_prefix_follows_project_namespace(
        self, monkeypatch: pytest.MonkeyPatch, s3_client: MagicMock
    ) -> None:
        monkeypatch.setenv("PROJECT_NAMESPACE", "other_project")
        backend = get_storage(Settings(_env_file=None))
        backend.put("contracts/x/y.pdf", b"data")
        assert s3_client.put_object.call_args.kwargs["Key"] == "other_project/contracts/x/y.pdf"

    def test_explicit_prefix_setting_wins(
        self, monkeypatch: pytest.MonkeyPatch, s3_client: MagicMock
    ) -> None:
        monkeypatch.setenv("OBJECT_STORAGE_PREFIX", "/shared/precedent/")
        backend = get_storage(Settings(_env_file=None))
        backend.put("a.txt", b"data")
        assert s3_client.put_object.call_args.kwargs["Key"] == "shared/precedent/a.txt"

    def test_health_check_key_is_prefixed(
        self, backend: S3StorageBackend, s3_client: MagicMock
    ) -> None:
        backend.put("__health_check__", b"ok")
        assert s3_client.put_object.call_args.kwargs["Key"] == "precedent/__health_check__"

    def test_client_built_from_settings(
        self, backend: S3StorageBackend, s3_client: MagicMock
    ) -> None:
        s3_client.factory.assert_called_once_with(
            "s3",
            endpoint_url="https://storage.invalid",
            aws_access_key_id="test-access-key",
            aws_secret_access_key="test-secret-key",
        )
        assert backend.prefix == "precedent"
        assert isinstance(backend, StorageBackend)


class TestS3ListTopLevel:
    def test_lists_root_names_only_and_reads_nothing(
        self, backend: S3StorageBackend, s3_client: MagicMock
    ) -> None:
        paginator = s3_client.get_paginator.return_value
        paginator.paginate.return_value = [
            {
                "Contents": [{"Key": "readme.txt"}],
                "CommonPrefixes": [{"Prefix": "precedent/"}, {"Prefix": "other-project/"}],
            },
            {"CommonPrefixes": [{"Prefix": "precedent/"}]},
            {},
        ]

        assert backend.list_top_level() == ["other-project/", "precedent/", "readme.txt"]

        s3_client.get_paginator.assert_called_once_with("list_objects_v2")
        paginator.paginate.assert_called_once_with(Bucket=_BUCKET, Delimiter="/")
        s3_client.get_object.assert_not_called()
        s3_client.put_object.assert_not_called()


# ── S3 backend: key validation and errors ─────────────────────────────────────


class TestS3KeyValidation:
    @pytest.mark.parametrize("key", _BAD_KEYS)
    def test_put_rejects_unsafe_key(
        self, backend: S3StorageBackend, s3_client: MagicMock, key: str
    ) -> None:
        with pytest.raises(ValueError):
            backend.put(key, b"data")
        s3_client.put_object.assert_not_called()

    @pytest.mark.parametrize("key", _BAD_KEYS)
    def test_get_rejects_unsafe_key(
        self, backend: S3StorageBackend, s3_client: MagicMock, key: str
    ) -> None:
        with pytest.raises(ValueError):
            backend.get(key)
        s3_client.get_object.assert_not_called()

    @pytest.mark.parametrize("key", _BAD_KEYS)
    def test_presign_rejects_unsafe_key(
        self, backend: S3StorageBackend, s3_client: MagicMock, key: str
    ) -> None:
        with pytest.raises(ValueError):
            backend.presign(key)
        s3_client.generate_presigned_url.assert_not_called()

    def test_dots_inside_a_filename_are_allowed(self) -> None:
        key = "contracts/x/report..final.v2.pdf"
        assert validate_key(key) == key

    def test_get_missing_key_raises_key_error(
        self, backend: S3StorageBackend, s3_client: MagicMock
    ) -> None:
        s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
        )
        with pytest.raises(KeyError):
            backend.get("contracts/missing.pdf")

    def test_get_other_client_error_propagates(
        self, backend: S3StorageBackend, s3_client: MagicMock
    ) -> None:
        s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject"
        )
        with pytest.raises(ClientError):
            backend.get("contracts/x/y.pdf")


# ── get_storage factory: no fallback ──────────────────────────────────────────


def _complete_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "object_storage_endpoint": "https://storage.invalid",
        "object_storage_bucket": _BUCKET,
        "object_storage_access_key": "test-access-key",
        "object_storage_secret_key": "test-secret-key",
        "object_storage_prefix": "precedent",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestGetStorageFactory:
    def test_returns_s3_backend(self, s3_client: MagicMock) -> None:
        assert isinstance(get_storage(_complete_settings()), S3StorageBackend)

    @pytest.mark.parametrize(
        ("attr", "env_name"),
        [
            ("object_storage_endpoint", "OBJECT_STORAGE_ENDPOINT"),
            ("object_storage_bucket", "OBJECT_STORAGE_BUCKET"),
            ("object_storage_access_key", "OBJECT_STORAGE_ACCESS_KEY"),
            ("object_storage_secret_key", "OBJECT_STORAGE_SECRET_KEY"),
            ("object_storage_prefix", "OBJECT_STORAGE_PREFIX"),
        ],
    )
    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_missing_setting_raises_naming_the_variable(
        self, s3_client: MagicMock, attr: str, env_name: str, blank: str | None
    ) -> None:
        with pytest.raises(StorageConfigurationError) as exc_info:
            get_storage(_complete_settings(**{attr: blank}))
        assert env_name in str(exc_info.value)
        s3_client.factory.assert_not_called()

    def test_object_without_storage_attributes_raises(self, s3_client: MagicMock) -> None:
        with pytest.raises(StorageConfigurationError) as exc_info:
            get_storage(object())
        message = str(exc_info.value)
        for env_name in (
            "OBJECT_STORAGE_ENDPOINT",
            "OBJECT_STORAGE_BUCKET",
            "OBJECT_STORAGE_ACCESS_KEY",
            "OBJECT_STORAGE_SECRET_KEY",
        ):
            assert env_name in message

    def test_no_local_backend_exists(self) -> None:
        assert not hasattr(storage_module, "FilesystemStorageBackend")
        assert "FilesystemStorageBackend" not in storage_module.__all__
        backends = [
            obj
            for obj in vars(storage_module).values()
            if isinstance(obj, type)
            and issubclass(obj, StorageBackend)
            and obj is not StorageBackend
        ]
        assert backends == [S3StorageBackend]


# ── InMemoryStorage test double ───────────────────────────────────────────────


class TestInMemoryStorage:
    def test_implements_storage_backend_interface(self) -> None:
        assert isinstance(InMemoryStorage(), StorageBackend)

    def test_round_trip(self) -> None:
        double = InMemoryStorage()
        double.put("contracts/x/y.pdf", b"payload")
        assert double.get("contracts/x/y.pdf") == b"payload"
        assert "contracts/x/y.pdf" in double
        assert double.keys() == ["contracts/x/y.pdf"]

    def test_put_overwrites_existing_key(self) -> None:
        double = InMemoryStorage()
        double.put("dup.txt", b"first")
        double.put("dup.txt", b"second")
        assert double.get("dup.txt") == b"second"

    def test_empty_bytes_round_trip(self) -> None:
        double = InMemoryStorage()
        double.put("empty.bin", b"")
        assert double.get("empty.bin") == b""

    def test_get_missing_key_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            InMemoryStorage().get("does/not/exist.bin")

    def test_presign_returns_a_url_for_the_key(self) -> None:
        url = InMemoryStorage().presign("contracts/x/y.pdf", expires_in=60)
        assert "contracts/x/y.pdf" in url

    @pytest.mark.parametrize("key", _BAD_KEYS)
    def test_rejects_the_same_keys_as_the_real_backend(self, key: str) -> None:
        double = InMemoryStorage()
        with pytest.raises(ValueError):
            double.put(key, b"data")
        with pytest.raises(ValueError):
            double.get(key)
        with pytest.raises(ValueError):
            double.presign(key)

    def test_instances_are_isolated(self) -> None:
        first, second = InMemoryStorage(), InMemoryStorage()
        first.put("a.txt", b"data")
        assert "a.txt" not in second


# ── Suite-wide wiring from conftest ───────────────────────────────────────────


class TestSuiteWiring:
    def test_application_factory_returns_the_double(self, storage: InMemoryStorage) -> None:
        """Application code that calls the factory gets the in-memory double."""
        from app.core.config import get_settings

        assert storage_module.get_storage(get_settings()) is storage

    def test_real_boto3_client_is_blocked_by_default(self, settings: Settings) -> None:
        """Without an explicit mock, building the S3 backend fails loudly."""
        with pytest.raises(AssertionError):
            get_storage(settings)
