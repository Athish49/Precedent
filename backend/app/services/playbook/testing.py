"""Rule test-case runner (task 4.10).

For every ``rule_test_case`` row on a rule (``playbook_plan.md`` section
3.10), simulate the clause the test case describes and run it through the
same pipeline a real contract's clause would go through — structural
checks (task 4.3's ``layer1_structural.py``), content extraction (a real
model call, the same pattern ``layer2_content.py`` uses for a real
contract — task 4.4), and the zone evaluator (``evaluator.evaluate_finding``,
task 4.3) — then compares the actual outcome/zone/rung/red-line-key against
what the test case says it should be.

Two cost tiers, matching the task's split exactly:

- A case is **decidable without a model call** when either:
    - its ``sample_text`` is empty — the ``missing`` case: "a missing
      expected_outcome doesn't need sample_text matched against anything, it
      tests the required-clause-absent path." That path is simulated here as
      an empty :class:`ExtractedClause` run through ``evaluate_finding`` —
      nothing matched at all lands on the ladder's step 5, "a deviation in
      the rule's default_zone" — which is exactly what an absent clause looks
      like to the evaluator, and (checked against every ``missing`` test case
      in the seed content) is exactly the zone those cases expect, regardless
      of the rule's own ``required`` flag.
    - the rule has a ``phrase``/``regex`` red line that matches the sample
      text directly — the same deterministic mechanism
      ``layer1_structural._find_red_line_matches`` uses for a real contract,
      negation guard included. This is checked for every case regardless of
      what it expects, not only ones that expect ``red_line``: a structural
      match is itself the ground truth a real contract scan would produce,
      so a ``compliant`` case whose sample text accidentally trips a red
      line is a real failure to surface, not a reason to skip it.
  ``--deterministic`` runs only these; everything else is reported as
  skipped, never calling the model.
- Every other case needs the model to decide which position (if any) the
  text matches, what each parameter's value is, and whether each semantic
  red line is triggered — exactly the judgment ``layer2_content.py`` asks
  the model for on a real contract. Default mode batches one
  ``gateway.call_batch`` request (task 4.4's per-contract batching pattern,
  ``layer2_content._call_llm``) covering every such case in the run, then
  feeds each result through ``layer2_content._build_extracted_clause`` and
  ``evaluator.evaluate_finding`` — the exact same two functions a real
  contract's Layer 2 pass uses, so this is testing the real pipeline, not a
  parallel implementation of it.

Judgment call worth flagging: the ``missing`` handling above does not use
``layer1_structural._check_missing`` (which only fires when ``rule.required``
is true). Several seeded ``missing`` test cases are on non-required rules yet
still carry an expected zone, and in every single one of them that expected
zone equals the rule's own ``default_zone`` — exactly what
``evaluate_finding``'s step 5 produces for a clause with nothing extracted.
Using that path instead of the narrower required-clause-family check lines
up with every seeded case and needs no ``required`` branch at all; the
alternative (skip missing cases on non-required rules) would make those
seeded cases fail outright with no way to pass.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.llm import gateway
from app.core.llm.schemas.analysis import RuleExtractionOut
from app.services.contract_analysis.evaluator import (
    EvaluationResult,
    ExtractedClause,
    evaluate_finding,
)
from app.services.contract_analysis.layer1_structural import _find_red_line_matches
from app.services.contract_analysis.layer2_content import _build_extracted_clause, _rule_block

# ---------------------------------------------------------------------------
# Publish-gate default (task 4.10 item 6; wired into
# ``app/services/playbook/versions.py::publish_draft``).
# ---------------------------------------------------------------------------

DEFAULT_PASS_THRESHOLD = 0.95

# Registry task key for the model call (task key -> tier mapping lives in
# ``app/core/llm/registry.py``; unregistered task names default to the
# "smart" tier, which is what this needs — same tier as "clause_analysis").
TASK = "playbook.rule_test"

_SYSTEM_PROMPT = (
    "You are testing one playbook rule against one sample contract clause, "
    "written to probe whether the rule's extraction would classify it "
    "correctly. You are given the rule's positions, parameters and semantic "
    "red lines, and the clause text. Decide: which position (if any) the "
    "clause text matches (echo its exact label); the value of each "
    "parameter the clause states, each with a verbatim supporting quote; "
    "and, for each semantic red line, whether it is triggered, with a "
    "verbatim quote if so. Do not decide the zone yourself — only report "
    "what the text says."
)


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """The outcome of running one test case, actual vs expected."""

    playbook_key: str
    rule_key: str
    test_case_name: str
    expected_outcome: str
    expected_zone: str | None
    expected_position_rung: int | None
    expected_red_line_key: str | None

    actual_outcome: str | None = None
    actual_zone: str | None = None
    actual_position_rung: int | None = None
    actual_red_line_key: str | None = None

    passed: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    reason: str | None = None
    is_trap: bool = False


@dataclass
class GroupStats:
    total: int = 0
    passed: int = 0

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total) if self.total else 1.0


@dataclass
class TestRunSummary:
    total_cases: int
    run_cases: int
    skipped_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    by_playbook: dict[str, GroupStats]
    by_rule: dict[str, GroupStats]
    by_expected_outcome: dict[str, GroupStats]
    failures: list[CaseResult]
    model_calls_required: int
    model_calls_made: int

    @property
    def meets_threshold(self) -> bool:
        return self.pass_rate >= DEFAULT_PASS_THRESHOLD


def meets_threshold(summary: TestRunSummary, threshold: float = DEFAULT_PASS_THRESHOLD) -> bool:
    return summary.pass_rate >= threshold


# ---------------------------------------------------------------------------
# Internal: one case pending a model call
# ---------------------------------------------------------------------------


@dataclass
class _PendingCase:
    playbook_key: str
    rule: Any
    test_case: Any


# ---------------------------------------------------------------------------
# Deterministic decision steps
# ---------------------------------------------------------------------------


def _structural_red_line_match(rule: Any, sample_text: str) -> EvaluationResult | None:
    """Direct phrase/regex match against *rule*'s own red lines.

    Same mechanism as ``layer1_structural._find_red_line_matches`` (negation
    guard included); checked at rule scope only — a test case exercises one
    rule, not a whole contract, so playbook/global scope is not applicable.
    Returns ``None`` when nothing deterministic fires (the case then needs a
    model call to decide, unless it is a ``missing`` case).
    """
    for red_line in getattr(rule, "red_lines", None) or []:
        if getattr(red_line, "condition_type", None) not in ("phrase", "regex"):
            continue
        if _find_red_line_matches(sample_text, red_line):
            return EvaluationResult(
                zone="red",
                reason=(
                    f"Matched red line '{red_line.key}' by direct phrase/regex text "
                    "match (no model call needed)"
                ),
                red_line_id=getattr(red_line, "id", None),
                red_line=red_line,
            )
    return None


def _missing_result(rule: Any, context: dict[str, Any]) -> EvaluationResult:
    """Simulate the clause family being entirely absent: nothing extracted,
    so the ladder falls through to step 5 (deviation in ``default_zone``)."""
    return evaluate_finding(rule, ExtractedClause(), context)


# ---------------------------------------------------------------------------
# Mapping an EvaluationResult to one of the test-case outcome labels
# ---------------------------------------------------------------------------

_POSITION_KIND_TO_OUTCOME = {
    "preferred": "compliant",
    "acceptable_variant": "acceptable_variant",
    "fallback": "fallback",
}


def _outcome_from_result(result: EvaluationResult) -> tuple[str, int | None, str | None]:
    """(actual_outcome, actual_position_rung, actual_red_line_key)."""
    if result.red_line_id is not None:
        key = result.red_line.key if result.red_line is not None else None
        return "red_line", None, key
    if result.position is not None:
        kind = getattr(result.position, "kind", None)
        outcome = _POSITION_KIND_TO_OUTCOME.get(kind)
        if outcome is not None:
            rung = getattr(result.position, "rung", None) if outcome == "fallback" else None
            return outcome, rung, None
    return "deviation", None, None


def _normalize_zone(zone: str | None) -> str | None:
    """``evaluate_finding`` returns ``"none"`` for a preferred/acceptable-variant
    match (section 5.2's "no finding"); the seed test cases encode that case's
    expected zone as ``"green"``, so the two are treated as equal here."""
    return "green" if zone == "none" else zone


# ---------------------------------------------------------------------------
# Pass/fail comparison
# ---------------------------------------------------------------------------


def _case_passes(
    test_case: Any,
    actual_outcome: str | None,
    actual_zone: str | None,
    actual_rung: int | None,
    actual_red_line_key: str | None,
) -> bool:
    if test_case.expected_outcome != actual_outcome:
        return False
    if test_case.expected_zone is not None and test_case.expected_zone != _normalize_zone(
        actual_zone
    ):
        return False
    if (
        test_case.expected_position_rung is not None
        and test_case.expected_position_rung != actual_rung
    ):
        return False
    if (
        test_case.expected_red_line_key is not None
        and test_case.expected_red_line_key != actual_red_line_key
    ):
        return False
    return True


def _finalize(
    playbook_key: str,
    rule_key: str,
    test_case: Any,
    result: EvaluationResult,
    *,
    is_missing: bool,
) -> CaseResult:
    if is_missing:
        actual_outcome, actual_rung, actual_red_line_key = "missing", None, None
    else:
        actual_outcome, actual_rung, actual_red_line_key = _outcome_from_result(result)
    actual_zone = result.zone
    passed = _case_passes(test_case, actual_outcome, actual_zone, actual_rung, actual_red_line_key)
    return CaseResult(
        playbook_key=playbook_key,
        rule_key=rule_key,
        test_case_name=test_case.name,
        expected_outcome=test_case.expected_outcome,
        expected_zone=test_case.expected_zone,
        expected_position_rung=test_case.expected_position_rung,
        expected_red_line_key=test_case.expected_red_line_key,
        actual_outcome=actual_outcome,
        actual_zone=actual_zone,
        actual_position_rung=actual_rung,
        actual_red_line_key=actual_red_line_key,
        passed=passed,
        reason=result.reason,
        is_trap=bool(getattr(test_case, "is_trap", False)),
    )


def _skipped(p: _PendingCase, reason: str) -> CaseResult:
    tc = p.test_case
    rule_key = p.rule.rule_key or str(p.rule.id)
    return CaseResult(
        playbook_key=p.playbook_key,
        rule_key=rule_key,
        test_case_name=tc.name,
        expected_outcome=tc.expected_outcome,
        expected_zone=tc.expected_zone,
        expected_position_rung=tc.expected_position_rung,
        expected_red_line_key=tc.expected_red_line_key,
        skipped=True,
        skip_reason=reason,
        is_trap=bool(getattr(tc, "is_trap", False)),
    )


# ---------------------------------------------------------------------------
# Classification: split every (playbook_key, rule, test_case) triple into
# decided-already (no model needed) and pending-a-model-call.
# ---------------------------------------------------------------------------


def _classify(
    rules_with_keys: Iterable[tuple[str, Any]],
) -> tuple[list[CaseResult], list[_PendingCase]]:
    decided: list[CaseResult] = []
    pending: list[_PendingCase] = []

    for playbook_key, rule in rules_with_keys:
        rule_key = rule.rule_key or str(rule.id)
        for test_case in getattr(rule, "test_cases", None) or []:
            context = test_case.context or {}

            if not test_case.sample_text:
                result = _missing_result(rule, context)
                decided.append(
                    _finalize(playbook_key, rule_key, test_case, result, is_missing=True)
                )
                continue

            structural = _structural_red_line_match(rule, test_case.sample_text)
            if structural is not None:
                decided.append(
                    _finalize(playbook_key, rule_key, test_case, structural, is_missing=False)
                )
                continue

            pending.append(_PendingCase(playbook_key, rule, test_case))

    return decided, pending


def count_required_model_calls(rules_with_keys: Iterable[tuple[str, Any]]) -> int:
    """How many test cases cannot be decided without a model call.

    Pure and free — classifies every case but never calls the model. Used by
    the CLI to print the cost-bearing confirmation prompt before deciding
    whether to proceed (task 4.10 item 2).
    """
    _, pending = _classify(rules_with_keys)
    return len(pending)


# ---------------------------------------------------------------------------
# Model call (default mode only)
# ---------------------------------------------------------------------------


def _build_messages(
    rule: Any, sample_text: str, context: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    """*context* (bug 2a fix) is the test case's own ``context`` — threaded
    through to ``_rule_block`` exactly like a real contract's context is, so
    a fallback position whose ``conditions`` don't match this test case's
    context is not offered to the model here either."""
    user = f"{_rule_block(rule, context)}\n\nClause text:\n{sample_text}\n"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _call_model_for_pending(pending: Sequence[_PendingCase]) -> dict[str, RuleExtractionOut]:
    items = [
        {
            "id": str(i),
            "messages": _build_messages(p.rule, p.test_case.sample_text, p.test_case.context),
        }
        for i, p in enumerate(pending)
    ]
    return gateway.call_batch(TASK, items, RuleExtractionOut, cache_prefix=_SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# Summary aggregation
# ---------------------------------------------------------------------------


def _group(
    results: Iterable[CaseResult], key: Callable[[CaseResult], str]
) -> dict[str, GroupStats]:
    out: dict[str, GroupStats] = {}
    for r in results:
        if r.skipped:
            continue
        stats = out.setdefault(key(r), GroupStats())
        stats.total += 1
        if r.passed:
            stats.passed += 1
    return out


def _summarize(
    results: list[CaseResult], model_calls_required: int, model_calls_made: int
) -> TestRunSummary:
    total = len(results)
    skipped = sum(1 for r in results if r.skipped)
    run = total - skipped
    passed = sum(1 for r in results if r.passed)
    failed = run - passed
    pass_rate = (passed / run) if run else 1.0

    return TestRunSummary(
        total_cases=total,
        run_cases=run,
        skipped_cases=skipped,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=pass_rate,
        by_playbook=_group(results, lambda r: r.playbook_key),
        by_rule=_group(results, lambda r: r.rule_key),
        by_expected_outcome=_group(results, lambda r: r.expected_outcome),
        failures=[r for r in results if not r.skipped and not r.passed],
        model_calls_required=model_calls_required,
        model_calls_made=model_calls_made,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_rule_tests(
    rules_with_keys: Sequence[tuple[str, Any]],
    *,
    deterministic: bool,
) -> TestRunSummary:
    """Run every test case on every rule in *rules_with_keys*.

    Args:
        rules_with_keys: ``(playbook_key, rule)`` pairs — *rule* is a
            ``PlaybookRule`` (or anything duck-typing it) with its six child
            lists attached, e.g. ``playbook_repo.get_rules_with_children``'s
            output paired with the owning playbook's ``key``.
        deterministic: ``True`` runs only cases decidable without a model
            call (phrase/regex red lines and ``missing`` cases) and never
            touches ``app.core.llm.gateway`` — every other case is reported
            as skipped. ``False`` additionally sends one batched model call
            (task 4.4's pattern) covering every remaining case.

    Returns:
        A :class:`TestRunSummary` with pass rate overall and broken down by
        playbook, by rule and by expected outcome, plus every failing case.
    """
    decided, pending = _classify(rules_with_keys)
    model_calls_required = len(pending)
    model_calls_made = 0

    results: list[CaseResult] = list(decided)

    if pending:
        if deterministic:
            results.extend(
                _skipped(p, "requires a model call; not decidable in --deterministic mode")
                for p in pending
            )
        else:
            extractions = _call_model_for_pending(pending)
            model_calls_made = len(pending)
            for i, p in enumerate(pending):
                extraction = extractions.get(str(i))
                if extraction is None:
                    results.append(_skipped(p, "model returned no result for this case"))
                    continue
                rule_key = p.rule.rule_key or str(p.rule.id)
                extracted = _build_extracted_clause(p.rule, extraction)
                result = evaluate_finding(p.rule, extracted, p.test_case.context or {})
                results.append(
                    _finalize(p.playbook_key, rule_key, p.test_case, result, is_missing=False)
                )

    return _summarize(results, model_calls_required, model_calls_made)


# ---------------------------------------------------------------------------
# Rendering (shared by the CLI and anything that wants a plain-text report)
# ---------------------------------------------------------------------------


def format_report(summary: TestRunSummary) -> str:
    lines: list[str] = []
    lines.append(
        f"Ran {summary.run_cases} case(s) ({summary.skipped_cases} skipped, "
        f"{summary.total_cases} total): {summary.passed_cases} passed, "
        f"{summary.failed_cases} failed — pass rate "
        f"{summary.pass_rate:.1%} (threshold {DEFAULT_PASS_THRESHOLD:.0%})"
    )
    lines.append(
        f"Model calls: {summary.model_calls_made} made, "
        f"{summary.model_calls_required} required"
    )

    def _table(title: str, groups: Mapping[str, GroupStats]) -> None:
        if not groups:
            return
        lines.append(f"\n{title}:")
        for key in sorted(groups):
            stats = groups[key]
            lines.append(f"  {key}: {stats.passed}/{stats.total} ({stats.pass_rate:.1%})")

    _table("By playbook", summary.by_playbook)
    _table("By rule", summary.by_rule)
    _table("By expected outcome", summary.by_expected_outcome)

    if summary.failures:
        lines.append(f"\nFailures ({len(summary.failures)}):")
        for f in summary.failures:
            trap = " [TRAP]" if f.is_trap else ""
            lines.append(
                f"  [{f.playbook_key}] {f.rule_key} / {f.test_case_name!r}{trap}: "
                f"expected outcome={f.expected_outcome!r} zone={f.expected_zone!r} "
                f"rung={f.expected_position_rung!r} red_line={f.expected_red_line_key!r} "
                f"-- actual outcome={f.actual_outcome!r} zone={f.actual_zone!r} "
                f"rung={f.actual_position_rung!r} red_line={f.actual_red_line_key!r}"
            )
            if f.reason:
                lines.append(f"      reason: {f.reason}")

    return "\n".join(lines)
