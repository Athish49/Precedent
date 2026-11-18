from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.drafting.service import (
    draft_clause,
    draft_document,
    draft_memo,
    draft_precedent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session() -> AsyncMock:
    return AsyncMock()


def _empty_resolve() -> AsyncMock:
    """A ``routing.resolve`` stand-in that resolves to no rules (playbook miss)."""
    return AsyncMock(return_value=SimpleNamespace(rules=[]))


# ---------------------------------------------------------------------------
# draft_clause tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_clause_playbook_hit() -> None:
    """preferred_language set → source='playbook', no frequency/LLM call."""
    session = _mock_session()
    with (
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            preferred_language="Liability is limited to fees paid in the prior 12 months.",
        )

    assert result.source == "playbook"
    assert result.text == "Liability is limited to fees paid in the prior 12 months."
    freq_mock.assert_not_called()
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_frequency_hit() -> None:
    """Playbook miss, frequency hit → source='frequency', no LLM call."""
    from app.services.drafting.frequency_tracker import FrequencyResult

    session = _mock_session()
    freq_result = FrequencyResult(text="Standard liability cap clause.", frequency=5, scoped=True)

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=_empty_resolve(),
        ),
        patch(
            "app.services.drafting.service.frequency_tracker.most_common_clause",
            new=AsyncMock(return_value=freq_result),
        ),
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            context="SaaS deal, standard terms.",
        )

    assert result.source == "frequency"
    assert result.text == "Standard liability cap clause."
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_llm_fallback() -> None:
    """Playbook miss, frequency miss → LLM called → source='llm'."""
    session = _mock_session()

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=_empty_resolve(),
        ),
        patch(
            "app.services.drafting.service.frequency_tracker.most_common_clause",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.drafting.service.gateway.call_text",
            return_value="LLM drafted clause text.",
        ) as llm_mock,
    ):
        result = await draft_clause(
            session,
            "indemnification",
            context="Services agreement.",
            instruction="Mutual indemnification only.",
        )

    assert result.source == "llm"
    assert result.text == "LLM drafted clause text."
    llm_mock.assert_called_once()
    call_args = llm_mock.call_args
    assert call_args[0][0] == "drafting_clause"


