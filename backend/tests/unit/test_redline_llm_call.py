"""Tests for T-047 S3 main LLM call — generate_redline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from app.core.llm.schemas.redline import AlternativeProposal, RedlineOut
from app.schemas.analysis import FlagDTO
from app.schemas.playbook import RulePositionResponse
from app.services.redline import llm_call as llm_call_module
from app.services.redline.llm_call import generate_redline
from tests.fake_llm import FakeLLMGateway

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(
    flag_type: str = "high_risk",
    severity: str = "high",
    detail: dict | None = None,
) -> FlagDTO:
    return FlagDTO(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        clause_id=uuid.uuid4(),
        flag_type=flag_type,
        severity=severity,
        source="llm",
        char_start=None,
        char_end=None,
        detail=detail or {"explanation": "Uncapped liability creates significant exposure."},
        matched_rule_id=None,
        created_at=datetime.now(UTC),
    )


def _canned_redline(
    replacement_text: str = "Vendor's liability shall not exceed fees paid in the prior 12 months.",
) -> RedlineOut:
    return RedlineOut(
        replacement_text=replacement_text,
        alternatives=[
            AlternativeProposal(
                label="Option A — Mutual Cap",
                text="Each party's liability is capped at 12-month fees.",
            ),
            AlternativeProposal(
                label="Option B — No Cap, Mutual",
                text="Neither party shall be liable for consequential damages.",
            ),
        ],
        explanation=(
            "The original clause exposed the vendor to unlimited liability. "
            "The revision caps damages at 12-month fees."
        ),
        counterparty_comment=(
            "We propose capping liability at 12-month fees, "
            "consistent with industry standard SaaS terms."
        ),
    )


def _make_fake(redline: RedlineOut | None = None) -> FakeLLMGateway:
    return FakeLLMGateway(
        structured_responses={"redline_generate": redline or _canned_redline()}
    )


def _position(
    rung: int = 1,
    label: str = "Fallback 1: 18-month cap",
    language: str = "Liability shall not exceed 18 months of Fees.",
    zone: str = "yellow",
) -> RulePositionResponse:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return RulePositionResponse(
        id=uuid.uuid4(),
        rule_id=uuid.uuid4(),
        kind="fallback",
        rung=rung,
        label=label,
        language=language,
        summary=None,
        zone=zone,
        approver_role_id=None,
        conditions=None,
        give_get=None,
        internal_note=None,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Return type and basic contract
# ---------------------------------------------------------------------------


def test_generate_redline_returns_redline_out() -> None:
    fake = _make_fake()
    with patch.object(llm_call_module, "gateway", fake):
        result = generate_redline(
            clause_text="Vendor shall be liable for all damages, direct or indirect.",
            flag=_flag(),
            preferred_language="Liability shall not exceed fees paid in prior 12 months.",
            nms_context="Historical acceptance rate: 80%. Apply balanced revisions.",
            stance_mode="balanced",
        )
    assert isinstance(result, RedlineOut)


def test_generate_redline_returns_replacement_text() -> None:
    expected = "Liability is capped at 12-month fees."
    fake = _make_fake(_canned_redline(replacement_text=expected))
    with patch.object(llm_call_module, "gateway", fake):
        result = generate_redline(
            clause_text="Vendor liable for all damages.",
            flag=_flag(),
            preferred_language=None,
            nms_context="No prior history. Apply light-touch revisions.",
            stance_mode="light",
        )
    assert result.replacement_text == expected


def test_generate_redline_alternatives_are_list_of_proposals() -> None:
    fake = _make_fake()
    with patch.object(llm_call_module, "gateway", fake):
        result = generate_redline("text", _flag(), None, "no history", "firm")
    assert isinstance(result.alternatives, list)
    assert all(isinstance(a, AlternativeProposal) for a in result.alternatives)


def test_generate_redline_has_explanation_and_comment() -> None:
    fake = _make_fake()
    with patch.object(llm_call_module, "gateway", fake):
        result = generate_redline("text", _flag(), None, "no history", "balanced")
    assert isinstance(result.explanation, str) and result.explanation
    assert isinstance(result.counterparty_comment, str) and result.counterparty_comment


# ---------------------------------------------------------------------------
# Gateway call discipline
# ---------------------------------------------------------------------------


def test_generate_redline_calls_gateway_exactly_once() -> None:
    fake = _make_fake()
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), None, "ctx", "balanced")
    assert len(fake.calls) == 1
    assert fake.calls[0]["method"] == "call_structured"


def test_generate_redline_uses_correct_task_name() -> None:
    fake = _make_fake()
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), None, "ctx", "balanced")
    assert fake.calls[0]["task"] == "redline_generate"


def test_generate_redline_system_prompt_in_messages() -> None:
    """The system prompt must appear in messages — not silently dropped."""
    captured: list[list[dict]] = []

    class _CapturingFake(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured.append(messages)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _CapturingFake(structured_responses={"redline_generate": _canned_redline()})
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), "Preferred lang.", "ctx", "firm")

    assert captured, "gateway was not called"
    messages = captured[0]
    system_msgs = [m for m in messages if m.get("role") == "system"]
    assert system_msgs, "system message must be present in messages"
    assert system_msgs[0]["content"].strip(), "system message content must not be empty"


def test_generate_redline_cache_prefix_set() -> None:
    """cache_prefix must be truthy so the gateway wraps the system block with cache_control."""
    captured_prefix: list[str | None] = []

    class _PrefixCapture(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured_prefix.append(cache_prefix)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _PrefixCapture(structured_responses={"redline_generate": _canned_redline()})
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), None, "ctx", "light")

    assert captured_prefix and captured_prefix[0], "cache_prefix must be truthy"


# ---------------------------------------------------------------------------
# User message content
# ---------------------------------------------------------------------------


def test_user_message_contains_clause_text() -> None:
    clause = "The vendor shall indemnify all parties for any damages whatsoever."
    captured: list[list[dict]] = []

    class _Cap(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured.append(messages)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _Cap(structured_responses={"redline_generate": _canned_redline()})
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline(clause, _flag(), None, "ctx", "balanced")

    user_msgs = [m for m in captured[0] if m.get("role") == "user"]
    assert any(clause in m["content"] for m in user_msgs)


def test_user_message_contains_stance_mode() -> None:
    captured: list[list[dict]] = []

    class _Cap(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured.append(messages)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _Cap(structured_responses={"redline_generate": _canned_redline()})
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), None, "ctx", "firm")

    user_msgs = [m for m in captured[0] if m.get("role") == "user"]
    assert any("firm" in m["content"] for m in user_msgs)


def test_user_message_contains_preferred_language() -> None:
    pref = "Liability shall not exceed fees paid in the prior twelve months."
    captured: list[list[dict]] = []

    class _Cap(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured.append(messages)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _Cap(structured_responses={"redline_generate": _canned_redline()})
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), pref, "ctx", "balanced")

    user_msgs = [m for m in captured[0] if m.get("role") == "user"]
    assert any(pref in m["content"] for m in user_msgs)


def test_user_message_contains_nms_context() -> None:
    ctx = "Historical acceptance rate: 60%. Maintain firm position."
    captured: list[list[dict]] = []

    class _Cap(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured.append(messages)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _Cap(structured_responses={"redline_generate": _canned_redline()})
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), None, ctx, "firm")

    user_msgs = [m for m in captured[0] if m.get("role") == "user"]
    assert any(ctx in m["content"] for m in user_msgs)


def test_user_message_none_preferred_language_gracefully_handled() -> None:
    """None preferred_language should not raise and should produce a coherent message."""
    fake = _make_fake()
    with patch.object(llm_call_module, "gateway", fake):
        result = generate_redline("text", _flag(), None, "ctx", "light")
    assert isinstance(result, RedlineOut)


def test_flag_detail_explanation_in_user_message() -> None:
    detail = {"explanation": "Unlimited indemnification scope."}
    captured: list[list[dict]] = []

    class _Cap(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured.append(messages)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _Cap(structured_responses={"redline_generate": _canned_redline()})
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(detail=detail), None, "ctx", "balanced")

    user_msgs = [m for m in captured[0] if m.get("role") == "user"]
    assert any("Unlimited indemnification scope." in m["content"] for m in user_msgs)


# ---------------------------------------------------------------------------
# fallback_positions (task 4.6 item 1): alternatives come from the
# playbook's own fallback rungs, in rung order, never invented.
# ---------------------------------------------------------------------------


def test_fallback_positions_listed_in_prompt_in_rung_order() -> None:
    f1 = _position(rung=1, label="Fallback 1: 18-month cap")
    f2 = _position(rung=2, label="Fallback 2: 24-month cap")
    captured: list[list[dict]] = []

    class _Cap(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured.append(messages)
            return super().call_structured(task, messages, response_model, cache_prefix)

    fake = _Cap(
        structured_responses={
            "redline_generate": RedlineOut(
                replacement_text="Preferred text.",
                alternatives=[
                    AlternativeProposal(label="A", text="18-month version."),
                    AlternativeProposal(label="B", text="24-month version."),
                ],
                explanation="Explanation.",
                counterparty_comment="Comment.",
            )
        }
    )
    with patch.object(llm_call_module, "gateway", fake):
        generate_redline("text", _flag(), "Preferred lang.", "ctx", "firm", [f1, f2])

    user_msgs = [m for m in captured[0] if m.get("role") == "user"]
    content = "\n".join(m["content"] for m in user_msgs)
    assert "Fallback 1: 18-month cap" in content
    assert "Fallback 2: 24-month cap" in content
    # Rung order preserved in the prompt text.
    assert content.index("Fallback 1") < content.index("Fallback 2")


def test_fallback_positions_reconciled_onto_returned_alternatives() -> None:
    f1 = _position(rung=1, label="Fallback 1")
    f2 = _position(rung=2, label="Fallback 2")

    fake = _make_fake(
        RedlineOut(
            replacement_text="Preferred text.",
            alternatives=[
                AlternativeProposal(label="A", text="Model wording for rung 1."),
                AlternativeProposal(label="B", text="Model wording for rung 2."),
            ],
            explanation="Explanation.",
            counterparty_comment="Comment.",
        )
    )
    with patch.object(llm_call_module, "gateway", fake):
        result = generate_redline("text", _flag(), None, "ctx", "balanced", [f1, f2])

    assert [a.position_id for a in result.alternatives] == [f1.id, f2.id]
    assert [a.rung for a in result.alternatives] == [1, 2]
    assert result.alternatives[0].text == "Model wording for rung 1."


def test_no_fallback_positions_alternatives_get_sequential_rungs() -> None:
    """Free-form path (no rule matched): alternatives still get a rung
    number (so toggle_fallback has something to step through), but no
    position_id since no real playbook position backs them."""
    fake = _make_fake()
    with patch.object(llm_call_module, "gateway", fake):
        result = generate_redline("text", _flag(), None, "ctx", "balanced")

    assert [a.rung for a in result.alternatives] == [1, 2]
    assert all(a.position_id is None for a in result.alternatives)
