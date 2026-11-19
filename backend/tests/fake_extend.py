"""Fake Extend client for use in unit and integration tests.

``FakeExtendClient`` has the same public interface as ``ExtendClient`` but
never makes network calls.  It is constructed from recorded responses and
can be configured to raise any error class the real client raises.
"""

from __future__ import annotations

from typing import Any

from app.core.extend.errors import ExtendError


class FakeExtendClient:
    """Drop-in replacement for :class:`~app.core.extend.client.ExtendClient`.

    Parameters
    ----------
    extract_response:
        A dict shaped like a completed Extend extract-run response (the full
        ``GET /extract_runs/{id}`` JSON body when ``status == "PROCESSED"``).
        ``upload``, ``extract``, and the internal poll are all satisfied from
        this single recorded response.
    parse_response:
        A dict shaped like a completed Extend parse-run response (the full
        ``GET /parse_runs/{id}`` JSON body when ``status == "PROCESSED"``).
        ``parse_output`` and ``parse`` both return blocks from this.
    raise_on_upload:
        If not ``None``, an instance of an :class:`~app.core.extend.errors.ExtendError`
        subclass that is raised when ``upload`` is called.
    raise_on_extract:
        If not ``None``, raised when ``extract`` is called.
    raise_on_parse:
        If not ``None``, raised when ``parse`` or ``parse_output`` is called.
    file_id:
        The fake file id returned by ``upload`` (default ``"fake-file-id"``).
    parse_run_id:
        The fake parse-run id embedded in the extract response
        (default ``"fake-parse-run-id"``).
    """

    def __init__(
        self,
        extract_response: dict[str, Any],
        parse_response: dict[str, Any],
        *,
        raise_on_upload: ExtendError | None = None,
        raise_on_extract: ExtendError | None = None,
        raise_on_parse: ExtendError | None = None,
        file_id: str = "fake-file-id",
        parse_run_id: str = "fake-parse-run-id",
    ) -> None:
        self._extract_response = extract_response
        self._parse_response = parse_response
        self._raise_on_upload = raise_on_upload
        self._raise_on_extract = raise_on_extract
        self._raise_on_parse = raise_on_parse
        self._file_id = file_id
        self._parse_run_id = parse_run_id

        # Track calls for assertions.
        self.upload_calls: list[dict[str, Any]] = []
        self.extract_calls: list[dict[str, Any]] = []
        self.parse_calls: list[str] = []
        self.parse_output_calls: list[str] = []

    async def upload(self, filename: str, data: bytes) -> str:
        """Return the configured fake file id or raise the configured error."""
        self.upload_calls.append({"filename": filename, "size": len(data)})
        if self._raise_on_upload is not None:
            raise self._raise_on_upload
        return self._file_id

    async def extract(self, file_id: str, schema: dict[str, Any]) -> Any:
        """Return a fake :class:`~app.core.extend.client.ExtractRun` or raise."""
        from app.core.extend.client import ExtractRun

        self.extract_calls.append({"file_id": file_id, "schema": schema})
        if self._raise_on_extract is not None:
            raise self._raise_on_extract

        resp = self._extract_response
        output = resp.get("output", {})
        return ExtractRun(
            value=output.get("value", {}),
            metadata=output.get("metadata", {}),
            parse_run_id=resp.get("parseRunId", self._parse_run_id),
            usage=resp.get("usage", {}),
            processor_version=resp.get("baseVersion", "3.8.0"),
        )

    async def parse_output(self, parse_run_id: str) -> list[dict[str, Any]]:
        """Return blocks from the recorded parse response or raise."""
        self.parse_output_calls.append(parse_run_id)
        if self._raise_on_parse is not None:
            raise self._raise_on_parse
        return self._flatten_blocks(self._parse_response)

    async def parse(self, file_id: str) -> list[dict[str, Any]]:
        """Return blocks from the recorded parse response or raise."""
        self.parse_calls.append(file_id)
        if self._raise_on_parse is not None:
            raise self._raise_on_parse
        return self._flatten_blocks(self._parse_response)

    @staticmethod
    def _flatten_blocks(parse_resp: dict[str, Any]) -> list[dict[str, Any]]:
        output = parse_resp.get("output", {})
        chunks = output.get("chunks", [])
        blocks: list[dict[str, Any]] = []
        for chunk in chunks:
            blocks.extend(chunk.get("blocks", []))
        return blocks

    async def __aenter__(self) -> "FakeExtendClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass
