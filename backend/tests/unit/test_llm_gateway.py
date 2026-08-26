"""Unit tests for the LLM gateway, registry, and fake helper."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

import app.core.llm.gateway as gw_module
from app.core.llm.errors import LLMError
from app.core.llm.registry import get_model_for_task
from tests.fake_llm import FakeLLMGateway

# ---------------------------------------------------------------------------
# Shared Pydantic model used across tests
# ---------------------------------------------------------------------------


class _ClauseResult(BaseModel):
    clause_type: str
    risk_level: int


# ---------------------------------------------------------------------------
# registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_known_fast_task_returns_haiku(self) -> None:
        model = get_model_for_task("chunk_classify")
        assert "haiku" in model.lower()

    def test_known_smart_task_returns_sonnet(self) -> None:
        model = get_model_for_task("clause_analysis")
        assert "sonnet" in model.lower()

    def test_unknown_task_defaults_to_smart(self) -> None:
        model = get_model_for_task("totally_unknown_task")
        assert "sonnet" in model.lower()

    def test_tier_override_from_settings(self) -> None:
        settings = MagicMock()
        settings.llm_tier_override = "claude-haiku-4-5-20251001"
        model = get_model_for_task("clause_analysis", settings=settings)
        assert model == "claude-haiku-4-5-20251001"

    def test_no_override_uses_registry(self) -> None:
        settings = MagicMock()
        settings.llm_tier_override = None
        model = get_model_for_task("chunk_classify", settings=settings)
        assert "haiku" in model.lower()


# ---------------------------------------------------------------------------
# FakeLLMGateway tests — verifies the fake itself behaves correctly
# ---------------------------------------------------------------------------


class TestFakeLLMGateway:
    def test_call_structured_returns_preset_model(self) -> None:
        expected = _ClauseResult(clause_type="indemnity", risk_level=3)
        fake = FakeLLMGateway(structured_responses={"clause_analysis": expected})

        result = fake.call_structured(
            "clause_analysis",
            [{"role": "user", "content": "Analyse this."}],
            _ClauseResult,
        )

        assert isinstance(result, _ClauseResult)
        assert result.clause_type == "indemnity"
        assert result.risk_level == 3

    def test_call_structured_logs_call(self) -> None:
        fake = FakeLLMGateway(
            default_structured=_ClauseResult(clause_type="nda", risk_level=1)
        )
        fake.call_structured("any_task", [], _ClauseResult)
        assert len(fake.calls) == 1
        assert fake.calls[0]["method"] == "call_structured"
        assert fake.calls[0]["task"] == "any_task"

    def test_call_structured_raises_when_no_response_configured(self) -> None:
        fake = FakeLLMGateway()
        with pytest.raises(ValueError, match="no structured response configured"):
            fake.call_structured("missing_task", [], _ClauseResult)

    def test_call_text_returns_preset_string(self) -> None:
        fake = FakeLLMGateway(text_responses={"summarise": "This is a summary."})
        result = fake.call_text("summarise", [{"role": "user", "content": "Summarise."}])
        assert result == "This is a summary."

    def test_call_text_returns_default_when_task_missing(self) -> None:
        fake = FakeLLMGateway(default_text="fallback")
        assert fake.call_text("unknown", []) == "fallback"

    def test_default_text_is_empty_string(self) -> None:
        fake = FakeLLMGateway()
        assert fake.call_text("unknown", []) == ""


# ---------------------------------------------------------------------------
# gateway.call_structured — integration with monkeypatched Anthropic client
# ---------------------------------------------------------------------------


def _make_parsed_response(
    parsed_obj: Any, input_tokens: int = 10, output_tokens: int = 20
) -> MagicMock:
    """Build a minimal mock that looks like ParsedBetaMessage."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.parsed_output = parsed_obj

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [text_block]
    response.usage = usage
    response.stop_reason = "end_turn"
    response.parsed_output = parsed_obj
    return response


