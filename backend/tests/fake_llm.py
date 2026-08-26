"""Fake LLM gateway for use in tests.

Provides ``FakeLLMGateway`` — a drop-in replacement for the real gateway
that returns preset values without hitting Anthropic.

Usage::

    fake = FakeLLMGateway(
        structured_responses={"my_task": MyModel(field="value")},
        text_responses={"other_task": "hello"},
    )
    result = fake.call_structured("my_task", [...], MyModel)
    assert isinstance(result, MyModel)
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


class FakeLLMGateway:
    """Configurable fake for ``app.core.llm.gateway``.

    Args:
        structured_responses: Mapping of task name → pre-built Pydantic instance
            returned by ``call_structured``.  A single default value can be
            set with ``default_structured``.
        text_responses: Mapping of task name → string returned by ``call_text``.
            A single default value can be set with ``default_text``.
        default_structured: Fallback when task not in *structured_responses*.
        default_text: Fallback when task not in *text_responses*.
    """

    def __init__(
        self,
        *,
        structured_responses: dict[str, Any] | None = None,
        text_responses: dict[str, str] | None = None,
        default_structured: Any = None,
        default_text: str = "",
    ) -> None:
        self._structured: dict[str, Any] = structured_responses or {}
        self._text: dict[str, str] = text_responses or {}
        self._default_structured = default_structured
        self._default_text = default_text

        # Call log — inspect in tests to assert gateway was called.
        self.calls: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Gateway interface
    # ------------------------------------------------------------------

    def call_structured(
        self,
        task: str,
        messages: list[dict],
        response_model: type[T],
        cache_prefix: str | None = None,
    ) -> T:
        self.calls.append(
            {"method": "call_structured", "task": task, "messages": messages}
        )
        result = self._structured.get(task, self._default_structured)
        if result is None:
            raise ValueError(
                f"FakeLLMGateway: no structured response configured for task={task!r}"
            )
        return result  # type: ignore[return-value]

    def call_text(
        self,
        task: str,
        messages: list[dict],
        cache_prefix: str | None = None,
    ) -> str:
        self.calls.append(
            {"method": "call_text", "task": task, "messages": messages}
        )
        return self._text.get(task, self._default_text)

    def call_batch(
        self,
        task: str,
        items: list[dict],
        response_model: type[T],
        cache_prefix: str | None = None,
    ) -> dict[str, Any]:
        """Return a preset structured response for each item, keyed by item id.

        Each item in *items* must have an ``"id"`` key (custom_id).  The same
        structured response that ``call_structured`` would return for *task* is
        used for every item.
        """
        self.calls.append(
            {"method": "call_batch", "task": task, "items": items}
        )
        preset = self._structured.get(task, self._default_structured)
        if preset is None:
            raise ValueError(
                f"FakeLLMGateway: no structured response configured for task={task!r}"
            )
        return {item["id"]: preset for item in items}
