"""Tests for the rule test-case runner (task 4.10,
``app/services/playbook/testing.py``).

Two modes, tested separately per the task's "done when":
- deterministic mode must never touch ``app.core.llm.gateway`` — asserted
  here by patching it with a gateway double that raises if either method is
  called at all;
- default mode must call the gateway (one batched ``call_batch``, task 4.4's
  pattern) and produce both passing and failing cases from a realistic mix
  of extraction responses.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.llm.schemas.analysis import (
    ExtractedParameterOut,
    ExtractedPositionOut,
    RuleExtractionOut,
)
from app.services.playbook import testing as test_runner

# ---------------------------------------------------------------------------
# Fixtures — same shape as tests/unit/test_layer2_content.py's helpers
# (SimpleNamespace standing in for the ORM rows ``get_rules_with_children``
# would attach), since ``testing.py`` only ever accesses plain attributes.
# ---------------------------------------------------------------------------


def _position(
    kind: str = "preferred",
    label: str = "Preferred",
    rung: int | None = None,
    zone: str = "green",
    summary: str | None = "A position summary.",
    language: str = "Position language.",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        kind=kind,
        label=label,
        rung=rung,
        zone=zone,
        summary=summary,
        language=language,
    )


def _parameter(
    key: str = "cap_multiple_months",
    label: str = "Cap (months of fees)",
    direction: str = "lower_is_better",
    value_type: str = "number",
    green_limit=12,
    yellow_limit=24,
    allowed_values: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        key=key,
        label=label,
        value_type=value_type,
        unit=None,
        extraction_hint=label,
        direction=direction,
        preferred_value=green_limit,
        green_limit=green_limit,
        yellow_limit=yellow_limit,
        allowed_values=allowed_values,
        context_overrides=None,
    )


def _red_line(
    key: str = "rl-phrase",
    description: str = "Disabling encryption without consent.",
    condition_type: str = "phrase",
    condition: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        key=key,
        description=description,
        condition_type=condition_type,
        condition=condition or {},
    )


def _test_case(
    name: str,
    expected_outcome: str,
    sample_text: str = "",
    context: dict | None = None,
    expected_zone: str | None = None,
    expected_position_rung: int | None = None,
    expected_red_line_key: str | None = None,
    is_trap: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        sample_text=sample_text,
        context=context,
        expected_outcome=expected_outcome,
        expected_zone=expected_zone,
        expected_position_rung=expected_position_rung,
        expected_red_line_key=expected_red_line_key,
        is_trap=is_trap,
    )


def _rule(
    rule_key: str,
    clause_type: str = "family",
    title: str = "Title",
    positions: list | None = None,
    parameters: list | None = None,
    red_lines: list | None = None,
    test_cases: list | None = None,
    default_zone: str = "red",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        rule_key=rule_key,
        clause_type=clause_type,
        title=title,
        position_summary="A summary.",
        detection_guidance="Look for a cap.",
        positions=positions or [],
        parameters=parameters or [],
        red_lines=red_lines or [],
        test_cases=test_cases or [],
        default_zone=default_zone,
    )


class _RefusingGateway:
    """A gateway double that fails the test if it is ever called — used to
    prove deterministic mode makes no model call."""

    def call_structured(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("deterministic mode must not call call_structured")

    def call_batch(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("deterministic mode must not call call_batch")


class _BatchGateway:
    """A gateway double for default mode: returns a preset
    ``dict[custom_id, RuleExtractionOut]`` from ``call_batch`` and records
    every call made, so a test can assert exactly one batched call was made
    covering every pending case."""

    def __init__(self, responses: dict[str, RuleExtractionOut]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def call_structured(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("default mode's test runner batches calls; call_structured unused")

    def call_batch(self, task, items, response_model, cache_prefix=None):  # noqa: ANN001
        self.calls.append({"task": task, "items": items, "response_model": response_model})
        return self._responses


# ---------------------------------------------------------------------------
# Deterministic mode: phrase red line, negated phrase (skipped), missing
# ---------------------------------------------------------------------------


def test_deterministic_mode_never_calls_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(test_runner, "gateway", _RefusingGateway())

    red_line = _red_line(
        key="phi-encryption-disabled-at-will",
        condition_type="phrase",
        condition={"any": ["may disable encryption at its discretion"], "negation_guard": True},
    )
    rule = _rule(
        "security.phi_encryption",
        red_lines=[red_line],
        default_zone="yellow",
        test_cases=[
            _test_case(
                "Encryption disabled at will",
                expected_outcome="red_line",
                expected_zone="red",
                expected_red_line_key="phi-encryption-disabled-at-will",
                sample_text="Business Associate may disable encryption at its discretion.",
            ),
            _test_case(
                "Negated — needs the model",
                expected_outcome="compliant",
                expected_zone="green",
                sample_text=(
                    "Business Associate shall not disable encryption at its discretion "
                    "for any reason."
                ),
            ),
            _test_case(
                "No encryption clause at all",
                expected_outcome="missing",
                expected_zone="yellow",
                sample_text="",
            ),
        ],
    )
    rows = [("hipaa_overlay", rule)]

    assert test_runner.count_required_model_calls(rows) == 1

    summary = test_runner.run_rule_tests(rows, deterministic=True)

    assert summary.total_cases == 3
    assert summary.skipped_cases == 1
    assert summary.run_cases == 2
    assert summary.passed_cases == 2
    assert summary.failed_cases == 0
    assert summary.pass_rate == 1.0
    assert summary.model_calls_required == 1
    assert summary.model_calls_made == 0


def test_deterministic_mode_catches_a_real_structural_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structural match is ground truth regardless of what the case
    expects — a case that expects something else but whose sample text
    actually trips a phrase red line is a genuine failure, not a skip."""
    monkeypatch.setattr(test_runner, "gateway", _RefusingGateway())

    red_line = _red_line(condition_type="phrase", condition={"any": ["uncapped liability"]})
    rule = _rule(
        "limitation_of_liability.cap_amount",
        red_lines=[red_line],
        test_cases=[
            _test_case(
                "Mislabeled trap",
                expected_outcome="compliant",
                expected_zone="green",
                sample_text="Each party accepts uncapped liability for any breach.",
            )
        ],
    )
    summary = test_runner.run_rule_tests([("pb", rule)], deterministic=True)

    assert summary.skipped_cases == 0
    assert summary.failed_cases == 1
    failure = summary.failures[0]
    assert failure.actual_outcome == "red_line"
    assert failure.expected_outcome == "compliant"


