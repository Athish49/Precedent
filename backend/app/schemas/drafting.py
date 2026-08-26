from __future__ import annotations

from pydantic import BaseModel


class DraftClauseRequest(BaseModel):
    clause_type: str
    context: dict = {}
    instruction: str | None = None
    preferred_language: str | None = None


class DraftDocumentRequest(BaseModel):
    template: str
    variables: dict = {}
    polish: bool = False


class DraftPrecedentRequest(BaseModel):
    clause_type: str
    context: dict = {}


class DraftMemoRequest(BaseModel):
    context: dict


class DraftResponse(BaseModel):
    text: str
    source: str  # "playbook" | "frequency" | "llm" | "template"
