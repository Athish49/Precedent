from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class DraftClauseRequest(BaseModel):
    """Body for ``POST /drafting/clause`` (task 4.7).

    * ``context`` — free-text description of what the clause should cover;
      goes into the LLM prompt only (the workspace's ``?prompt=`` routing
      pre-fills it).
    * ``deal_context`` — the structured resolution context
      ``routing.resolve()`` matches overlay playbooks' and rules'
      ``applies_when`` against (e.g. ``{"regimes": ["hipaa"]}``). Kept as a
      separate field rather than retyping ``context`` so free-text callers
      keep working.
    * ``contract_type`` / ``party_role`` / ``paper_origin`` — playbook
      resolution facts. All optional: the playbook lookup always runs, and a
      missing value falls back to ``""`` / ``"vendor"`` / ``"own"`` (baseline
      playbook plus matching overlays when ``contract_type`` is unknown).
    * ``mode`` — where the cascade starts: ``"playbook"`` (default, full
      cascade), ``"frequency"`` (skip playbook), ``"llm"`` (straight to the
      LLM, e.g. NL rewrite).
    """

    clause_type: str
    context: str | None = None
    instruction: str | None = None
    preferred_language: str | None = None
    mode: Literal["playbook", "frequency", "llm"] | None = None
    contract_type: str | None = None
    party_role: str | None = None
    paper_origin: str | None = None
    deal_context: dict[str, Any] | None = None


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
