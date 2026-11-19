"""Unit tests for the Extend AI client.

All tests use ``httpx.MockTransport`` — no sockets are opened.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.extend.client import ExtendClient, ExtractRun, get_extend_client
from app.core.extend.errors import (
    ExtendAuthError,
    ExtendRunFailed,
    ExtendTimeout,
    ExtendUnavailable,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXTRACT_PROCESSED = {
    "id": "run-1",
    "status": "PROCESSED",
    "parseRunId": "parse-1",
    "baseVersion": "3.8.0",
    "usage": {"credits": 1.2},
    "output": {
        "value": {"title": "Test Contract"},
        "metadata": {"title": {"citations": []}},
    },
}

_PARSE_PROCESSED = {
    "id": "parse-1",
    "status": "PROCESSED",
    "output": {
        "chunks": [
            {
                "blocks": [
                    {"type": "text", "content": "Hello world", "metadata": {"page": {"number": 1}}},
                    {"type": "heading", "content": "Section 1", "metadata": {"page": {"number": 1}}},
                ]
            },
            {
                "blocks": [
                    {"type": "text", "content": "Page two text", "metadata": {"page": {"number": 2}}},
                ]
            },
        ]
    },
}


def _make_response(
    status_code: int,
    body: Any,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        json=body,
    )


class _SequentialTransport(httpx.AsyncBaseTransport):
    """Return responses from a fixed list in order."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self._index = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._index >= len(self._responses):
            raise AssertionError(f"Unexpected request #{self._index}: {request.url}")
        response = self._responses[self._index]
        self._index += 1
        return response


_TEST_BASE_URL = "https://extend.test"


