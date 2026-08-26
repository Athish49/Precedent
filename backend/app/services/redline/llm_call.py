"""S3 main LLM call — per-clause redline generation (T-047).

One ``call_structured`` per clause.  The system prompt (static instructions)
is sent with cache_control so repeated calls for the same contract amortise
its token cost.  Per-clause content (clause text, flag, preferred language,
NMS context, stance) goes in the user message.
"""

from __future__ import annotations

from pathlib import Path

from app.core.llm import gateway
from app.core.llm.schemas.redline import RedlineOut
from app.schemas.analysis import FlagDTO

# ---------------------------------------------------------------------------
# Prompt + task
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_SYSTEM = (_PROMPTS_DIR / "redline_generate.md").read_text()

_TASK = "redline_generate"

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_redline(
    clause_text: str,
    flag: FlagDTO,
    preferred_language: str | None,
    nms_context: str,
    stance_mode: str,
) -> RedlineOut:
    """Generate a redline for a single flagged clause.

    Args:
        clause_text: Full text of the clause to be revised.
        flag: The flag that triggered redlining for this clause.
        preferred_language: Playbook preferred language for this clause type,
            or None if no rule exists.
        nms_context: Deterministic NMS context string from
            ``services.redline.stance.build_nms_context``.
        stance_mode: "light" | "balanced" | "firm" — baked into the user message.

    Returns:
        A validated ``RedlineOut`` instance with replacement text, alternatives,
        explanation, and counterparty comment.
    """
    user_content = _build_user_message(
        clause_text, flag, preferred_language, nms_context, stance_mode
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]
    return gateway.call_structured(_TASK, messages, RedlineOut, cache_prefix=_SYSTEM)


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------


def _build_user_message(
    clause_text: str,
    flag: FlagDTO,
    preferred_language: str | None,
    nms_context: str,
    stance_mode: str,
) -> str:
    flag_detail = flag.detail.get("explanation") or flag.detail.get("detail") or str(flag.detail)

    parts = [
        "## Clause to revise",
        clause_text,
        "",
        "## Identified issue",
        f"Flag type: {flag.flag_type}",
        f"Severity: {flag.severity}",
        f"Detail: {flag_detail}",
        "",
        "## Playbook preferred language",
        preferred_language
        if preferred_language
        else "(none — no playbook rule for this clause type)",
        "",
        "## Negotiation context",
        f"Stance: {stance_mode}",
        nms_context,
    ]
    return "\n".join(parts)
