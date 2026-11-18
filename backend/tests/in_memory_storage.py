"""In-memory storage double for tests.

The application has one storage backend, the S3-compatible cloud one, and no
local alternative. Tests must not reach the cloud and must not write to disk,
so they use this double instead. It keeps objects in a dict for the lifetime
of the instance and leaves nothing behind.

How tests get it: ``tests/conftest.py`` installs a fresh instance for every
test (the ``get_storage`` factory is replaced everywhere the application
looks it up), and the ``storage`` fixture returns that same instance so a
test can inspect what was written::

    def test_upload(storage: InMemoryStorage) -> None:
        ...
        assert storage.get("contracts/abc/file.pdf") == b"..."

It can also be constructed directly: ``InMemoryStorage()``.
"""

from __future__ import annotations

from app.core.storage import StorageBackend, validate_key


class InMemoryStorage(StorageBackend):
    """Dict-backed :class:`StorageBackend` holding logical (unprefixed) keys.

    Mirrors the contract of the real backend: the same key validation,
    ``KeyError`` for a missing key, and overwrite on a repeated put.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[validate_key(key)] = bytes(data)

    def get(self, key: str) -> bytes:
        validate_key(key)
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    def presign(self, key: str, expires_in: int = 3600) -> str:
        # Like S3, signing does not check that the object exists.
        validate_key(key)
        return f"memory://{key}?expires_in={expires_in}"

    # ── helpers for assertions ────────────────────────────────────────────────

    def keys(self) -> list[str]:
        """Return all stored keys, sorted."""
        return sorted(self.objects)

    def __contains__(self, key: object) -> bool:
        return key in self.objects
