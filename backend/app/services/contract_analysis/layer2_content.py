"""S2 Layer 2 — LLM content analysis (T-042; rewritten by task 4.4).

One ``call_structured`` per contract where the prompt fits the configured
size budget (``settings.layer2_max_prompt_chars``); when it does not, clauses
are split into multiple batches submitted together through
``gateway.call_batch`` — the Anthropic Message Batches API, the same
multi-item batching pattern ``services/playbook/bootstrap.py`` already uses
for its per-clause-type LLM calls — rather than N sequential
``call_structured`` calls.

For each clause, the model receives every resolved playbook rule sharing its
``clause_type`` (its "family" — ``rule_matcher.match_clauses_to_rules``) with
title, summary, positions (labels), parameters (extraction hints) and
semantic red-line tests, and returns one ``RuleExtractionOut`` per rule:
which position the clause text matches, extracted parameter values with a
verbatim quote, and a yes/no judgment with a quote for each semantic red
line. The model also still returns free-standing ``high_risk``/``vague``/
``inconsistent`` flags, unchanged in spirit from before task 4.4.

The model never assigns a zone. Each ``RuleExtractionOut`` is converted into
task 4.3's ``evaluator.ExtractedClause`` (``_build_extracted_clause``) and
handed to ``evaluate_finding`` to decide green/yellow/red, exactly like
``playbook_plan.md`` section 5.2 specifies — this module never computes a
zone itself. ``evaluator.py`` did not exist yet when this task started
(task 4.3 runs in parallel); it landed mid-task, so this integration is
against its real ``ExtractedClause``/``EvaluationResult`` shapes (see
``_build_extracted_clause`` and ``_extraction_to_flag``), not a guess.

The LLM still returns verbatim quotes, not positions; char offsets are
computed deterministically in code (``_locate_quote``), as before.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.llm import gateway
from app.core.llm.schemas.analysis import (
    ContractAnalysisOut,
    RuleExtractionOut,
    SemanticRedLineOut,
)
from app.schemas.playbook import RedLineResponse, ResolvedRule, RuleParameterResponse
from app.services.contract_analysis.evaluator import (
    EvaluationResult,
    ExtractedClause,
    evaluate_finding,
)
from app.services.contract_analysis.models import AnalysisFlag, ClauseRuleMatch
from app.services.playbook.routing import matches as context_matches

logger = logging.getLogger(__name__)

# ``{(clause_id, rule_id): {red_line_id, ...}}`` — rule-scope red lines
# Layer 1 already matched (``layer1_structural.rule_scope_red_line_hits``).
Layer1RedLineHits = dict[tuple[uuid.UUID, uuid.UUID], set[uuid.UUID]]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "core" / "llm" / "prompts"
_SYSTEM_OWN = (_PROMPTS_DIR / "analysis_own_paper.md").read_text()
_SYSTEM_COUNTERPARTY = (_PROMPTS_DIR / "analysis_counterparty.md").read_text()

# Registry task key — maps to "smart" tier (claude-sonnet-4-6). Shared by the
# single-call and batched paths, same as bootstrap.py's single task key.
_TASK = "clause_analysis"

# Zone -> severity (scoring.py's own severity_base table: low=1, medium=3,
# high=9 — a red finding must always dominate many green/yellow ones).
_ZONE_SEVERITY: dict[str, str] = {"red": "high", "yellow": "medium", "green": "low"}

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
    context: dict[str, Any] | None = None,
    global_red_lines: list[RedLineResponse] | None = None,
    *,
    layer1_red_line_hits: Layer1RedLineHits | None = None,
) -> list[AnalysisFlag]:
    """Run LLM content analysis and return flags for the contract.

    Args:
        contract_id: UUID of the contract being analysed.
        paper_origin: "own" or "counterparty" — selects the prompt and flag set.
        matches: Output of ``rule_matcher.match_clauses_to_rules`` — one entry
            per clause, each carrying every resolved rule in its clause-type
            family (``[]`` for an ungoverned clause).
        context: The contract's context dimensions (``deal_value_band``,
            ``regimes``, ...), forwarded to the zone evaluator for
            ``context_overrides`` on parameters (``playbook_plan.md`` section
            3.6), and (bug 2a fix) to ``_rule_block`` so a fallback position
            whose own ``conditions`` don't match this contract's context is
            not even offered to the model. Defaults to ``{}``.
        global_red_lines: Playbook- and global-scope red lines whose
            ``condition_type`` is ``semantic`` (bug 2b fix) —
            ``app.db.repositories.playbook_repo.list_red_lines_for_playbook``/
            ``list_global_red_lines``, pre-filtered to ``condition_type ==
            "semantic"`` by the caller. The deterministic (phrase/regex) ones
            at the same scopes are already handled by
            ``layer1_structural.run_layer1``; this is the semantic slice,
            checked once per contract (not once per clause) since a
            playbook/global red line is a document-wide condition. Defaults
            to ``[]``.
        layer1_red_line_hits: The Layer 1 -> Layer 2 join —
            ``layer1_structural.rule_scope_red_line_hits(layer1_flags)``,
            i.e. ``{(clause_id, rule_id): {red_line_id, ...}}`` for every
            rule-scope phrase/regex red line Layer 1 already matched. For
            such a clause+rule pair those red lines are folded into the
            evaluator's ``matched_red_lines`` (so ``evaluate_finding`` step 1
            decides red on them) and no Layer 2 flag is emitted for the pair
            — Layer 1's own ``prohibited`` flag is the finding. Defaults to
            no hits.

    Returns:
        List of AnalysisFlag instances (source="llm") for every issue found —
        both free-standing risk/vagueness flags and zone findings from
        matched rules.
    """
    if not matches:
        return []

    context = context or {}
    global_red_lines = global_red_lines or []
    hits = layer1_red_line_hits or {}
    if paper_origin == "own":
        return _run_own(contract_id, matches, context, global_red_lines, hits)
    return _run_counterparty(contract_id, matches, context, global_red_lines, hits)


# ---------------------------------------------------------------------------
# Own-paper / counterparty entry points
# ---------------------------------------------------------------------------


def _run_own(
    contract_id: uuid.UUID,
    matches: list[ClauseRuleMatch],
    context: dict[str, Any],
    global_red_lines: list[RedLineResponse],
    layer1_red_line_hits: Layer1RedLineHits | None = None,
) -> list[AnalysisFlag]:
    candidates = _find_inconsistency_candidates(matches)
    result = _call_llm(_SYSTEM_OWN, matches, candidates, context, global_red_lines)
    flags = _to_flags(contract_id, matches, result, "own", context, layer1_red_line_hits)
    flags.extend(_global_red_line_flags(contract_id, matches, result, global_red_lines))
    return flags


def _run_counterparty(
    contract_id: uuid.UUID,
    matches: list[ClauseRuleMatch],
    context: dict[str, Any],
    global_red_lines: list[RedLineResponse],
    layer1_red_line_hits: Layer1RedLineHits | None = None,
) -> list[AnalysisFlag]:
    result = _call_llm(
        _SYSTEM_COUNTERPARTY,
        matches,
        candidates=None,
        context=context,
        global_red_lines=global_red_lines,
    )
    flags = _to_flags(
        contract_id, matches, result, "counterparty", context, layer1_red_line_hits
    )
    flags.extend(_global_red_line_flags(contract_id, matches, result, global_red_lines))
    return flags


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _rule_block(rule: ResolvedRule, context: dict[str, Any] | None = None) -> str:
    """Render one resolved rule's title, summary, positions, parameters,
    semantic red-line tests and detection guidance for the prompt.

    Args:
        rule: The resolved rule to render.
        context: The contract's context dimensions (bug 2a fix). When given
            (non-empty), a ``fallback`` position whose own ``conditions`` is
            set and does not match *context* (``routing.matches``) is
            omitted entirely — that rung is not actually offered on this
            deal, so showing it to the model is an invitation to mismatch.
            When *context* is ``None``/empty, or a position has no
            ``conditions`` at all, rendering is unchanged from before this
            fix.
    """
    rule_key = rule.rule_key or str(rule.id)
    lines = [
        f"  Rule key: {rule_key}",
        f"  Issue: {rule.title or rule.clause_type}",
    ]
    if rule.position_summary:
        lines.append(f"  Summary: {rule.position_summary}")
    if rule.detection_guidance:
        lines.append(f"  Detection guidance: {rule.detection_guidance}")

    if rule.positions:
        lines.append("  Positions:")
        for p in rule.positions:
            conditions = getattr(p, "conditions", None)
            if (
                p.kind == "fallback"
                and conditions
                and context
                and not context_matches(conditions, context)
            ):
                # Context is known and this rung's own conditions don't match
                # it — not actually offered on this deal (bug 2a fix).
                continue
            rung_note = f" rung {p.rung}" if p.kind == "fallback" and p.rung is not None else ""
            desc = p.summary or (p.language[:160] if p.language else "")
            lines.append(f'    - [{p.kind}{rung_note}] "{p.label}": {desc}')

    if rule.parameters:
        lines.append("  Parameters:")
        for param in rule.parameters:
            unit = f" ({param.unit})" if param.unit else ""
            hint = param.extraction_hint or param.label
            allowed = getattr(param, "allowed_values", None)
            # Bug 1 fix: an enum/set_membership parameter's exact backend
            # token strings are unguessable from extraction_hint alone — spell
            # them out so the model echoes one of the real values instead of
            # a plausible-looking guess that zone_for_parameter can't resolve.
            allowed_note = (
                f" (use exactly one of: {', '.join(str(v) for v in allowed)})"
                if allowed
                else ""
            )
            lines.append(f"    - {param.key}{unit}: {hint}{allowed_note}")

    semantic_red_lines = [rl for rl in rule.red_lines if rl.condition_type == "semantic"]
    if semantic_red_lines:
        lines.append("  Semantic red lines:")
        for rl in semantic_red_lines:
            test = (rl.condition or {}).get("test") or rl.description
            lines.append(f"    - {rl.key}: {test}")

    return "\n".join(lines)


def _global_red_lines_block(global_red_lines: list[RedLineResponse]) -> str:
    """Render the contract-wide (playbook/global scope, ``semantic``) red-line
    checks for the prompt (bug 2b fix).

    Unlike a rule's own semantic red lines in ``_rule_block`` (checked per
    clause, against that rule's family only), these are not tied to any one
    clause — they're a document-wide condition (e.g. "governing law/venue
    falls outside the approved jurisdiction list") — so they are asked once
    per call, against every clause text that call's prompt included, using
    the same "key: test" rendering style ``_rule_block`` uses for a rule's
    own semantic red lines.
    """
    lines = [
        "---\nContract-wide red lines (playbook/global scope — read every "
        "clause above and decide, for the clauses as a whole, whether each "
        "is triggered anywhere in them; echo the exact key):"
    ]
    for rl in global_red_lines:
        test = (rl.condition or {}).get("test") or rl.description
        lines.append(f"    - {rl.key}: {test}")
    return "\n".join(lines)


def _clause_block(match: ClauseRuleMatch, context: dict[str, Any] | None = None) -> str:
    c = match.clause
    parts = [f"---\nClause ID: {c.id}\nType: {c.clause_type}"]
    if match.rules:
        parts.append(f"Resolved rules for this clause family ({len(match.rules)}):")
        parts.extend(_rule_block(rule, context) for rule in match.rules)
    else:
        parts.append(
            "Playbook rules: (none — this clause is ungoverned. Still assess it "
            "for high_risk and vague; do not produce rule_extractions for it.)"
        )
    parts.append(f"Clause text:\n{c.text}\n")
    return "\n".join(parts)


def _build_user_message(
    matches: list[ClauseRuleMatch],
    candidates: list[str] | None,
    context: dict[str, Any] | None = None,
    global_red_lines: list[RedLineResponse] | None = None,
) -> str:
    parts: list[str] = ["Analyze the following contract clauses.\n"]
    parts.extend(_clause_block(m, context) for m in matches)

    if candidates:
        parts.append(
            "---\nInconsistency candidates (terms that may be used differently "
            "across clauses — confirm or dismiss each):\n"
            + "\n".join(f"- {t}" for t in candidates)
        )

    if global_red_lines:
        parts.append(_global_red_lines_block(global_red_lines))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Batching (task 4.4 item 2): one call per contract where the prompt fits the
# configured size limit; otherwise split by clause into multiple batches and
# submit them together via gateway.call_batch, the same multi-item batching
# pattern services/playbook/bootstrap.py uses.
# ---------------------------------------------------------------------------


def _split_into_batches(
    matches: list[ClauseRuleMatch], max_chars: int
) -> list[list[ClauseRuleMatch]]:
    """Greedily group clauses so each batch's rendered blocks stay under
    *max_chars*. A single clause whose own block exceeds the budget still
    gets its own batch rather than being dropped."""
    batches: list[list[ClauseRuleMatch]] = []
    current: list[ClauseRuleMatch] = []
    current_len = 0

    for m in matches:
        block_len = len(_clause_block(m))
        if current and current_len + block_len > max_chars:
            batches.append(current)
            current = []
            current_len = 0
        current.append(m)
        current_len += block_len

    if current:
        batches.append(current)
    return batches


def _merge_global_red_lines(
    results: list[ContractAnalysisOut],
) -> list[SemanticRedLineOut]:
    """OR the per-batch document-level judgments together by ``red_line_key``
    (bug 2b fix).

    Each batch only sees a subset of the contract's clauses, so a red line
    whose triggering text lands in batch 2 is correctly reported "not
    triggered" by batch 1 — that is not a contradiction, just a batch that
    saw no evidence. A ``triggered=True`` from any batch must therefore win
    outright over a ``triggered=False`` from another; it is never acceptable
    for a later, evidence-free batch to silently clear an earlier true
    positive.
    """
    by_key: dict[str, SemanticRedLineOut] = {}
    for result in results:
        for rl in result.global_red_lines:
            existing = by_key.get(rl.red_line_key)
            if existing is None or (rl.triggered and not existing.triggered):
                by_key[rl.red_line_key] = rl
    return list(by_key.values())


def _call_llm(
    system_prompt: str,
    matches: list[ClauseRuleMatch],
    candidates: list[str] | None,
    context: dict[str, Any] | None = None,
    global_red_lines: list[RedLineResponse] | None = None,
) -> ContractAnalysisOut:
    """Run the content-analysis call for *matches*, splitting into multiple
    batched calls only when one call's prompt would exceed the configured
    size limit."""
    max_chars = get_settings().layer2_max_prompt_chars
    batches = _split_into_batches(matches, max_chars)

    if len(batches) <= 1:
        user_content = _build_user_message(matches, candidates, context, global_red_lines)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        return gateway.call_structured(
            _TASK, messages, ContractAnalysisOut, cache_prefix=system_prompt
        )

    logger.debug(
        "layer2 content analysis split into %d batches (max_chars=%d)",
        len(batches),
        max_chars,
    )
    items = [
        {
            "id": f"batch-{idx}",
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": _build_user_message(batch, candidates, context, global_red_lines),
                },
            ],
        }
        for idx, batch in enumerate(batches)
    ]
    batch_results: dict[str, ContractAnalysisOut] = gateway.call_batch(
        _TASK, items, ContractAnalysisOut, cache_prefix=system_prompt
    )

    merged_items = []
    batch_outputs: list[ContractAnalysisOut] = []
    for idx in range(len(batches)):
        result = batch_results.get(f"batch-{idx}")
        if result is not None:
            merged_items.extend(result.items)
            batch_outputs.append(result)
    return ContractAnalysisOut(
        items=merged_items, global_red_lines=_merge_global_red_lines(batch_outputs)
    )


# ---------------------------------------------------------------------------
# Inconsistency candidate extraction (own-paper only; unchanged by task 4.4)
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
# Zone evaluator integration (task 4.3). ``evaluator.py`` did not exist when
# this task started (4.3 runs in parallel) but landed before this task
# finished, so this is wired against its real ``ExtractedClause`` /
# ``EvaluationResult`` shapes rather than an assumed one.
# ---------------------------------------------------------------------------

# Numeric parameter values (value_type "number", "duration_days", "percent",
# "currency_usd") come back from the model as free text, e.g. "18 months" or
# "2x annual Fees" — evaluate_finding/zone_for_parameter compare against
# green_limit/yellow_limit numerically, so the leading number is pulled out
# here. The clause's wording is expected to use the same unit as the
# parameter's green_limit/yellow_limit (the parameter's extraction_hint is
# what tells the model which unit to read) — this module does not convert
# between units.
_NUMERIC_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _parse_parameter_value(parameter: RuleParameterResponse, raw: str) -> Any:
    """Parse a free-text extracted value into the type ``zone_for_parameter``
    compares against ``green_limit``/``yellow_limit`` for *parameter*.

    Unset/unparseable values return ``None`` rather than guessing — matching
    ``zone_for_parameter``'s own fail-safe-to-red behaviour on ``None``."""
    value_type = parameter.value_type
    if value_type in ("number", "duration_days", "percent", "currency_usd"):
        match = _NUMERIC_RE.search(raw.replace(",", ""))
        if match is None:
            return None
        num = float(match.group(0))
        return int(num) if num.is_integer() else num
    if value_type == "boolean":
        lowered = raw.strip().lower()
        if lowered in ("true", "yes", "y"):
            return True
        if lowered in ("false", "no", "n"):
            return False
        return None
    # "enum" (and anything else): prefer an exact case-insensitive match
    # against allowed_values so it compares equal to green_limit/yellow_limit
    # (set_membership/exact direction); fall back to the trimmed raw text.
    if parameter.allowed_values:
        lowered = raw.strip().lower()
        for allowed in parameter.allowed_values:
            if isinstance(allowed, str) and allowed.lower() == lowered:
                return allowed
    return raw.strip() or None