def test_missing_case_uses_rule_default_zone_regardless_of_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Judgment call documented in testing.py: a 'missing' case is decided
    by evaluate_finding's own step-5 default, not layer1's required-clause
    check — so it is exercised (and can pass) even on a non-required rule."""
    monkeypatch.setattr(test_runner, "gateway", _RefusingGateway())

    rule = _rule(
        "indemnification.regulatory_penalties_indemnity",
        default_zone="yellow",
        test_cases=[
            _test_case(
                "No regulatory penalties indemnity",
                expected_outcome="missing",
                expected_zone="yellow",
                sample_text="",
            )
        ],
    )
    rule.required = False  # explicit, even though the runner never reads it

    summary = test_runner.run_rule_tests([("pb", rule)], deterministic=True)
    assert summary.passed_cases == 1
    assert summary.failed_cases == 0


# ---------------------------------------------------------------------------
# Default mode: one batched model call, mixed pass/fail
# ---------------------------------------------------------------------------


def _extraction(
    rule_key: str,
    match_kind: str,
    label: str | None,
    parameters: list[ExtractedParameterOut] | None = None,
) -> RuleExtractionOut:
    return RuleExtractionOut(
        rule_key=rule_key,
        position=ExtractedPositionOut(match_kind=match_kind, position_label=label, quote="q"),
        parameters=parameters or [],
        red_lines=[],
    )


def test_default_mode_batches_one_call_with_mixed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preferred = _position(kind="preferred", label="Preferred")
    fallback = _position(kind="fallback", label="Fallback 1", rung=1, zone="yellow")
    rule = _rule(
        "limitation_of_liability.cap_amount",
        positions=[preferred, fallback],
        test_cases=[
            _test_case(
                "12-month cap",
                expected_outcome="compliant",
                expected_zone="green",
                sample_text="Liability capped at 12 months of fees.",
            ),
            _test_case(
                "20-month cap, enterprise",
                expected_outcome="fallback",
                expected_zone="yellow",
                expected_position_rung=1,
                sample_text="Liability capped at 20 months of fees.",
            ),
            _test_case(
                "40-month cap (expected deviation)",
                expected_outcome="deviation",
                expected_zone="red",
                sample_text="Liability capped at 40 months of fees.",
            ),
        ],
    )

    responses = {
        "0": _extraction(rule.rule_key, "preferred", "Preferred"),
        "1": _extraction(rule.rule_key, "fallback", "Fallback 1"),
        # Simulate a bad/over-generous extraction: the model wrongly reports
        # a preferred match for sample text that should be a deviation.
        "2": _extraction(rule.rule_key, "preferred", "Preferred"),
    }
    fake = _BatchGateway(responses)
    monkeypatch.setattr(test_runner, "gateway", fake)

    summary = test_runner.run_rule_tests([("saas_msa_vendor", rule)], deterministic=False)

    assert len(fake.calls) == 1
    assert fake.calls[0]["task"] == test_runner.TASK
    assert len(fake.calls[0]["items"]) == 3

    assert summary.total_cases == 3
    assert summary.skipped_cases == 0
    assert summary.model_calls_required == 3
    assert summary.model_calls_made == 3
    assert summary.passed_cases == 2
    assert summary.failed_cases == 1

    assert len(summary.failures) == 1
    failure = summary.failures[0]
    assert failure.test_case_name == "40-month cap (expected deviation)"
    assert failure.expected_outcome == "deviation"
    assert failure.actual_outcome == "compliant"

    assert summary.by_expected_outcome["compliant"].passed == 1
    assert summary.by_expected_outcome["fallback"].passed == 1
    assert summary.by_expected_outcome["deviation"].total == 1
    assert summary.by_expected_outcome["deviation"].passed == 0

    assert summary.by_rule[rule.rule_key].total == 3
    assert summary.by_playbook["saas_msa_vendor"].total == 3

    assert summary.pass_rate == pytest.approx(2 / 3)
    assert not test_runner.meets_threshold(summary)


def test_default_mode_matches_expected_fallback_outcome_when_parameter_also_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the pilot-found bug: a rule with BOTH a parameter
    and fallback positions, where the model's extraction gives a parameter
    value AND identifies the matching fallback rung for the same clause, and
    the two signals agree on the zone. Before the evaluator fix, step 2 (the
    parameter check) won outright and discarded the position/rung, so this
    case reported a generic "deviation" instead of matching
    ``expected_outcome: "fallback"`` / ``expected_position_rung: 1`` -- even
    though the zone (yellow) was already correct."""
    parameter = _parameter(green_limit=12, yellow_limit=24)
    fallback = _position(kind="fallback", label="Fallback 1", rung=1, zone="yellow")
    rule = _rule(
        "limitation_of_liability.cap_amount",
        positions=[fallback],
        parameters=[parameter],
        test_cases=[
            _test_case(
                "20-month cap, enterprise (parameter agrees with fallback rung)",
                expected_outcome="fallback",
                expected_zone="yellow",
                expected_position_rung=1,
                sample_text="Liability capped at 20 months of fees, enterprise deal.",
            ),
        ],
    )

    extraction = _extraction(
        rule.rule_key,
        "fallback",
        "Fallback 1",
        parameters=[
            ExtractedParameterOut(
                parameter_key="cap_multiple_months", value="20 months", quote="20 months of fees"
            )
        ],
    )
    fake = _BatchGateway({"0": extraction})
    monkeypatch.setattr(test_runner, "gateway", fake)

    summary = test_runner.run_rule_tests([("saas_msa_vendor", rule)], deterministic=False)

    assert summary.failed_cases == 0
    assert summary.passed_cases == 1
    case = summary.by_expected_outcome["fallback"]
    assert case.total == 1
    assert case.passed == 1


