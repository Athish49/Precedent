"""Bundled renewal recommendation + compliance verification (T-082)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.core.llm.schemas.renewal import RenewalComplianceOut
from app.db.models.obligation import Alert
from app.db.repositories import analysis_repo, contract_repo, obligation_repo

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_SYSTEM = (_PROMPTS_DIR / "renewal_compliance.md").read_text()

_TASK = "renewal_compliance"


@dataclass
class RenewalResult:
    recommendation: str
    rationale: str
    compliance_pass: bool
    compliance_issues: list[str]


def _build_user_message(contract, meta, flags, obligations) -> str:
    expiry = (meta.expiry_date if meta is not None else None) or "unknown"
    auto_renewal = (meta.auto_renewal if meta is not None else None)
    governing_law = (meta.governing_law if meta is not None else None) or "unknown"

    lines = [
        "## Contract",
        f"Title: {contract.title}",
        f"Type: {contract.contract_type or 'unknown'}",
        f"Expiry: {expiry}",
        f"Auto-renewal: {auto_renewal}",
        f"Governing law: {governing_law}",
        "",
        f"## S2 Flags ({len(flags)} total)",
    ]
    if flags:
        for f in flags:
            lines.append(f"- [{f.severity.upper()}] {f.flag_type}: {f.detail}")
    else:
        lines.append("(none)")

    lines += [
        "",
        f"## Obligations ({len(obligations)} total)",
    ]
    if obligations:
        for ob in obligations:
            entry = (
                f"- {ob.commitment} | Owner: {ob.owner}"
                f" | Deadline: {ob.deadline} | Status: {ob.status}"
            )
            lines.append(entry)
    else:
        lines.append("(none)")

    return "\n".join(lines)


def _llm_call(contract, meta, flags, obligations) -> RenewalComplianceOut:
    user_content = _build_user_message(contract, meta, flags, obligations)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]
    return gateway.call_structured(_TASK, messages, RenewalComplianceOut, cache_prefix=_SYSTEM)


async def evaluate_renewal(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> RenewalResult:
    """Bundled LLM call: renewal recommendation + compliance verification.

    One call. Fires a renewal Alert with the recommendation payload.
    """
    pair = await contract_repo.get_contract_with_metadata(session, contract_id)
    if pair is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    contract, meta = pair
    flags = await analysis_repo.get_flags_for_contract(session, contract_id)
    obligations = await obligation_repo.get_obligations_for_contract(session, contract_id)

    out = _llm_call(contract, meta, flags, obligations)

    alert = Alert(
        contract_id=contract_id,
        alert_type="renewal",
        payload={
            "recommendation": out.renewal_recommendation,
            "rationale": out.renewal_rationale,
            "compliance_pass": out.compliance_pass,
            "compliance_issues": out.compliance_issues,
        },
    )
    await obligation_repo.create_alert(session, alert)
    await session.flush()

    return RenewalResult(
        recommendation=out.renewal_recommendation,
        rationale=out.renewal_rationale,
        compliance_pass=out.compliance_pass,
        compliance_issues=out.compliance_issues,
    )


async def check_compliance(
    session: AsyncSession,
    contract_id: uuid.UUID,
) -> RenewalResult:
    """On-demand compliance check. Same LLM call, no alert fired."""
    pair = await contract_repo.get_contract_with_metadata(session, contract_id)
    if pair is None:
        raise AppError(404, "contract_not_found", f"Contract {contract_id} not found")

    contract, meta = pair
    flags = await analysis_repo.get_flags_for_contract(session, contract_id)
    obligations = await obligation_repo.get_obligations_for_contract(session, contract_id)

    out = _llm_call(contract, meta, flags, obligations)

    return RenewalResult(
        recommendation=out.renewal_recommendation,
        rationale=out.renewal_rationale,
        compliance_pass=out.compliance_pass,
        compliance_issues=out.compliance_issues,
    )
