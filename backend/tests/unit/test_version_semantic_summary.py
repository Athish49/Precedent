"""Unit tests for T-091: Version Semantic Summary workflow and route."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.versions import _get_session
from app.main import app
from app.workflows.version_comparison import ClauseDiff, VersionDiffResult
from app.workflows.version_semantic_summary import SemanticSummaryResult

mock_session = AsyncMock()


async def _mock_get_session():
    yield mock_session


app.dependency_overrides[_get_session] = _mock_get_session

client = TestClient(app, raise_server_exceptions=False)

_CONTRACT_ID = uuid.uuid4()
_V_A = uuid.uuid4()
_V_B = uuid.uuid4()

_fake_result = VersionDiffResult(
    contract_id=_CONTRACT_ID,
    v_a=_V_A,
    v_b=_V_B,
    v_a_number=1,
    v_b_number=2,
    clause_diffs=[
        ClauseDiff(
            clause_id=uuid.uuid4(),
            clause_type="indemnification",
            heading_text="Indemnification",
            ordinal=1,
            char_start=0,
            char_end=100,
            change_type="modified",
            changes=[
                {
                    "op": "delete",
                    "text": "old text",
                    "old_start": 0,
                    "old_end": 8,
                    "new_start": -1,
                    "new_end": -1,
                }
            ],
        ),
        ClauseDiff(
            clause_id=uuid.uuid4(),
            clause_type="payment",
            heading_text="Payment",
            ordinal=2,
            char_start=100,
            char_end=200,
            change_type="unchanged",
            changes=[],
        ),
    ],
    global_changes=[],
)


@pytest.mark.asyncio
async def test_summarize_diff_calls_llm() -> None:
    """summarize_diff() calls compare_versions and gateway.call_text, returns SemanticSummaryResult."""
    with patch(
        "app.workflows.version_semantic_summary.compare_versions",
        new_callable=AsyncMock,
    ) as mock_diff, patch(
        "app.workflows.version_semantic_summary.gateway.call_text"
    ) as mock_llm:
        mock_diff.return_value = _fake_result
        mock_llm.return_value = "Version 2 adds new indemnification obligations."

        from app.workflows.version_semantic_summary import summarize_diff

        result = await summarize_diff(mock_session, _CONTRACT_ID, _V_A, _V_B)

        assert result.summary == "Version 2 adds new indemnification obligations."
        assert result.modified_clause_types == ["indemnification"]
        assert result.v_a_number == 1
        assert result.v_b_number == 2
        mock_llm.assert_called_once()
        mock_diff.assert_called_once_with(mock_session, _CONTRACT_ID, _V_A, _V_B)


@pytest.mark.asyncio
async def test_modified_clause_types_extracted_correctly() -> None:
    """Modified clause types are deduplicated and sorted."""
    multi_modified = VersionDiffResult(
        contract_id=_CONTRACT_ID,
        v_a=_V_A,
        v_b=_V_B,
        v_a_number=1,
        v_b_number=2,
        clause_diffs=[
            ClauseDiff(
                clause_id=uuid.uuid4(),
                clause_type="warranty",
                heading_text="Warranty",
                ordinal=1,
                char_start=0,
                char_end=50,
                change_type="modified",
                changes=[{"op": "insert", "text": "new", "old_start": -1, "old_end": -1, "new_start": 0, "new_end": 3}],
            ),
            ClauseDiff(
                clause_id=uuid.uuid4(),
                clause_type="indemnification",
                heading_text="Indemnification",
                ordinal=2,
                char_start=50,
                char_end=100,
                change_type="modified",
                changes=[{"op": "delete", "text": "old", "old_start": 50, "old_end": 53, "new_start": -1, "new_end": -1}],
            ),
            ClauseDiff(
                clause_id=uuid.uuid4(),
                clause_type="warranty",
                heading_text="Warranty 2",
                ordinal=3,
                char_start=100,
                char_end=150,
                change_type="modified",
                changes=[],
            ),
        ],
        global_changes=[],
    )

    with patch(
        "app.workflows.version_semantic_summary.compare_versions",
        new_callable=AsyncMock,
        return_value=multi_modified,
    ), patch(
        "app.workflows.version_semantic_summary.gateway.call_text",
        return_value="Summary text.",
    ):
        from app.workflows.version_semantic_summary import summarize_diff

        result = await summarize_diff(mock_session, _CONTRACT_ID, _V_A, _V_B)

        assert result.modified_clause_types == ["indemnification", "warranty"]


@pytest.mark.asyncio
async def test_no_modified_clauses_still_produces_summary() -> None:
    """When no clauses are modified, summary is still produced."""
    no_changes = VersionDiffResult(
        contract_id=_CONTRACT_ID,
        v_a=_V_A,
        v_b=_V_B,
        v_a_number=1,
        v_b_number=2,
        clause_diffs=[
            ClauseDiff(
                clause_id=uuid.uuid4(),
                clause_type="payment",
                heading_text="Payment",
                ordinal=1,
                char_start=0,
                char_end=100,
                change_type="unchanged",
                changes=[],
            ),
        ],
        global_changes=[],
    )

    with patch(
        "app.workflows.version_semantic_summary.compare_versions",
        new_callable=AsyncMock,
        return_value=no_changes,
    ), patch(
        "app.workflows.version_semantic_summary.gateway.call_text",
        return_value="No substantive changes detected.",
    ):
        from app.workflows.version_semantic_summary import summarize_diff

        result = await summarize_diff(mock_session, _CONTRACT_ID, _V_A, _V_B)

        assert result.summary == "No substantive changes detected."
        assert result.modified_clause_types == []


def test_post_diff_summary_endpoint() -> None:
    """POST /api/versions/diff/summary → 200 with summary and modified_clause_types."""
    fake_semantic_result = SemanticSummaryResult(
        contract_id=_CONTRACT_ID,
        v_a=_V_A,
        v_b=_V_B,
        v_a_number=1,
        v_b_number=2,
        summary="Indemnification obligations expanded significantly.",
        modified_clause_types=["indemnification"],
    )

    with patch(
        "app.api.routes.versions.version_semantic_summary.summarize_diff",
        new=AsyncMock(return_value=fake_semantic_result),
    ):
        response = client.post(
            "/api/versions/diff/summary",
            json={
                "contract_id": str(_CONTRACT_ID),
                "v_a": str(_V_A),
                "v_b": str(_V_B),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Indemnification obligations expanded significantly."
    assert body["modified_clause_types"] == ["indemnification"]
    assert body["v_a_number"] == 1
    assert body["v_b_number"] == 2
