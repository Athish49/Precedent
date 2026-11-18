"""Zone evaluator (task 4.3; ``playbook_plan.md`` section 5.2).

Pure functions — no I/O, no LLM calls — that decide the zone (green/yellow/
red, or "no finding") of one extracted finding against one resolved rule.
Layer 1 (``layer1_structural.py``) and Layer 2 (LLM content extraction, task
4.4) both produce the raw material this module turns into a zone; neither
layer assigns the zone itself (task 4.4's "Done when": "the model never
assigns the zone").

Section 5.2's ladder, in order — the first matching step decides:

    1. A red line matches -> red.
    2. A parameter is beyond yellow_limit -> red; beyond green_limit -> yellow.
    3. The text matches the preferred position or an acceptable variant -> no finding.
    4. The text matches a fallback rung -> that rung's zone.
    5. Otherwise -> a deviation in the rule's default_zone.

Step 3 is "no finding", not "a green finding": a clause that matches the
preferred position produces no flag at all, so ``evaluate_finding`` returns
``zone="none"`` for it (``layer2_content._extraction_to_flag`` treats a
falsy/``"none"`` zone as "nothing to persist").

Combining step 2 and steps 3/4 for the *same* clause
------------------------------------------------------
Section 5.2 is written as a clean ladder assuming one signal per clause, but
a real (or test-case) extraction can legitimately produce both a parameter
value (step 2) *and* a matched fallback position (step 4) for the same rule
at once — e.g. "liability cap: 30 months" extracted as a parameter while the
text also happens to match the rule's "Fallback 2" rung. The ladder's literal
"first match decides" reading would let step 2 win outright and silently
drop the matched position (and its rung/position_id) from the result, even
when the position match was the more informative signal to report and the
zones agree. ``playbook_plan.md`` section 5.2 does not address this
combination explicitly, so ``evaluate_finding`` resolves it like this: when
both a parameter breach (yellow/red) and a matched **fallback** position are
present, it reports the fallback's ``position``/``position_id`` (so callers
can recover which rung matched) together with the **worse** of the
parameter's zone and the fallback's own declared zone — a parameter's red
verdict is never silently downgraded just because a fallback rung happens to
be labelled green, but a correctly-matched rung is also never discarded just
because a parameter also fired. ``parameter_key``/``parameter_value`` are
kept too, so this is the one case where more than one of
``red_line_id``/``position_id``/``parameter_key`` can be set at once.

This combination is deliberately *not* extended to the preferred/
acceptable-variant positions (step 3): those mean "no finding" regardless of
zone, and ``layer2_content._extraction_to_flag`` uses
``result.position.kind in ("preferred", "acceptable_variant")`` to suppress
the flag entirely whenever a position of that kind comes back — attaching
such a position to a result whose zone is actually yellow/red (from a
parameter breach) would make that real deviation vanish instead of being
reported. A parameter breach alongside a preferred/acceptable-variant match
therefore still behaves exactly as before: the parameter wins outright and
the position is dropped from the result.

Parameter-condition red lines (step 1, before the ladder runs)
----------------------------------------------------------------
``RedLine.condition_type`` can be ``"phrase"``, ``"regex"``, ``"semantic"``,
or ``"parameter"``. The first three are populated into
``ExtractedClause.matched_red_lines`` upstream -- Layer 1's deterministic
check for ``"phrase"``/``"regex"``, Layer 2's LLM prompt for
``"semantic"`` -- before ``evaluate_finding`` ever sees them. Nobody
upstream evaluates a ``"parameter"``-condition red line (Layer 1's
deterministic check does not handle that ``condition_type``, and Layer 2's
prompt never surfaces parameter-condition red lines to the model at all),
so ``evaluate_finding`` evaluates them itself, right before step 1 runs:
for each of *rule*'s red lines with ``condition_type == "parameter"``, its
``condition`` (``{parameter_key, op, value}``) is checked against
``extracted.parameter_values.get(parameter_key)`` (see
``_derive_parameter_red_line_matches``), and any that match are merged into
``extracted.matched_red_lines`` (appended, not replacing what Layer
1/Layer 2 already populated) so step 1's existing logic resolves the
correct ``red_line_id``/description/action/approver_role exactly as it
would for a phrase/regex/semantic match. For a comparison op, a parameter
key the extraction doesn't have at all is "cannot evaluate", not
"matches". The presence ops ``is_absent``/``is_present`` are evaluated
against whether the key was extracted (see
``_derive_parameter_red_line_matches`` for the guards).

How Layer 1's phrase/regex hits reach this function: ``service.analyze``
collects Layer 1's rule-scope red-line flags per (clause, rule)
(``layer1_structural.rule_scope_red_line_hits``) and hands them to
``layer2_content.run_layer2``, whose ``_extraction_to_flag`` puts those red
lines first in ``matched_red_lines`` before calling ``evaluate_finding``.
Step 1 therefore resolves to the Layer 1 red line, and Layer 2 emits no
flag of its own for that clause+rule (Layer 1's flag already records it),
instead of a second, possibly contradictory, fallback/deviation flag.

Two calling conventions for ``extracted``
------------------------------------------
This module's own tests and any other Layer-1-style caller can pass an
``ExtractedClause`` directly: the matched red lines, parameter values and
matched position, each a real object with a stable identity.

Layer 2 (task 4.4, ``layer2_content.py``) was built in parallel against a
plain-dict shape mirroring the LLM extraction schema instead — the model
only echoes a position's *label* and a red line's *key*, not any id — so
``evaluate_finding`` also accepts that dict shape and resolves it against
*rule*'s own positions/red_lines/parameters by label/key (see
``_extracted_from_dict``). Either input ends up normalised to an
``ExtractedClause`` before the ladder runs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.schemas.playbook import (
    RedLineResponse,
    ResolvedRule,
    RuleParameterResponse,
    RulePositionResponse,
)
from app.services.playbook.routing import matches

# ---------------------------------------------------------------------------
# Input / output shapes
# ---------------------------------------------------------------------------


@dataclass
class ExtractedClause:
    """What was found when one clause was checked against one resolved rule.

    ``matched_red_lines``: red lines that fired for this clause (from Layer
    1's phrase/regex matching and/or Layer 2's semantic red-line tests), in
    no particular priority order — ``evaluate_finding`` only looks at
    whether the list is non-empty, per section 5.2 step 1 ("A red line
    matches -> red": any match is enough).
    ``parameter_values``: extracted value per ``RuleParameter.key`` that was
    found in the clause text.
    ``matched_position``: the single best-matching position (preferred, an
    acceptable variant, or a fallback rung), or ``None`` if the text matches
    none of the rule's positions.
    """

    matched_red_lines: list[Any] = field(default_factory=list)
    parameter_values: dict[str, Any] = field(default_factory=dict)
    matched_position: Any | None = None


@dataclass
class EvaluationResult:
    """The zone for one finding, plus what decided it and why.

    ``zone`` is ``"green"``, ``"yellow"``, ``"red"``, or ``"none"`` (step 3:
    no finding — the preferred/acceptable-variant case). Usually at most one
    of ``red_line_id``/``position_id``/``parameter_key`` is set, matching
    whichever ladder step decided — the one exception is a parameter breach
    combined with a matched *fallback* position on the same clause, where
    both ``position_id`` and ``parameter_key`` are set together (see the
    module docstring's "Combining step 2 and steps 3/4" section). These are
    exactly the ``flag`` table's
    new columns (task 4.3 item 5; task 1.3's migration 012):
    ``zone`` <- ``zone``, ``red_line_id`` <- ``red_line_id``,
    ``position_id`` <- ``position_id``,
    ``parameter_values`` <- ``{parameter_key: parameter_value}``.

    ``red_line``/``position`` carry the full matched object (when the
    caller supplied one with an ``id`` to resolve), for callers that want
    more than the bare id.
    """

    zone: str
    reason: str
    position_id: uuid.UUID | None = None
    red_line_id: uuid.UUID | None = None
    parameter_key: str | None = None
    parameter_value: Any = None
    red_line: RedLineResponse | None = None
    position: RulePositionResponse | None = None


# ---------------------------------------------------------------------------
# Normalising the Layer-2-shaped dict into an ExtractedClause
# ---------------------------------------------------------------------------


def _extracted_from_dict(rule: ResolvedRule, payload: dict[str, Any]) -> ExtractedClause:
    """Build an ``ExtractedClause`` from the LLM-extraction-shaped dict.

    The shape ``layer2_content._extracted_payload`` builds from one
    ``RuleExtractionOut``::

        {
            "position": {"match_kind": ..., "position_label": ..., "quote": ...},
            "parameters": {parameter_key: {"value": ..., "quote": ...}, ...},
            "red_lines": {red_line_key: {"triggered": bool, "quote": ...}, ...},
        }

    The model only echoes a position's ``label`` and a red line's ``key``
    (``core/llm/schemas/analysis.py``'s docstrings: "it is how
    evaluate_finding looks up the matched rule_position row"), so this
    resolves both against *rule*'s own ``positions``/``red_lines`` lists to
    recover their real ids.
    """
    position_payload = payload.get("position") or {}
    match_kind = position_payload.get("match_kind")
    label = position_payload.get("position_label")

    matched_position = None
    if label:
        matched_position = next(
            (p for p in rule.positions if getattr(p, "label", None) == label), None
        )
    if matched_position is None and match_kind and match_kind != "none":
        matched_position = next(
            (p for p in rule.positions if getattr(p, "kind", None) == match_kind), None
        )

    parameter_values = {
        key: entry.get("value")
        for key, entry in (payload.get("parameters") or {}).items()
        if entry is not None
    }

    matched_red_lines = [
        red_line
        for key, entry in (payload.get("red_lines") or {}).items()
        if entry and entry.get("triggered")
        for red_line in (next((rl for rl in rule.red_lines if rl.key == key), None),)
        if red_line is not None
    ]

    return ExtractedClause(
        matched_red_lines=matched_red_lines,
        parameter_values=parameter_values,
        matched_position=matched_position,
    )


# ---------------------------------------------------------------------------
# Parameter-type red lines
# ---------------------------------------------------------------------------
#
# Neither Layer 1 (phrase/regex only) nor Layer 2 (semantic only) ever
# evaluates a red line whose ``condition_type`` is ``"parameter"`` against
# the extracted parameter values, so those red lines never land in
# ``ExtractedClause.matched_red_lines`` on their own. ``evaluate_finding``
# derives them itself, right before step 1 of the ladder runs, from
# *rule*'s own ``red_lines`` and the already-extracted
# ``parameter_values`` -- see that function for how the derived matches are
# merged in.

_PARAMETER_CONDITION_OPS: dict[str, Any] = {
    "eq": lambda actual, expected: actual == expected,
    "ne": lambda actual, expected: actual != expected,
    "gt": lambda actual, expected: actual > expected,
    "gte": lambda actual, expected: actual >= expected,
    "lt": lambda actual, expected: actual < expected,
    "lte": lambda actual, expected: actual <= expected,
    "in": lambda actual, expected: actual in expected,
    "not_in": lambda actual, expected: actual not in expected,
}

# Ops that test whether the parameter was extracted at all, not its value
# (``seed/playbooks/models.py``'s ``OPS_WITHOUT_VALUE``).
_PRESENCE_OPS = frozenset({"is_absent", "is_present"})

# Sentinel for "this parameter was not extracted for this clause".
_ABSENT = object()


def _parameter_condition_matches(condition: dict[str, Any], actual: Any = _ABSENT) -> bool:
    """Evaluate one ``condition_type: "parameter"`` red line's ``condition``
    dict (``{parameter_key, op, value?}``) against an extracted parameter
    value, or against its absence (``actual`` left as ``_ABSENT``).

    - ``is_absent``: true when the parameter was *not* extracted for the
      clause (``playbook_plan.md`` section 3.7's canonical example,
      ``{"parameter_key": "cap_multiple_months", "op": "is_absent"}``);
      false when a value was found.
    - ``is_present``: the reverse.
    - Comparisons (``eq``, ``ne``, ``gt``, ``gte``, ``lt``, ``lte``, ``in``,
      ``not_in``): need a value, so an absent parameter is "cannot
      evaluate" and never matches. An unknown ``op`` never matches either.
    """
    op = condition.get("op")
    if op == "is_absent":
        return actual is _ABSENT
    if op == "is_present":
        return actual is not _ABSENT
    if actual is _ABSENT:
        return False
    comparator = _PARAMETER_CONDITION_OPS.get(op)
    if comparator is None:
        return False
    try:
        return bool(comparator(actual, condition.get("value")))
    except TypeError:
        return False


def _extraction_is_empty(extracted: ExtractedClause) -> bool:
    """Nothing at all was extracted: no position, no parameter, no red line."""
    return (
        extracted.matched_position is None
        and not extracted.parameter_values
        and not extracted.matched_red_lines
    )


def _derive_parameter_red_line_matches(
    rule: ResolvedRule, extracted: ExtractedClause
) -> list[Any]:
    """Red lines from *rule* whose ``condition_type`` is ``"parameter"`` and
    whose ``condition`` matches *extracted*'s parameter values.

    Comparison ops: a parameter key missing from
    ``extracted.parameter_values`` is "cannot evaluate", not "matches" --
    this deliberately does *not* fail safe to a match the way
    ``zone_for_parameter`` fails safe to red.

    Presence ops (``is_absent``/``is_present``) are evaluated against
    whether the key was extracted, with two guards so ``is_absent`` cannot
    fire indiscriminately:

    - the rule must itself declare ``parameter_key`` among its
      ``parameters`` (otherwise the model was never asked to extract it,
      so its absence says nothing);
    - the extraction must not be completely empty (no position, no
      parameter, no red line). A completely empty extraction means the
      clause does not engage with this rule at all -- a sibling clause in
      the same family, or the family being absent entirely, which the
      missing-clause check owns (``layer1_structural._check_missing``;
      ``playbook/testing.py``'s ``_missing_result`` simulates exactly that
      with an empty ``ExtractedClause``, and the seed's ``missing`` test
      cases for rules carrying an ``is_absent`` red line expect a yellow
      deviation, not that red line).
    """
    declared_keys = {
        getattr(p, "key", None) for p in (getattr(rule, "parameters", None) or [])
    }
    empty = _extraction_is_empty(extracted)
    matches: list[Any] = []
    for red_line in getattr(rule, "red_lines", None) or []:
        if getattr(red_line, "condition_type", None) != "parameter":
            continue
        condition = getattr(red_line, "condition", None) or {}
        parameter_key = condition.get("parameter_key")
        if parameter_key is None:
            continue
        if condition.get("op") in _PRESENCE_OPS:
            if empty or parameter_key not in declared_keys:
                continue
            actual = extracted.parameter_values.get(parameter_key, _ABSENT)
        else:
            if parameter_key not in extracted.parameter_values:
                continue
            actual = extracted.parameter_values[parameter_key]
        if _parameter_condition_matches(condition, actual):
            matches.append(red_line)
    return matches


# ---------------------------------------------------------------------------
# zone_for_parameter
# ---------------------------------------------------------------------------


def _effective_limits(
    parameter: RuleParameterResponse, context: dict[str, Any]
) -> tuple[Any, Any, Any]:
    """Apply any ``context_overrides`` entry whose ``when`` matches *context*.

    ``context_overrides`` is a list of ``{when, preferred_value?, green_limit?,
    yellow_limit?, allowed_values?}`` objects (``playbook_plan.md`` section
    3.6; see ``seed/playbooks/models.py::ParameterOverride``). Overrides are
    applied in list order, each one overwriting only the fields it sets, so
    a later matching override wins over an earlier one on any field they
    both touch.
    """
    green_limit = getattr(parameter, "green_limit", None)
    yellow_limit = getattr(parameter, "yellow_limit", None)
    allowed_values = getattr(parameter, "allowed_values", None)

    overrides = getattr(parameter, "context_overrides", None) or []
    if isinstance(overrides, dict):
        overrides = [overrides]

    for override in overrides:
        if not isinstance(override, dict):
            continue
        if not matches(override.get("when"), context):
            continue
        if override.get("green_limit") is not None:
            green_limit = override["green_limit"]
        if override.get("yellow_limit") is not None:
            yellow_limit = override["yellow_limit"]
        if override.get("allowed_values") is not None:
            allowed_values = override["allowed_values"]

    return green_limit, yellow_limit, allowed_values


def zone_for_parameter(
    parameter: RuleParameterResponse,
    value: Any,
    context: dict[str, Any] | None = None,
) -> str:
    """Zone for one extracted parameter value (``playbook_plan.md`` 5.2 step 2).

    Applies ``parameter.direction`` against the effective ``green_limit``/
    ``yellow_limit`` (after any matching ``context_overrides``):

    - ``lower_is_better`` (smaller is safer, e.g. a liability cap in months):
      green when ``value <= green_limit``, yellow when ``value <= yellow_limit``,
      red otherwise.
    - ``higher_is_better`` (bigger is safer, e.g. an uptime percentage):
      green when ``value >= green_limit``, yellow when ``value >= yellow_limit``,
      red otherwise.
    - ``set_membership`` (e.g. a governing-law jurisdiction bucket):
      green when ``value`` is in the (list-valued) ``green_limit``, yellow
      when it is in ``yellow_limit``, red otherwise.
    - ``exact``: green when ``value`` equals ``green_limit`` (or
      ``preferred_value`` when no ``green_limit`` is set), yellow when it
      equals ``yellow_limit``, red otherwise.

    A missing limit on a given rung is treated as "this rung is not
    reachable" rather than "anything passes" — e.g. a parameter with only
    ``yellow_limit`` set has no green zone at all. An unset value, or a
    direction this function does not recognise, fails safe to red: a
    playbook gate is a compliance control, and silently waving an
    unassessable value through as green would defeat it.
    """
    if value is None:
        return "red"

    context = context or {}
    green_limit, yellow_limit, _allowed_values = _effective_limits(parameter, context)
    direction = getattr(parameter, "direction", None)

    if direction == "lower_is_better":
        if green_limit is not None and value <= green_limit:
            return "green"
        if yellow_limit is not None and value <= yellow_limit:
            return "yellow"
        return "red"

    if direction == "higher_is_better":
        if green_limit is not None and value >= green_limit:
            return "green"
        if yellow_limit is not None and value >= yellow_limit:
            return "yellow"
        return "red"

    if direction == "set_membership":
        green_set = (
            green_limit
            if isinstance(green_limit, (list, tuple, set))
            else ([green_limit] if green_limit is not None else [])
        )
        yellow_set = (
            yellow_limit
            if isinstance(yellow_limit, (list, tuple, set))
            else ([yellow_limit] if yellow_limit is not None else [])
        )
        if value in green_set:
            return "green"
        if value in yellow_set:
            return "yellow"
        return "red"

    if direction == "exact":
        preferred_value = getattr(parameter, "preferred_value", None)
        green_target = green_limit if green_limit is not None else preferred_value
        if green_target is not None and value == green_target:
            return "green"
        if yellow_limit is not None and value == yellow_limit:
            return "yellow"
        return "red"

    return "red"


# ---------------------------------------------------------------------------
# evaluate_finding
# ---------------------------------------------------------------------------

# Severity ordering used only to reconcile a step-2 parameter result with a
# step-4 fallback-position result for the same clause (see the module
# docstring). "none" (a preferred/acceptable-variant "no finding") is lower
# than "green" so that an actual finding is never treated as better than no
# finding at all; this ranking never otherwise decides a zone on its own.
_ZONE_RANK = {"none": -1, "green": 0, "yellow": 1, "red": 2}


def evaluate_finding(
    rule: ResolvedRule,
    extracted: ExtractedClause | dict[str, Any],
    context: dict[str, Any] | None = None,
) -> EvaluationResult:
    """Zone for one clause against one rule (``playbook_plan.md`` section 5.2).

    *extracted* is either an ``ExtractedClause`` or the Layer-2-shaped dict
    ``_extracted_from_dict`` understands (see the module docstring). Before
    the ladder runs, any of *rule*'s ``condition_type == "parameter"`` red
    lines that match the extracted parameter values are merged into
    *extracted*'s matched red lines (see the module docstring's
    "Parameter-condition red lines" section).

    Walks the five-step ladder and returns at the first step that decides:
    any matched red line is red; else the worst zone among the rule's
    parameters that were extracted; else "no finding" for a
    preferred/acceptable-variant match, or the matched fallback position's
    own zone; else a deviation in ``rule.default_zone`` (falling back to red
    if the rule has none, for the same fail-safe reason as
    ``zone_for_parameter``). When a parameter breach *and* a matched
    fallback position both apply to the same clause, see the module
    docstring's "Combining step 2 and steps 3/4" section for how the two are
    reconciled instead of the parameter silently winning outright.
    """
    context = context or {}
    if isinstance(extracted, dict):
        extracted = _extracted_from_dict(rule, extracted)

    # Before step 1: derive matches for "parameter"-condition red lines
    # (neither Layer 1 nor Layer 2 ever evaluates these -- see
    # ``_derive_parameter_red_line_matches``) and merge them in, so step 1
    # below picks them up exactly like any other matched red line.
    parameter_red_line_matches = _derive_parameter_red_line_matches(rule, extracted)
    if parameter_red_line_matches:
        extracted = ExtractedClause(
            matched_red_lines=[*extracted.matched_red_lines, *parameter_red_line_matches],
            parameter_values=extracted.parameter_values,
            matched_position=extracted.matched_position,
        )

    # Step 1: a red line matches -> red.
    if extracted.matched_red_lines:
        red_line = extracted.matched_red_lines[0]
        return EvaluationResult(
            zone="red",
            reason=f"Matched red line '{red_line.key}': {red_line.description}",
            red_line_id=getattr(red_line, "id", None),
            red_line=red_line,
        )

    # Step 2: a parameter beyond yellow_limit -> red; beyond green_limit -> yellow.
    # Red on a parameter short-circuits the parameter scan immediately;
    # yellow is remembered in case a later parameter is worse (red), but the
    # first yellow found is kept if nothing beats it. The result is held
    # rather than returned immediately so steps 3/4 below can still inspect
    # the matched position and reconcile it with this result (see the module
    # docstring's "Combining step 2 and steps 3/4" section) instead of it
    # being silently discarded.
    worst_yellow: EvaluationResult | None = None
    param_result: EvaluationResult | None = None
    for parameter in rule.parameters:
        key = getattr(parameter, "key", None)
        if key is None or key not in extracted.parameter_values:
            continue
        value = extracted.parameter_values[key]
        zone = zone_for_parameter(parameter, value, context)
        if zone == "red":
            label = getattr(parameter, "label", key)
            param_result = EvaluationResult(
                zone="red",
                reason=f"Parameter '{label}' value {value!r} is beyond the yellow limit",
                parameter_key=key,
                parameter_value=value,
            )
            break
        if zone == "yellow" and worst_yellow is None:
            label = getattr(parameter, "label", key)
            worst_yellow = EvaluationResult(
                zone="yellow",
                reason=f"Parameter '{label}' value {value!r} is beyond the green limit",
                parameter_key=key,
                parameter_value=value,
            )
    if param_result is None:
        param_result = worst_yellow

    # Steps 3/4: the matched position decides.
    position = extracted.matched_position
    position_result: EvaluationResult | None = None
    position_kind = None
    if position is not None:
        position_kind = getattr(position, "kind", None)
        label = getattr(position, "label", None)
        position_id = getattr(position, "id", None)
        if position_kind in ("preferred", "acceptable_variant"):
            position_result = EvaluationResult(
                zone="none",
                reason=f"Matches the {position_kind} position '{label}'; no finding",
                position_id=position_id,
                position=position,
            )
        elif position_kind == "fallback":
            # The position's own `zone` column decides (RulePosition.zone is
            # "green" or "yellow" per playbook_plan.md section 3.5); fall
            # back to the "fallback rungs are yellow" convention when a
            # lightweight caller's position object has no `zone` attribute.
            rung = getattr(position, "rung", None)
            zone = getattr(position, "zone", None) or "yellow"
            position_result = EvaluationResult(
                zone=zone,
                reason=f"Matches fallback position '{label}' (rung {rung})",
                position_id=position_id,
                position=position,
            )

    # Reconcile a parameter breach with a matched fallback position on the
    # same clause: report the fallback's position/rung (so callers such as
    # the rule-test runner can recover which rung matched) together with the
    # worse of the two zones, so a parameter's red/yellow verdict can never
    # be silently improved on by a better-looking fallback label. Preferred/
    # acceptable-variant matches are deliberately excluded (see the module
    # docstring) -- a parameter breach alongside one of those still wins
    # outright, exactly as before this fix.
    if param_result is not None and position_result is not None and position_kind == "fallback":
        if _ZONE_RANK.get(param_result.zone, 0) >= _ZONE_RANK.get(position_result.zone, 0):
            combined_zone = param_result.zone
            reason = f"{param_result.reason}; {position_result.reason}"
        else:
            combined_zone = position_result.zone
            reason = f"{position_result.reason}; {param_result.reason}"
        return EvaluationResult(
            zone=combined_zone,
            reason=reason,
            position_id=position_result.position_id,
            position=position_result.position,
            parameter_key=param_result.parameter_key,
            parameter_value=param_result.parameter_value,
        )

    if param_result is not None:
        return param_result

    if position_result is not None:
        return position_result

    # Step 5: otherwise, a deviation in the rule's default_zone.
    return EvaluationResult(
        zone=getattr(rule, "default_zone", None) or "red",
        reason="No matching position or red line; deviation from the playbook",
    )
