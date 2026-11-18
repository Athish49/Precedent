"""Unit tests for contract type and context capture (task 4.1).

Covers classification (via the fake LLM gateway), deterministic regime
detection, deal_value_band derivation (from context_dimension and from the
hardcoded fallback), and validation of contract_type / party_role / context
against the agreement_type / context_dimension lookup tables, including
their graceful handling when those tables are empty.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.errors import AppError
from app.core.llm.schemas.classification import ContractTypeClassification
from app.services.document_processing import context_capture as cc
from tests.fake_llm import FakeLLMGateway

# ── Helpers ───────────────────────────────────────────────────────────────────


def _agreement_type_row(key: str, name: str = "", kind: str = "agreement") -> MagicMock:
    row = MagicMock()
    row.key = key
    row.name = name or key
    row.kind = kind
    return row


def _dimension_row(key: str, values: object, value_type: str = "enum") -> MagicMock:
    row = MagicMock()
    row.key = key
    row.value_type = value_type
    row.values = values
    return row


def _session_returning(*results: object) -> AsyncMock:
    """An AsyncMock session whose .execute() yields *results* in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


def _scalars_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _scalar_one_result(row: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    return result


_AGREEMENT_TYPES = [
    _agreement_type_row("nda", "Mutual NDA"),
    _agreement_type_row("saas_msa", "SaaS MSA"),
    _agreement_type_row("dpa", "DPA"),
    _agreement_type_row("vendor_msa", "Vendor MSA"),
]


# ── classify_contract_type ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_high_confidence_returns_type(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLLMGateway(
        structured_responses={
            "contract_type_classify": ContractTypeClassification(
                contract_type="saas_msa", confidence=0.95
            )
        }
    )
    monkeypatch.setattr(cc, "gateway", fake)
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))

    result = await cc.classify_contract_type(session, title="SaaS Agreement", text_excerpt="...")

    assert result == "saas_msa"
    assert len(fake.calls) == 1
    assert fake.calls[0]["task"] == "contract_type_classify"


@pytest.mark.asyncio
async def test_classify_low_confidence_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLLMGateway(
        structured_responses={
            "contract_type_classify": ContractTypeClassification(
                contract_type="saas_msa", confidence=0.2
            )
        }
    )
    monkeypatch.setattr(cc, "gateway", fake)
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))

    result = await cc.classify_contract_type(session, title="Ambiguous Doc", text_excerpt="...")

    assert result is None


@pytest.mark.asyncio
async def test_classify_hallucinated_type_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLLMGateway(
        structured_responses={
            "contract_type_classify": ContractTypeClassification(
                contract_type="made_up_type", confidence=0.99
            )
        }
    )
    monkeypatch.setattr(cc, "gateway", fake)
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))

    result = await cc.classify_contract_type(session, title="Doc", text_excerpt="...")

    assert result is None


@pytest.mark.asyncio
async def test_classify_null_type_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLLMGateway(
        structured_responses={
            "contract_type_classify": ContractTypeClassification(contract_type=None, confidence=0.1)
        }
    )
    monkeypatch.setattr(cc, "gateway", fake)
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))

    result = await cc.classify_contract_type(session, title="Doc", text_excerpt="...")

    assert result is None


@pytest.mark.asyncio
async def test_classify_no_candidates_skips_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLLMGateway()
    monkeypatch.setattr(cc, "gateway", fake)
    session = _session_returning(_scalars_result([]))

    result = await cc.classify_contract_type(session, title="Doc", text_excerpt="...")

    assert result is None
    assert fake.calls == []


@pytest.mark.asyncio
async def test_classify_truncates_excerpt_to_3000_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLLMGateway(
        structured_responses={
            "contract_type_classify": ContractTypeClassification(contract_type="nda", confidence=0.9)
        }
    )
    monkeypatch.setattr(cc, "gateway", fake)
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))

    long_text = "x" * 10_000
    await cc.classify_contract_type(session, title="Doc", text_excerpt=long_text)

    user_message = fake.calls[0]["messages"][1]["content"]
    # Only the first 3000 characters of the excerpt should appear in the prompt.
    assert "x" * 3000 in user_message
    assert "x" * 3001 not in user_message


# ── derive_regimes ───────────────────────────────────────────────────────────


def test_derive_regimes_hipaa_via_phi_word() -> None:
    text = "Vendor may access PHI in connection with the Services."
    assert cc.derive_regimes(text) == ["hipaa"]


def test_derive_regimes_hipaa_phi_substring_not_matched() -> None:
    # "philosophy" contains "phi" as a substring but must not match \bphi\b.
    text = "This agreement reflects our shared philosophy on data handling."
    assert cc.derive_regimes(text) == []


def test_derive_regimes_hipaa_via_business_associate() -> None:
    text = "Vendor is a Business Associate of Customer under HIPAA."
    assert cc.derive_regimes(text) == ["hipaa"]


def test_derive_regimes_gdpr_requires_all_three_terms() -> None:
    text = "This Agreement is governed by GDPR."
    # Mentions GDPR but not controller/processor language.
    assert cc.derive_regimes(text) == []

    text_full = (
        "This Agreement is governed by GDPR. Customer acts as Controller and "
        "Vendor acts as Processor of Personal Data."
    )
    assert cc.derive_regimes(text_full) == ["gdpr"]


