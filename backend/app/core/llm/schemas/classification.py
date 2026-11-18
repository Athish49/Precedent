from __future__ import annotations

from pydantic import BaseModel, Field


class ContractTypeClassification(BaseModel):
    """Structured output from the contract-type classification LLM call
    (task 4.1, item 2 of ``playbook_implementation.md``).
    """

    contract_type: str | None = Field(
        default=None,
        description=(
            "The key of the best-matching candidate contract type, or null if none "
            "of the candidates plausibly matches the document."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the classification, from 0.0 (guess) to 1.0 (certain).",
    )
