"""Tests for S2 scoring — severity-weighted risk score (T-043)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.services.contract_analysis.models import AnalysisFlag
from app.services.contract_analysis.scoring import (
    WEIGHTS_VERSION,
    ContractScore,
    score_flags,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(
    clause_type: str,
    severity: str,
    source: str = "deterministic",
    flag_type: str = "missing",
) -> AnalysisFlag:
    return AnalysisFlag(
        contract_id=uuid.uuid4(),
        flag_type=flag_type,
        severity=severity,
        source=source,
        clause_type=clause_type,
    )


def _rule(clause_type: str, risk_weight: float = 1.0) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.clause_type = clause_type
    r.risk_weight = risk_weight
    return r


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_no_flags_returns_zero_score() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], {})
    assert score.score == 0.0


def test_no_flags_returns_none_max_severity() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], {})
    assert score.max_clause_severity is None


def test_no_flags_returns_correct_contract_id() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], {})
    assert score.contract_id == cid


def test_no_flags_includes_weights_version() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [], {})
    assert score.weights_version == WEIGHTS_VERSION


# ---------------------------------------------------------------------------
# Severity-base correctness
# ---------------------------------------------------------------------------


def test_high_severity_outweighs_three_lows() -> None:
    """One high-severity flag must score more than three low-severity flags."""
    cid = uuid.uuid4()
    rule = _rule("indemnification", risk_weight=1.0)
    rules = {"indemnification": rule}

    high_score = score_flags(cid, [_flag("indemnification", "high")], rules)
    three_low = score_flags(
        cid,
        [
            _flag("indemnification", "low"),
            _flag("indemnification", "low"),
            _flag("indemnification", "low"),
        ],
        rules,
    )
    assert high_score.score > three_low.score


def test_medium_severity_outweighs_two_lows() -> None:
    cid = uuid.uuid4()
    rule = _rule("termination", risk_weight=1.0)
    rules = {"termination": rule}

    medium = score_flags(cid, [_flag("termination", "medium")], rules)
    two_low = score_flags(
        cid,
        [_flag("termination", "low"), _flag("termination", "low")],
        rules,
    )
    assert medium.score > two_low.score


def test_scores_are_additive() -> None:
    """Two flags of the same type sum their contributions."""
    cid = uuid.uuid4()
    rule = _rule("governing_law", risk_weight=1.0)
    rules = {"governing_law": rule}

    single = score_flags(cid, [_flag("governing_law", "low")], rules)
    double = score_flags(
        cid,
        [_flag("governing_law", "low"), _flag("governing_law", "low")],
        rules,
    )
    assert double.score == single.score * 2


# ---------------------------------------------------------------------------
# Risk-weight application
# ---------------------------------------------------------------------------


def test_higher_risk_weight_increases_score() -> None:
    cid = uuid.uuid4()
    low_weight = score_flags(
        cid, [_flag("indemnification", "high")], {"indemnification": _rule("indemnification", 1.0)}
    )
    high_weight = score_flags(
        cid, [_flag("indemnification", "high")], {"indemnification": _rule("indemnification", 5.0)}
    )
    assert high_weight.score > low_weight.score


def test_risk_weight_multiplies_severity_base() -> None:
    """score = severity_base × risk_weight exactly."""
    cid = uuid.uuid4()
    rule = _rule("payment", risk_weight=2.0)
    # medium base = 3.0, weight 2.0 → expected 6.0
    score = score_flags(cid, [_flag("payment", "medium")], {"payment": rule})
    assert score.score == 6.0


def test_zero_risk_weight_contributes_nothing() -> None:
    cid = uuid.uuid4()
    rule = _rule("notices", risk_weight=0.0)
    score = score_flags(cid, [_flag("notices", "high")], {"notices": rule})
    assert score.score == 0.0


# ---------------------------------------------------------------------------
# Ungoverned flags (no matching rule)
# ---------------------------------------------------------------------------


def test_ungoverned_flag_uses_default_weight() -> None:
    """Flags with no matching rule in resolved_rules still contribute to score."""
    cid = uuid.uuid4()
    # Empty rules dict — ungoverned clause
    score = score_flags(cid, [_flag("payment", "high")], {})
    # high base (9.0) × default weight (1.0) = 9.0
    assert score.score == 9.0


def test_ungoverned_flag_updates_max_severity() -> None:
    cid = uuid.uuid4()
    score = score_flags(cid, [_flag("payment", "high")], {})
    assert score.max_clause_severity == "high"


# ---------------------------------------------------------------------------
# max_clause_severity — ordering correctness
# ---------------------------------------------------------------------------


def test_max_severity_is_not_alphabetical() -> None:
    """max_clause_severity must be 'high', not 'medium' (alphabetically largest)."""
    cid = uuid.uuid4()
    rule = _rule("indemnification")
    flags = [
        _flag("indemnification", "low"),
        _flag("indemnification", "high"),
        _flag("indemnification", "medium"),
    ]
    score = score_flags(cid, flags, {"indemnification": rule})
    assert score.max_clause_severity == "high"


def test_max_severity_low_when_all_low() -> None:
    cid = uuid.uuid4()
    rule = _rule("indemnification")
    flags = [_flag("indemnification", "low"), _flag("indemnification", "low")]
    score = score_flags(cid, flags, {"indemnification": rule})
    assert score.max_clause_severity == "low"


def test_max_severity_high_beats_medium() -> None:
    cid = uuid.uuid4()
    rules = {
        "indemnification": _rule("indemnification"),
        "termination": _rule("termination"),
    }
    flags = [
        _flag("termination", "medium"),
        _flag("indemnification", "high"),
    ]
    score = score_flags(cid, flags, rules)
    assert score.max_clause_severity == "high"


# ---------------------------------------------------------------------------
# Combined layer 1 + layer 2 flags
# ---------------------------------------------------------------------------


def test_mixed_source_flags_all_contribute() -> None:
    """Layer 1 (deterministic) and Layer 2 (llm) flags both score."""
    cid = uuid.uuid4()
    rule = _rule("indemnification", risk_weight=1.0)
    flags = [
        _flag("indemnification", "high", source="deterministic", flag_type="missing"),
        _flag("indemnification", "medium", source="llm", flag_type="non_standard"),
    ]
    score = score_flags(cid, flags, {"indemnification": rule})
    # 9.0 + 3.0 = 12.0
    assert score.score == 12.0
    assert score.max_clause_severity == "high"


def test_return_type_is_contract_score() -> None:
    cid = uuid.uuid4()
    result = score_flags(cid, [], {})
    assert isinstance(result, ContractScore)


def test_clause_id_defaults_to_none() -> None:
    """ContractScore.clause_id is None for contract-level roll-ups."""
    cid = uuid.uuid4()
    score = score_flags(cid, [], {})
    assert score.clause_id is None
