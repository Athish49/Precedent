"""Unit tests for call_batch — both the FakeLLMGateway implementation and the
real gateway wired to a mocked Anthropic client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

import app.core.llm.gateway as gw_module
from app.core.llm.errors import LLMError
from tests.fake_llm import FakeLLMGateway

# ---------------------------------------------------------------------------
# Shared Pydantic model
# ---------------------------------------------------------------------------


class _RiskResult(BaseModel):
    clause_type: str
    risk_level: int


# ---------------------------------------------------------------------------
# FakeLLMGateway.call_batch tests
# ---------------------------------------------------------------------------


class TestFakeCallBatch:
    def test_returns_dict_keyed_by_item_ids(self) -> None:
        preset = _RiskResult(clause_type="indemnity", risk_level=4)
        fake = FakeLLMGateway(structured_responses={"clause_analysis": preset})

        items = [
            {"id": "item-1", "messages": [{"role": "user", "content": "Clause 1"}]},
            {"id": "item-2", "messages": [{"role": "user", "content": "Clause 2"}]},
        ]
        result = fake.call_batch("clause_analysis", items, _RiskResult)

        assert set(result.keys()) == {"item-1", "item-2"}

    def test_each_value_is_preset_model_instance(self) -> None:
        preset = _RiskResult(clause_type="liability", risk_level=2)
        fake = FakeLLMGateway(structured_responses={"clause_analysis": preset})

        items = [
            {"id": "a", "messages": [{"role": "user", "content": "A"}]},
            {"id": "b", "messages": [{"role": "user", "content": "B"}]},
        ]
        result = fake.call_batch("clause_analysis", items, _RiskResult)

        for value in result.values():
            assert isinstance(value, _RiskResult)
            assert value.clause_type == "liability"
            assert value.risk_level == 2

    def test_uses_default_structured_when_task_not_in_responses(self) -> None:
        default = _RiskResult(clause_type="default", risk_level=0)
        fake = FakeLLMGateway(default_structured=default)

        items = [{"id": "x", "messages": []}]
        result = fake.call_batch("unknown_task", items, _RiskResult)

        assert result["x"].clause_type == "default"

    def test_raises_when_no_response_configured(self) -> None:
        fake = FakeLLMGateway()
        items = [{"id": "z", "messages": []}]
        with pytest.raises(ValueError, match="no structured response configured"):
            fake.call_batch("missing_task", items, _RiskResult)

    def test_logs_call_in_calls_list(self) -> None:
        fake = FakeLLMGateway(
            default_structured=_RiskResult(clause_type="test", risk_level=1)
        )
        items = [{"id": "i1", "messages": []}, {"id": "i2", "messages": []}]
        fake.call_batch("my_task", items, _RiskResult)

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "call_batch"
        assert call["task"] == "my_task"
        assert call["items"] is items

    def test_empty_items_returns_empty_dict(self) -> None:
        fake = FakeLLMGateway(
            default_structured=_RiskResult(clause_type="x", risk_level=0)
        )
        result = fake.call_batch("any_task", [], _RiskResult)
        assert result == {}


# ---------------------------------------------------------------------------
# gateway.call_batch — integration with mocked Anthropic client
# ---------------------------------------------------------------------------


def _make_batch_result(custom_id: str, parsed_obj: Any) -> MagicMock:
    """Build a mock BetaMessageBatchIndividualResponse with a succeeded result."""
    message = MagicMock()
    message.parsed_output = parsed_obj

    res = MagicMock()
    res.type = "succeeded"
    res.message = message

    item = MagicMock()
    item.custom_id = custom_id
    item.result = res
    return item


class TestGatewayCallBatch:
    def _make_mock_client(
        self, batch_results: list[Any], poll_status: str = "ended"
    ) -> MagicMock:
        """Return a mock Anthropic client whose batches API behaves predictably."""
        batch_obj = MagicMock()
        batch_obj.id = "msgbatch_test123"
        batch_obj.processing_status = poll_status

        mock_batches = MagicMock()
        mock_batches.create.return_value = batch_obj
        mock_batches.retrieve.return_value = batch_obj
        mock_batches.results.return_value = iter(batch_results)

        mock_client = MagicMock()
        mock_client.beta.messages.batches = mock_batches
        return mock_client

    def test_returns_dict_keyed_by_custom_ids(self) -> None:
        obj_a = _RiskResult(clause_type="nda", risk_level=1)
        obj_b = _RiskResult(clause_type="ip", risk_level=3)
        batch_results = [
            _make_batch_result("item-a", obj_a),
            _make_batch_result("item-b", obj_b),
        ]
        mock_client = self._make_mock_client(batch_results)

        with patch.object(gw_module, "_build_client", return_value=mock_client):
            result = gw_module.call_batch(
                "clause_analysis",
                [
                    {"id": "item-a", "messages": [{"role": "user", "content": "A"}]},
                    {"id": "item-b", "messages": [{"role": "user", "content": "B"}]},
                ],
                _RiskResult,
            )

        assert set(result.keys()) == {"item-a", "item-b"}
        assert result["item-a"].clause_type == "nda"
        assert result["item-b"].clause_type == "ip"

    def test_batch_create_called_once(self) -> None:
        parsed = _RiskResult(clause_type="liability", risk_level=5)
        batch_results = [_make_batch_result("only", parsed)]
        mock_client = self._make_mock_client(batch_results)

        with patch.object(gw_module, "_build_client", return_value=mock_client):
            gw_module.call_batch(
                "clause_analysis",
                [{"id": "only", "messages": [{"role": "user", "content": "Hi"}]}],
                _RiskResult,
            )

        mock_client.beta.messages.batches.create.assert_called_once()

    def test_raises_llmerror_on_non_succeeded_result(self) -> None:
        errored = MagicMock()
        errored.type = "errored"
        errored.custom_id = "bad-item"
        errored.result = MagicMock()
        errored.result.type = "errored"

        mock_client = self._make_mock_client([errored])

        with patch.object(gw_module, "_build_client", return_value=mock_client):
            with pytest.raises(LLMError, match="bad-item"):
                gw_module.call_batch(
                    "clause_analysis",
                    [{"id": "bad-item", "messages": [{"role": "user", "content": "Hi"}]}],
                    _RiskResult,
                )

    def test_raises_llmerror_when_parsed_output_is_none(self) -> None:
        item = _make_batch_result("null-item", None)
        mock_client = self._make_mock_client([item])

        with patch.object(gw_module, "_build_client", return_value=mock_client):
            with pytest.raises(LLMError, match="null-item"):
                gw_module.call_batch(
                    "clause_analysis",
                    [{"id": "null-item", "messages": [{"role": "user", "content": "Hi"}]}],
                    _RiskResult,
                )

    def test_system_messages_split_into_params(self) -> None:
        parsed = _RiskResult(clause_type="test", risk_level=0)
        batch_results = [_make_batch_result("sys-item", parsed)]
        mock_client = self._make_mock_client(batch_results)

        with patch.object(gw_module, "_build_client", return_value=mock_client):
            gw_module.call_batch(
                "clause_analysis",
                [
                    {
                        "id": "sys-item",
                        "messages": [
                            {"role": "system", "content": "You are an analyst."},
                            {"role": "user", "content": "Analyse."},
                        ],
                    }
                ],
                _RiskResult,
            )

        create_call = mock_client.beta.messages.batches.create.call_args
        requests = create_call.kwargs["requests"]
        assert len(requests) == 1
        params = requests[0]["params"]
        # System message should have been extracted out of messages.
        for msg in params["messages"]:
            assert msg.get("role") != "system"
        assert "system" in params

    def test_polls_until_ended(self) -> None:
        """Verify retrieve is called when batch is not immediately done."""
        parsed = _RiskResult(clause_type="poll", risk_level=0)
        batch_results = [_make_batch_result("p", parsed)]

        # First retrieve returns "processing", second returns "ended".
        processing_batch = MagicMock()
        processing_batch.id = "msgbatch_poll"
        processing_batch.processing_status = "processing"

        ended_batch = MagicMock()
        ended_batch.id = "msgbatch_poll"
        ended_batch.processing_status = "ended"

        create_batch = MagicMock()
        create_batch.id = "msgbatch_poll"
        create_batch.processing_status = "processing"

        mock_batches = MagicMock()
        mock_batches.create.return_value = create_batch
        mock_batches.retrieve.side_effect = [processing_batch, ended_batch]
        mock_batches.results.return_value = iter(batch_results)

        mock_client = MagicMock()
        mock_client.beta.messages.batches = mock_batches

        with (
            patch.object(gw_module, "_build_client", return_value=mock_client),
            patch("app.core.llm.gateway.time") as mock_time,
        ):
            gw_module.call_batch(
                "clause_analysis",
                [{"id": "p", "messages": [{"role": "user", "content": "Poll me"}]}],
                _RiskResult,
                poll_interval=0.0,
            )

        # retrieve should have been called twice (processing → processing → ended).
        assert mock_batches.retrieve.call_count == 2
        # sleep should have been called for each non-ended poll.
        assert mock_time.sleep.call_count == 2
