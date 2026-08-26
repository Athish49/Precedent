from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

_FAST_MODEL = "claude-haiku-4-5-20251001"
_SMART_MODEL = "claude-sonnet-4-6"

_TIER: dict[str, str] = {
    "fast": _FAST_MODEL,
    "smart": _SMART_MODEL,
}

# ---------------------------------------------------------------------------
# Task → tier mapping
#
# Tasks not listed here default to the "smart" tier.
# ---------------------------------------------------------------------------

_TASK_TIER: dict[str, str] = {
    # Fast / cheap tasks
    "chunk_classify": "fast",
    "entity_extract_simple": "fast",
    "section_label": "fast",
    "search.nl_to_filter": "fast",
    # Smart / complex tasks
    "clause_analysis": "smart",
    "risk_score": "smart",
    "contract_summary": "smart",
    "obligation_extract": "smart",
    "negotiation_suggest": "smart",
}


def get_model_for_task(task: str, settings: Settings | None = None) -> str:
    """Return the Anthropic model ID to use for *task*.

    Resolution order:
    1. ``settings.llm_tier_override`` if set — forces all tasks to one model.
    2. Task registry lookup (falls back to "smart" tier for unknown tasks).
    """
    if settings is not None and settings.llm_tier_override:
        return settings.llm_tier_override

    tier = _TASK_TIER.get(task, "smart")
    return _TIER[tier]
