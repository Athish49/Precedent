"""Tests for S2 Layer 1 deterministic structural analysis (T-040; task 4.3).

Covers the rewritten red-line check (phrase/regex at rule, playbook and
global scope), the negation guard, and the missing-clause-per-family check,
plus the task 4.3 regression: the four benign probe sentences from
``playbook_status.md`` section 5 must not flag.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.contract_analysis.layer1_structural import negation_guard, run_layer1

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


def _red_line(
    key: str,
    condition_type: str,
    condition: dict,
    scope: str = "rule",
    playbook_id: uuid.UUID | None = None,
    action: str = "block",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        scope=scope,
        rule_id=None,
        playbook_id=playbook_id,
        key=key,
        description=f"Red line {key}",
        condition_type=condition_type,
        condition=condition,
        action=action,
        approver_role_id=None,
        rationale=None,
    )


def _rule(
    clause_type: str,
    required: bool = True,
    red_lines: list | None = None,
    rule_key: str | None = None,
    source_playbook_id: uuid.UUID | None = None,
) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.clause_type = clause_type
    r.required = required
    r.red_lines = red_lines or []
    r.rule_key = rule_key or f"{clause_type}.issue"
    r.source_playbook_id = source_playbook_id or uuid.uuid4()
    return r


# ---------------------------------------------------------------------------
# Missing-clause checks
# ---------------------------------------------------------------------------


def test_missing_required_clause_flagged() -> None:
    """A required clause absent from the contract produces a missing flag."""
    contract_id = uuid.uuid4()
    rule = _rule("indemnification", required=True)
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"indemnification": rule})
    assert len(flags) == 1
    f = flags[0]
    assert f.flag_type == "missing"
    assert f.severity == "high"
    assert f.source == "deterministic"
    assert f.clause_type == "indemnification"
    assert f.clause_id is None
    assert f.char_start is None
    assert f.char_end is None
    assert f.matched_rule_id == rule.id
    assert f.rule_key == rule.rule_key
    assert f.zone == "red"


def test_present_required_clause_not_flagged() -> None:
    """A required clause that is present produces no missing flag."""
    contract_id = uuid.uuid4()
    rule = _rule("indemnification", required=True)
    clause = _clause("indemnification")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"indemnification": rule})
    assert all(f.flag_type != "missing" for f in flags)


def test_non_required_absent_clause_not_flagged() -> None:
    """An absent clause that is not required produces no flag."""
    contract_id = uuid.uuid4()
    rule = _rule("governing_law", required=False)
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"governing_law": rule})
    assert flags == []


def test_multiple_missing_required_clauses() -> None:
    """Each missing required clause family produces its own flag."""
    contract_id = uuid.uuid4()
    rules = {
        "indemnification": _rule("indemnification", required=True),
        "termination": _rule("termination", required=True),
        "governing_law": _rule("governing_law", required=False),
    }
    flags = run_layer1(contract_id, clauses=[], resolved_rules=rules)
    missing_types = {f.clause_type for f in flags if f.flag_type == "missing"}
    assert missing_types == {"indemnification", "termination"}


def test_missing_flag_detail_contains_rule_id() -> None:
    """Missing flag detail records the playbook_rule_id for T-044 lookup."""
    contract_id = uuid.uuid4()
    rule = _rule("confidentiality", required=True)
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"confidentiality": rule})
    assert flags[0].detail["playbook_rule_id"] == str(rule.id)


def test_missing_reported_once_per_family_not_once_per_rule() -> None:
    """Task 4.3 item 3: one flag per clause family, even with several
    required rule_keys in that family.

    ``resolved_rules`` is already collapsed to one ``ResolvedRule`` per
    clause_type by ``routing.rules_by_clause_type`` (the caller's job, not
    run_layer1's) — several rule_keys sharing a family (e.g.
    ``limitation_of_liability.cap_amount`` and
    ``limitation_of_liability.carve_outs``) collapse to a single dict entry
    before run_layer1 ever sees them, so iterating that dict can only ever
    report the family once.
    """
    contract_id = uuid.uuid4()
    # Simulates what rules_by_clause_type already collapsed several
    # rule_keys in the "limitation_of_liability" family down to.
    representative_rule = _rule(
        "limitation_of_liability", required=True, rule_key="limitation_of_liability.cap_amount"
    )
    flags = run_layer1(
        contract_id, clauses=[], resolved_rules={"limitation_of_liability": representative_rule}
    )
    missing = [f for f in flags if f.flag_type == "missing"]
    assert len(missing) == 1
    assert missing[0].clause_type == "limitation_of_liability"


# ---------------------------------------------------------------------------
# negation_guard() — unit tests
# ---------------------------------------------------------------------------


def test_negation_guard_true_when_word_immediately_before() -> None:
    text = "There is no limitation of liability here."
    idx = text.index("limitation")
    assert negation_guard(text, idx) is True


def test_negation_guard_false_with_no_negation_word() -> None:
    text = "There is a limitation of liability here."
    idx = text.index("limitation")
    assert negation_guard(text, idx) is False


def test_negation_guard_false_when_word_beyond_60_chars() -> None:
    text = "Not withstanding anything else written here that is just filler, limitation applies."
    idx = text.index("limitation")
    # "Not" is index 0; confirm the gap exceeds 60 chars so the guard must not fire.
    assert idx > 60
    assert negation_guard(text, idx) is False


def test_negation_guard_false_across_sentence_boundary() -> None:
    text = "There is no doubt about that. Limitation of liability applies here."
    idx = text.index("Limitation")
    assert negation_guard(text, idx) is False


def test_negation_guard_case_insensitive() -> None:
    text = "NOTHING shall impose unlimited liability."
    idx = text.index("unlimited")
    assert negation_guard(text, idx) is True


def test_negation_guard_recognises_all_listed_words() -> None:
    phrase = "excludes special damages"
    for word in ("not", "no", "nothing", "neither", "never", "without"):
        text = f"{word} {phrase}"
        idx = text.index("excludes")
        assert negation_guard(text, idx) is True, f"{word!r} should trigger the guard"


# ---------------------------------------------------------------------------
# Red-line checks — rule scope
# ---------------------------------------------------------------------------


def test_phrase_red_line_match_produces_flag() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line("lol-no-limit", "phrase", {"any": ["no limitation"]})
    rule = _rule("limitation_of_liability", required=False, red_lines=[red_line])
    clause = _clause("limitation_of_liability", text="There shall be no limitation on damages.")
    flags = run_layer1(
        contract_id, clauses=[clause], resolved_rules={"limitation_of_liability": rule}
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1
    f = prohibited[0]
    assert f.severity == "high"
    assert f.source == "deterministic"
    assert f.clause_id == clause.id
    assert f.matched_rule_id == rule.id
    assert f.rule_key == rule.rule_key
    assert f.zone == "red"
    assert f.red_line_id == red_line.id
    assert f.detail["red_line_key"] == "lol-no-limit"
    assert f.detail["red_line_scope"] == "rule"
    assert f.detail["matched_text"] == "no limitation"


def test_phrase_red_line_case_insensitive() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line(
        "indem-unlimited", "phrase", {"any": ["unlimited indemnification"]}
    )
    rule = _rule("indemnification", red_lines=[red_line])
    clause = _clause("indemnification", text="This grants UNLIMITED INDEMNIFICATION to all.")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"indemnification": rule})
    assert any(f.flag_type == "prohibited" for f in flags)


def test_phrase_red_line_char_offsets_contract_level() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line("lol-unlimited", "phrase", {"any": ["unlimited liability"]})
    rule = _rule("limitation_of_liability", red_lines=[red_line])
    text = "The agreement includes unlimited liability for all breaches."
    clause = _clause("limitation_of_liability", text=text, char_start=500)
    flags = run_layer1(
        contract_id, clauses=[clause], resolved_rules={"limitation_of_liability": rule}
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1
    f = prohibited[0]
    in_clause_start = text.lower().index("unlimited liability")
    assert f.char_start == 500 + in_clause_start
    assert f.char_end == 500 + in_clause_start + len("unlimited liability")


def test_multiple_phrase_occurrences_produce_multiple_flags() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line("conf-no-obligation", "phrase", {"any": ["no obligation"]})
    rule = _rule("confidentiality", red_lines=[red_line])
    text = "There is no obligation to disclose. There is no obligation to act."
    clause = _clause("confidentiality", text=text)
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"confidentiality": rule})
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 2


def test_multiple_red_lines_each_flagged() -> None:
    contract_id = uuid.uuid4()
    rl1 = _red_line("indem-unlimited", "phrase", {"any": ["unlimited indemnification"]})
    rl2 = _red_line("indem-regardless", "phrase", {"any": ["indemnify regardless"]})
    rule = _rule("indemnification", red_lines=[rl1, rl2])
    text = "This provides unlimited indemnification and shall indemnify regardless of fault."
    clause = _clause("indemnification", text=text)
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"indemnification": rule})
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 2
    matched = {f.detail["red_line_key"] for f in prohibited}
    assert matched == {"indem-unlimited", "indem-regardless"}


def test_clause_with_no_matching_rule_not_flagged() -> None:
    """A clause whose type has no rule, and no playbook/global red lines
    are supplied, is not checked."""
    contract_id = uuid.uuid4()
    clause = _clause("payment", text="Payment shall be unlimited and unconditional.")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={})
    assert flags == []


def test_clause_with_no_red_lines_not_flagged() -> None:
    contract_id = uuid.uuid4()
    rule = _rule("governing_law", required=True, red_lines=[])
    clause = _clause("governing_law", text="Governed by the laws of Delaware.")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"governing_law": rule})
    assert not any(f.flag_type == "prohibited" for f in flags)


def test_semantic_and_parameter_red_lines_skipped_at_layer1() -> None:
    """Layer 1 is deterministic; semantic/parameter conditions need an LLM
    or an extracted value, so they are left for Layer 2 (task 4.4) /
    evaluator.py, not matched against raw text here."""
    contract_id = uuid.uuid4()
    semantic_rl = _red_line("lol-semantic", "semantic", {"test": "is liability uncapped?"})
    parameter_rl = _red_line(
        "lol-parameter", "parameter", {"parameter_key": "cap_months", "op": "gt", "value": 24}
    )
    rule = _rule("limitation_of_liability", red_lines=[semantic_rl, parameter_rl])
    clause = _clause(
        "limitation_of_liability", text="Liability is uncapped for cap_months beyond 24."
    )
    flags = run_layer1(
        contract_id, clauses=[clause], resolved_rules={"limitation_of_liability": rule}
    )
    assert flags == []


# ---------------------------------------------------------------------------
# Red-line checks — regex condition
# ---------------------------------------------------------------------------


def test_regex_red_line_match_produces_flag() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line(
        "gov-law-unspecified",
        "regex",
        {
            "pattern": r"laws? of the (jurisdiction|country) in which .{0,40} incorporated",
            "flags": "i",
        },
    )
    rule = _rule("governing_law", red_lines=[red_line])
    clause = _clause(
        "governing_law",
        text=(
            "This Agreement is governed by the law of the jurisdiction in which "
            "Customer is incorporated."
        ),
    )
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"governing_law": rule})
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1
    assert prohibited[0].detail["red_line_key"] == "gov-law-unspecified"


def test_regex_red_line_respects_negation_guard() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line(
        "payment-set-off", "regex", {"pattern": r"set[- ]off against fees", "flags": "i"}
    )
    rule = _rule("payment", red_lines=[red_line])
    clause = _clause(
        "payment",
        text="Customer shall never exercise set-off against Fees under any circumstances.",
    )
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"payment": rule})
    assert flags == []


def test_invalid_regex_pattern_does_not_raise() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line("broken", "regex", {"pattern": "("})  # invalid regex
    rule = _rule("payment", red_lines=[red_line])
    clause = _clause("payment", text="Net 30 days from invoice.")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={"payment": rule})
    assert flags == []


# ---------------------------------------------------------------------------
# Red-line checks — playbook scope
# ---------------------------------------------------------------------------


def test_playbook_scoped_red_line_matches_clause_under_its_playbook() -> None:
    contract_id = uuid.uuid4()
    playbook_id = uuid.uuid4()
    rule = _rule("audit", required=False, source_playbook_id=playbook_id)
    playbook_rl = _red_line(
        "audit-unannounced", "phrase", {"any": ["without prior notice"]},
        scope="playbook", playbook_id=playbook_id,
    )
    clause = _clause("audit", text="The auditor may inspect without prior notice.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"audit": rule},
        playbook_red_lines=[playbook_rl],
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1
    assert prohibited[0].detail["red_line_scope"] == "playbook"


def test_playbook_scoped_red_line_does_not_leak_to_another_playbook() -> None:
    contract_id = uuid.uuid4()
    rule = _rule("audit", required=False, source_playbook_id=uuid.uuid4())
    other_playbook_rl = _red_line(
        "audit-unannounced", "phrase", {"any": ["without prior notice"]},
        scope="playbook", playbook_id=uuid.uuid4(),  # a different playbook
    )
    clause = _clause("audit", text="The auditor may inspect without prior notice.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"audit": rule},
        playbook_red_lines=[other_playbook_rl],
    )
    assert flags == []


# ---------------------------------------------------------------------------
# Red-line checks — global scope
# ---------------------------------------------------------------------------


def test_global_red_line_matches_regardless_of_clause_type() -> None:
    """A global red line applies document-wide, even to a clause whose type
    has no governing rule at all."""
    contract_id = uuid.uuid4()
    global_rl = _red_line(
        "global-non-compete", "phrase", {"any": ["shall not compete"]}, scope="global"
    )
    clause = _clause("miscellaneous", text="Halcyon shall not compete in Customer's territory.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={},
        global_red_lines=[global_rl],
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1
    assert prohibited[0].detail["red_line_scope"] == "global"
    assert prohibited[0].matched_rule_id is None
    assert prohibited[0].rule_key is None


def test_global_semantic_red_line_not_evaluated_at_layer1() -> None:
    """All 12 seeded global red lines are condition_type 'semantic'
    (authority.yaml) — Layer 1 must not attempt to text-match them."""
    contract_id = uuid.uuid4()
    global_rl = _red_line(
        "global-uncapped-liability", "semantic", {"test": "is liability uncapped?"}
    )
    clause = _clause("limitation_of_liability", text="Liability is uncapped for all claims.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={},
        global_red_lines=[global_rl],
    )
    assert flags == []


# ---------------------------------------------------------------------------
# Combined behaviour
# ---------------------------------------------------------------------------


def test_run_layer1_combines_missing_and_red_line_checks() -> None:
    contract_id = uuid.uuid4()
    red_line = _red_line("indem-unlimited", "phrase", {"any": ["unlimited indemnification"]})
    rule_indem = _rule("indemnification", required=True, red_lines=[red_line])
    rule_term = _rule("termination", required=True, red_lines=[])
    clause_indem = _clause(
        "indemnification", text="This grants unlimited indemnification to all."
    )
    resolved_rules = {"indemnification": rule_indem, "termination": rule_term}
    flags = run_layer1(contract_id, clauses=[clause_indem], resolved_rules=resolved_rules)
    types = {f.flag_type for f in flags}
    assert "missing" in types  # termination absent
    assert "prohibited" in types  # unlimited indemnification match


def test_empty_contract_all_required_missing() -> None:
    contract_id = uuid.uuid4()
    rules = {
        "data_protection": _rule("data_protection", required=True),
        "compliance": _rule("compliance", required=True),
        "audit": _rule("audit", required=True),
    }
    flags = run_layer1(contract_id, clauses=[], resolved_rules=rules)
    assert len(flags) == 3
    assert all(f.flag_type == "missing" for f in flags)


def test_no_rules_no_flags() -> None:
    contract_id = uuid.uuid4()
    clause = _clause("indemnification", text="Party A shall indemnify Party B in all cases.")
    flags = run_layer1(contract_id, clauses=[clause], resolved_rules={})
    assert flags == []


# ---------------------------------------------------------------------------
# Task 4.3 regression: the four benign probe sentences
# (playbook_status.md section 5) must not flag.
# ---------------------------------------------------------------------------


def test_four_benign_probe_sentences_do_not_flag() -> None:
    """The four sentences the pre-4.3 ``prohibited_terms`` loop wrongly
    flagged (``playbook_status.md`` section 5), run verbatim.

    Sentences 1-3 each place one of the task's negation words ("Nothing",
    "not", "no") earlier in the same sentence than a phrase a red line bans
    outright — the negation guard is what keeps them from flagging (see
    ``test_negation_guard_disabled_lets_negated_phrase_flag`` below for the
    control that proves the guard is doing the work).

    Sentence 4 contains no negation word at all ("...optional language has
    been removed"); what stops it is scoping, not the guard. The pre-4.3
    mechanism flagged on crude single/double-word substrings (deleted along
    with ``scripts/seed_playbooks.py``). A red line authored precisely
    enough to name the actual risk — "compliance with HIPAA is optional" —
    is never a substring of this sentence's wording ("HIPAA compliance
    optional language"), so it is never a match candidate. This is a
    deliberate judgment call: task 4.3 only specifies the negation-word
    guard, so sentence 4's fix is the move from unscoped substrings to
    scoped, specific phrase/regex red lines, not a second guard mechanism.
    """
    contract_id = uuid.uuid4()

    liability_rl = _red_line("lol-uncapped-phrase", "phrase", {"any": ["unlimited liability"]})
    confidentiality_rl = _red_line(
        "conf-waiver-phrase", "phrase", {"any": ["waiver of confidentiality"]}
    )
    termination_rl = _red_line("term-no-right-phrase", "phrase", {"any": ["termination right"]})
    hipaa_rl = _red_line(
        "hipaa-compliance-optional",
        "phrase",
        {"any": ["compliance with hipaa is optional", "hipaa compliance is optional"]},
    )

    resolved_rules = {
        "limitation_of_liability": _rule(
            "limitation_of_liability", required=False, red_lines=[liability_rl]
        ),
        "confidentiality": _rule(
            "confidentiality", required=False, red_lines=[confidentiality_rl]
        ),
        "termination": _rule("termination", required=False, red_lines=[termination_rl]),
        "data_protection": _rule("data_protection", required=False, red_lines=[hipaa_rl]),
    }

    clauses = [
        _clause(
            "limitation_of_liability",
            "Nothing in this Agreement shall impose unlimited liability on either party.",
        ),
        _clause(
            "confidentiality",
            "This clause shall not be construed as a waiver of confidentiality.",
        ),
        _clause(
            "termination",
            "This Section shall not be read as granting no termination right to Customer.",
        ),
        _clause(
            "data_protection",
            "The parties acknowledge that HIPAA compliance optional language has been removed.",
        ),
    ]

    flags = run_layer1(contract_id, clauses=clauses, resolved_rules=resolved_rules)
    assert flags == [], f"expected no flags, got: {[(f.flag_type, f.detail) for f in flags]}"


def test_negation_guard_disabled_lets_negated_phrase_flag() -> None:
    """Control for the probe-sentence regression above: with
    ``negation_guard: false`` on the condition, the identical phrase in the
    identical negated sentence (probe 1) does flag — proving the guard,
    not scoping, is what kept that sentence green."""
    contract_id = uuid.uuid4()
    red_line = _red_line(
        "lol-uncapped-phrase",
        "phrase",
        {"any": ["unlimited liability"], "negation_guard": False},
    )
    rule = _rule("limitation_of_liability", required=False, red_lines=[red_line])
    clause = _clause(
        "limitation_of_liability",
        "Nothing in this Agreement shall impose unlimited liability on either party.",
    )
    flags = run_layer1(
        contract_id, clauses=[clause], resolved_rules={"limitation_of_liability": rule}
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert len(prohibited) == 1


# ---------------------------------------------------------------------------
# Full clause families (no one-rule-per-clause_type collapse)
# ---------------------------------------------------------------------------


def test_missing_fires_when_first_rule_optional_but_later_rule_required() -> None:
    """Regression: routing.rules_by_clause_type kept only the first rule
    (by rule_key) per family, so an optional first rule hid a required
    sibling and the family was never reported missing."""
    contract_id = uuid.uuid4()
    optional = _rule("audit", required=False, rule_key="audit.a_optional")
    required = _rule("audit", required=True, rule_key="audit.b_required")
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"audit": [optional, required]})
    missing = [f for f in flags if f.flag_type == "missing"]
    assert len(missing) == 1
    assert missing[0].matched_rule_id == required.id
    assert missing[0].rule_key == "audit.b_required"
    assert missing[0].detail["required_rule_keys"] == ["audit.b_required"]


def test_missing_family_lists_every_required_rule_key_once() -> None:
    contract_id = uuid.uuid4()
    a = _rule("audit", required=True, rule_key="audit.a")
    b = _rule("audit", required=False, rule_key="audit.b")
    c = _rule("audit", required=True, rule_key="audit.c")
    flags = run_layer1(contract_id, clauses=[], resolved_rules={"audit": [a, b, c]})
    assert len(flags) == 1
    assert flags[0].rule_key == "audit.a"
    assert flags[0].detail["required_rule_keys"] == ["audit.a", "audit.c"]


def test_family_with_no_required_rule_not_missing() -> None:
    contract_id = uuid.uuid4()
    rules = [_rule("audit", required=False, rule_key=f"audit.{k}") for k in "ab"]
    assert run_layer1(contract_id, clauses=[], resolved_rules={"audit": rules}) == []


def test_present_family_not_missing_even_with_several_required_rules() -> None:
    contract_id = uuid.uuid4()
    rules = [_rule("audit", required=True, rule_key=f"audit.{k}") for k in "ab"]
    flags = run_layer1(contract_id, clauses=[_clause("audit")], resolved_rules={"audit": rules})
    assert all(f.flag_type != "missing" for f in flags)


def test_red_lines_of_every_rule_in_family_checked_and_attributed_to_owner() -> None:
    """Regression: only the first rule's red lines were checked before."""
    contract_id = uuid.uuid4()
    rl_a = _red_line("audit-a", "phrase", {"any": ["unlimited audits"]})
    rl_b = _red_line("audit-b", "phrase", {"any": ["without prior notice"]})
    rule_a = _rule("audit", required=False, red_lines=[rl_a], rule_key="audit.a")
    rule_b = _rule("audit", required=False, red_lines=[rl_b], rule_key="audit.b")
    clause = _clause("audit", text="Customer may conduct unlimited audits without prior notice.")
    flags = run_layer1(
        contract_id, clauses=[clause], resolved_rules={"audit": [rule_a, rule_b]}
    )
    by_key = {f.detail["red_line_key"]: f for f in flags if f.flag_type == "prohibited"}
    assert set(by_key) == {"audit-a", "audit-b"}
    assert by_key["audit-a"].matched_rule_id == rule_a.id
    assert by_key["audit-a"].rule_key == "audit.a"
    assert by_key["audit-b"].matched_rule_id == rule_b.id
    assert by_key["audit-b"].rule_key == "audit.b"
    assert all(f.detail["red_line_scope"] == "rule" for f in by_key.values())


def test_group_rules_by_clause_type_keeps_every_rule() -> None:
    from app.services.contract_analysis.layer1_structural import group_rules_by_clause_type

    a1 = _rule("audit", rule_key="audit.a")
    a2 = _rule("audit", rule_key="audit.b")
    t = _rule("termination", rule_key="termination.x")
    grouped = group_rules_by_clause_type([a1, a2, t])
    assert grouped == {"audit": [a1, a2], "termination": [t]}


# ---------------------------------------------------------------------------
# Playbook/global-scope phrase/regex red lines: every clause, no rule
# ---------------------------------------------------------------------------


def test_playbook_scoped_red_line_checked_against_every_clause_unattributed() -> None:
    """A playbook-scope red line (of a contributing playbook) is not tied to
    one clause family: it is checked against every clause, including
    ungoverned ones, and carries no rule attribution."""
    contract_id = uuid.uuid4()
    playbook_id = uuid.uuid4()
    rule = _rule("audit", required=False, source_playbook_id=playbook_id)
    playbook_rl = _red_line(
        "pb-escrow", "regex", {"pattern": r"source code escrow", "flags": "i"},
        scope="playbook", playbook_id=playbook_id,
    )
    governed = _clause("audit", text="Source code escrow applies to audits.")
    ungoverned = _clause("misc", text="Vendor shall maintain a Source Code Escrow.")
    flags = run_layer1(
        contract_id,
        clauses=[governed, ungoverned],
        resolved_rules={"audit": [rule]},
        playbook_red_lines=[playbook_rl],
    )
    prohibited = [f for f in flags if f.flag_type == "prohibited"]
    assert {f.clause_id for f in prohibited} == {governed.id, ungoverned.id}
    for f in prohibited:
        assert f.matched_rule_id is None
        assert f.rule_key is None
        assert f.red_line_id == playbook_rl.id
        assert f.detail["red_line_scope"] == "playbook"
        assert f.zone == "red"


def test_global_phrase_red_line_on_governed_clause_not_attributed_to_rule() -> None:
    contract_id = uuid.uuid4()
    rule = _rule("audit", required=False)
    global_rl = _red_line(
        "global-no-compete", "phrase", {"any": ["shall not compete"]}, scope="global"
    )
    clause = _clause("audit", text="Vendor shall not compete with Customer.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"audit": [rule]},
        global_red_lines=[global_rl],
    )
    assert len(flags) == 1
    assert flags[0].matched_rule_id is None
    assert flags[0].rule_key is None
    assert flags[0].red_line_id == global_rl.id
    assert flags[0].detail["red_line_scope"] == "global"


def test_rule_scope_red_line_hits_only_collects_rule_scope() -> None:
    from app.services.contract_analysis.layer1_structural import rule_scope_red_line_hits

    contract_id = uuid.uuid4()
    rule_rl = _red_line("audit-a", "phrase", {"any": ["unlimited audits"]})
    rule = _rule("audit", required=False, red_lines=[rule_rl])
    global_rl = _red_line("g", "phrase", {"any": ["unlimited audits"]}, scope="global")
    clause = _clause("audit", text="Customer may conduct unlimited audits.")
    flags = run_layer1(
        contract_id,
        clauses=[clause],
        resolved_rules={"audit": [rule]},
        global_red_lines=[global_rl],
    )
    assert len([f for f in flags if f.flag_type == "prohibited"]) == 2
    assert rule_scope_red_line_hits(flags) == {(clause.id, rule.id): {rule_rl.id}}
