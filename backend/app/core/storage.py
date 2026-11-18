"""Object storage abstraction layer.

Provides a common interface for storing and retrieving binary objects in an
S3-compatible cloud bucket (e.g. Cloudflare R2).

Cloud storage is required. There is one backend, :class:`S3StorageBackend`,
and no local alternative: nothing in this module reads or writes the local
filesystem, and :func:`get_storage` raises a configuration error instead of
falling back when a storage setting is missing.

The storage account is shared with other projects. Callers pass *logical*
keys such as ``contracts/{id}/{filename}``; the backend prepends the project
prefix (``settings.object_storage_prefix``) on every operation, so stored
``object_key`` values stay unprefixed.

Only this module may import boto3.
"""

from __future__ import annotations

import abc

_NOT_FOUND_CODES = frozenset({"NoSuchKey", "404", "NotFound"})

# Setting attribute → environment variable named in configuration errors.
_REQUIRED_SETTINGS: tuple[tuple[str, str], ...] = (
    ("object_storage_endpoint", "OBJECT_STORAGE_ENDPOINT"),
    ("object_storage_bucket", "OBJECT_STORAGE_BUCKET"),
    ("object_storage_access_key", "OBJECT_STORAGE_ACCESS_KEY"),
    ("object_storage_secret_key", "OBJECT_STORAGE_SECRET_KEY"),
    ("object_storage_prefix", "OBJECT_STORAGE_PREFIX (or PROJECT_NAMESPACE)"),
)


class StorageConfigurationError(RuntimeError):
    """Raised when object storage is not fully configured."""


def validate_key(key: str) -> str:
    """Return *key* unchanged if it is a safe logical object key.

    Raises:
        ValueError: if *key* is empty, absolute (starts with ``/`` or ``\\``),
            or has a ``..`` path segment. Such a key could address an object
            outside the project prefix.
    """
    if not isinstance(key, str) or not key:
        raise ValueError("Object key must be a non-empty string.")
    if key.startswith(("/", "\\")):
        raise ValueError(f"Object key must be relative, got absolute key {key!r}.")
    if ".." in key.replace("\\", "/").split("/"):
        raise ValueError(f"Object key must not contain '..' segments: {key!r}.")
    return key


class StorageBackend(abc.ABC):
    """Abstract base class for object storage backends."""

    @abc.abstractmethod
    def put(self, key: str, data: bytes) -> None:
        """Store *data* under *key*. Overwrites if key already exists.

        Raises:
            ValueError: if *key* is absolute or contains a ``..`` segment.
        """

    @abc.abstractmethod
    def get(self, key: str) -> bytes:
        """Return the bytes stored under *key*.

        Raises:
            KeyError: if *key* does not exist.
            ValueError: if *key* is absolute or contains a ``..`` segment.
        """

    @abc.abstractmethod
    def presign(self, key: str, expires_in: int = 3600) -> str:
        """Return a pre-signed URL granting temporary read access to *key*.

        Args:
            key: logical object key.
            expires_in: URL validity in seconds (default 3600).

        Raises:
            ValueError: if *key* is absolute or contains a ``..`` segment.
        """


class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend backed by boto3.

    Configured from five settings fields:
        object_storage_endpoint   – base URL of the S3-compatible service
        object_storage_bucket     – bucket name
        object_storage_access_key – access key ID
        object_storage_secret_key – secret access key
        object_storage_prefix     – project prefix prepended to every key

    Every key sent to the bucket is ``{prefix}/{logical key}``.
    """

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        prefix: str,
    ) -> None:
        import boto3  # noqa: PLC0415 — intentionally restricted to this module

        prefix = prefix.strip("/")
        if not prefix:
            raise StorageConfigurationError(
                "Object storage prefix is empty; set OBJECT_STORAGE_PREFIX or PROJECT_NAMESPACE."
            )
        validate_key(prefix)

        self._bucket = bucket
        self._prefix = prefix
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    @property
    def prefix(self) -> str:
        """The project prefix prepended to every key."""
        return self._prefix

    def _full_key(self, key: str) -> str:
        """Validate the logical *key* and return the prefixed bucket key."""
        return f"{self._prefix}/{validate_key(key)}"

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=self._full_key(key), Body=data)

    def get(self, key: str) -> bytes:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        full_key = self._full_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=full_key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in _NOT_FOUND_CODES:
                raise KeyError(key) from exc
            raise
        return response["Body"].read()  # type: ignore[no-any-return]

    def presign(self, key: str, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(  # type: ignore[no-any-return]
            "get_object",
            Params={"Bucket": self._bucket, "Key": self._full_key(key)},
            ExpiresIn=expires_in,
        )

    def list_top_level(self) -> list[str]:
        """Return the names at the root of the bucket, without the prefix applied.

        Root-level keys are returned as they are; each top-level "folder" is
        returned once with a trailing ``/``. Only names at the root are
        listed: no object is read, and other projects' folders are not
        descended into. Used by the partition check to confirm that this
        project has written nothing outside its prefix.
        """
        names: set[str] = set()
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Delimiter="/"):
            for item in page.get("Contents") or []:
                names.add(item["Key"])
            for item in page.get("CommonPrefixes") or []:
                names.add(item["Prefix"])
        return sorted(names)


def get_storage(settings: object) -> StorageBackend:
    """Factory: return the S3 storage backend configured from *settings*.

    There is no fallback backend.

    Args:
        settings: a Settings instance (or any object with the four
            ``object_storage_*`` connection attributes and
            ``object_storage_prefix``).

    Raises:
        StorageConfigurationError: if any required storage setting is missing
            or empty. The message names the environment variable(s) to set.
    """
    values: dict[str, str] = {}
    missing: list[str] = []
    for attr, env_name in _REQUIRED_SETTINGS:
        value = getattr(settings, attr, None)
        if isinstance(value, str) and value.strip():
            values[attr] = value.strip()
        else:
            missing.append(env_name)
    if missing:
        raise StorageConfigurationError(
            "Object storage is not configured: missing "
            + ", ".join(missing)
            + ". Cloud object storage is required; there is no local storage fallback."
        )
    return S3StorageBackend(
        endpoint=values["object_storage_endpoint"],
        bucket=values["object_storage_bucket"],
        access_key=values["object_storage_access_key"],
        secret_key=values["object_storage_secret_key"],
        prefix=values["object_storage_prefix"],
    )


__all__ = [
    "S3StorageBackend",
    "StorageBackend",
    "StorageConfigurationError",
    "get_storage",
    "validate_key",
]