def _build_extracted_clause(rule: ResolvedRule, extraction: RuleExtractionOut) -> ExtractedClause:
    """Convert one ``RuleExtractionOut`` (the model's output) into the
    ``ExtractedClause`` ``evaluate_finding`` expects, resolving the model's
    text-based identifiers (``position_label``, ``red_line_key``,
    ``parameter_key``) back to the actual rows offered for *rule* — a
    label/key the model echoes that was not actually offered resolves to
    "not matched" rather than being trusted blindly."""
    matched_position = None
    if extraction.position.match_kind != "none" and extraction.position.position_label:
        matched_position = next(
            (p for p in rule.positions if p.label == extraction.position.position_label),
            None,
        )

    triggered_keys = {rl.red_line_key for rl in extraction.red_lines if rl.triggered}
    matched_red_lines = [
        rl
        for rl in rule.red_lines
        if rl.condition_type == "semantic" and rl.key in triggered_keys
    ]

    parameter_values: dict[str, Any] = {}
    params_by_key = {p.key: p for p in rule.parameters}
    for extracted_param in extraction.parameters:
        parameter = params_by_key.get(extracted_param.parameter_key)
        if parameter is None:
            continue
        parsed = _parse_parameter_value(parameter, extracted_param.value)
        if parsed is not None:
            parameter_values[extracted_param.parameter_key] = parsed

    return ExtractedClause(
        matched_red_lines=matched_red_lines,
        parameter_values=parameter_values,
        matched_position=matched_position,
    )


