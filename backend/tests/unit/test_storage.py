"""Unit tests for app.core.storage — filesystem backend only.

S3 backend is excluded: it requires boto3 network calls and is covered
by integration tests against a live or mock S3-compatible service.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.storage import FilesystemStorageBackend, StorageBackend, get_storage

# ── helpers ──────────────────────────────────────────────────────────────────

def _base_env() -> dict[str, str]:
    return {
        "DATABASE_URL": (
            "postgresql+psycopg://user:pass@ep-test.us-east-2.aws.neon.tech/testdb?sslmode=require"
        ),
        "ANTHROPIC_API_KEY": "sk-ant-test",
    }


# ── FilesystemStorageBackend ──────────────────────────────────────────────────

class TestFilesystemStorageBackend:
    """Tests that exercise FilesystemStorageBackend in an isolated temp dir."""

    @pytest.fixture()
    def backend(self, tmp_path: pytest.TempPathFactory) -> FilesystemStorageBackend:
        return FilesystemStorageBackend(base_dir=tmp_path)

    def test_put_creates_file(self, backend: FilesystemStorageBackend, tmp_path) -> None:
        backend.put("hello.txt", b"world")
        assert (tmp_path / "hello.txt").read_bytes() == b"world"

    def test_get_returns_bytes(self, backend: FilesystemStorageBackend) -> None:
        backend.put("data.bin", b"\x00\x01\x02")
        result = backend.get("data.bin")
        assert result == b"\x00\x01\x02"

    def test_round_trip(self, backend: FilesystemStorageBackend) -> None:
        payload = b"the quick brown fox jumps over the lazy dog"
        backend.put("roundtrip/key", payload)
        assert backend.get("roundtrip/key") == payload

    def test_put_overwrites_existing_key(self, backend: FilesystemStorageBackend) -> None:
        backend.put("dup.txt", b"first")
        backend.put("dup.txt", b"second")
        assert backend.get("dup.txt") == b"second"

    def test_get_nonexistent_raises_file_not_found(
        self, backend: FilesystemStorageBackend
    ) -> None:
        with pytest.raises(FileNotFoundError):
            backend.get("does/not/exist.bin")

    def test_nested_key_creates_subdirectory(
        self, backend: FilesystemStorageBackend, tmp_path
    ) -> None:
        backend.put("a/b/c/file.txt", b"nested")
        assert (tmp_path / "a" / "b" / "c" / "file.txt").exists()

    def test_presign_raises_not_implemented(self, backend: FilesystemStorageBackend) -> None:
        backend.put("x.bin", b"data")
        with pytest.raises(NotImplementedError):
            backend.presign("x.bin")

    def test_implements_storage_backend_interface(
        self, backend: FilesystemStorageBackend
    ) -> None:
        assert isinstance(backend, StorageBackend)

    def test_empty_bytes_round_trip(self, backend: FilesystemStorageBackend) -> None:
        backend.put("empty.bin", b"")
        assert backend.get("empty.bin") == b""

    def test_large_payload_round_trip(self, backend: FilesystemStorageBackend) -> None:
        large = b"x" * (4 * 1024 * 1024)  # 4 MiB
        backend.put("large.bin", large)
        assert backend.get("large.bin") == large


# ── get_storage factory ───────────────────────────────────────────────────────

class TestGetStorageFactory:
    """Tests for the get_storage() factory function."""

    def test_returns_filesystem_backend_when_no_endpoint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        for k, v in _base_env().items():
            monkeypatch.setenv(k, v)
        settings = Settings(_env_file=None)
        backend = get_storage(settings)
        assert isinstance(backend, FilesystemStorageBackend)

    def test_filesystem_backend_from_factory_is_functional(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        for k, v in _base_env().items():
            monkeypatch.setenv(k, v)
        settings = Settings(_env_file=None)
        backend = get_storage(settings)
        # Override internal base_dir so the test stays inside tmp_path
        backend._base_dir = tmp_path  # type: ignore[union-attr]
        backend.put("factory-test.txt", b"ok")
        assert backend.get("factory-test.txt") == b"ok"