def test_default_mode_surfaces_worse_zone_when_parameter_beats_fallback_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same dual-signal shape as above, but the two signals disagree: the
    matched fallback rung is labelled "green" while the raw parameter value
    is actually beyond the yellow limit (red). The rung/position must still
    be reported (it was correctly identified), but the zone must be the
    worse of the two -- red, not the fallback's own green label -- per the
    reconciliation documented in ``evaluator.evaluate_finding``."""
    parameter = _parameter(green_limit=12, yellow_limit=24)
    fallback = _position(kind="fallback", label="Fallback 2", rung=2, zone="green")
    rule = _rule(
        "limitation_of_liability.cap_amount",
        positions=[fallback],
        parameters=[parameter],
        test_cases=[
            _test_case(
                "40-month cap mislabeled as a green fallback rung",
                expected_outcome="fallback",
                expected_zone="red",
                expected_position_rung=2,
                sample_text="Liability capped at 40 months of fees.",
            ),
        ],
    )

    extraction = _extraction(
        rule.rule_key,
        "fallback",
        "Fallback 2",
        parameters=[
            ExtractedParameterOut(
                parameter_key="cap_multiple_months", value="40 months", quote="40 months of fees"
            )
        ],
    )
    fake = _BatchGateway({"0": extraction})
    monkeypatch.setattr(test_runner, "gateway", fake)

    summary = test_runner.run_rule_tests([("saas_msa_vendor", rule)], deterministic=False)

    assert summary.failed_cases == 0
    assert summary.passed_cases == 1


def test_default_mode_counts_required_calls_without_calling_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule(
        "limitation_of_liability.cap_amount",
        positions=[_position()],
        test_cases=[
            _test_case("a", expected_outcome="compliant", sample_text="text one"),
            _test_case("b", expected_outcome="compliant", sample_text="text two"),
        ],
    )
    monkeypatch.setattr(test_runner, "gateway", _RefusingGateway())
    assert test_runner.count_required_model_calls([("pb", rule)]) == 2


# ---------------------------------------------------------------------------
# Bug 2a: the test case's own `context` must thread into the prompt exactly
# like a real contract's context does, so a conditioned fallback position
# that doesn't apply to this test case's context isn't offered to the model.
# ---------------------------------------------------------------------------


def test_build_messages_threads_test_case_context_to_omit_nonmatching_fallback() -> None:
    matching = _position(kind="fallback", label="Fallback A: personal data", rung=1)
    matching.conditions = {"data_sensitivity": ["personal_data"]}
    nonmatching = _position(kind="fallback", label="Fallback B: special category", rung=2)
    nonmatching.conditions = {"data_sensitivity": ["special_category"]}
    rule = _rule("dpa.fallback_rungs", positions=[matching, nonmatching])

    messages = test_runner._build_messages(
        rule, "Processor shall implement technical measures.", {"data_sensitivity": "personal_data"}
    )
    user_msg = next(m["content"] for m in messages if m["role"] == "user")

    assert "Fallback A: personal data" in user_msg
    assert "Fallback B: special category" not in user_msg


def test_build_messages_with_no_context_renders_all_fallbacks() -> None:
    conditioned = _position(kind="fallback", label="Fallback A: conditioned", rung=1)
    conditioned.conditions = {"data_sensitivity": ["special_category"]}
    rule = _rule("dpa.fallback_rungs", positions=[conditioned])

    messages = test_runner._build_messages(rule, "Some clause text.")
    user_msg = next(m["content"] for m in messages if m["role"] == "user")

    assert "Fallback A: conditioned" in user_msg


# ---------------------------------------------------------------------------
# Report rendering — smoke test only
# ---------------------------------------------------------------------------


def test_format_report_includes_pass_rate_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    preferred = _position(kind="preferred", label="Preferred")
    rule = _rule(
        "limitation_of_liability.cap_amount",
        positions=[preferred],
        test_cases=[
            _test_case(
                "mismatch",
                expected_outcome="deviation",
                expected_zone="red",
                sample_text="Liability capped at 12 months of fees.",
            )
        ],
    )
    fake = _BatchGateway({"0": _extraction(rule.rule_key, "preferred", "Preferred")})
    monkeypatch.setattr(test_runner, "gateway", fake)

    summary = test_runner.run_rule_tests([("pb", rule)], deterministic=False)
    report = test_runner.format_report(summary)

    assert "pass rate" in report
    assert "Failures (1)" in report
    assert "mismatch" in report