def _primary_quote(extraction: RuleExtractionOut, result: EvaluationResult) -> str | None:
    """Pick the quote backing whichever step of section 5.2's ladder decided
    *result* — the matched red line's quote, the breaching parameter's
    quote, or the position's quote (for a fallback match, or a step-5
    default_zone deviation with no red line/parameter/position at all)."""
    if result.red_line is not None:
        hit = next(
            (
                rl
                for rl in extraction.red_lines
                if rl.red_line_key == result.red_line.key and rl.triggered
            ),
            None,
        )
        if hit is not None and hit.quote:
            return hit.quote
    if result.parameter_key is not None:
        hit = next(
            (p for p in extraction.parameters if p.parameter_key == result.parameter_key),
            None,
        )
        if hit is not None and hit.quote:
            return hit.quote
    return extraction.position.quote


def _extraction_to_flag(
    contract_id: uuid.UUID,
    clause: Any,
    rule: ResolvedRule,
    extraction: RuleExtractionOut,
    paper_origin: str,
    context: dict[str, Any],
    layer1_red_line_ids: set[uuid.UUID] | None = None,
) -> AnalysisFlag | None:
    extracted_clause = _build_extracted_clause(rule, extraction)

    # Layer 1 -> Layer 2 join: a rule-scope phrase/regex red line Layer 1
    # already matched on this clause is a definitive red-line finding for
    # this clause+rule. Put it first in matched_red_lines so the evaluator's
    # step 1 decides on it (not on whatever the model said about positions),
    # then emit nothing — Layer 1's own "prohibited" flag is the record, and
    # a second Layer 2 flag would duplicate or contradict it.
    layer1_red_lines = (
        [rl for rl in rule.red_lines if rl.id in layer1_red_line_ids]
        if layer1_red_line_ids
        else []
    )
    if layer1_red_lines:
        extracted_clause = ExtractedClause(
            matched_red_lines=[*layer1_red_lines, *extracted_clause.matched_red_lines],
            parameter_values=extracted_clause.parameter_values,
            matched_position=extracted_clause.matched_position,
        )
    result = evaluate_finding(rule, extracted_clause, context)
    if result.red_line is not None and any(result.red_line is rl for rl in layer1_red_lines):
        return None

    # playbook_plan.md section 5.2 step 3 ("matches preferred or acceptable
    # variant -> no finding"): evaluate_finding still returns zone="green"
    # for this case (a valid, pre-approved outcome, not a sentinel), but it
    # is not a deviation worth a flag row.
    if result.position is not None and result.position.kind in (
        "preferred",
        "acceptable_variant",
    ):
        return None

    # A red-line match is "prohibited" (consistent with Layer 1's structural
    # phrase/regex red-line flags); a parameter breach, fallback match, or
    # step-5 default_zone deviation is a playbook deviation — "non_standard"
    # on our own paper, "deviation" on the counterparty's.
    flag_type = (
        "prohibited"
        if result.red_line is not None
        else ("non_standard" if paper_origin == "own" else "deviation")
    )
    quote = _primary_quote(extraction, result)
    char_start, char_end = _locate_quote(clause, quote or "")
    # EvaluationResult's own docstring: "parameter_values <- {parameter_key:
    # parameter_value}" — the one parameter that decided the zone, not every
    # extracted value (those that did not breach are not findings).
    parameter_values = (
        {result.parameter_key: result.parameter_value} if result.parameter_key else None
    )

    return AnalysisFlag(
        contract_id=contract_id,
        flag_type=flag_type,
        severity=_ZONE_SEVERITY.get(result.zone, "low"),
        source="llm",
        clause_type=clause.clause_type,
        clause_id=clause.id,
        char_start=char_start,
        char_end=char_end,
        detail={"reason": result.reason, "rule_key": extraction.rule_key},
        matched_rule_id=rule.id,
        rule_key=extraction.rule_key,
        zone=result.zone,
        position_id=result.position.id if result.position is not None else None,
        red_line_id=result.red_line.id if result.red_line is not None else None,
        parameter_values=parameter_values,
    )


