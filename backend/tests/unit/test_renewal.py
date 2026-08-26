"""Unit tests for services.obligations.renewal (T-082)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.errors import AppError
from app.core.llm.schemas.renewal import RenewalComplianceOut
from app.services.obligations.renewal import RenewalResult, check_compliance, evaluate_renewal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONTRACT_ID = uuid.uuid4()

_BASE_PATH = "app.services.obligations.renewal"


def _make_contract():
    c = MagicMock()
    c.title = "Master Services Agreement"
    c.contract_type = "MSA"
    return c


def _make_meta(*, present: bool = True):
    if not present:
        return None
    m = MagicMock()
    m.expiry_date = "2025-12-31"
    m.auto_renewal = True
    m.governing_law = "New York"
    return m


def _make_flag(flag_type="limitation_of_liability", severity="high", detail=None):
    f = MagicMock()
    f.flag_type = flag_type
    f.severity = severity
    f.detail = detail or {"explanation": "Cap too low"}
    return f


def _make_obligation(commitment="Deliver report", owner="Client", deadline=None, status="open"):
    ob = MagicMock()
    ob.commitment = commitment
    ob.owner = owner
    ob.deadline = deadline
    ob.status = status
    return ob


def _make_llm_out(
    recommendation="renew",
    rationale="Low risk.",
    compliance_pass=True,
    compliance_issues=None,
) -> RenewalComplianceOut:
    return RenewalComplianceOut(
        renewal_recommendation=recommendation,
        renewal_rationale=rationale,
        compliance_pass=compliance_pass,
        compliance_issues=compliance_issues or [],
    )


# ---------------------------------------------------------------------------
# evaluate_renewal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_renewal_happy_path():
    session = AsyncMock()
    contract = _make_contract()
    meta = _make_meta()
    flag = _make_flag()
    ob = _make_obligation()
    llm_out = _make_llm_out()

    with (
        patch(f"{_BASE_PATH}.contract_repo.get_contract_with_metadata", new_callable=AsyncMock) as mock_contract,
        patch(f"{_BASE_PATH}.analysis_repo.get_flags_for_contract", new_callable=AsyncMock) as mock_flags,
        patch(f"{_BASE_PATH}.obligation_repo.get_obligations_for_contract", new_callable=AsyncMock) as mock_obs,
        patch(f"{_BASE_PATH}.obligation_repo.create_alert", new_callable=AsyncMock) as mock_alert,
        patch(f"{_BASE_PATH}.gateway.call_structured", return_value=llm_out) as mock_llm,
    ):
        mock_contract.return_value = (contract, meta)
        mock_flags.return_value = [flag]
        mock_obs.return_value = [ob]
        mock_alert.return_value = MagicMock()

        result = await evaluate_renewal(session, CONTRACT_ID)

    mock_llm.assert_called_once()
    assert mock_llm.call_args[0][0] == "renewal_compliance"
    mock_alert.assert_called_once()
    assert isinstance(result, RenewalResult)
    assert result.recommendation == "renew"
    assert result.rationale == "Low risk."
    assert result.compliance_pass is True
    assert result.compliance_issues == []


@pytest.mark.asyncio
async def test_evaluate_renewal_contract_not_found():
    session = AsyncMock()

    with patch(f"{_BASE_PATH}.contract_repo.get_contract_with_metadata", new_callable=AsyncMock) as mock_contract:
        mock_contract.return_value = None

        with pytest.raises(AppError) as exc_info:
            await evaluate_renewal(session, CONTRACT_ID)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_evaluate_renewal_meta_is_none():
    """No ContractMetadata row — must not crash; LLM called; Alert created."""
    session = AsyncMock()
    contract = _make_contract()
    llm_out = _make_llm_out()

    with (
        patch(f"{_BASE_PATH}.contract_repo.get_contract_with_metadata", new_callable=AsyncMock) as mock_contract,
        patch(f"{_BASE_PATH}.analysis_repo.get_flags_for_contract", new_callable=AsyncMock) as mock_flags,
        patch(f"{_BASE_PATH}.obligation_repo.get_obligations_for_contract", new_callable=AsyncMock) as mock_obs,
        patch(f"{_BASE_PATH}.obligation_repo.create_alert", new_callable=AsyncMock) as mock_alert,
        patch(f"{_BASE_PATH}.gateway.call_structured", return_value=llm_out),
    ):
        mock_contract.return_value = (contract, None)  # no metadata
        mock_flags.return_value = []
        mock_obs.return_value = []
        mock_alert.return_value = MagicMock()

        result = await evaluate_renewal(session, CONTRACT_ID)

    mock_alert.assert_called_once()
    assert isinstance(result, RenewalResult)


# ---------------------------------------------------------------------------
# check_compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_compliance_happy_path():
    session = AsyncMock()
    contract = _make_contract()
    meta = _make_meta()
    llm_out = _make_llm_out(compliance_pass=True)

    with (
        patch(f"{_BASE_PATH}.contract_repo.get_contract_with_metadata", new_callable=AsyncMock) as mock_contract,
        patch(f"{_BASE_PATH}.analysis_repo.get_flags_for_contract", new_callable=AsyncMock) as mock_flags,
        patch(f"{_BASE_PATH}.obligation_repo.get_obligations_for_contract", new_callable=AsyncMock) as mock_obs,
        patch(f"{_BASE_PATH}.obligation_repo.create_alert", new_callable=AsyncMock) as mock_alert,
        patch(f"{_BASE_PATH}.gateway.call_structured", return_value=llm_out) as mock_llm,
    ):
        mock_contract.return_value = (contract, meta)
        mock_flags.return_value = []
        mock_obs.return_value = []

        result = await check_compliance(session, CONTRACT_ID)

    mock_llm.assert_called_once()
    mock_alert.assert_not_called()  # no alert for on-demand compliance
    assert isinstance(result, RenewalResult)
    assert result.compliance_pass is True


@pytest.mark.asyncio
async def test_check_compliance_contract_not_found():
    session = AsyncMock()

    with patch(f"{_BASE_PATH}.contract_repo.get_contract_with_metadata", new_callable=AsyncMock) as mock_contract:
        mock_contract.return_value = None

        with pytest.raises(AppError) as exc_info:
            await check_compliance(session, CONTRACT_ID)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_compliance_pass_false_has_issues():
    """compliance_pass=False → compliance_issues list is non-empty."""
    session = AsyncMock()
    contract = _make_contract()
    meta = _make_meta()
    llm_out = _make_llm_out(
        compliance_pass=False,
        compliance_issues=["Cap too low", "Indemnity clause missing"],
    )

    with (
        patch(f"{_BASE_PATH}.contract_repo.get_contract_with_metadata", new_callable=AsyncMock) as mock_contract,
        patch(f"{_BASE_PATH}.analysis_repo.get_flags_for_contract", new_callable=AsyncMock) as mock_flags,
        patch(f"{_BASE_PATH}.obligation_repo.get_obligations_for_contract", new_callable=AsyncMock) as mock_obs,
        patch(f"{_BASE_PATH}.obligation_repo.create_alert", new_callable=AsyncMock),
        patch(f"{_BASE_PATH}.gateway.call_structured", return_value=llm_out),
    ):
        mock_contract.return_value = (contract, meta)
        mock_flags.return_value = []
        mock_obs.return_value = []

        result = await check_compliance(session, CONTRACT_ID)

    assert result.compliance_pass is False
    assert len(result.compliance_issues) == 2


@pytest.mark.asyncio
async def test_recommendation_renegotiate():
    """LLM returns 'renegotiate' → result.recommendation == 'renegotiate'."""
    session = AsyncMock()
    contract = _make_contract()
    meta = _make_meta()
    llm_out = _make_llm_out(recommendation="renegotiate", rationale="High risk flags present.")

    with (
        patch(f"{_BASE_PATH}.contract_repo.get_contract_with_metadata", new_callable=AsyncMock) as mock_contract,
        patch(f"{_BASE_PATH}.analysis_repo.get_flags_for_contract", new_callable=AsyncMock) as mock_flags,
        patch(f"{_BASE_PATH}.obligation_repo.get_obligations_for_contract", new_callable=AsyncMock) as mock_obs,
        patch(f"{_BASE_PATH}.obligation_repo.create_alert", new_callable=AsyncMock),
        patch(f"{_BASE_PATH}.gateway.call_structured", return_value=llm_out),
    ):
        mock_contract.return_value = (contract, meta)
        mock_flags.return_value = []
        mock_obs.return_value = []

        result = await check_compliance(session, CONTRACT_ID)

    assert result.recommendation == "renegotiate"
