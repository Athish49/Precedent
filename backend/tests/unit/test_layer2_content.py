"""Tests for S2 Layer 2 LLM content analysis (T-042)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.llm.schemas.analysis import (
    ClauseAnalysisItem,
    ClauseFlagOut,
    ContractAnalysisOut,
)
from app.services.contract_analysis.layer2_content import (
    _find_inconsistency_candidates,
    run_layer2,
)
from app.services.contract_analysis.models import ClauseRuleMatch
from tests.fake_llm import FakeLLMGateway

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clause(
    clause_type: str,
    text: str = "Standard clause text.",
    char_start: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        clause_type=clause_type,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )


def _rule(clause_type: str, preferred: str = "Preferred language.") -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.clause_type = clause_type
    r.preferred_language = preferred
    r.acceptable_variations = []
    r.prohibited_terms = []
    return r


def _match(clause, rule=None) -> ClauseRuleMatch:
    return ClauseRuleMatch(clause=clause, rule=rule)


def _fake_result(*items: ClauseAnalysisItem) -> ContractAnalysisOut:
    return ContractAnalysisOut(items=list(items))


def _item(clause_id: uuid.UUID, *flags: ClauseFlagOut) -> ClauseAnalysisItem:
    return ClauseAnalysisItem(clause_id=str(clause_id), flags=list(flags))


def _flag(
    flag_type: str,
    severity: str = "medium",
    detail: str = "test detail",
    quote: str | None = None,
) -> ClauseFlagOut:
    return ClauseFlagOut(
        flag_type=flag_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        detail=detail,
        offending_quote=quote,
    )


# ---------------------------------------------------------------------------
# run_layer2 — basic routing
# ---------------------------------------------------------------------------


def test_empty_matches_returns_no_flags() -> None:
    contract_id = uuid.uuid4()
    flags = run_layer2(contract_id, "own", [])
    assert flags == []


def test_empty_matches_counterparty_returns_no_flags() -> None:
    contract_id = uuid.uuid4()
    flags = run_layer2(contract_id, "counterparty", [])
    assert flags == []


# ---------------------------------------------------------------------------
# Own-paper path
# ---------------------------------------------------------------------------


def test_own_paper_non_standard_flag_produced() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("indemnification", "Party A indemnifies Party B unconditionally.")
    rule = _rule("indemnification", preferred="Standard indemnification language.")
    m = _match(clause, rule)

    fake_item = _item(clause.id, _flag("non_standard", "high", "Deviates from playbook."))
    fake_result = _fake_result(fake_item)
    fake = FakeLLMGateway(structured_responses={"clause_analysis": fake_result})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert len(flags) == 1
    f = flags[0]
    assert f.flag_type == "non_standard"
    assert f.severity == "high"
    assert f.source == "llm"
    assert f.clause_type == "indemnification"
    assert f.clause_id == clause.id
    assert f.matched_rule_id == rule.id


def test_own_paper_high_risk_and_vague_flags() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("limitation_of_liability", "Party A has unlimited liability for all losses.")
    m = _match(clause, _rule("limitation_of_liability"))

    fake_item = _item(
        clause.id,
        _flag("high_risk", "high", "Unlimited liability."),
        _flag("vague", "low", "All losses is undefined."),
    )
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert len(flags) == 2
    types = {f.flag_type for f in flags}
    assert types == {"high_risk", "vague"}


def test_own_paper_no_flags_returns_empty() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("governing_law", "This agreement is governed by Delaware law.")
    m = _match(clause, _rule("governing_law"))

    fake_item = _item(clause.id)  # no flags
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags == []


def test_own_paper_calls_gateway_once() -> None:
    contract_id = uuid.uuid4()
    clauses = [
        _match(_clause("indemnification"), _rule("indemnification")),
        _match(_clause("termination"), _rule("termination")),
        _match(_clause("governing_law"), _rule("governing_law")),
    ]
    fake_items = [_item(m.clause.id) for m in clauses]
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(*fake_items)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        run_layer2(contract_id, "own", clauses)

    assert len(fake.calls) == 1
    assert fake.calls[0]["method"] == "call_structured"
    assert fake.calls[0]["task"] == "clause_analysis"


def test_own_paper_inconsistent_flag_included() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("confidentiality", "All Confidential Information must be protected.")
    m = _match(clause, _rule("confidentiality"))

    fake_item = _item(clause.id, _flag("inconsistent", "medium", "Term used inconsistently."))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert any(f.flag_type == "inconsistent" for f in flags)


# ---------------------------------------------------------------------------
# Counterparty path
# ---------------------------------------------------------------------------


def test_counterparty_deviation_flag() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("indemnification", "Vendor shall indemnify Client for all claims.")
    rule = _rule("indemnification", preferred="Mutual indemnification for gross negligence only.")
    m = _match(clause, rule)

    fake_item = _item(clause.id, _flag("deviation", "high", "Deviates materially."))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m])

    assert len(flags) == 1
    assert flags[0].flag_type == "deviation"
    assert flags[0].matched_rule_id == rule.id


def test_counterparty_ungoverned_clause_can_have_flags() -> None:
    """Clauses with rule=None must still produce flags on the counterparty path."""
    contract_id = uuid.uuid4()
    clause = _clause("payment", "Client waives all rights to dispute invoices.")
    m = _match(clause, rule=None)  # ungoverned

    fake_item = _item(clause.id, _flag("high_risk", "high", "Waiver of invoice dispute rights."))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "counterparty", [m])

    assert len(flags) == 1
    assert flags[0].flag_type == "high_risk"
    assert flags[0].matched_rule_id is None


def test_counterparty_ungoverned_clause_included_in_prompt() -> None:
    """Ungoverned clauses appear in the counterparty prompt (not silently dropped)."""
    contract_id = uuid.uuid4()
    governed = _match(_clause("indemnification"), _rule("indemnification"))
    ungoverned = _match(_clause("payment", "Client waives all rights."), rule=None)

    captured_messages: list[list[dict]] = []

    class CapturingFake(FakeLLMGateway):
        def call_structured(self, task, messages, response_model, cache_prefix=None):
            captured_messages.append(messages)
            items = [_item(governed.clause.id), _item(ungoverned.clause.id)]
            return _fake_result(*items)

    fake = CapturingFake()

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        run_layer2(contract_id, "counterparty", [governed, ungoverned])

    assert captured_messages
    msgs = captured_messages[0]
    user_msg = next(m["content"] for m in msgs if m.get("role") == "user")
    assert str(ungoverned.clause.id) in user_msg
    assert "payment" in user_msg


# ---------------------------------------------------------------------------
# Char-offset resolution
# ---------------------------------------------------------------------------


def test_offending_quote_resolved_to_contract_level_offsets() -> None:
    """char_start/char_end are clause.char_start + in-clause position of quote."""
    contract_id = uuid.uuid4()
    text = "This agreement grants unlimited liability to the vendor."
    clause = _clause("limitation_of_liability", text=text, char_start=300)
    m = _match(clause, _rule("limitation_of_liability"))

    quote = "unlimited liability"
    fake_item = _item(clause.id, _flag("high_risk", "high", "Too broad.", quote=quote))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert len(flags) == 1
    f = flags[0]
    expected_start = 300 + text.lower().index("unlimited liability")
    assert f.char_start == expected_start
    assert f.char_end == expected_start + len("unlimited liability")


def test_missing_quote_produces_none_offsets() -> None:
    """A flag with no offending_quote gets char_start=None, char_end=None."""
    contract_id = uuid.uuid4()
    clause = _clause("indemnification")
    m = _match(clause, _rule("indemnification"))

    fake_item = _item(clause.id, _flag("non_standard", quote=None))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags[0].char_start is None
    assert flags[0].char_end is None


def test_quote_not_found_in_clause_produces_none_offsets() -> None:
    """If the quote isn't found in clause text, offsets gracefully return None."""
    contract_id = uuid.uuid4()
    clause = _clause("indemnification", "Short text.")
    m = _match(clause, _rule("indemnification"))

    fake_item = _item(clause.id, _flag("high_risk", quote="text that is not there"))
    fake = FakeLLMGateway(structured_responses={"clause_analysis": _fake_result(fake_item)})

    with patch("app.services.contract_analysis.layer2_content.gateway", fake):
        flags = run_layer2(contract_id, "own", [m])

    assert flags[0].char_start is None
    assert flags[0].char_end is None


# ---------------------------------------------------------------------------
# Inconsistency candidate extraction
# ---------------------------------------------------------------------------


def test_find_inconsistency_candidates_returns_terms_in_minority_of_clauses() -> None:
    """Terms present in fewer than half the clauses are surfaced as candidates."""
    clauses = [
        _match(_clause("indemnification", "Confidential Information must be protected.")),
        _match(_clause("termination", "Either party may terminate the Agreement.")),
        _match(_clause("governing_law", "This Agreement is governed by Delaware law.")),
    ]
    # "Confidential Information" appears in 1/3 clauses → candidate
    candidates = _find_inconsistency_candidates(clauses)
    assert any("Confidential" in c for c in candidates)


def test_find_inconsistency_candidates_empty_input() -> None:
    assert _find_inconsistency_candidates([]) == []


def test_find_inconsistency_candidates_respects_limit() -> None:
    """Returns at most 20 candidates regardless of input size."""
    texts = [
        f"Term{i} is a defined term used in clause {i}." for i in range(50)
    ]
    clauses = [_match(_clause("indemnification", t)) for t in texts]
    candidates = _find_inconsistency_candidates(clauses)
    assert len(candidates) <= 20
