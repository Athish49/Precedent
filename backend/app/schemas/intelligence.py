from __future__ import annotations

import uuid

from pydantic import BaseModel


class QARequest(BaseModel):
    question: str


class QAResponse(BaseModel):
    answer: str
    citations: list[dict]
    cached: bool


class EasyPromptRequest(BaseModel):
    user_request: str


class EasyPromptResponse(BaseModel):
    structured_prompt: str
    route: str  # "s3" | "s4"


class ResearchRequest(BaseModel):
    question: str
    search_results: list[dict] = []  # caller supplies [{title, snippet, url}]


class ResearchResponse(BaseModel):
    answer: str
    sources: list[dict]


class ClauseRefDTO(BaseModel):
    clause_id: uuid.UUID
    ordinal: int
    heading_text: str | None
    char_start: int
    char_end: int


class NavigationIndexDTO(BaseModel):
    contract_id: uuid.UUID
    index: dict[str, list[ClauseRefDTO]]
    toc: list[str]


class SummaryResponse(BaseModel):
    summary: str


class RedlineSummaryResponse(BaseModel):
    summary: str
    clause_type: str
