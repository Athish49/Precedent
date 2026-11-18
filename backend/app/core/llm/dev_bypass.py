"""TEMPORARY DEV-ONLY MODULE — see ``backend/.llm_bypass_queue/README.md``.

This module implements a local file-based request/response queue that
stands in for the real Anthropic API when ``settings.llm_file_queue_bypass``
is ``True``. It exists purely so a human-run Claude Code agent (not this
backend process) can answer LLM calls for free during cost-sensitive
testing, instead of billing the real paid model.

It is wired into ``app/core/llm/gateway.py`` at each real Anthropic SDK call
site, gated behind the ``llm_file_queue_bypass`` setting (default ``False``).

DELETE THIS ENTIRE FILE — along with the bypass blocks in ``gateway.py``,
the ``llm_file_queue_bypass`` setting in ``app/core/config.py``, the
``LLM_FILE_QUEUE_BYPASS`` line in ``.env.example``, the ``.llm_bypass_queue/``
entry in ``.gitignore``, and the ``.llm_bypass_queue/`` directory itself —
once testing is done. None of this must ever run in production.

Queue layout (see the README for the human-facing explanation):
    backend/.llm_bypass_queue/requests/<id>.json   — written by this module
    backend/.llm_bypass_queue/responses/<id>.json  — written by the responder
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.llm.errors import LLMError

# backend/app/core/llm/dev_bypass.py -> parents[3] == backend/
_QUEUE_ROOT = Path(__file__).resolve().parents[3] / ".llm_bypass_queue"
_REQUESTS_DIR = _QUEUE_ROOT / "requests"
_RESPONSES_DIR = _QUEUE_ROOT / "responses"

_POLL_INTERVAL_SECONDS = 2.0
_TIMEOUT_SECONDS = 20 * 60  # 20 minutes


class LLMBypassTimeoutError(LLMError):
    """No response file appeared in the bypass queue before the timeout.

    Deliberately a distinct type from any real Anthropic API timeout, so
    callers/logs can tell "the human responder didn't answer in time" apart
    from "the real API timed out".
    """


def _ensure_dirs() -> None:
    _REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    _RESPONSES_DIR.mkdir(parents=True, exist_ok=True)


def _write_request(payload: dict[str, Any]) -> str:
    _ensure_dirs()
    request_id = payload["id"]
    path = _REQUESTS_DIR / f"{request_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return request_id


def _wait_for_response(request_id: str) -> dict[str, Any]:
    path = _RESPONSES_DIR / f"{request_id}.json"
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    while True:
        if path.exists():
            return json.loads(path.read_text())
        if time.monotonic() >= deadline:
            raise LLMBypassTimeoutError(
                f"LLM file-queue bypass: no response for request_id={request_id!r} "
                f"after {_TIMEOUT_SECONDS}s. Drop a response file at {path} "
                "(see backend/.llm_bypass_queue/README.md)."
            )
        time.sleep(_POLL_INTERVAL_SECONDS)


def bypass_structured(
    *,
    task: str,
    intended_model: str,
    system: Any,
    messages: list[dict],
    response_model: type,
) -> Any:
    """Stand in for ``client.beta.messages.parse()`` inside ``call_structured``.

    Request file: {"id", "call_type": "structured", "task", "intended_model",
    "system", "messages", "output_schema"}.
    Expected response file: {"content": <JSON object matching output_schema>}.
    """
    request_id = str(uuid.uuid4())
    _write_request(
        {
            "id": request_id,
            "call_type": "structured",
            "task": task,
            "intended_model": intended_model,
            "system": system,
            "messages": messages,
            "output_schema": response_model.model_json_schema(),
        }
    )
    response = _wait_for_response(request_id)
    return response_model.model_validate(response["content"])


def bypass_text(
    *,
    task: str,
    intended_model: str,
    system: Any,
    messages: list[dict],
) -> str:
    """Stand in for ``client.beta.messages.parse()`` inside ``call_text``.

    Request file: {"id", "call_type": "text", "task", "intended_model",
    "system", "messages"}.
    Expected response file: {"content": "<plain text response>"}.
    """
    request_id = str(uuid.uuid4())
    _write_request(
        {
            "id": request_id,
            "call_type": "text",
            "task": task,
            "intended_model": intended_model,
            "system": system,
            "messages": messages,
        }
    )
    response = _wait_for_response(request_id)
    return response["content"]


def bypass_batch(
    *,
    task: str,
    intended_model: str,
    items: list[dict],
    response_model: type,
) -> dict[str, Any]:
    """Stand in for the batches.create/retrieve/results trio in ``call_batch``.

    One request file covers the whole batch: {"id" (the batch's own
    custom_id), "call_type": "batch", "task", "intended_model",
    "output_schema", "items": [{"custom_id", "system", "messages"}, ...]}.
    Expected response file: {"results": {"<custom_id>": <JSON object matching
    output_schema>, ...}} — one entry per item, keyed by custom_id (order
    does not matter, matching the real batches.results() iterator).
    """
    request_id = str(uuid.uuid4())
    _write_request(
        {
            "id": request_id,
            "call_type": "batch",
            "task": task,
            "intended_model": intended_model,
            "output_schema": response_model.model_json_schema(),
            "items": items,
        }
    )
    response = _wait_for_response(request_id)
    return {
        custom_id: response_model.model_validate(content)
        for custom_id, content in response["results"].items()
    }
