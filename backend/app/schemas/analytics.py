from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel


class ContractIntelligenceRow(BaseModel):
    model_config = {"from_attributes": True}
    contract_id: uuid.UUID
    title: str
    contract_type: str | None
    paper_origin: str | None
    status: str | None
    counterparty_id: uuid.UUID | None
    counterparty_name: str | None
    effective_date: datetime.date | None
    expiry_date: datetime.date | None
    governing_law: str | None
    auto_renewal: bool | None
    notice_period_days: int | None
    liability_cap: Any | None
    payment_terms: str | None
    risk_score: float | None
    max_clause_severity: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None


class PortfolioRiskResponse(BaseModel):
    total_contracts: int
    total_high_flags: int
    total_medium_flags: int
    total_low_flags: int
    total_flags: int
    avg_weighted_flag_score: float | None
    avg_risk_score: float | None
    contracts_high_severity: int
    contracts_medium_severity: int
    contracts_low_severity: int


class ContractValueRow(BaseModel):
    model_config = {"from_attributes": True}
    contract_id: uuid.UUID
    title: str
    contract_type: str | None
    counterparty_id: uuid.UUID | None
    counterparty_name: str | None
    financial_fields: Any | None
    total_value: str | None
    currency: str | None
    annual_value: str | None
    payment_frequency: str | None
    effective_date: datetime.date | None
    expiry_date: datetime.date | None
    duration_days: int | None
    status: str | None
    created_at: datetime.datetime


class TabularReviewRow(BaseModel):
    model_config = {"from_attributes": True}
    contract_id: uuid.UUID
    title: str
    contract_type: str | None
    paper_origin: str | None
    status: str | None
    counterparty_name: str | None
    effective_date: datetime.date | None
    expiry_date: datetime.date | None
    governing_law: str | None
    auto_renewal: bool | None
    notice_period_days: int | None
    payment_terms: str | None
    liability_cap: Any | None
    risk_score: float | None
    max_clause_severity: str | None
    high_flags: int
    medium_flags: int
    low_flags: int
    open_obligations: int
    overdue_obligations: int
    proposed_redlines: int | None
    accepted_redlines: int | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None


class RenewalDashboardRow(BaseModel):
    model_config = {"from_attributes": True}
    contract_id: uuid.UUID
    title: str
    contract_type: str | None
    counterparty_id: uuid.UUID | None
    counterparty_name: str | None
    expiry_date: datetime.date | None
    auto_renewal: bool | None
    notice_period_days: int | None
    governing_law: str | None
    risk_score: float | None
    max_clause_severity: str | None
    renewal_recommendation: str | None
    renewal_rationale: str | None
    compliance_pass: str | None
    last_alert_at: datetime.datetime | None
    alert_acknowledged: bool | None
    contract_status: str | None