def _make_client(responses: list[httpx.Response], **kwargs: Any) -> ExtendClient:
    transport = _SequentialTransport(responses)
    return ExtendClient(
        api_key="test-key",
        base_url=_TEST_BASE_URL,
        extract_processor="extraction_light",
        extract_version="3.8.0",
        parse_engine="parse_light",
        parse_version="1.0.0",
        poll_interval=0,  # no sleep in tests
        timeout=60,
        _transport=transport,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_success():
    """upload() returns the file id from the API."""
    transport = _SequentialTransport([
        _make_response(200, {"id": "file-abc"}),
    ])
    client = ExtendClient(
        api_key="test-key",
        base_url=_TEST_BASE_URL,
        extract_processor="extraction_light",
        extract_version="3.8.0",
        parse_engine="parse_light",
        parse_version="1.0.0",
        poll_interval=0,
        timeout=60,
        _transport=transport,
    )
    file_id = await client.upload("contract.pdf", b"fake-bytes")
    assert file_id == "file-abc"


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_success():
    """extract() creates a run, polls until PROCESSED, returns ExtractRun."""
    # POST /extract_runs → 200 with run id
    # GET  /extract_runs/run-1 → PROCESSED
    responses = [
        _make_response(200, {"id": "run-1", "status": "RUNNING"}),
        _make_response(200, _EXTRACT_PROCESSED),
    ]
    client = _make_client(responses)
    result = await client.extract("file-1", {"type": "object"})
    assert isinstance(result, ExtractRun)
    assert result.value == {"title": "Test Contract"}
    assert result.parse_run_id == "parse-1"
    assert result.processor_version == "3.8.0"


@pytest.mark.asyncio
async def test_extract_failed_run():
    """extract() raises ExtendRunFailed when the run ends with status FAILED."""
    responses = [
        _make_response(200, {"id": "run-2", "status": "RUNNING"}),
        _make_response(200, {"id": "run-2", "status": "FAILED", "failureReason": "CORRUPT_FILE"}),
    ]
    client = _make_client(responses)
    with pytest.raises(ExtendRunFailed) as exc_info:
        await client.extract("file-2", {})
    assert exc_info.value.failure_reason == "CORRUPT_FILE"


@pytest.mark.asyncio
async def test_extract_timeout():
    """extract() raises ExtendTimeout when the run does not finish in time."""
    # Always return RUNNING so the client polls until timeout.
    running = {"id": "run-3", "status": "RUNNING"}

    class _AlwaysRunningTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return _make_response(200, running)

    client = ExtendClient(
        api_key="test-key",
        base_url=_TEST_BASE_URL,
        extract_processor="extraction_light",
        extract_version="3.8.0",
        parse_engine="parse_light",
        parse_version="1.0.0",
        poll_interval=0,
        timeout=0,  # immediate timeout
        _transport=_AlwaysRunningTransport(),
    )
    with pytest.raises(ExtendTimeout):
        await client.extract("file-3", {})


# ---------------------------------------------------------------------------
# parse_output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_output_success():
    """parse_output() fetches and flattens blocks across chunks."""
    responses = [
        _make_response(200, _PARSE_PROCESSED),
    ]
    client = _make_client(responses)
    blocks = await client.parse_output("parse-1")
    assert len(blocks) == 3
    assert blocks[0]["content"] == "Hello world"
    assert blocks[2]["content"] == "Page two text"


# ---------------------------------------------------------------------------
# parse (standalone)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_success():
    """parse() creates a parse run, polls until PROCESSED, returns blocks."""
    running = {"id": "parse-run-1", "status": "RUNNING"}
    done = dict(_PARSE_PROCESSED)
    done["id"] = "parse-run-1"
    responses = [
        _make_response(200, {"id": "parse-run-1", "status": "RUNNING"}),
        _make_response(200, done),
    ]
    client = _make_client(responses)
    blocks = await client.parse("file-1")
    assert len(blocks) == 3


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_429_then_success():
    """A 429 response is retried; on success the result is returned."""
    responses = [
        # 429 on the upload call
        _make_response(429, {"code": "RATE_LIMIT_EXCEEDED"}, headers={"Retry-After": "0"}),
        # Success on retry
        _make_response(200, {"id": "file-retry"}),
    ]
    client = _make_client(responses)
    file_id = await client.upload("doc.pdf", b"bytes")
    assert file_id == "file-retry"


@pytest.mark.asyncio
async def test_5xx_exhaustion_raises_unavailable():
    """Five-hundred errors exhaust retries and raise ExtendUnavailable."""
    responses = [
        _make_response(503, {"error": "Service Unavailable"}),
        _make_response(503, {"error": "Service Unavailable"}),
        _make_response(503, {"error": "Service Unavailable"}),
        _make_response(503, {"error": "Service Unavailable"}),
    ]
    client = _make_client(responses)
    with pytest.raises(ExtendUnavailable):
        await client.upload("doc.pdf", b"bytes")


@pytest.mark.asyncio
async def test_network_error_raises_unavailable():
    """A network-level error raises ExtendUnavailable."""

    class _ErrorTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

    client = ExtendClient(
        api_key="test-key",
        base_url=_TEST_BASE_URL,
        extract_processor="extraction_light",
        extract_version="3.8.0",
        parse_engine="parse_light",
        parse_version="1.0.0",
        poll_interval=0,
        timeout=60,
        _transport=_ErrorTransport(),
    )
    with pytest.raises(ExtendUnavailable):
        await client.upload("doc.pdf", b"bytes")


# ---------------------------------------------------------------------------
# Auth errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_raises_auth_error():
    """A 401 response raises ExtendAuthError and is not retried."""
    responses = [
        _make_response(401, {"error": "Unauthorized"}),
    ]
    client = _make_client(responses)
    with pytest.raises(ExtendAuthError):
        await client.upload("doc.pdf", b"bytes")


@pytest.mark.asyncio
async def test_403_raises_auth_error():
    """A 403 response raises ExtendAuthError and is not retried."""
    responses = [
        _make_response(403, {"error": "Forbidden"}),
    ]
    client = _make_client(responses)
    with pytest.raises(ExtendAuthError):
        await client.upload("doc.pdf", b"bytes")


# ---------------------------------------------------------------------------
# get_extend_client factory
# ---------------------------------------------------------------------------


def test_get_extend_client_missing_key_raises():
    """get_extend_client raises ValueError when extend_api_key is None."""

    class _FakeSettings:
        extend_api_key = None
        extend_base_url = _TEST_BASE_URL
        extend_extract_processor = "extraction_light"
        extend_extract_version = "3.8.0"
        extend_parse_engine = "parse_light"
        extend_parse_version = "1.0.0"
        extend_poll_interval_seconds = 3
        extend_timeout_seconds = 300

    with pytest.raises(ValueError, match="EXTEND_API_KEY"):
        get_extend_client(_FakeSettings())


def test_get_extend_client_blank_key_raises():
    """get_extend_client raises ValueError when extend_api_key is empty string."""

    class _FakeSettings:
        extend_api_key = ""
        extend_base_url = _TEST_BASE_URL
        extend_extract_processor = "extraction_light"
        extend_extract_version = "3.8.0"
        extend_parse_engine = "parse_light"
        extend_parse_version = "1.0.0"
        extend_poll_interval_seconds = 3
        extend_timeout_seconds = 300

    with pytest.raises(ValueError, match="EXTEND_API_KEY"):
        get_extend_client(_FakeSettings())


def test_get_extend_client_success():
    """get_extend_client returns an ExtendClient when the key is set."""

    class _FakeSettings:
        extend_api_key = "sk-test-key"
        extend_base_url = _TEST_BASE_URL
        extend_extract_processor = "extraction_light"
        extend_extract_version = "3.8.0"
        extend_parse_engine = "parse_light"
        extend_parse_version = "1.0.0"
        extend_poll_interval_seconds = 3
        extend_timeout_seconds = 300

    client = get_extend_client(_FakeSettings())
    assert isinstance(client, ExtendClient)


# ---------------------------------------------------------------------------
# No string "api.extend.ai" outside app/core/extend/
# ---------------------------------------------------------------------------


def test_no_extend_url_outside_extend_package():
    """Verify that nothing outside app/core/extend/ contains 'api.extend.ai'.

    Exclusions:
    - ``extend_eval/`` scripts contain the URL by design; they are
      being removed in task 0.3.  Exclude them here so this guard does not
      fail before that task runs.
    - This test file itself is excluded from the scan to avoid a
      self-referential false positive.
    """
    import subprocess
    import os

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    # Directories to skip: the extend package itself and the legacy eval scripts.
    result = subprocess.run(
        [
            "grep",
            "-rn",
            "--include=*.py",
            "--exclude-dir=extend",
            "--exclude-dir=extend_eval",
            "api.extend.ai",
            os.path.join(backend_dir, "app"),
            os.path.join(backend_dir, "tests"),
        ],
        capture_output=True,
        text=True,
    )
    # Filter out this test file from results (it has the string in comments/strings
    # for documentary purposes).
    this_file = os.path.abspath(__file__)
    lines = [
        line for line in result.stdout.splitlines()
        if not line.startswith(this_file)
    ]
    assert lines == [], (
        f"Found 'api.extend.ai' outside app/core/extend/:\n" + "\n".join(lines)
    )