# ---------------------------------------------------------------------------
# draft_clause: playbook resolution (task 4.7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_clause_playbook_resolution_hit() -> None:
    """Known contract_type + party_role resolve (task 4.2) to a rule whose
    requested clause type has a preferred (rung-0) position → source=
    'playbook', with no frequency lookup and no model call at all."""
    session = _mock_session()
    position = SimpleNamespace(
        kind="preferred", rung=0, language="Mutual cap at 12 months of Fees."
    )
    rule = SimpleNamespace(
        rule_key="limitation_of_liability.cap_amount",
        clause_type="limitation_of_liability",
        positions=[position],
    )
    resolved = SimpleNamespace(rules=[rule])

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=AsyncMock(return_value=resolved),
        ) as resolve_mock,
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            contract_type="saas_msa",
            party_role="vendor",
        )

    assert result.source == "playbook"
    assert result.text == "Mutual cap at 12 months of Fees."
    resolve_mock.assert_called_once()
    freq_mock.assert_not_called()
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_playbook_resolution_by_issue_key() -> None:
    """The requested clause type may be the bare issue (the part of
    rule_key after the dot) rather than the clause family; that still
    resolves to the rung-0 language with no model call."""
    session = _mock_session()
    position = SimpleNamespace(kind="preferred", rung=0, language="Net 30 payment terms.")
    rule = SimpleNamespace(
        rule_key="payment.payment_terms",
        clause_type="payment",
        positions=[position],
    )
    resolved = SimpleNamespace(rules=[rule])

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=AsyncMock(return_value=resolved),
        ),
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "payment_terms",
            contract_type="saas_msa",
            party_role="vendor",
        )

    assert result.source == "playbook"
    assert result.text == "Net 30 payment terms."
    freq_mock.assert_not_called()
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_playbook_preferred_language_override_wins() -> None:
    """An explicit preferred_language still wins over playbook resolution,
    and short-circuits before resolve() is even called."""
    session = _mock_session()

    with (
        patch("app.services.drafting.service.playbook_routing.resolve") as resolve_mock,
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            contract_type="saas_msa",
            party_role="vendor",
            preferred_language="Caller-supplied override language.",
        )

    assert result.source == "playbook"
    assert result.text == "Caller-supplied override language."
    resolve_mock.assert_not_called()
    freq_mock.assert_not_called()
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_playbook_miss_no_rule_falls_through_to_frequency() -> None:
    """contract_type/party_role resolve, but no rule matches the requested
    clause type/issue → falls through to frequency, exactly as the cascade
    worked before this task."""
    from app.services.drafting.frequency_tracker import FrequencyResult

    session = _mock_session()
    resolved = SimpleNamespace(rules=[])  # no rule for this clause type
    freq_result = FrequencyResult(text="Standard liability cap clause.", frequency=5, scoped=True)

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=AsyncMock(return_value=resolved),
        ),
        patch(
            "app.services.drafting.service.frequency_tracker.most_common_clause",
            new=AsyncMock(return_value=freq_result),
        ),
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            contract_type="saas_msa",
            party_role="vendor",
        )

    assert result.source == "frequency"
    assert result.text == "Standard liability cap clause."
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_missing_facts_still_resolves_baseline() -> None:
    """No contract_type/party_role/paper_origin/deal_context supplied →
    resolve() still runs (task 4.2: an unknown type resolves the baseline
    playbook), with the repo-wide fallbacks ``""`` / ``"vendor"`` /
    ``"own"`` and an empty context. A baseline rule for the clause type
    therefore still yields playbook language."""
    session = _mock_session()
    position = SimpleNamespace(kind="preferred", rung=0, language="Baseline indemnity.")
    rule = SimpleNamespace(
        rule_key="indemnification.scope",
        clause_type="indemnification",
        positions=[position],
    )

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=AsyncMock(return_value=SimpleNamespace(rules=[rule])),
        ) as resolve_mock,
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session, "indemnification", context="Mutual indemnification only."
        )

    assert result.source == "playbook"
    assert result.text == "Baseline indemnity."
    resolve_mock.assert_awaited_once_with(session, "", "vendor", "own", context={})
    freq_mock.assert_not_called()
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_threads_deal_context_to_resolve() -> None:
    """contract_type/party_role/paper_origin/deal_context reach resolve()
    unchanged, so overlay playbooks and ``applies_when`` rules can apply."""
    session = _mock_session()
    deal_context = {"regimes": ["hipaa"], "deal_value_band": "mid"}
    position = SimpleNamespace(kind="preferred", rung=0, language="HIPAA BAA language.")
    rule = SimpleNamespace(
        rule_key="data_protection.baa",
        clause_type="data_protection",
        positions=[position],
    )

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=AsyncMock(return_value=SimpleNamespace(rules=[rule])),
        ) as resolve_mock,
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "data_protection",
            contract_type="saas_msa",
            party_role="customer",
            paper_origin="counterparty",
            deal_context=deal_context,
        )

    assert result.source == "playbook"
    assert result.text == "HIPAA BAA language."
    resolve_mock.assert_awaited_once_with(
        session, "saas_msa", "customer", "counterparty", context=deal_context
    )
    freq_mock.assert_not_called()
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_clause_llm_fallback_includes_deal_facts_in_prompt() -> None:
    """On a playbook + frequency miss the structured deal facts are not
    dropped: they are rendered into the LLM user prompt alongside the
    free-text context."""
    session = _mock_session()

    with (
        patch(
            "app.services.drafting.service.playbook_routing.resolve",
            new=_empty_resolve(),
        ),
        patch(
            "app.services.drafting.service.frequency_tracker.most_common_clause",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.drafting.service.gateway.call_text",
            return_value="LLM text.",
        ) as llm_mock,
    ):
        result = await draft_clause(
            session,
            "data_protection",
            context="Cover PHI handling.",
            contract_type="saas_msa",
            party_role="vendor",
            deal_context={"regimes": ["hipaa"]},
        )

    assert result.source == "llm"
    user_prompt = llm_mock.call_args[0][1][1]["content"]
    assert "Contract type: saas_msa" in user_prompt
    assert "Party role: vendor" in user_prompt
    assert '"regimes": ["hipaa"]' in user_prompt
    assert "Context: Cover PHI handling." in user_prompt


