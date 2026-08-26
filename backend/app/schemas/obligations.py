"""Pydantic API schemas for S8 Obligations."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel


class ObligationDTO(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    contract_id: uuid.UUID
    commitment: str
    owner: str
    deadline: datetime.date | None
    deliverable: str
    char_start: int | None
    char_end: int | None
    status: str
    created_at: datetime.datetime


class AlertDTO(BaseModel):
    model_config = {"from_attributes": True}
    id: uuid.UUID
    contract_id: uuid.UUID
    alert_type: str
    payload: dict
    fired_at: datetime.datetime
    acknowledged: bool


class MonitorRunResponse(BaseModel):
    deadline_alerts: int
    renewal_alerts: int
    total: int


class ComplianceCheckResponse(BaseModel):
    compliance_pass: bool
    compliance_issues: list[str]
    recommendation: str
    rationale: str
