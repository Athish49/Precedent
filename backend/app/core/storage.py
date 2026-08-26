"""Object storage abstraction layer.

Provides a common interface for storing and retrieving binary objects.
In production, delegates to an S3-compatible backend (e.g. Cloudflare R2).
In local development, stores files on the local filesystem.

Only this module may import boto3.
"""

from __future__ import annotations

import abc
from pathlib import Path


class StorageBackend(abc.ABC):
    """Abstract base class for object storage backends."""

    @abc.abstractmethod
    def put(self, key: str, data: bytes) -> None:
        """Store *data* under *key*. Overwrites if key already exists."""

    @abc.abstractmethod
    def get(self, key: str) -> bytes:
        """Return the bytes stored under *key*.

        Raises:
            KeyError: if *key* does not exist (S3 backend).
            FileNotFoundError: if *key* does not exist (filesystem backend).
        """

    @abc.abstractmethod
    def presign(self, key: str, expires_in: int = 3600) -> str:
        """Return a pre-signed URL granting temporary read access to *key*.

        Args:
            key: object key.
            expires_in: URL validity in seconds (default 3600).

        Raises:
            NotImplementedError: on backends that do not support pre-signing.
        """


class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend backed by boto3.

    Configured from four settings fields:
        object_storage_endpoint  – base URL of the S3-compatible service
        object_storage_bucket    – bucket name
        object_storage_access_key – access key ID
        object_storage_secret_key – secret access key
    """

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        import boto3  # noqa: PLC0415 — intentionally restricted to this module

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()  # type: ignore[no-any-return]

    def presign(self, key: str, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(  # type: ignore[no-any-return]
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )


class FilesystemStorageBackend(StorageBackend):
    """Local filesystem storage backend for development and testing.

    Files are written to *base_dir* using the object key as a relative path.
    Nested keys (containing ``/``) create sub-directories automatically.
    """

    DEFAULT_BASE_DIR = Path("/tmp/precedent-storage")  # noqa: S108

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else self.DEFAULT_BASE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """Return absolute path for *key*, creating parent directories."""
        path = self._base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, key: str, data: bytes) -> None:
        self._resolve(key).write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key!r} (looked in {path})")
        return path.read_bytes()

    def presign(self, key: str, expires_in: int = 3600) -> str:  # noqa: ARG002
        raise NotImplementedError("FilesystemStorageBackend does not support pre-signed URLs.")


def get_storage(settings: object) -> StorageBackend:
    """Factory: return the appropriate StorageBackend for *settings*.

    Returns an :class:`S3StorageBackend` when ``settings.object_storage_endpoint``
    is set, otherwise returns a :class:`FilesystemStorageBackend`.

    Args:
        settings: a Settings instance (or any object with the four
            ``object_storage_*`` attributes).
    """
    endpoint: str | None = getattr(settings, "object_storage_endpoint", None)
    if endpoint:
        bucket: str = settings.object_storage_bucket or ""
        access_key: str = settings.object_storage_access_key or ""
        secret_key: str = settings.object_storage_secret_key or ""
        return S3StorageBackend(
            endpoint=endpoint,
            bucket=bucket,
            access_key=access_key,
            secret_key=secret_key,
        )
    return FilesystemStorageBackend()


__all__ = [
    "FilesystemStorageBackend",
    "S3StorageBackend",
    "StorageBackend",
    "get_storage",
]