@pytest.mark.asyncio
async def test_draft_clause_mode_llm_skips_playbook_and_frequency() -> None:
    """mode='llm' (the frontend's rewrite action) goes straight to the LLM,
    even when a preferred_language override or playbook data is available."""
    session = _mock_session()

    with (
        patch("app.services.drafting.service.playbook_routing.resolve") as resolve_mock,
        patch("app.services.drafting.service.frequency_tracker.most_common_clause") as freq_mock,
        patch(
            "app.services.drafting.service.gateway.call_text",
            return_value="Rewritten clause.",
        ) as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            instruction="Make the cap mutual.",
            contract_type="saas_msa",
            party_role="vendor",
            preferred_language="Override that must be ignored.",
            mode="llm",
        )

    assert result.source == "llm"
    assert result.text == "Rewritten clause."
    resolve_mock.assert_not_called()
    freq_mock.assert_not_called()
    llm_mock.assert_called_once()
    assert "Instruction: Make the cap mutual." in llm_mock.call_args[0][1][1]["content"]


@pytest.mark.asyncio
async def test_draft_clause_mode_frequency_skips_playbook() -> None:
    """mode='frequency' starts the cascade at the frequency step."""
    from app.services.drafting.frequency_tracker import FrequencyResult

    session = _mock_session()
    freq_result = FrequencyResult(text="Most common clause.", frequency=3, scoped=True)

    with (
        patch("app.services.drafting.service.playbook_routing.resolve") as resolve_mock,
        patch(
            "app.services.drafting.service.frequency_tracker.most_common_clause",
            new=AsyncMock(return_value=freq_result),
        ),
        patch("app.services.drafting.service.gateway.call_text") as llm_mock,
    ):
        result = await draft_clause(
            session,
            "limitation_of_liability",
            contract_type="saas_msa",
            party_role="vendor",
            mode="frequency",
        )

    assert result.source == "frequency"
    assert result.text == "Most common clause."
    resolve_mock.assert_not_called()
    llm_mock.assert_not_called()


# ---------------------------------------------------------------------------
# draft_document tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_document_no_polish() -> None:
    """No polish → source='template', variables substituted, no LLM."""
    session = _mock_session()

    with patch("app.services.drafting.service.gateway.call_text") as llm_mock:
        result = await draft_document(
            session,
            template="This agreement is between $party_a and $party_b.",
            variables={"party_a": "Acme Corp", "party_b": "Beta LLC"},
        )

    assert result.source == "template"
    assert result.text == "This agreement is between Acme Corp and Beta LLC."
    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_draft_document_polish() -> None:
    """polish=True → LLM called → source='llm'."""
    session = _mock_session()

    with patch(
        "app.services.drafting.service.gateway.call_text",
        return_value="Polished document text.",
    ) as llm_mock:
        result = await draft_document(
            session,
            template="This agreement is between $party_a and $party_b.",
            variables={"party_a": "Acme Corp", "party_b": "Beta LLC"},
            polish=True,
        )

    assert result.source == "llm"
    assert result.text == "Polished document text."
    llm_mock.assert_called_once()
    assert llm_mock.call_args[0][0] == "drafting_document_polish"


# ---------------------------------------------------------------------------
# draft_precedent tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_precedent_vector_then_llm() -> None:
    """Vector search called, then LLM → source='llm'."""
    from app.services.repository.vector import PrecedentResult

    session = _mock_session()
    precedents = [
        PrecedentResult(
            clause_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            clause_type="governing_law",
            text="Precedent clause one.",
            distance=0.1,
        ),
        PrecedentResult(
            clause_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            clause_type="governing_law",
            text="Precedent clause two.",
            distance=0.2,
        ),
    ]

    with (
        patch(
            "app.services.drafting.service.vector.precedent_search",
            new=AsyncMock(return_value=precedents),
        ) as search_mock,
        patch(
            "app.services.drafting.service.gateway.call_text",
            return_value="Precedent-style drafted clause.",
        ) as llm_mock,
    ):
        result = await draft_precedent(
            session,
            "governing_law",
            context={"contract_type": "SaaS"},
        )

    assert result.source == "llm"
    assert result.text == "Precedent-style drafted clause."
    search_mock.assert_called_once()
    llm_mock.assert_called_once()
    assert llm_mock.call_args[0][0] == "drafting_precedent"


# ---------------------------------------------------------------------------
# draft_memo tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_memo_llm_called() -> None:
    """LLM called → source='llm'."""
    context = {"to": "Client", "re": "Contract Review", "issues": ["liability cap"]}

    with patch(
        "app.services.drafting.service.gateway.call_text",
        return_value="Drafted memo text.",
    ) as llm_mock:
        result = await draft_memo(context)

    assert result.source == "llm"
    assert result.text == "Drafted memo text."
    llm_mock.assert_called_once()
    assert llm_mock.call_args[0][0] == "drafting_memo"
