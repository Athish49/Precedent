"""S2 Layer 2 — LLM content analysis (T-042).

One ``call_structured`` per contract (all clauses in one prompt), mode-switched
by ``paper_origin``:

  own         → non_standard / high_risk / vague + confirm inconsistent
  counterparty → deviation / high_risk / vague (including ungoverned clauses)

The LLM returns verbatim ``offending_quote`` strings; char offsets are computed
deterministically in code to avoid relying on the model's unreliable position
arithmetic.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.core.llm import gateway
from app.core.llm.schemas.analysis import ContractAnalysisOut
from app.services.contract_analysis.models import AnalysisFlag, ClauseRuleMatch

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_SYSTEM_OWN = (_PROMPTS_DIR / "analysis_own_paper.md").read_text()
_SYSTEM_COUNTERPARTY = (_PROMPTS_DIR / "analysis_counterparty.md").read_text()

# Registry task key — maps to "smart" tier (claude-sonnet-4-6).
_TASK = "clause_analysis"

# Regex pre-filter: extract capitalized defined-term candidates from clause text.
# Matches runs of title-cased words (2–5 words) or single all-caps words (≥ 3 chars).
_DEFINED_TERM_RE = re.compile(
    r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}|[A-Z]{3,})\b"
)

# Common document words that match the pattern but are not defined terms.
_STOPWORDS = frozenset({
    "This", "The", "Each", "Any", "Such", "All", "No", "In", "On",
    "With", "By", "For", "And", "Or", "But", "If", "To", "Of", "At",
    "As", "An", "Be", "Is", "It", "Its", "From", "That", "These",
    "Those", "When", "Where", "Which", "Who", "Will", "Shall", "May",
    "Section", "Article", "Exhibit", "Schedule", "Appendix", "Agreement",
    "Party", "Parties", "Company", "Client", "Vendor", "Provider",
})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_layer2(
    contract_id: uuid.UUID,
    paper_origin: str,
    matches: list[ClauseRuleMatch],
) -> list[AnalysisFlag]:
    """Run LLM content analysis and return flags for the contract.

    Args:
        contract_id: UUID of the contract being analysed.
        paper_origin: "own" or "counterparty" — selects the prompt and flag set.
        matches: Output of T-041 rule_matcher — one entry per clause.

    Returns:
        List of AnalysisFlag instances (source="llm") for every issue found.
    """
    if not matches:
        return []

    if paper_origin == "own":
        return _run_own(contract_id, matches)
    return _run_counterparty(contract_id, matches)


# ---------------------------------------------------------------------------
# Own-paper path
# ---------------------------------------------------------------------------


def _run_own(
    contract_id: uuid.UUID,
    matches: list[ClauseRuleMatch],
) -> list[AnalysisFlag]:
    candidates = _find_inconsistency_candidates(matches)
    user_content = _build_own_user_message(matches, candidates)
    messages = [
        {"role": "system", "content": _SYSTEM_OWN},
        {"role": "user", "content": user_content},
    ]

    result: ContractAnalysisOut = gateway.call_structured(
        _TASK,
        messages,
        ContractAnalysisOut,
        cache_prefix=_SYSTEM_OWN,
    )
    return _to_flags(contract_id, matches, result)


def _build_own_user_message(
    matches: list[ClauseRuleMatch],
    candidates: list[str],
) -> str:
    parts: list[str] = ["Analyze the following contract clauses.\n"]

    for m in matches:
        c = m.clause
        parts.append(f"---\nClause ID: {c.id}\nType: {c.clause_type}")
        if m.rule:
            rule = m.rule
            parts.append(f"Playbook preferred language: {rule.preferred_language or '(none)'}")
            if rule.acceptable_variations:
                joined = "; ".join(rule.acceptable_variations)
                parts.append(f"Acceptable variations: {joined}")
        else:
            parts.append("Playbook rule: (none — assess freely for high_risk and vague)")
        parts.append(f"Clause text:\n{c.text}\n")

    if candidates:
        parts.append(
            "---\nInconsistency candidates (terms that may be used differently "
            "across clauses — confirm or dismiss each):\n"
            + "\n".join(f"- {t}" for t in candidates)
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Counterparty path
# ---------------------------------------------------------------------------


def _run_counterparty(
    contract_id: uuid.UUID,
    matches: list[ClauseRuleMatch],
) -> list[AnalysisFlag]:
    user_content = _build_counterparty_user_message(matches)
    messages = [
        {"role": "system", "content": _SYSTEM_COUNTERPARTY},
        {"role": "user", "content": user_content},
    ]

    result: ContractAnalysisOut = gateway.call_structured(
        _TASK,
        messages,
        ContractAnalysisOut,
        cache_prefix=_SYSTEM_COUNTERPARTY,
    )
    return _to_flags(contract_id, matches, result)


def _build_counterparty_user_message(matches: list[ClauseRuleMatch]) -> str:
    parts: list[str] = ["Analyze the following contract clauses.\n"]

    for m in matches:
        c = m.clause
        parts.append(f"---\nClause ID: {c.id}\nType: {c.clause_type}")
        if m.rule:
            rule = m.rule
            parts.append(f"Playbook preferred language: {rule.preferred_language or '(none)'}")
            if rule.acceptable_variations:
                joined = "; ".join(rule.acceptable_variations)
                parts.append(f"Acceptable variations: {joined}")
        else:
            parts.append(
                "Playbook rule: (none — assess for high_risk and vague only; "
                "deviation flag must NOT be raised)"
            )
        parts.append(f"Clause text:\n{c.text}\n")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Inconsistency candidate extraction
# ---------------------------------------------------------------------------


def _find_inconsistency_candidates(matches: list[ClauseRuleMatch]) -> list[str]:
    """Return terms that appear in some but not all clauses — potential inconsistencies.

    Extracts capitalized multi-word phrases and all-caps abbreviations from
    clause texts, then surfaces those present in fewer than half the clauses.
    The LLM receives these as candidates to confirm.
    """
    from collections import Counter

    term_counts: Counter[str] = Counter()
    for m in matches:
        # Deduplicate within a clause — count clause presence, not occurrences.
        seen = set()
        for hit in _DEFINED_TERM_RE.finditer(m.clause.text):
            term = hit.group(0)
            if term not in _STOPWORDS and len(term) > 3 and term not in seen:
                seen.add(term)
                term_counts[term] += 1

    total = len(matches)
    threshold = max(2, total // 2)

    # Surface terms that appear in some (1+) but fewer than half the clauses.
    candidates = [
        term for term, count in term_counts.items() if 1 <= count < threshold
    ]
    # Prioritise terms that appear most (more likely to be real defined terms).
    candidates.sort(key=lambda t: -term_counts[t])
    return candidates[:20]


# ---------------------------------------------------------------------------
# Output conversion
# ---------------------------------------------------------------------------


def _locate_quote(clause, quote: str) -> tuple[int | None, int | None]:
    """Return contract-level char offsets for *quote* within clause text.

    Case-insensitive search; returns (None, None) if not found.
    """
    if not quote:
        return None, None
    idx = clause.text.lower().find(quote.lower())
    if idx == -1:
        return None, None
    return clause.char_start + idx, clause.char_start + idx + len(quote)


def _to_flags(
    contract_id: uuid.UUID,
    matches: list[ClauseRuleMatch],
    result: ContractAnalysisOut,
) -> list[AnalysisFlag]:
    """Convert LLM output items into AnalysisFlag instances."""
    clause_by_id = {str(m.clause.id): m for m in matches}
    flags: list[AnalysisFlag] = []

    for item in result.items:
        match = clause_by_id.get(item.clause_id)
        if match is None:
            continue
        clause = match.clause
        rule = match.rule

        for llm_flag in item.flags:
            char_start, char_end = _locate_quote(clause, llm_flag.offending_quote or "")
            flags.append(
                AnalysisFlag(
                    contract_id=contract_id,
                    flag_type=llm_flag.flag_type,
                    severity=llm_flag.severity,
                    source="llm",
                    clause_type=clause.clause_type,
                    clause_id=clause.id,
                    char_start=char_start,
                    char_end=char_end,
                    detail={"explanation": llm_flag.detail},
                    matched_rule_id=rule.id if rule else None,
                )
            )

    return flags
