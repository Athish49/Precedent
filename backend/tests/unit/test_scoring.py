"""Tests for S2 scoring — severity-weighted, 0-1-normalised risk score.

Rewritten for task 4.5 (``playbook_plan.md`` section 5.3). The old test
suite fed ``score_flags`` a ``dict[clause_type, rule]`` and asserted raw,
unbounded totals (9.0, 12.0, 27.0 ...) — exactly the scale
``playbook_status.md`` defect #2 says ``gate.py`` could never have been
checked against ("tests pass on a scale the scorer never produces"). This
version exercises the real normalised formula::

    score = min(total_points / (9 x sum(risk_weight over resolved_rules)), 1.0)

against a list of resolved rules (duck-typed: anything with ``rule_key`` and
``risk_weight``), which is what ``ResolveResponse.rules`` actually looks
like — one entry per surviving ``rule_key``, not one per clause_type.
"""

from __future__ import annotations

import itertools
import uuid
from types import SimpleNamespace

import pytest

from app.services.contract_analysis.models import AnalysisFlag
from app.services.contract_analysis.scoring import (
    WEIGHTS_VERSION,
    ContractScore,
    max_zone_for_flags,
    score_flags,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(
    severity: str = "low",
    rule_key: str | None = None,
    zone: str | None = None,
    clause_type: str = "indemnification",
) -> AnalysisFlag:
    return AnalysisFlag(
        contract_id=uuid.uuid4(),
        flag_type="deviation",
        severity=severity,
        source="deterministic",
        clause_type=clause_type,
        rule_key=rule_key,
        zone=zone,
    )


def _rule(rule_key: str, risk_weight: float = 1.0) -> SimpleNamespace:
    return SimpleNamespace(rule_key=rule_key, risk_weight=risk_weight)


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_no_flags_returns_zero_score() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], [])
    assert score.score == 0.0


def test_no_flags_returns_none_max_severity_and_zone() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], [])
    assert score.max_clause_severity is None
    assert score.max_zone is None


def test_no_flags_returns_correct_contract_id() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], [])
    assert score.contract_id == cid


def test_no_flags_includes_weights_version_v2() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], [])
    assert score.weights_version == WEIGHTS_VERSION == "v2"


def test_return_type_is_contract_score() -> None:
    assert isinstance(score_flags(uuid.uuid4(), [], []), ContractScore)


def test_clause_id_defaults_to_none() -> None:
    assert score_flags(uuid.uuid4(), [], []).clause_id is None


# ---------------------------------------------------------------------------
# Normalisation — the exact formula (playbook_plan.md section 5.3)
# ---------------------------------------------------------------------------


def test_normalisation_formula_exact() -> None:
    """score = (severity_base x weight) / (9 x sum(weight over resolved_rules))."""
    cid = uuid.uuid4()
    rules = [_rule("issue.one", risk_weight=4.0)]
    # severity_base(low) = 1 -> 1 x 4 = 4; denominator = 9 x 4 = 36.
    score = score_flags(cid, [_flag("low", rule_key="issue.one")], rules)
    assert score.score == pytest.approx(4.0 / 36.0)


def test_single_breached_rule_at_its_own_weight_scores_one() -> None:
    """A rule breached at high severity, alone, scores exactly 1.0 —
    the theoretical worst case for that one rule."""
    cid = uuid.uuid4()
    rules = [_rule("issue.one", risk_weight=5.0)]
    score = score_flags(cid, [_flag("high", rule_key="issue.one")], rules)
    assert score.score == pytest.approx(1.0)


def test_score_capped_at_one_when_same_rule_flagged_twice() -> None:
    """The same rule_key flagged on two clauses can push the raw total past
    the denominator; the cap keeps the score within [0, 1]."""
    cid = uuid.uuid4()
    rules = [_rule("issue.one", risk_weight=1.0)]
    flags = [_flag("high", rule_key="issue.one"), _flag("high", rule_key="issue.one")]
    score = score_flags(cid, flags, rules)
    # Raw: (9 + 9) / (9 x 1) = 2.0, capped to 1.0.
    assert score.score == 1.0


def test_additional_unbreached_resolved_rules_lower_the_score() -> None:
    """Resolving more rules (even ones with no flag) raises the
    denominator and so lowers the score for the same flags."""
    cid = uuid.uuid4()
    flags = [_flag("high", rule_key="issue.one")]
    narrow = score_flags(cid, flags, [_rule("issue.one", 1.0)])
    wide = score_flags(cid, flags, [_rule("issue.one", 1.0), _rule("issue.two", 1.0)])
    assert wide.score < narrow.score


# ---------------------------------------------------------------------------
# Ungoverned flags and the no-resolved-rules edge case
# ---------------------------------------------------------------------------


def test_ungoverned_flag_uses_default_weight_of_one() -> None:
    """A flag with no rule_key (or one absent from resolved_rules) is
    weighted 1, same as any resolved rule's default."""
    cid = uuid.uuid4()
    rules = [_rule("issue.one", risk_weight=9.0)]
    score = score_flags(cid, [_flag("high", rule_key=None)], rules)
    # 9 (severity base) x 1 (default weight) / (9 x 9) = 1/9.
    assert score.score == pytest.approx(9.0 / 81.0)


def test_rule_key_not_among_resolved_rules_also_uses_default_weight() -> None:
    cid = uuid.uuid4()
    rules = [_rule("issue.one", risk_weight=9.0)]
    score = score_flags(cid, [_flag("high", rule_key="issue.unmatched")], rules)
    assert score.score == pytest.approx(9.0 / 81.0)