# ---------------------------------------------------------------------------
# Output conversion
# ---------------------------------------------------------------------------


def _locate_quote(clause: Any, quote: str) -> tuple[int | None, int | None]:
    """Return contract-level char offsets for *quote* within clause text.

    Case-insensitive search; returns (None, None) if not found.
    """
    if not quote:
        return None, None
    idx = clause.text.lower().find(quote.lower())
    if idx == -1:
        return None, None
    return clause.char_start + idx, clause.char_start + idx + len(quote)


def _locate_quote_across_matches(
    matches: list[ClauseRuleMatch], quote: str
) -> tuple[uuid.UUID | None, str | None, int | None, int | None]:
    """Same lookup as ``_locate_quote``, but across every clause in the
    contract (bug 2b fix): a contract-wide red line's quote is not known in
    advance to belong to any one clause, unlike a rule-scoped extraction's
    quote. Returns ``(clause_id, clause_type, char_start, char_end)`` for the
    first clause the quote is found in, or all-``None`` if it is not found in
    any of them.
    """
    if not quote:
        return None, None, None, None
    for m in matches:
        char_start, char_end = _locate_quote(m.clause, quote)
        if char_start is not None:
            return m.clause.id, m.clause.clause_type, char_start, char_end
    return None, None, None, None


def _global_red_line_flags(
    contract_id: uuid.UUID,
    matches: list[ClauseRuleMatch],
    result: ContractAnalysisOut,
    global_red_lines: list[RedLineResponse],
) -> list[AnalysisFlag]:
    """Convert triggered contract-wide (playbook/global scope, ``semantic``)
    red-line judgments into ``AnalysisFlag`` rows (bug 2b fix).

    This is a document-level check (one judgment per red line per contract),
    unlike the rule-scoped semantic red lines ``_extraction_to_flag`` already
    handles per clause. Flags use the exact same shape
    ``layer1_structural._check_red_lines`` produces for its deterministic
    playbook/global red lines: ``flag_type="prohibited"``, ``zone="red"``
    (any matched red line is red — ``evaluate_finding``'s step 1 convention),
    and the same ``detail`` keys (``red_line_key``, ``red_line_scope``,
    ``action``), so these flow through ``scoring.py``/the gate exactly like
    a deterministic playbook/global red-line flag would.
    """
    if not global_red_lines:
        return []

    red_lines_by_key = {rl.key: rl for rl in global_red_lines}
    flags: list[AnalysisFlag] = []
    for item in result.global_red_lines:
        if not item.triggered:
            continue
        red_line = red_lines_by_key.get(item.red_line_key)
        if red_line is None:
            # The model echoed a key that was not offered for this contract
            # (hallucination) — ignore rather than mis-attribute, same guard
            # _to_flags uses for an unrecognized rule_key.
            continue

        quote = item.quote or ""
        clause_id, clause_type, char_start, char_end = _locate_quote_across_matches(
            matches, quote
        )
        detail: dict[str, Any] = {
            "red_line_key": red_line.key,
            "red_line_scope": red_line.scope,
            "action": red_line.action,
        }
        if quote:
            detail["matched_text"] = quote

        flags.append(
            AnalysisFlag(
                contract_id=contract_id,
                flag_type="prohibited",
                severity="high",
                source="llm",
                clause_type=clause_type or "",
                clause_id=clause_id,
                char_start=char_start,
                char_end=char_end,
                detail=detail,
                matched_rule_id=None,
                rule_key=None,
                zone="red",
                red_line_id=red_line.id,
            )
        )
    return flags


