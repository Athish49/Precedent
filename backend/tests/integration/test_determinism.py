"""Determinism tests: same input → identical output across repeated calls."""
from __future__ import annotations


def test_diff_determinism():
    """Same two texts → identical change set on repeated calls."""
    from app.core.diff.differ import diff

    old = "This is the original contract text with several clauses and terms."
    new = "This is the revised contract text with several updated clauses and terms."

    result1 = diff(old, new)
    result2 = diff(old, new)
    result3 = diff(old, new)

    assert result1 == result2 == result3
    assert all(c.op in ("equal", "insert", "delete") for c in result1)


def test_aligner_determinism():
    """Same clause lists → identical alignment on repeated calls."""
    from app.core.diff.aligner import Clause, align

    old_clauses = [
        Clause(clause_id="c1", text="First clause text."),
        Clause(clause_id="c2", text="Second clause text."),
        Clause(clause_id="c3", text="Third clause text."),
    ]
    new_clauses = [
        Clause(clause_id="c2", text="Second clause modified."),
        Clause(clause_id="c3", text="Third clause text."),
        Clause(clause_id="c4", text="New fourth clause."),
    ]

    result1 = align(old_clauses, new_clauses)
    result2 = align(old_clauses, new_clauses)

    assert result1 == result2

    changes = {
        (p.old.clause_id if p.old else p.new.clause_id): p.change
        for p in result1
    }
    assert changes["c1"] == "deleted"
    assert changes["c2"] == "modified"
    assert changes["c3"] == "unchanged"
    assert changes["c4"] == "inserted"


def test_diff_aligner_roundtrip_determinism():
    """Clause-aligned diff is deterministic across multiple runs."""
    from app.core.diff.aligner import Clause, align
    from app.core.diff.differ import diff

    old_clauses = [
        Clause(clause_id="ind", text="Party A shall indemnify Party B."),
        Clause(clause_id="pay", text="Payment is due in 30 days."),
    ]
    new_clauses = [
        Clause(clause_id="ind", text="Party A shall indemnify and hold harmless Party B."),
        Clause(clause_id="pay", text="Payment is due in 30 days."),
    ]

    def run():
        pairs = align(old_clauses, new_clauses)
        results = []
        for pair in pairs:
            if pair.change == "modified":
                changes = diff(pair.old.text, pair.new.text)
                results.append((pair.old.clause_id, [c.op for c in changes]))
        return results

    r1, r2, r3 = run(), run(), run()
    assert r1 == r2 == r3


def test_analytics_portfolio_risk_determinism():
    """Same raw data dict → same PortfolioRiskResponse on repeated validation."""
    from app.schemas.analytics import PortfolioRiskResponse

    raw = {
        "total_contracts": 10,
        "total_high_flags": 3,
        "total_medium_flags": 5,
        "total_low_flags": 7,
        "total_flags": 15,
        "avg_weighted_flag_score": 2.13,
        "avg_risk_score": 0.45,
        "contracts_high_severity": 2,
        "contracts_medium_severity": 4,
        "contracts_low_severity": 4,
    }

    r1 = PortfolioRiskResponse.model_validate(raw)
    r2 = PortfolioRiskResponse.model_validate(raw)
    r3 = PortfolioRiskResponse.model_validate(raw)

    assert r1 == r2 == r3
    assert r1.total_contracts == 10
    assert r1.contracts_high_severity == 2


# The old pipeline's segmentation-determinism case (same ParsedDocument ->
# identical SegmentedClause list) was removed with parsers.py and
# segmentation.py (doc_proc task 5.1). The new pipeline's determinism —
# same recorded Extend response -> identical pipeline.build_result output —
# is proved by tests/unit/test_dp_pipeline_replay.py, which runs the full
# replay corpus, not reproduced here.