class TestGatewayCallStructured:
    def test_returns_validated_pydantic_instance(self) -> None:
        expected = _ClauseResult(clause_type="liability", risk_level=5)
        mock_response = _make_parsed_response(expected)

        with patch.object(gw_module, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.beta.messages.parse.return_value = mock_response
            mock_build.return_value = mock_client

            result = gw_module.call_structured(
                "clause_analysis",
                [{"role": "user", "content": "Analyse."}],
                _ClauseResult,
            )

        assert isinstance(result, _ClauseResult)
        assert result.clause_type == "liability"
        assert result.risk_level == 5

    def test_raises_llmerror_on_refusal(self) -> None:
        refusal_response = _make_parsed_response(None)
        refusal_response.stop_reason = "refusal"
        refusal_response.parsed_output = None

        with patch.object(gw_module, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.beta.messages.parse.return_value = refusal_response
            mock_build.return_value = mock_client

            with pytest.raises(LLMError, match="refusal"):
                gw_module.call_structured(
                    "clause_analysis",
                    [{"role": "user", "content": "Analyse."}],
                    _ClauseResult,
                )

    def test_raises_llmerror_when_parsed_output_is_none(self) -> None:
        none_response = _make_parsed_response(None)
        none_response.stop_reason = "end_turn"

        with patch.object(gw_module, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.beta.messages.parse.return_value = none_response
            mock_build.return_value = mock_client

            with pytest.raises(LLMError):
                gw_module.call_structured(
                    "clause_analysis",
                    [{"role": "user", "content": "Analyse."}],
                    _ClauseResult,
                )

    def test_system_message_passed_separately(self) -> None:
        expected = _ClauseResult(clause_type="ip", risk_level=2)
        mock_response = _make_parsed_response(expected)

        with patch.object(gw_module, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.beta.messages.parse.return_value = mock_response
            mock_build.return_value = mock_client

            gw_module.call_structured(
                "clause_analysis",
                [
                    {"role": "system", "content": "You are a contract analyst."},
                    {"role": "user", "content": "Analyse."},
                ],
                _ClauseResult,
            )

        call_kwargs = mock_client.beta.messages.parse.call_args.kwargs
        # System message should have been split out, not left in messages.
        for msg in call_kwargs.get("messages", []):
            assert msg.get("role") != "system"
        assert "system" in call_kwargs

    def test_cache_prefix_adds_cache_control(self) -> None:
        expected = _ClauseResult(clause_type="ip", risk_level=2)
        mock_response = _make_parsed_response(expected)

        with patch.object(gw_module, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.beta.messages.parse.return_value = mock_response
            mock_build.return_value = mock_client

            gw_module.call_structured(
                "clause_analysis",
                [
                    {"role": "system", "content": "You are a contract analyst."},
                    {"role": "user", "content": "Analyse."},
                ],
                _ClauseResult,
                cache_prefix="contracts-v1",
            )

        call_kwargs = mock_client.beta.messages.parse.call_args.kwargs
        system = call_kwargs.get("system")
        assert isinstance(system, list), "system should be a list of blocks when cache_prefix set"
        assert system[0].get("cache_control") == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# gateway.call_text
# ---------------------------------------------------------------------------


class TestGatewayCallText:
    def _make_text_response(self, text: str) -> MagicMock:
        block = MagicMock()
        block.type = "text"
        block.text = text

        usage = MagicMock()
        usage.input_tokens = 5
        usage.output_tokens = 15

        response = MagicMock()
        response.content = [block]
        response.usage = usage
        response.stop_reason = "end_turn"
        return response

    def test_returns_text_content(self) -> None:
        mock_response = self._make_text_response("Summary here.")

        with patch.object(gw_module, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.beta.messages.parse.return_value = mock_response
            mock_build.return_value = mock_client

            result = gw_module.call_text(
                "contract_summary",
                [{"role": "user", "content": "Summarise."}],
            )

        assert result == "Summary here."

    def test_raises_llmerror_when_no_text_block(self) -> None:
        non_text_block = MagicMock()
        non_text_block.type = "tool_use"

        usage = MagicMock()
        usage.input_tokens = 5
        usage.output_tokens = 5

        response = MagicMock()
        response.content = [non_text_block]
        response.usage = usage
        response.stop_reason = "end_turn"

        with patch.object(gw_module, "_build_client") as mock_build:
            mock_client = MagicMock()
            mock_client.beta.messages.parse.return_value = response
            mock_build.return_value = mock_client

            with pytest.raises(LLMError, match="no text content"):
                gw_module.call_text(
                    "contract_summary",
                    [{"role": "user", "content": "Summarise."}],
                )
