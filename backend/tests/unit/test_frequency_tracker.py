from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.drafting.frequency_tracker import (
    FrequencyResult,
    _pick_best,
    most_common_clause,
)

MODULE = "app.services.drafting.frequency_tracker._fetch_clause_texts"


@pytest.mark.asyncio
async def test_scoped_hit():
    """Scoped pass meets threshold → returns FrequencyResult(scoped=True)."""
    session = AsyncMock()
    ct_id = uuid.uuid4()
    scoped_texts = ["clause A", "clause A", "clause B"]
    unscoped_texts = ["clause C", "clause C", "clause C"]

    with patch(MODULE, side_effect=[scoped_texts, unscoped_texts]) as mock_fetch:
        result = await most_common_clause(
            session,
            "indemnity",
            contract_type="MSA",
            counterparty_id=ct_id,
        )

    assert result == FrequencyResult(text="clause A", frequency=2, scoped=True)
    # unscoped should not have been called
    assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_scoped_miss_unscoped_hit():
    """Scoped pass below threshold, unscoped meets threshold → scoped=False."""
    session = AsyncMock()
    scoped_texts = ["clause A"]  # count=1, below default min_frequency=2
    unscoped_texts = ["clause B", "clause B", "clause C"]

    with patch(MODULE, side_effect=[scoped_texts, unscoped_texts]):
        result = await most_common_clause(
            session,
            "limitation",
            contract_type="NDA",
        )

    assert result == FrequencyResult(text="clause B", frequency=2, scoped=False)


@pytest.mark.asyncio
async def test_both_miss():
    """Neither pass meets threshold → None."""
    session = AsyncMock()
    scoped_texts = ["clause A"]
    unscoped_texts = ["clause B"]

    with patch(MODULE, side_effect=[scoped_texts, unscoped_texts]):
        result = await most_common_clause(
            session,
            "warranty",
            contract_type="SaaS",
        )

    assert result is None


@pytest.mark.asyncio
async def test_no_context_filters_skips_scoped():
    """No context filters → skips scoped pass, goes straight to unscoped."""
    session = AsyncMock()
    unscoped_texts = ["clause X", "clause X", "clause Y"]

    with patch(MODULE, side_effect=[unscoped_texts]) as mock_fetch:
        result = await most_common_clause(session, "governing_law")

    assert result == FrequencyResult(text="clause X", frequency=2, scoped=False)
    assert mock_fetch.call_count == 1
    # verify it was called with no filters
    call_kwargs = mock_fetch.call_args
    assert call_kwargs.args[2] is None   # contract_type
    assert call_kwargs.args[3] is None   # counterparty_id


@pytest.mark.asyncio
async def test_determinism_tie_breaking():
    """Tie-break by text alphabetically → always picks lexicographically first."""
    session = AsyncMock()
    # "bravo" and "alpha" both appear twice — "alpha" wins alphabetically
    unscoped_texts = ["bravo", "alpha", "bravo", "alpha"]

    with patch(MODULE, side_effect=[unscoped_texts]):
        result = await most_common_clause(session, "payment")

    assert result is not None
    assert result.text == "alpha"
    assert result.frequency == 2


@pytest.mark.asyncio
async def test_min_frequency_one():
    """min_frequency=1 → single occurrence qualifies."""
    session = AsyncMock()
    unscoped_texts = ["only once"]

    with patch(MODULE, side_effect=[unscoped_texts]):
        result = await most_common_clause(session, "termination", min_frequency=1)

    assert result == FrequencyResult(text="only once", frequency=1, scoped=False)


# Pure unit tests for _pick_best (no async needed)

def test_pick_best_returns_none_on_empty():
    assert _pick_best([], 2) is None


def test_pick_best_below_threshold():
    assert _pick_best(["a"], 2) is None


def test_pick_best_tie_breaks_alphabetically():
    texts = ["z text", "a text", "z text", "a text"]
    result = _pick_best(texts, 2)
    assert result == ("a text", 2)


def test_pick_best_single_item_min_one():
    result = _pick_best(["hello"], 1)
    assert result == ("hello", 1)
