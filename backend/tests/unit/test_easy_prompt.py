"""Unit tests for easy_prompt service (T-076)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.core.llm.schemas.intelligence import EasyPromptOut
from app.services.intelligence.easy_prompt import EasyPromptResult, generate_easy_prompt


def _mock_session() -> AsyncMock:
    return AsyncMock()


def _make_clause(clause_type: str) -> MagicMock:
    c = MagicMock()
    c.clause_type = clause_type
    return c


@pytest.mark.asyncio
async def test_generate_easy_prompt_success() -> None:
    """Contract found → LLM called once → returns EasyPromptResult."""
    session = _mock_session()
    contract_id = uuid.uuid4()

    contract = MagicMock()
    contract.title = "Service Agreement"
    contract.contract_type = "SaaS"

    clauses = [_make_clause("indemnification"), _make_clause("limitation_of_liability")]
    llm_out = EasyPromptOut(
        structured_prompt="Review indemnification clause for one-sidedness.",
        route="s3",
    )

    with (
        patch(
            "app.services.intelligence.easy_prompt.contract_repo.get_contract",
            new=AsyncMock(return_value=contract),
        ),
        patch(
            "app.services.intelligence.easy_prompt.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=clauses),
        ),
        patch(
            "app.services.intelligence.easy_prompt.gateway.call_structured",
            return_value=llm_out,
        ) as llm_mock,
    ):
        result = await generate_easy_prompt(session, contract_id, "Check the indemnification")

    assert isinstance(result, EasyPromptResult)
    assert result.structured_prompt == "Review indemnification clause for one-sidedness."
    assert result.route == "s3"
    llm_mock.assert_called_once()


@pytest.mark.asyncio
async def test_generate_easy_prompt_contract_not_found() -> None:
    """Contract not found → AppError raised."""
    session = _mock_session()
    contract_id = uuid.uuid4()

    with patch(
        "app.services.intelligence.easy_prompt.contract_repo.get_contract",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(AppError) as exc_info:
            await generate_easy_prompt(session, contract_id, "some request")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "contract_not_found"


@pytest.mark.asyncio
async def test_generate_easy_prompt_route_literal() -> None:
    """route value is 's3' or 's4' — validate the Literal constraint works."""
    session = _mock_session()
    contract_id = uuid.uuid4()

    contract = MagicMock()
    contract.title = "MSA"
    contract.contract_type = "master_services"

    llm_out = EasyPromptOut(
        structured_prompt="Draft a new governing law clause for New York.",
        route="s4",
    )

    with (
        patch(
            "app.services.intelligence.easy_prompt.contract_repo.get_contract",
            new=AsyncMock(return_value=contract),
        ),
        patch(
            "app.services.intelligence.easy_prompt.clause_repo.get_clauses_for_contract",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.intelligence.easy_prompt.gateway.call_structured",
            return_value=llm_out,
        ),
    ):
        result = await generate_easy_prompt(session, contract_id, "Create a governing law clause")

    assert result.route in {"s3", "s4"}
    assert result.route == "s4"
