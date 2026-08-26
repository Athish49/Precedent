from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RenewalComplianceOut(BaseModel):
    renewal_recommendation: Literal["renew", "renegotiate", "terminate"]
    renewal_rationale: str
    compliance_pass: bool
    compliance_issues: list[str]
