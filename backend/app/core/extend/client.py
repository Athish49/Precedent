"""Extend AI HTTP client.

This is the only module that knows the Extend base URL or touches the
Authorization header.  ``get_extend_client`` is the single factory;
nothing else constructs this class directly.

The API key is never logged or included in any exception message.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.extend.errors import (
    ExtendAuthError,
    ExtendRunFailed,
    ExtendTimeout,
    ExtendUnavailable,
)

# API version header sent with every request.
_API_VERSION = "2026-02-09"

# How many times to retry on 429 or 5xx before giving up.
_MAX_RETRIES = 3


@dataclass
class ExtractRun:
    """The result of a completed Extend extract run."""

    value: dict[str, Any]
    metadata: dict[str, Any]
    parse_run_id: str
    usage: dict[str, Any]
    processor_version: str


class ExtendClient:
    """Async HTTP client for the Extend AI API.

    Parameters
    ----------
    api_key:
        Extend API key.  Never logged.
    base_url:
        Base URL for the Extend API.
    extract_processor:
        ``baseProcessor`` for extract runs.
    extract_version:
        ``baseVersion`` for extract runs.
    parse_engine:
        ``engine`` for parse runs.
    parse_version:
        ``engineVersion`` for parse runs.
    poll_interval:
        Seconds to wait between polls.
    timeout:
        Maximum seconds to wait for a run to finish.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        extract_processor: str,
        extract_version: str,
        parse_engine: str,
        parse_version: str,
        poll_interval: float,
        timeout: float,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._extract_processor = extract_processor
        self._extract_version = extract_version
        self._parse_engine = parse_engine
        self._parse_version = parse_version
        self._poll_interval = poll_interval
        self._timeout = timeout

        # Build headers without the key in any public attribute.
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-extend-api-version": _API_VERSION,
        }
        kwargs: dict[str, Any] = {
            "base_url": self._base_url,
            "headers": headers,
            "timeout": httpx.Timeout(60.0),
        }
        if _transport is not None:
            kwargs["transport"] = _transport
        self._client = httpx.AsyncClient(**kwargs)

    # ── Public methods ────────────────────────────────────────────────────────

    async def upload(self, filename: str, data: bytes) -> str:
        """Upload a file to Extend and return its file id.

        Parameters
        ----------
        filename:
            Original filename; used as the multipart filename field.
        data:
            Raw bytes of the file.

        Returns
        -------
        str
            The Extend file id (``id`` in the JSON response).
        """
        response = await self._request_with_retry(
            "POST",
            "/files/upload",
            files={"file": (filename, data)},
        )
        return response["id"]

    async def extract(self, file_id: str, schema: dict[str, Any]) -> ExtractRun:
        """Create an extract run and poll until it finishes.

        Parameters
        ----------
        file_id:
            The Extend file id returned by :meth:`upload`.
        schema:
            The JSON schema to pass to Extract.

        Returns
        -------
        ExtractRun
            The completed run result.

        Raises
        ------
        ExtendRunFailed
            When the run ends with ``status: FAILED``.
        ExtendTimeout
            When polling exceeds the configured timeout.
        """
        payload = {
            "file": {"id": file_id},
            "config": {
                "baseProcessor": self._extract_processor,
                "baseVersion": self._extract_version,
                "parseConfig": {
                    "engine": self._parse_engine,
                    "engineVersion": self._parse_version,
                },
                "schema": schema,
                "advancedOptions": {"citationsEnabled": True},
            },
        }
        create_resp = await self._request_with_retry("POST", "/extract_runs", json=payload)
        run_id: str = create_resp["id"]

        # Poll until the run reaches a terminal state.
        deadline = time.monotonic() + self._timeout
        while True:
            if time.monotonic() >= deadline:
                raise ExtendTimeout()

            poll_resp = await self._request_with_retry("GET", f"/extract_runs/{run_id}")
            status: str = poll_resp.get("status", "")

            if status == "PROCESSED":
                output = poll_resp.get("output", {})
                return ExtractRun(
                    value=output.get("value", {}),
                    metadata=output.get("metadata", {}),
                    parse_run_id=poll_resp.get("parseRunId", ""),
                    usage=poll_resp.get("usage", {}),
                    processor_version=poll_resp.get("baseVersion", self._extract_version),
                )
            elif status == "FAILED":
                failure_reason = poll_resp.get("failureReason", "UNKNOWN")
                raise ExtendRunFailed(failure_reason)

            await asyncio.sleep(self._poll_interval)

    async def parse_output(self, parse_run_id: str) -> list[dict[str, Any]]:
        """Fetch parse blocks from a completed parse run.

        Blocks from all chunks are flattened in order.

        Parameters
        ----------
        parse_run_id:
            The parse run id from a completed extract run.

        Returns
        -------
        list[dict]
            Flattened list of block dicts across all chunks.
        """
        resp = await self._request_with_retry("GET", f"/parse_runs/{parse_run_id}")
        output = resp.get("output", {})
        chunks = output.get("chunks", [])
        blocks: list[dict[str, Any]] = []
        for chunk in chunks:
            blocks.extend(chunk.get("blocks", []))
        return blocks

    async def parse(self, file_id: str) -> list[dict[str, Any]]:
        """Run a standalone parse on a file and return its blocks.

        Used for the text-only path (no Extract schema needed).

        Parameters
        ----------
        file_id:
            The Extend file id returned by :meth:`upload`.

        Returns
        -------
        list[dict]
            Flattened list of block dicts.
        """
        payload = {
            "file": {"id": file_id},
            "config": {
                "engine": self._parse_engine,
                "engineVersion": self._parse_version,
                "blockOptions": {
                    "tables": {"targetFormat": "markdown"},
                },
            },
        }
        create_resp = await self._request_with_retry("POST", "/parse_runs", json=payload)
        run_id: str = create_resp["id"]

        # Poll until done.
        deadline = time.monotonic() + self._timeout
        while True:
            if time.monotonic() >= deadline:
                raise ExtendTimeout()

            poll_resp = await self._request_with_retry("GET", f"/parse_runs/{run_id}")
            status: str = poll_resp.get("status", "")

            if status == "PROCESSED":
                return self._flatten_blocks(poll_resp)
            elif status == "FAILED":
                failure_reason = poll_resp.get("failureReason", "UNKNOWN")
                raise ExtendRunFailed(failure_reason)

            await asyncio.sleep(self._poll_interval)

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _flatten_blocks(parse_resp: dict[str, Any]) -> list[dict[str, Any]]:
        output = parse_resp.get("output", {})
        chunks = output.get("chunks", [])
        blocks: list[dict[str, Any]] = []
        for chunk in chunks:
            blocks.extend(chunk.get("blocks", []))
        return blocks

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request, retrying on 429 and 5xx up to _MAX_RETRIES times."""
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                # Exponential backoff: 1s, 2s, 4s, …
                await asyncio.sleep(2 ** (attempt - 1))

            try:
                response = await self._client.request(method, path, **kwargs)
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.TimeoutException) as exc:
                last_error = ExtendUnavailable(str(exc))
                if attempt < _MAX_RETRIES:
                    continue
                raise ExtendUnavailable(str(exc)) from exc

            if response.status_code == 401 or response.status_code == 403:
                # Do not retry auth errors.
                raise ExtendAuthError()

            if response.status_code == 429:
                # Honour Retry-After if present.
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        await asyncio.sleep(float(retry_after))
                    except ValueError:
                        await asyncio.sleep(2 ** attempt)
                last_error = ExtendUnavailable("Rate limited (429)")
                if attempt < _MAX_RETRIES:
                    continue
                raise ExtendUnavailable("Rate limited (429): retries exhausted")

            if response.status_code >= 500:
                last_error = ExtendUnavailable(f"HTTP {response.status_code}")
                if attempt < _MAX_RETRIES:
                    continue
                raise ExtendUnavailable(
                    f"HTTP {response.status_code}: retries exhausted"
                )

            response.raise_for_status()
            return response.json()

        # Should never be reached, but keep type checker happy.
        if last_error is not None:
            raise last_error
        raise ExtendUnavailable("Unknown error")

    async def __aenter__(self) -> "ExtendClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()


def get_extend_client(settings: Any) -> ExtendClient:
    """Factory: build an :class:`ExtendClient` from application settings.

    Parameters
    ----------
    settings:
        An application ``Settings`` instance.  The ``extend_api_key`` field
        must be non-empty; if it is ``None`` or blank this function raises
        ``ValueError`` with a clear message so ingest fails at startup rather
        than at the first API call.

    Returns
    -------
    ExtendClient
        A configured client instance.  Callers are responsible for closing it.
    """
    api_key: str | None = getattr(settings, "extend_api_key", None)
    if not api_key:
        raise ValueError(
            "EXTEND_API_KEY is not set. "
            "An Extend API key is required to ingest documents. "
            "Set the EXTEND_API_KEY environment variable."
        )

    return ExtendClient(
        api_key=api_key,
        base_url=getattr(settings, "extend_base_url", None) or "https://api.extend.ai",
        extract_processor=settings.extend_extract_processor,
        extract_version=settings.extend_extract_version,
        parse_engine=settings.extend_parse_engine,
        parse_version=settings.extend_parse_version,
        poll_interval=float(settings.extend_poll_interval_seconds),
        timeout=float(settings.extend_timeout_seconds),
    )
