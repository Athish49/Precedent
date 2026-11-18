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
from app.schemas.playbook import RulePositionResponse
from app.services.redline import ladder

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
    fallback_positions: list[RulePositionResponse] | None = None,
) -> RedlineOut:
    """Generate a redline for a single flagged clause.

    Args:
        clause_text: Full text of the clause to be revised.
        flag: The flag that triggered redlining for this clause.
        preferred_language: Playbook preferred (rung 0) language for this
            clause type, or None if no rule exists.
        nms_context: Deterministic NMS context string from
            ``services.redline.stance.build_nms_context``.
        stance_mode: "light" | "balanced" | "firm" — baked into the user message.
        fallback_positions: the rule's fallback rungs that apply to this
            contract's context (task 4.6 item 1; already filtered by
            ``conditions`` and sorted by rung via
            ``app.services.redline.ladder.select_offered_positions`` —
            this function does not re-filter or re-sort them). Each is
            listed in the prompt in rung order so the model adapts one
            alternative per rung rather than inventing its own. Empty or
            None for the free-form path (no rule matched).

    Returns:
        A validated ``RedlineOut``. Its ``alternatives`` have been
        reconciled against *fallback_positions* by
        ``ladder.reconcile_alternatives`` — the model's wording survives,
        but ``position_id``/``rung`` are always the canonical ones, so the
        count and identity of alternatives can never drift from what the
        playbook actually offers.
    """
    positions = fallback_positions or []
    user_content = _build_user_message(
        clause_text, flag, preferred_language, nms_context, stance_mode, positions
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]
    result = gateway.call_structured(_TASK, messages, RedlineOut, cache_prefix=_SYSTEM)
    result.alternatives = ladder.reconcile_alternatives(result.alternatives, positions)
    return result


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------


def _build_user_message(
    clause_text: str,
    flag: FlagDTO,
    preferred_language: str | None,
    nms_context: str,
    stance_mode: str,
    fallback_positions: list[RulePositionResponse],
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
    ]
    if fallback_positions:
        parts.append(
            "## Allowed fallback positions, in the order we concede them\n"
            "Produce exactly one alternative per rung below, in this same order. "
            "Adapt wording and defined terms to this contract only — do not change "
            "which position each rung represents, and do not add, drop, reorder or "
            "invent a rung."
        )
        for position in fallback_positions:
            parts.append(
                f"- Rung {position.rung} ({position.label}, {position.zone} zone): "
                f"{position.language}"
            )
        parts.append("")
    parts += [
        "## Negotiation context",
        f"Stance: {stance_mode}",
        nms_context,
    ]
    return "\n".join(parts)
