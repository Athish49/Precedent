from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel

from app.schemas.redline import RedlineDTO


class RunReviewRequest(BaseModel):
    contract_id: uuid.UUID
    stance_mode: str = "balanced"


class WebhookRequest(BaseModel):
    contract_id: uuid.UUID
    stance_mode: str = "balanced"


class ReviewRunDTO(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    contract_id: uuid.UUID
    trigger: str
    gate_decision: str | None
    gate_reason: dict | None
    status: str
    started_at: datetime.datetime
    completed_at: datetime.datetime | None


class RunReviewResponse(BaseModel):
    run: ReviewRunDTO
    gate_decision: str
    gate_reason: dict
    redlines: list[RedlineDTO]
    flags_count: int
    risk_score: float | None