def test_derive_regimes_both_hipaa_and_gdpr() -> None:
    text = (
        "Vendor is a Business Associate handling PHI. This Agreement is also "
        "governed by GDPR, with Customer as Controller and Vendor as Processor."
    )
    assert cc.derive_regimes(text) == ["hipaa", "gdpr"]


def test_derive_regimes_neither() -> None:
    text = "This is a standard services agreement with no special data handling terms."
    assert cc.derive_regimes(text) == []


# ── derive_deal_value_band ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deal_value_band_default_boundaries() -> None:
    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 50_000) == "standard"

    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 99_999) == "standard"

    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 100_000) == "mid"

    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 499_999) == "mid"

    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 500_000) == "enterprise"

    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 1_499_999) == "enterprise"

    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 1_500_000) == "strategic"

    session = _session_returning(_scalar_one_result(None))
    assert await cc.derive_deal_value_band(session, 5_000_000) == "strategic"


@pytest.mark.asyncio
async def test_deal_value_band_none_input_returns_none() -> None:
    session = AsyncMock()
    assert await cc.derive_deal_value_band(session, None) is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_deal_value_band_reads_custom_boundaries_from_dimension() -> None:
    dimension = _dimension_row(
        "deal_value_band",
        {
            "standard": {"min": None, "max": 50_000},
            "mid": {"min": 50_000, "max": 200_000},
            "enterprise": {"min": 200_000, "max": None},
        },
    )
    session = _session_returning(_scalar_one_result(dimension))
    assert await cc.derive_deal_value_band(session, 60_000) == "mid"


@pytest.mark.asyncio
async def test_deal_value_band_malformed_dimension_falls_back_to_defaults() -> None:
    dimension = _dimension_row("deal_value_band", ["not", "a", "dict"])
    session = _session_returning(_scalar_one_result(dimension))
    assert await cc.derive_deal_value_band(session, 50_000) == "standard"


# ── validate_contract_type ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_contract_type_accepts_known_key() -> None:
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))
    await cc.validate_contract_type(session, "dpa")  # should not raise


@pytest.mark.asyncio
async def test_validate_contract_type_rejects_unknown_key() -> None:
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))
    with pytest.raises(AppError) as exc_info:
        await cc.validate_contract_type(session, "not_a_real_type")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_contract_type"


@pytest.mark.asyncio
async def test_validate_contract_type_rejects_non_agreement_kind() -> None:
    # "hipaa" exists in agreement_type but as kind='regime', not a selectable
    # contract type.
    session = _session_returning(_scalars_result(_AGREEMENT_TYPES))
    with pytest.raises(AppError):
        await cc.validate_contract_type(session, "hipaa")


# ── validate_party_role ──────────────────────────────────────────────────────


def test_validate_party_role_accepts_known_values() -> None:
    for role in ("vendor", "customer", "mutual"):
        cc.validate_party_role(role)  # should not raise


def test_validate_party_role_rejects_unknown_value() -> None:
    with pytest.raises(AppError) as exc_info:
        cc.validate_party_role("partner")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_party_role"


# ── validate_context ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_context_skips_when_no_dimensions_defined() -> None:
    session = _session_returning(_scalars_result([]))
    # Garbage values should pass through untouched when the table is empty.
    await cc.validate_context(session, {"region": "mars", "counterparty_tier": "nope"})


@pytest.mark.asyncio
async def test_validate_context_accepts_known_value() -> None:
    dims = [_dimension_row("region", {"us": {}, "eu": {}, "uk": {}, "other": {}})]
    session = _session_returning(_scalars_result(dims))
    await cc.validate_context(session, {"region": "eu"})  # should not raise


@pytest.mark.asyncio
async def test_validate_context_rejects_unknown_value_for_known_dimension() -> None:
    dims = [_dimension_row("region", {"us": {}, "eu": {}, "uk": {}, "other": {}})]
    session = _session_returning(_scalars_result(dims))
    with pytest.raises(AppError) as exc_info:
        await cc.validate_context(session, {"region": "mars"})
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_context_value"


@pytest.mark.asyncio
async def test_validate_context_passes_through_unknown_keys_leniently() -> None:
    # "region" is defined, "counterparty_tier" is not (not yet seeded) — the
    # latter should pass through without validation per task item 6.
    dims = [_dimension_row("region", {"us": {}, "eu": {}})]
    session = _session_returning(_scalars_result(dims))
    await cc.validate_context(session, {"region": "us", "counterparty_tier": "anything"})


@pytest.mark.asyncio
async def test_validate_context_validates_multi_enum_list_values() -> None:
    dims = [_dimension_row("regimes", {"hipaa": {}, "gdpr": {}}, value_type="multi_enum")]
    session = _session_returning(_scalars_result(dims))
    await cc.validate_context(session, {"regimes": ["hipaa"]})  # should not raise

    session = _session_returning(_scalars_result(dims))
    with pytest.raises(AppError):
        await cc.validate_context(session, {"regimes": ["hipaa", "ccpa"]})


@pytest.mark.asyncio
async def test_validate_context_ignores_raw_deal_value_key() -> None:
    dims = [_dimension_row("region", {"us": {}})]
    session = _session_returning(_scalars_result(dims))
    # "deal_value" is a raw number, not a dimension — must never be checked
    # against an "allowed values" set.
    await cc.validate_context(session, {"deal_value": 250_000})
