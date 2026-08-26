"""LLM gateway — single entry point for all Anthropic API calls.

``import anthropic`` lives only in this module.
"""

from __future__ import annotations

import logging
import time

import anthropic

from app.core.config import get_settings
from app.core.llm.errors import LLMError
from app.core.llm.registry import get_model_for_task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_client() -> anthropic.Anthropic:
    settings = get_settings()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _split_messages(
    messages: list[dict],
    cache_prefix: str | None,
) -> tuple[list[dict] | str | None, list[dict]]:
    """Separate system-role dicts from user/assistant messages.

    The Anthropic beta ``parse()`` method accepts ``system`` as a separate
    argument (string or list of text blocks); the ``messages`` iterable must
    contain only user/assistant turns.

    If ``cache_prefix`` is set, the first system block receives
    ``cache_control={"type": "ephemeral"}`` for prompt caching.

    Returns (system, non_system_messages).
    """
    system_texts: list[str] = []
    other: list[dict] = []

    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            system_texts.append(content if isinstance(content, str) else str(content))
        else:
            other.append(msg)

    if not system_texts:
        return None, other

    if cache_prefix:
        # Wrap into block format so we can attach cache_control.
        system_blocks: list[dict] = []
        for i, text in enumerate(system_texts):
            block: dict = {"type": "text", "text": text}
            if i == 0:
                block["cache_control"] = {"type": "ephemeral"}
            system_blocks.append(block)
        return system_blocks, other  # type: ignore[return-value]

    # Plain string is fine when caching is not needed.
    return "\n\n".join(system_texts), other


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def call_structured[T](
    task: str,
    messages: list[dict],
    response_model: type[T],
    cache_prefix: str | None = None,
) -> T:
    """Call the LLM and return a validated *response_model* instance.

    Args:
        task: Logical task name used for model routing (see ``registry.py``).
        messages: Conversation history including optional system-role dicts.
        response_model: A Pydantic model class; the API parses JSON into it.
        cache_prefix: If set, the first system message is wrapped with
            ``cache_control={"type": "ephemeral"}`` for prompt caching.

    Returns:
        A validated instance of *response_model*.

    Raises:
        LLMError: If the model returns a refusal or the parsed output is None.
    """
    settings = get_settings()
    model = get_model_for_task(task, settings)
    client = _build_client()

    system, user_messages = _split_messages(messages, cache_prefix)

    kwargs: dict = {
        "model": model,
        "max_tokens": 4096,
        "messages": user_messages,  # type: ignore[arg-type]
        "output_format": response_model,
    }
    if system is not None:
        kwargs["system"] = system  # type: ignore[assignment]

    response = client.beta.messages.parse(**kwargs)

    logger.debug(
        "LLM usage task=%s model=%s input_tokens=%d output_tokens=%d",
        task,
        model,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise LLMError(
            f"LLM returned no structured output for task={task!r} "
            f"(stop_reason={response.stop_reason!r})"
        )

    return response.parsed_output  # type: ignore[return-value]


def call_text(
    task: str,
    messages: list[dict],
    cache_prefix: str | None = None,
) -> str:
    """Call the LLM and return the plain-text response.

    Args:
        task: Logical task name used for model routing.
        messages: Conversation history including optional system-role dicts.
        cache_prefix: If set, the first system message gets prompt-caching.

    Returns:
        The text content of the first content block.

    Raises:
        LLMError: If the response contains no text content.
    """
    settings = get_settings()
    model = get_model_for_task(task, settings)
    client = _build_client()

    system, user_messages = _split_messages(messages, cache_prefix)

    kwargs: dict = {
        "model": model,
        "max_tokens": 4096,
        "messages": user_messages,  # type: ignore[arg-type]
    }
    if system is not None:
        kwargs["system"] = system  # type: ignore[assignment]

    response = client.beta.messages.parse(**kwargs)

    logger.debug(
        "LLM usage task=%s model=%s input_tokens=%d output_tokens=%d",
        task,
        model,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    for block in response.content:
        if block.type == "text":
            return block.text  # type: ignore[attr-defined]

    raise LLMError(f"LLM returned no text content for task={task!r}")


def call_batch[T](
    task: str,
    items: list[dict],
    response_model: type[T],
    cache_prefix: str | None = None,
    *,
    poll_interval: float = 2.0,
) -> dict[str, T]:
    """Send multiple structured LLM calls as a single batch.

    Uses the Anthropic Message Batches API to submit all items in one request,
    polls until the batch completes, then returns validated model instances keyed
    by each item's ``custom_id``.

    Args:
        task: Logical task name used for model routing (see ``registry.py``).
        items: List of dicts, each with:
            - ``"id"`` (str): Unique custom_id for this item.
            - ``"messages"`` (list[dict]): Conversation messages (same format as
              ``call_structured``).
        response_model: A Pydantic model class; each result is parsed into it.
        cache_prefix: If set, the first system message in each item is wrapped
            with ``cache_control={"type": "ephemeral"}`` for prompt caching.
        poll_interval: Seconds to wait between status polls (default: 2).

    Returns:
        ``dict[custom_id, validated_response_model_instance]`` for every item.

    Raises:
        LLMError: If any item returns a refusal, error, cancellation, expiry,
            or a ``None`` parsed output.
    """
    settings = get_settings()
    model = get_model_for_task(task, settings)
    client = _build_client()

    # Build per-item request params.
    requests: list[dict] = []
    for item in items:
        system, user_messages = _split_messages(item["messages"], cache_prefix)
        params: dict = {
            "model": model,
            "max_tokens": 4096,
            "messages": user_messages,
            "output_format": response_model,
        }
        if system is not None:
            params["system"] = system
        requests.append({"custom_id": item["id"], "params": params})

    batch = client.beta.messages.batches.create(requests=requests)
    logger.debug("LLM batch created batch_id=%s task=%s items=%d", batch.id, task, len(items))

    # Poll until processing ends.
    while batch.processing_status != "ended":
        time.sleep(poll_interval)
        batch = client.beta.messages.batches.retrieve(batch.id)
        logger.debug(
            "LLM batch status batch_id=%s status=%s", batch.id, batch.processing_status
        )

    # Collect and validate results.
    results: dict[str, T] = {}
    for result in client.beta.messages.batches.results(batch.id):
        custom_id = result.custom_id
        res = result.result

        if res.type != "succeeded":
            raise LLMError(
                f"LLM batch item custom_id={custom_id!r} failed with result type={res.type!r} "
                f"(task={task!r})"
            )

        message = res.message
        # Prefer parsed_output when present (beta parse path); fall back to None.
        parsed = getattr(message, "parsed_output", None)

        if parsed is None:
            raise LLMError(
                f"LLM batch item custom_id={custom_id!r} returned no structured output "
                f"(task={task!r})"
            )

        results[custom_id] = parsed  # type: ignore[assignment]

    return results