def _to_flags(
    contract_id: uuid.UUID,
    matches: list[ClauseRuleMatch],
    result: ContractAnalysisOut,
    paper_origin: str,
    context: dict[str, Any],
    layer1_red_line_hits: Layer1RedLineHits | None = None,
) -> list[AnalysisFlag]:
    """Convert LLM output items into AnalysisFlag instances.

    Each clause's ``rule_extractions`` are looked up against that *same*
    clause's own rule family (not any rule anywhere in the contract), so a
    model-echoed ``rule_key`` can only resolve to a rule actually offered for
    that clause.
    """
    match_by_clause_id = {str(m.clause.id): m for m in matches}
    flags: list[AnalysisFlag] = []

    for item in result.items:
        match = match_by_clause_id.get(item.clause_id)
        if match is None:
            continue
        clause = match.clause
        rules_by_key = {(r.rule_key or str(r.id)): r for r in match.rules}

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
                    matched_rule_id=None,
                )
            )

        for extraction in item.rule_extractions:
            rule = rules_by_key.get(extraction.rule_key)
            if rule is None:
                # Model echoed a rule_key that was not offered for this
                # clause (hallucination) — ignore rather than mis-attribute.
                continue
            flag = _extraction_to_flag(
                contract_id,
                clause,
                rule,
                extraction,
                paper_origin,
                context,
                (layer1_red_line_hits or {}).get((clause.id, rule.id)),
            )
            if flag is not None:
                flags.append(flag)

    return flags
