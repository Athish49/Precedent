"""S2 Layer 1 — deterministic structural analysis (T-040; task 4.3).

Two checks, no LLM:
  - missing-clause: required clause types absent from the contract, reported
    once per clause *family* (``clause_type``) even when several required
    rule_keys in that family are all missing (``playbook_plan.md`` section
    5.2: "A required rule with no matching clause is a `missing` finding").
  - red-line: clause text matches a ``phrase`` or ``regex`` red line at rule,
    playbook or global scope (task 4.3 item 1). This replaces the old
    ``prohibited_terms`` substring loop, which had no scoping and no
    negation handling (``playbook_status.md`` section 5).

Red lines whose ``condition_type`` is ``parameter`` or ``semantic`` are not
evaluated here: ``parameter`` conditions need an extracted structured value
(``evaluator.zone_for_parameter`` handles that, fed by Layer 2 — task 4.4),
and ``semantic`` conditions need an LLM judgement. All 12 of the seeded
global red lines (``authority.yaml``) are ``semantic``, so — on today's seed
content — the global scope here matches nothing yet; the mechanism is in
place for any ``phrase``/``regex`` global red line added later.

Negation guard (task 4.3 item 2): a phrase or regex match is discarded when
one of "not", "no", "nothing", "neither", "never", "without" appears earlier
in the same sentence, within 60 characters of the match. This is what makes
"Nothing in this Agreement shall impose unlimited liability..." stop
matching a red line written as "unlimited liability" — see
``playbook_status.md`` section 5 for the four probe sentences this guards.

Assumption: clause.text is the verbatim contract slice [char_start:char_end].
If segmentation normalises whitespace the citation offsets will drift; verify
against real segmentation output before trusting char_start/char_end in T-044.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence

from app.schemas.playbook import RedLineResponse, ResolvedRule
from app.services.contract_analysis.models import AnalysisFlag

# ---------------------------------------------------------------------------
# Negation guard (task 4.3 item 2)
# ---------------------------------------------------------------------------

_NEGATION_WORDS = ("not", "no", "nothing", "neither", "never", "without")
_NEGATION_RE = re.compile(r"\b(?:" + "|".join(_NEGATION_WORDS) + r")\b", re.IGNORECASE)
_NEGATION_GUARD_WINDOW = 60
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]")

# Red-line condition types this deterministic layer can evaluate without an
# LLM. ``parameter`` needs an extracted value (evaluator.py); ``semantic``
# needs a model judgement (Layer 2 / task 4.4).
_DETERMINISTIC_CONDITION_TYPES = frozenset({"phrase", "regex"})

_REGEX_FLAG_CHARS = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
}


def _sentence_start(text: str, pos: int) -> int:
    """Return the offset where the sentence containing *pos* begins.

    Scans for the last sentence-ending punctuation mark before *pos*; the
    sentence starts just after it (leading whitespace trimmed). With no such
    mark, the sentence starts at 0.
    """
    start = 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(text, 0, pos):
        start = m.end()
    while start < pos and text[start].isspace():
        start += 1
    return start


def negation_guard(text: str, match_start: int, window: int = _NEGATION_GUARD_WINDOW) -> bool:
    """Should a match at *match_start* in *text* be discarded as negated?

    True when one of the negation words appears earlier in the same
    sentence, within *window* characters of the match (task 4.3 item 2).
    """
    sentence_start = _sentence_start(text, match_start)
    window_start = max(sentence_start, match_start - window)
    preceding = text[window_start:match_start]
    return bool(_NEGATION_RE.search(preceding))


# ---------------------------------------------------------------------------
# Phrase / regex matching
# ---------------------------------------------------------------------------


def _compile_regex_flags(flag_letters: str) -> int:
    flags = 0
    for ch in flag_letters or "":
        flags |= _REGEX_FLAG_CHARS.get(ch, 0)
    return flags


def _find_red_line_matches(clause_text: str, red_line: RedLineResponse) -> list[re.Match]:
    """Every surviving (non-negated) match of *red_line* in *clause_text*.

    ``phrase`` conditions are ``{"any": [phrase, ...], "negation_guard": bool}``
    (default ``True``); ``regex`` conditions are
    ``{"pattern": <regex>, "flags": "<letters from imsx>"}`` and always run
    the guard, since the condition shape has no per-rule opt-out for it.
    """
    condition = red_line.condition or {}

    if red_line.condition_type == "phrase":
        phrases = [p for p in (condition.get("any") or []) if p]
        guard_enabled = condition.get("negation_guard", True)
        matches: list[re.Match] = []
        for phrase in phrases:
            for m in re.finditer(re.escape(phrase), clause_text, re.IGNORECASE):
                if guard_enabled and negation_guard(clause_text, m.start()):
                    continue
                matches.append(m)
        return matches

    if red_line.condition_type == "regex":
        pattern = condition.get("pattern")
        if not pattern:
            return []
        try:
            compiled = re.compile(pattern, _compile_regex_flags(condition.get("flags", "")))
        except re.error:
            return []
        return [
            m
            for m in compiled.finditer(clause_text)
            if not negation_guard(clause_text, m.start())
        ]

    # 'parameter' and 'semantic' conditions are not evaluated here.
    return []


def _normalise_families(
    resolved_rules: Mapping[str, ResolvedRule | Sequence[ResolvedRule]],
) -> dict[str, list[ResolvedRule]]:
    """Coerce *resolved_rules* to ``{clause_type: [every rule in that family]}``.

    The canonical input is one list per clause family (``service.analyze``
    builds it from every rule in ``resolved.rules``). A bare ``ResolvedRule``
    value (the old ``routing.rules_by_clause_type`` one-rule-per-family
    shape) is still accepted and treated as a one-rule family, so older
    callers and fixtures keep working.
    """
    families: dict[str, list[ResolvedRule]] = {}
    for clause_type, value in resolved_rules.items():
        if isinstance(value, (list, tuple)):
            families[clause_type] = list(value)
        else:
            families[clause_type] = [value]  # type: ignore[list-item]
    return families


def group_rules_by_clause_type(rules: Iterable[ResolvedRule]) -> dict[str, list[ResolvedRule]]:
    """Group *every* resolved rule by ``clause_type`` (one list per family),
    preserving input order (``resolved.rules`` is rule_key-sorted).

    Unlike ``routing.rules_by_clause_type``, nothing is collapsed: a family
    with several rule_keys keeps all of them, which is what both checks in
    this module need (task 4.3).
    """
    families: dict[str, list[ResolvedRule]] = {}
    for rule in rules:
        families.setdefault(rule.clause_type, []).append(rule)
    return families


def run_layer1(
    contract_id: uuid.UUID,
    clauses: list,
    resolved_rules: Mapping[str, ResolvedRule | Sequence[ResolvedRule]],
    playbook_red_lines: list[RedLineResponse] | None = None,
    global_red_lines: list[RedLineResponse] | None = None,
) -> list[AnalysisFlag]:
    """Run both structural checks and return the combined flag list.

    Args:
        contract_id:    UUID of the contract being analysed.
        clauses:        All Clause ORM objects for the contract.
        resolved_rules: Clause-type-keyed map of *every* resolved rule in each
                        clause family (``group_rules_by_clause_type``). A
                        bare ``ResolvedRule`` per key is still accepted as a
                        one-rule family (see ``_normalise_families``). Every
                        rule's own rule-scope red lines are checked against
                        every clause of its family.
        playbook_red_lines: Red lines with ``scope == "playbook"``
                        (``playbook_repo.list_red_lines_for_playbook``). A
                        playbook's red lines apply only when that playbook
                        contributed at least one rule to this resolution;
                        when it did, they are checked against *every* clause
                        in the contract (a playbook-scope red line is not
                        tied to any one clause family). Optional.
        global_red_lines: Red lines with ``scope == "global"``
                        (``playbook_repo.list_global_red_lines``). Checked
                        against every clause regardless of clause type, since
                        a global red line applies document-wide. Optional.

    Playbook- and global-scope hits are not attributed to any rule
    (``matched_rule_id``/``rule_key`` are ``None``); ``red_line_id`` and
    ``detail["red_line_scope"]`` identify them, the same shape
    ``layer2_content._global_red_line_flags`` uses for semantic ones.
    """
    families = _normalise_families(resolved_rules)
    flags: list[AnalysisFlag] = []
    flags.extend(_check_missing(contract_id, families, clauses))
    flags.extend(
        _check_red_lines(contract_id, clauses, families, playbook_red_lines, global_red_lines)
    )
    return flags


def rule_scope_red_line_hits(
    flags: Iterable[AnalysisFlag],
) -> dict[tuple[uuid.UUID, uuid.UUID], set[uuid.UUID]]:
    """``{(clause_id, rule_id): {red_line_id, ...}}`` for every rule-scope
    red-line flag Layer 1 produced.

    This is the Layer 1 -> Layer 2 join (``layer2_content.run_layer2``'s
    ``layer1_red_line_hits``): a clause+rule pair already decided red here
    is folded into the evaluator's ``matched_red_lines`` there, so Layer 2
    does not emit a second, possibly contradictory, flag for the same pair.
    Playbook/global-scope hits carry no rule and are deliberately excluded:
    they do not decide any one rule's zone.
    """
    hits: dict[tuple[uuid.UUID, uuid.UUID], set[uuid.UUID]] = {}
    for f in flags:
        if (
            f.flag_type != "prohibited"
            or f.clause_id is None
            or f.matched_rule_id is None
            or f.red_line_id is None
            or (f.detail or {}).get("red_line_scope") != "rule"
        ):
            continue
        hits.setdefault((f.clause_id, f.matched_rule_id), set()).add(f.red_line_id)
    return hits


# ---------------------------------------------------------------------------
# Missing-clause check
# ---------------------------------------------------------------------------


def _check_missing(
    contract_id: uuid.UUID,
    families: dict[str, list[ResolvedRule]],
    clauses: list,
) -> list[AnalysisFlag]:
    """Flag required clause families that are absent from the contract.

    A family is reported at most once (task 4.3 item 3), and only when it
    has at least one required rule and *none* of its rules is matched by a
    clause. Every rule in a family shares its ``clause_type``, so "no
    clause of that type is present" is exactly "all of its required rules
    are unmatched". The flag is attributed to the family's first required
    rule (rule_key order); every required rule_key is listed in
    ``detail["required_rule_keys"]``.

    Before this fix only the family's *first* rule (by rule_key) was seen,
    so a family whose first rule was optional but whose later rules were
    required was never reported missing at all.
    """
    present_types = {c.clause_type for c in clauses}
    flags: list[AnalysisFlag] = []
    for clause_type, family in families.items():
        if clause_type in present_types:
            continue
        required = [r for r in family if r.required]
        if not required:
            continue
        rule = required[0]
        flags.append(
            AnalysisFlag(
                contract_id=contract_id,
                flag_type="missing",
                severity="high",
                source="deterministic",
                clause_type=clause_type,
                clause_id=None,
                char_start=None,
                char_end=None,
                detail={
                    "playbook_rule_id": str(rule.id),
                    "required_rule_keys": [r.rule_key for r in required],
                },
                matched_rule_id=rule.id,
                rule_key=rule.rule_key,
                zone="red",
            )
        )
    return flags


# ---------------------------------------------------------------------------
# Red-line check (rule / playbook / global scope)
# ---------------------------------------------------------------------------


def _red_line_flag(
    contract_id: uuid.UUID,
    clause: object,
    red_line: RedLineResponse,
    scope: str,
    m: re.Match,
    rule: ResolvedRule | None,
) -> AnalysisFlag:
    text = clause.text  # type: ignore[attr-defined]
    return AnalysisFlag(
        contract_id=contract_id,
        flag_type="prohibited",
        severity="high",
        source="deterministic",
        clause_type=clause.clause_type,  # type: ignore[attr-defined]
        clause_id=clause.id,  # type: ignore[attr-defined]
        char_start=clause.char_start + m.start(),  # type: ignore[attr-defined]
        char_end=clause.char_start + m.end(),  # type: ignore[attr-defined]
        detail={
            "red_line_key": red_line.key,
            "red_line_scope": scope,
            "action": red_line.action,
            "matched_text": text[m.start() : m.end()],
            "clause_excerpt": text[max(0, m.start() - 50) : m.end() + 50],
        },
        matched_rule_id=rule.id if rule is not None else None,
        rule_key=rule.rule_key if rule is not None else None,
        zone="red",
        red_line_id=red_line.id,
    )


def _check_red_lines(
    contract_id: uuid.UUID,
    clauses: list,
    families: dict[str, list[ResolvedRule]],
    playbook_red_lines: list[RedLineResponse] | None,
    global_red_lines: list[RedLineResponse] | None,
) -> list[AnalysisFlag]:
    """Flag every surviving phrase/regex red-line match, at every scope.

    - Rule scope: every rule in the clause's family, each with its own red
      lines; a hit is attributed to the rule that owns the red line.
    - Playbook scope: red lines of any playbook that contributed a rule to
      this resolution, checked against every clause; unattributed to a rule.
    - Global scope: checked against every clause; unattributed to a rule.

    A red line object reachable through more than one path (e.g. the same
    row passed in twice) is only evaluated once per clause.
    """
    contributing_playbooks = {
        r.source_playbook_id for family in families.values() for r in family
    }
    scope_wide: list[tuple[str, RedLineResponse]] = []
    for rl in playbook_red_lines or []:
        if (
            rl.scope == "playbook"
            and rl.playbook_id is not None
            and rl.playbook_id in contributing_playbooks
            and rl.condition_type in _DETERMINISTIC_CONDITION_TYPES
        ):
            scope_wide.append(("playbook", rl))
    for rl in global_red_lines or []:
        if rl.scope == "global" and rl.condition_type in _DETERMINISTIC_CONDITION_TYPES:
            scope_wide.append(("global", rl))

    flags: list[AnalysisFlag] = []
    for clause in clauses:
        seen: set[object] = set()

        for rule in families.get(clause.clause_type, []):
            for red_line in rule.red_lines:
                if red_line.condition_type not in _DETERMINISTIC_CONDITION_TYPES:
                    continue
                if red_line.id in seen:
                    continue
                seen.add(red_line.id)
                for m in _find_red_line_matches(clause.text, red_line):
                    flags.append(_red_line_flag(contract_id, clause, red_line, "rule", m, rule))

        for scope, red_line in scope_wide:
            if red_line.id in seen:
                continue
            seen.add(red_line.id)
            for m in _find_red_line_matches(clause.text, red_line):
                flags.append(_red_line_flag(contract_id, clause, red_line, scope, m, None))
    return flags
