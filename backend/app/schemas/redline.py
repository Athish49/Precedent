from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel


class GenerateRedlinesRequest(BaseModel):
    stance_mode: str  # "light" | "balanced" | "firm"


class AlternativeDTO(BaseModel):
    label: str
    text: str


class TrackedChangeDTO(BaseModel):
    op: str  # "equal" | "insert" | "delete"
    text: str
    old_start: int
    old_end: int
    new_start: int
    new_end: int


class RedlineDTO(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    contract_id: uuid.UUID
    clause_id: uuid.UUID | None
    flag_id: uuid.UUID | None
    stance_mode: str
    position: str
    replacement_text: str
    tracked_changes: list[dict]
    alternatives: list[dict]
    explanation: str
    counterparty_comment: str
    rationale: dict
    status: str
    created_at: datetime.datetime


class GenerateRedlinesResponse(BaseModel):
    redlines: list[RedlineDTO]


class RefineRequest(BaseModel):
    instruction: str


class DecisionRequest(BaseModel):
    outcome: str  # "accepted" | "rejected"
    final_text: str | None = None
