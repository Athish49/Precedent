"""Pydantic API schemas for S6 Playbook & Rules."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Playbook schemas
# ---------------------------------------------------------------------------

_VALID_PRACTICE_AREAS = frozenset({"hipaa", "gdpr", "saas_msa", "nda", "dpa"})


class PlaybookCreate(BaseModel):
    name: str
    practice_area: str
    precedence: int = 0


class PlaybookUpdate(BaseModel):
    name: str | None = None
    practice_area: str | None = None
    precedence: int | None = None


class PlaybookResponse(BaseModel):
    id: uuid.UUID
    name: str
    practice_area: str
    precedence: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Rule schemas
# ---------------------------------------------------------------------------


class RuleCreate(BaseModel):
    clause_type: str
    preferred_language: str = ""
    acceptable_variations: list | None = None
    prohibited_terms: list | None = None
    fallback_language: str | None = None
    required: bool = False
    risk_weight: float = Field(default=1.0, ge=0.0)
    escalation_threshold: float | None = None


class RuleUpdate(BaseModel):
    clause_type: str | None = None
    preferred_language: str | None = None
    acceptable_variations: list | None = None
    prohibited_terms: list | None = None
    fallback_language: str | None = None
    required: bool | None = None
    risk_weight: float | None = Field(default=None, ge=0.0)
    escalation_threshold: float | None = None


class RuleResponse(BaseModel):
    id: uuid.UUID
    playbook_id: uuid.UUID
    clause_type: str
    preferred_language: str
    acceptable_variations: list | None
    prohibited_terms: list | None
    fallback_language: str | None
    required: bool
    risk_weight: float
    escalation_threshold: float | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Playbook + nested rules
# ---------------------------------------------------------------------------


class PlaybookWithRulesResponse(PlaybookResponse):
    rules: list[RuleResponse] = []


# ---------------------------------------------------------------------------
# Resolve response
# ---------------------------------------------------------------------------


class BootstrapRequest(BaseModel):
    """Body for POST /playbooks/bootstrap.

    Either *contract_ids* (explicit list) or *contract_type* (load all
    contracts of that type) must be provided.
    """

    playbook_id: uuid.UUID
    contract_ids: list[uuid.UUID] | None = None
    contract_type: str | None = None

    @model_validator(mode="after")
    def _check_corpus(self) -> BootstrapRequest:
        if not self.contract_ids and not self.contract_type:
            raise ValueError("Either contract_ids or contract_type must be provided")
        return self


class BootstrapResponse(BaseModel):
    created_rule_count: int


class ResolveResponse(BaseModel):
    """Result of resolving all applicable playbooks for a given contract type.

    Rules are keyed by clause_type; the value is the rule from the
    highest-precedence playbook that defines that clause type.
    """

    contract_type: str
    applied_practice_areas: list[str]
    rules: dict[str, RuleResponse]