def test_no_resolved_rules_at_all_fails_safe_to_one() -> None:
    """Resolution should never return zero rules in practice (the baseline
    playbook always matches), but if it ever did, a flag with nothing to
    normalise against must not divide by zero or silently score 0."""
    cid = uuid.uuid4()
    score = score_flags(cid, [_flag("low", rule_key=None)], [])
    assert score.score == 1.0


# ---------------------------------------------------------------------------
# max_clause_severity — explicit ordering, not alphabetical
# ---------------------------------------------------------------------------


def test_max_severity_is_not_alphabetical() -> None:
    cid = uuid.uuid4()
    rules = [_rule("issue.one", 1.0)]
    flags = [_flag("low", "issue.one"), _flag("high", "issue.one"), _flag("medium", "issue.one")]
    assert score_flags(cid, flags, rules).max_clause_severity == "high"


def test_max_severity_low_when_all_low() -> None:
    cid = uuid.uuid4()
    rules = [_rule("issue.one", 1.0)]
    flags = [_flag("low", "issue.one"), _flag("low", "issue.one")]
    assert score_flags(cid, flags, rules).max_clause_severity == "low"


# ---------------------------------------------------------------------------
# max_zone (task 4.5 item 3) — explicit ordering, flags without a zone ignored
# ---------------------------------------------------------------------------


def test_max_zone_is_worst_among_flags() -> None:
    cid = uuid.uuid4()
    rules = [_rule("issue.one", 1.0)]
    flags = [
        _flag("low", "issue.one", zone="green"),
        _flag("medium", "issue.one", zone="red"),
        _flag("low", "issue.one", zone="yellow"),
    ]
    assert score_flags(cid, flags, rules).max_zone == "red"


def test_max_zone_ignores_flags_with_no_zone() -> None:
    """A flag with zone=None (e.g. a vagueness flag with no rule binding)
    must not count as worse than an explicit 'green'."""
    cid = uuid.uuid4()
    rules = [_rule("issue.one", 1.0)]
    flags = [_flag("low", "issue.one", zone=None), _flag("low", "issue.one", zone="green")]
    assert score_flags(cid, flags, rules).max_zone == "green"


def test_max_zone_none_when_no_flag_carries_a_zone() -> None:
    cid = uuid.uuid4()
    rules = [_rule("issue.one", 1.0)]
    flags = [_flag("low", "issue.one", zone=None)]
    assert score_flags(cid, flags, rules).max_zone is None


def test_max_zone_for_flags_helper_matches_score_flags() -> None:
    """The standalone helper app/workflows/gate.py reuses must agree with
    what score_flags computes internally."""
    flags = [_flag(zone="yellow"), _flag(zone="green"), _flag(zone=None)]
    assert max_zone_for_flags(flags) == "yellow"


# ---------------------------------------------------------------------------
# Boundary / property test: the score is always in [0, 1] (task 4.5's
# "Done when": "score is always between 0 and 1").
# ---------------------------------------------------------------------------


_SEVERITIES = ("low", "medium", "high")
_WEIGHTS = (0.0, 1.0, 2.5, 10.0)
_FLAG_COUNTS = (0, 1, 3, 7)


@pytest.mark.parametrize(
    "severity,weight,flag_count,n_rules",
    list(itertools.product(_SEVERITIES, _WEIGHTS, _FLAG_COUNTS, (0, 1, 4))),
)
def test_score_always_between_zero_and_one(
    severity: str, weight: float, flag_count: int, n_rules: int
) -> None:
    cid = uuid.uuid4()
    rules = [_rule(f"issue.{i}", weight) for i in range(n_rules)]
    rule_key = "issue.0" if n_rules else None
    flags = [_flag(severity, rule_key=rule_key) for _ in range(flag_count)]
    score = score_flags(cid, flags, rules)
    assert 0.0 <= score.score <= 1.0


def test_score_always_between_zero_and_one_with_mixed_zero_and_nonzero_weights() -> None:
    """A mix of a zero-weight rule and a normal-weight rule must not push
    the score out of range or raise on the zero term."""
    cid = uuid.uuid4()
    rules = [_rule("issue.zero", 0.0), _rule("issue.one", 3.0)]
    flags = [
        _flag("high", rule_key="issue.zero"),
        _flag("high", rule_key="issue.one"),
        _flag("high", rule_key="issue.one"),
        _flag("high", rule_key="issue.one"),
    ]
    score = score_flags(cid, flags, rules)
    assert 0.0 <= score.score <= 1.0


# ---------------------------------------------------------------------------
# Combined layer 1 + layer 2 flags
# ---------------------------------------------------------------------------


def test_mixed_source_flags_all_contribute() -> None:
    cid = uuid.uuid4()
    rules = [_rule("issue.one", 1.0)]
    flags = [
        AnalysisFlag(
            contract_id=cid,
            flag_type="missing",
            severity="high",
            source="deterministic",
            clause_type="indemnification",
            rule_key="issue.one",
        ),
        AnalysisFlag(
            contract_id=cid,
            flag_type="non_standard",
            severity="medium",
            source="llm",
            clause_type="indemnification",
            rule_key="issue.one",
        ),
    ]
    score = score_flags(cid, flags, rules)
    # (9 + 3) / (9 x 1) = 12/9, capped to 1.0.
    assert score.score == 1.0
    assert score.max_clause_severity == "high"
