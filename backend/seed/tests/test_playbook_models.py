"""Tests for the playbook seed models and validator (task 0.2).

Fixtures live in ``fixtures/``:

* ``fixtures/valid/`` is a small, complete data directory: a taxonomy, an
  authority file and two playbooks with three rules. The first rule of
  ``playbooks/saas_msa_vendor/risk.yaml`` is the example from section 4 of
  ``playbook_implementation.md`` written out in full. It validates with no
  errors and no warnings, also under ``--strict``.
* ``fixtures/invalid/<case>.yaml`` is one failing case each. A case names a
  file of the valid directory, the edits to make to it (or raw replacement
  text), and the finding the validator must report. The test applies it to a
  temporary copy of ``fixtures/valid``.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from seed.common import SeedError, load_yaml
from seed.playbooks import models
from seed.playbooks.validate import (
    SeedValidationError,
    check_directory,
    find_placeholder,
    has_errors,
    load_directory,
    load_valid_directory,
    main,
    mentions_number,
    select_issues,
    sentence_count,
    validate_directory,
)

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valid"
INVALID_CASES = sorted((FIXTURES / "invalid").glob("*.yaml"))

RISK = "playbooks/saas_msa_vendor/risk.yaml"
BASELINE_RULES = "playbooks/baseline/rules.yaml"
CAP = "limitation_of_liability.cap_amount"
SUPER_CAP = "limitation_of_liability.data_breach_super_cap"


# -- helpers -----------------------------------------------------------------


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    """A writable copy of the valid fixture."""
    target = tmp_path / "data"
    shutil.copytree(VALID, target)
    return target


def edit(root: Path, file: str, edits: list[dict[str, Any]]) -> None:
    """Apply ``{path, set}`` / ``{path, delete}`` edits to one YAML file."""
    path = root / file
    doc = load_yaml(path)
    for item in edits:
        *parents, last = item["path"]
        node = doc
        for part in parents:
            node = node[part]
        if item.get("delete"):
            del node[last]
        else:
            node[last] = item["set"]
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")


def codes(issues: list[models.Issue], level: str | None = None) -> set[str]:
    return {i.code for i in issues if level is None or i.level == level}


def find(issues: list[models.Issue], code: str) -> list[models.Issue]:
    return [i for i in issues if i.code == code]


# -- the valid fixture ---------------------------------------------------------


def test_valid_fixture_has_no_findings() -> None:
    seed, issues = validate_directory(VALID, strict=True)
    assert [i.format(seed.root) for i in issues] == []
    assert main([str(VALID), "--strict"]) == 0


def test_valid_fixture_loads_into_typed_objects() -> None:
    seed = load_valid_directory(VALID)

    assert isinstance(seed.taxonomy, models.Taxonomy)
    assert len(seed.taxonomy.expected_families) == 4
    assert len(seed.taxonomy.issues) == 4
    assert isinstance(seed.authority, models.Authority)
    assert [d.key for d in seed.authority.context_dimensions] == [
        "deal_value_band",
        "counterparty_tier",
        "data_sensitivity",
        "region",
        "regimes",
    ]
    assert seed.authority.role_keys() == {
        "contracts_manager",
        "commercial_counsel",
        "cfo",
        "general_counsel",
    }
    assert len(seed.authority.global_red_lines) == 2
    assert len(seed.authority.escalation_policies) == 3

    assert [pb.key for pb in seed.playbooks] == ["halcyon-baseline", "halcyon-saas-msa-vendor"]
    saas = seed.playbook("halcyon-saas-msa-vendor")
    assert saas is not None and saas.header is not None
    assert saas.header.parent == "halcyon-baseline"
    assert saas.header.version.version == "1.0"
    assert saas.header.version.status == "published"
    assert saas.header.version.effective_from == dt.date(2026, 1, 15)
    assert [r.rule_key for r in saas.rules] == [CAP, SUPER_CAP]
    assert all(r.source == VALID / RISK for r in saas.rules)
    assert [r.index for r in saas.rules] == [0, 1]
    assert len(seed.all_rules()) == 3
    assert set(seed.rules_by_key()) == {CAP, SUPER_CAP, "governing_law.choice_of_law"}


def test_section_4_example_is_written_out_in_full() -> None:
    seed = load_valid_directory(VALID)
    rule = seed.playbook("halcyon-saas-msa-vendor").rule(CAP).rule

    assert rule.risk_weight == 10 and rule.negotiable and rule.default_zone == "yellow"
    assert rule.last_reviewed_at == dt.date(2026, 1, 10)
    assert rule.preferred.label == "12-month cap"
    assert [(p.rung, p.zone, p.approver_role) for p in rule.fallbacks] == [
        (1, "yellow", "commercial_counsel"),
        (2, "yellow", "general_counsel"),
    ]
    assert rule.fallbacks[0].conditions == {"deal_value_band": ["mid", "enterprise", "strategic"]}
    assert len(rule.variants) == 1
    assert "US$[amount]" in rule.variants[0].language  # a bracketed blank is legitimate
    assert rule.position_at(0) is rule.preferred and rule.position_at(2).label == "24-month cap"
    for position in rule.positions:
        assert find_placeholder(position.language) is None
        assert position.language == position.language.strip()

    parameter = rule.parameters[0]
    assert (parameter.preferred_value, parameter.green_limit, parameter.yellow_limit) == (
        12,
        12,
        24,
    )
    assert parameter.context_overrides[0].when == {"deal_value_band": ["strategic"]}
    assert parameter.context_overrides[0].yellow_limit == 36

    condition = models.parse_red_line_condition(rule.red_lines[0])
    assert isinstance(condition, models.SemanticCondition)
    assert rule.objections[0].recommended_position.rule_key == SUPER_CAP
    assert rule.dependencies[0].relation == "trade_against"
    assert {t.expected_outcome for t in rule.test_cases} >= {
        "compliant",
        "acceptable_variant",
        "fallback",
        "deviation",
        "red_line",
    }
    assert any(t.is_trap for t in rule.test_cases)


def test_red_line_conditions_parse_by_type() -> None:
    seed = load_valid_directory(VALID)
    red_lines = seed.playbook("halcyon-baseline").rules[0].rule.red_lines
    parsed = [models.parse_red_line_condition(r) for r in red_lines]
    assert [type(c) for c in parsed] == [
        models.ParameterCondition,
        models.PhraseCondition,
        models.RegexCondition,
    ]
    assert parsed[1].negation_guard is True
    assert parsed[2].flags == "i"


# -- failing fixtures ------------------------------------------------------------


def test_there_are_at_least_eight_failing_fixtures() -> None:
    assert len(INVALID_CASES) >= 8


@pytest.mark.parametrize("case_path", INVALID_CASES, ids=lambda p: p.stem)
def test_failing_fixture_is_reported(
    case_path: Path, seed_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = load_yaml(case_path)
    if "raw" in case:
        (seed_dir / case["file"]).write_text(case["raw"], encoding="utf-8")
    else:
        edit(seed_dir, case["file"], case["edits"])
    expect = case["expect"]

    seed, issues = validate_directory(seed_dir)
    matching = [
        i
        for i in issues
        if i.code == expect["code"]
        and i.is_error
        and i.file == seed_dir / case["file"]
        and ("rule_key" not in expect or i.rule_key == expect["rule_key"])
        and expect["message"] in i.format(seed.root)
    ]
    assert matching, f"{case['description']}\nexpected {expect}, got:\n" + "\n".join(
        i.format(seed.root) for i in issues
    )

    # The command fails and prints file, rule key and message.
    assert main([str(seed_dir)]) == 1
    out = capsys.readouterr().out
    line = matching[0].format(seed.root)
    assert line in out
    assert line.startswith("ERROR") and case["file"] in line
    if "rule_key" in expect:
        assert f"[{expect['rule_key']}]" in line


def test_every_error_in_a_rule_is_reported_in_one_run(seed_dir: Path) -> None:
    edit(
        seed_dir,
        RISK,
        [
            {"path": ["rules", 0, "positions", 1, "approver_role"], "delete": True},
            {"path": ["rules", 0, "positions", 2, "rung"], "set": 4},
            {"path": ["rules", 0, "objections", 1], "delete": True},
            {"path": ["rules", 0, "positions", 0, "language"], "set": "Liability is capped at ..."},
        ],
    )
    _, issues = validate_directory(seed_dir)
    assert codes(issues, "error") >= {
        "position.approver_missing",
        "position.rung_sequence",
        "minimum.objections",
        "text.placeholder",
    }
    assert {i.rule_key for i in issues} == {CAP}


def test_load_valid_directory_raises_with_all_findings(seed_dir: Path) -> None:
    edit(seed_dir, RISK, [{"path": ["rules", 0, "positions", 3], "delete": True}])
    with pytest.raises(SeedValidationError) as caught:
        load_valid_directory(seed_dir)
    assert isinstance(caught.value, SeedError)
    assert "minimum.variants" in str(caught.value)
    assert has_errors(caught.value.issues)


# -- rules that are not negotiable ---------------------------------------------


def _make_non_negotiable(seed_dir: Path, replacement_outcome: str) -> None:
    doc = load_yaml(seed_dir / RISK)
    rule = doc["rules"][0]
    rule["negotiable"] = False
    rule["positions"] = [p for p in rule["positions"] if p["kind"] != "fallback"]
    rule["objections"] = []
    case = rule["test_cases"][2]  # the fallback case
    case.pop("expected_position_rung")
    case["expected_outcome"] = replacement_outcome
    case["expected_zone"] = "red"
    if replacement_outcome == "missing":
        case["sample_text"] = ""
    (seed_dir / RISK).write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize("replacement", ["missing", "deviation"])
def test_non_negotiable_rule_needs_no_fallbacks_or_objections(
    seed_dir: Path, replacement: str
) -> None:
    _make_non_negotiable(seed_dir, replacement)
    _, issues = validate_directory(seed_dir, strict=True)
    assert not has_errors(issues), [i.format(seed_dir) for i in issues]


def test_non_negotiable_rule_still_needs_a_case_in_place_of_the_fallback(seed_dir: Path) -> None:
    _make_non_negotiable(seed_dir, "missing")
    edit(seed_dir, RISK, [{"path": ["rules", 0, "test_cases", 2], "delete": True}])
    _, issues = validate_directory(seed_dir)
    (issue,) = find(issues, "minimum.test_case_mix")
    assert "missing or a second deviation" in issue.message
    assert "minimum.variants" not in codes(issues)


def test_non_negotiable_rule_still_needs_a_variant(seed_dir: Path) -> None:
    _make_non_negotiable(seed_dir, "missing")
    edit(seed_dir, RISK, [{"path": ["rules", 0, "positions", 1], "delete": True}])
    _, issues = validate_directory(seed_dir)
    assert "minimum.variants" in codes(issues, "error")


# -- warnings ------------------------------------------------------------------


def test_number_in_language_without_parameter_is_a_warning(seed_dir: Path) -> None:
    edit(seed_dir, RISK, [{"path": ["rules", 0, "parameters"], "set": []}])
    _, issues = validate_directory(seed_dir, strict=True)
    (issue,) = find(issues, "minimum.parameters")
    assert issue.level == "warning" and issue.rule_key == CAP
    assert not has_errors(issues)
    assert main([str(seed_dir), "--strict"]) == 0


def test_fallback_case_zone_differs_from_rung_zone_is_a_warning(seed_dir: Path) -> None:
    edit(seed_dir, RISK, [{"path": ["rules", 0, "test_cases", 2, "expected_zone"], "set": "red"}])
    _, issues = validate_directory(seed_dir)
    assert codes(issues) == {"test_case.zone_mismatch"}
    assert not has_errors(issues)


def test_unparseable_version_file_is_a_schema_error(seed_dir: Path) -> None:
    (seed_dir / "versions").mkdir()
    (seed_dir / "versions" / "saas_msa_vendor_1_1.yaml").write_text("not: validated\n")
    seed, issues = validate_directory(seed_dir, strict=True)
    assert codes(issues, "error") == {"schema"}
    assert seed.versions == []
    assert len(seed.all_rules()) == 3  # the broken version file contributes no rules


def test_version_file_rules_are_checked_like_a_playbooks_own(seed_dir: Path) -> None:
    doc = load_yaml(seed_dir / RISK)
    version_doc = {
        "playbook_key": "halcyon-saas-msa-vendor",
        "based_on_version": "1.0",
        "version": {
            "version": "1.1",
            "effective_from": "2026-07-01",
            "change_summary": "Test version.",
            "created_by": "Senior Commercial Counsel",
            "approved_by": "General Counsel",
        },
        "changes": [
            {
                "field_path": f"{CAP}.risk_weight",
                "change_type": "modified",
                "old_value": 10,
                "new_value": 9,
                "reason": "Example change for the test fixture.",
            }
        ],
        "rules": doc["rules"],
    }
    (seed_dir / "versions").mkdir()
    (seed_dir / "versions" / "saas_msa_vendor_1_1.yaml").write_text(
        yaml.safe_dump(version_doc, sort_keys=False), encoding="utf-8"
    )
    seed, issues = validate_directory(seed_dir, strict=True)
    # The lone change entry is far below the 3.14 change-log quota, which is
    # checked across the whole versions/ directory, not by this test.
    assert codes(issues) == {"version.change_log_minimum"}
    assert len(seed.versions) == 1
    assert seed.versions[0].version_set.playbook_key == "halcyon-saas-msa-vendor"
    assert len(seed.versions[0].version_set.changes) == 1

    # A broken rule inside a version file is reported exactly like a broken
    # playbook rule (same cross-checks, e.g. a missing acceptable_variant).
    version_doc["rules"] = [
        {**doc["rules"][0], "positions": [p for p in doc["rules"][0]["positions"] if p["kind"] != "acceptable_variant"]},
        doc["rules"][1],
    ]
    (seed_dir / "versions" / "saas_msa_vendor_1_1.yaml").write_text(
        yaml.safe_dump(version_doc, sort_keys=False), encoding="utf-8"
    )
    _, issues = validate_directory(seed_dir)
    assert "minimum.variants" in codes(issues, "error")

    # A playbook_key that does not match any loaded playbook is an error.
    version_doc["playbook_key"] = "halcyon-nope"
    version_doc["rules"] = doc["rules"]
    (seed_dir / "versions" / "saas_msa_vendor_1_1.yaml").write_text(
        yaml.safe_dump(version_doc, sort_keys=False), encoding="utf-8"
    )
    _, issues = validate_directory(seed_dir)
    assert "version.unknown_playbook" in codes(issues, "error")


def test_version_change_log_minimums_are_enforced(seed_dir: Path) -> None:
    doc = load_yaml(seed_dir / RISK)
    version_doc = {
        "playbook_key": "halcyon-saas-msa-vendor",
        "based_on_version": "1.0",
        "version": {
            "version": "1.1",
            "effective_from": "2026-07-01",
            "change_summary": "Test version.",
            "created_by": "Senior Commercial Counsel",
            "approved_by": "General Counsel",
        },
        "changes": [
            {
                "field_path": f"{CAP}.risk_weight",
                "change_type": "modified",
                "old_value": 10,
                "new_value": 9,
                "reason": "Only one change; below every minimum.",
            }
        ],
        "rules": doc["rules"],
    }
    (seed_dir / "versions").mkdir()
    (seed_dir / "versions" / "saas_msa_vendor_1_1.yaml").write_text(
        yaml.safe_dump(version_doc, sort_keys=False), encoding="utf-8"
    )
    _, issues = validate_directory(seed_dir)
    messages = [i.message for i in issues if i.code == "version.change_log_minimum"]
    assert any("20 change-log entries" in m for m in messages)
    assert any("'modified'" in m for m in messages)
    assert any("'added'" in m for m in messages)
    assert any("'removed'" in m for m in messages)


# -- partly written directories ---------------------------------------------------


def test_empty_directory_is_warnings_only(tmp_path: Path) -> None:
    seed, issues = validate_directory(tmp_path)
    assert codes(issues) == {"taxonomy.missing", "authority.missing", "playbooks.missing"}
    assert not has_errors(issues)
    assert all(i.pending for i in issues)
    assert seed.taxonomy is None and seed.authority is None and seed.playbooks == []
    assert main([str(tmp_path)]) == 0
    assert main([str(tmp_path), "--strict"]) == 1


def test_missing_directory_fails(tmp_path: Path) -> None:
    assert main([str(tmp_path / "nope")]) == 1


def test_one_rule_file_alone_validates(tmp_path: Path) -> None:
    folder = tmp_path / "playbooks" / "saas_msa_vendor"
    folder.mkdir(parents=True)
    shutil.copy(VALID / RISK, folder / "risk.yaml")

    seed, issues = validate_directory(tmp_path)
    assert not has_errors(issues), [i.format(tmp_path) for i in issues]
    assert codes(issues) == {
        "taxonomy.missing",
        "authority.missing",
        "playbook.header_missing",
        "test_case.red_line_pending",  # the case that expects a global red line
    }
    (playbook,) = seed.playbooks
    assert playbook.header is None and playbook.key == "saas_msa_vendor"
    assert len(playbook.rules) == 2

    # Checks that need no other file still run.
    edit(tmp_path, RISK, [{"path": ["rules", 0, "positions", 1, "approver_role"], "delete": True}])
    assert "position.approver_missing" in codes(validate_directory(tmp_path)[1], "error")


def test_listed_rule_file_not_written_yet_is_a_warning(seed_dir: Path) -> None:
    edit(
        seed_dir,
        "playbooks/saas_msa_vendor/playbook.yaml",
        [
            {"path": ["rule_files"], "set": ["commercial.yaml", "risk.yaml", "data.yaml"]},
        ],
    )
    seed, issues = validate_directory(seed_dir)
    assert codes(issues) == {"playbook.rule_file_missing"}
    assert not has_errors(issues)
    assert seed.playbook("halcyon-saas-msa-vendor").missing_rule_files == [
        "commercial.yaml",
        "data.yaml",
    ]
    assert has_errors(validate_directory(seed_dir, strict=True)[1])


def test_unlisted_rule_file_is_validated_and_warned_about(seed_dir: Path) -> None:
    shutil.copy(seed_dir / BASELINE_RULES, seed_dir / "playbooks/saas_msa_vendor/extra.yaml")
    seed, issues = validate_directory(seed_dir)
    assert codes(issues) == {"playbook.rule_file_unlisted"}
    assert len(seed.playbook("halcyon-saas-msa-vendor").rules) == 3


def test_reference_to_a_rule_not_written_yet_is_a_warning(seed_dir: Path) -> None:
    # Drop the super-cap rule: cap_amount still points at it, and it is in the taxonomy.
    edit(seed_dir, RISK, [{"path": ["rules", 1], "delete": True}])
    _, issues = validate_directory(seed_dir)
    assert codes(issues) == {"objection.recommended_position_pending", "dependency.pending"}
    assert not has_errors(issues)
    assert has_errors(validate_directory(seed_dir, strict=True)[1])


def test_reference_resolves_against_a_rule_in_another_playbook(seed_dir: Path) -> None:
    edit(
        seed_dir,
        RISK,
        [
            {
                "path": ["rules", 0, "objections", 1, "recommended_position"],
                "set": {"rule_key": "governing_law.choice_of_law", "rung": 2},
            },
            {
                "path": ["rules", 0, "dependencies", 0, "related_rule_key"],
                "set": "governing_law.choice_of_law",
            },
        ],
    )
    assert validate_directory(seed_dir, strict=True)[1] == []

    edit(
        seed_dir,
        RISK,
        [{"path": ["rules", 0, "objections", 1, "recommended_position", "rung"], "set": 3}],
    )
    assert codes(validate_directory(seed_dir)[1], "error") == {"objection.recommended_position"}


def test_parent_playbook_not_written_yet_is_a_warning(seed_dir: Path) -> None:
    shutil.rmtree(seed_dir / "playbooks/baseline")
    _, issues = validate_directory(seed_dir)
    assert codes(issues) == {"playbook.parent_pending"}
    assert not has_errors(issues)


def test_broken_authority_file_skips_its_cross_checks(seed_dir: Path) -> None:
    edit(seed_dir, "authority.yaml", [{"path": ["roles", 0, "function"], "set": "marketing"}])
    seed, issues = validate_directory(seed_dir)
    assert seed.authority is None
    assert codes(issues, "error") == {"schema"}
    assert "authority.invalid" in codes(issues, "warning")
    assert "role.unknown" not in codes(issues)


# -- --only --------------------------------------------------------------------


def test_only_reports_on_matching_files_but_loads_everything(
    seed_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edit(seed_dir, BASELINE_RULES, [{"path": ["rules", 0, "positions", 3], "delete": True}])
    assert main([str(seed_dir)]) == 1

    # The saas file is clean, and its references into other files still resolve.
    capsys.readouterr()
    assert main([str(seed_dir), "--only", RISK]) == 0
    out = capsys.readouterr().out
    assert "3 rule(s) loaded" in out and "0 error(s)" in out and "minimum.variants" not in out

    assert main([str(seed_dir), "--only", str(seed_dir / BASELINE_RULES)]) == 1
    assert main([str(seed_dir), "--only", "playbooks/baseline"]) == 1  # a folder
    assert main([str(seed_dir), "--only", "*/baseline/*.yaml"]) == 1  # a glob
    assert (
        main([str(seed_dir), "--only", "risk.yaml", "--only", "taxonomy.yaml"]) == 0
    )  # bare names


def test_only_that_matches_nothing_fails(
    seed_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(seed_dir), "--only", "playbooks/nope/rules.yaml"]) == 1
    assert "matches no seed file" in capsys.readouterr().err


def test_only_keeps_the_missing_reference_file_notice(seed_dir: Path) -> None:
    (seed_dir / "authority.yaml").unlink()
    seed, issues = validate_directory(seed_dir)
    kept = select_issues(issues, seed, [BASELINE_RULES])
    assert codes(kept) == {"authority.missing"}


# -- API pieces ------------------------------------------------------------------


def test_load_and_check_are_separate_steps(seed_dir: Path) -> None:
    edit(
        seed_dir,
        RISK,
        [
            {"path": ["rules", 0, "surprise"], "set": 1},  # model error: found while loading
            {"path": ["rules", 1, "positions", 3], "delete": True},  # cross-check
        ],
    )
    seed = load_directory(seed_dir)
    assert codes(seed.issues) == {"schema"}
    saas = seed.playbook("halcyon-saas-msa-vendor")
    assert [r.rule_key for r in saas.rules] == [SUPER_CAP]  # the invalid rule is left out
    assert saas.invalid_rule_keys == {CAP}
    # References to the rule that failed its model are not reported a second time.
    assert codes(check_directory(seed)) == {"minimum.variants"}


def test_models_forbid_unknown_keys_and_bad_literals() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        models.Dependency.model_validate(
            {"related_rule_key": "a.b", "relation": "read_with", "note": "x", "extra": 1}
        )
    with pytest.raises(ValidationError, match="read_with"):
        models.Dependency.model_validate(
            {"related_rule_key": "a.b", "relation": "blocks", "note": "x"}
        )
    with pytest.raises(ValidationError):
        models.Dependency.model_validate(
            {"related_rule_key": "not a key", "relation": "requires", "note": "x"}
        )


def test_issue_format() -> None:
    issue = models.Issue(
        "error",
        "minimum.variants",
        Path("/data/playbooks/x/rules.yaml"),
        "needs a variant",
        rule_key="a.b",
        location="positions",
    )
    assert issue.format(Path("/data")) == (
        "ERROR   playbooks/x/rules.yaml [a.b] positions: needs a variant  (minimum.variants)"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("... eighteen (18) months ...", "..."),
        ("capped at [TBD]", "[TBD]"),
        ("capped at [ todo ]", "[ todo ]"),
        ("amount is TBD", "TBD"),
        ("capped at…", "…"),
        ("the greater of (a) the Fees and (b) US$[amount].", None),
        ("the laws of the State of [state]", None),
    ],
)
def test_find_placeholder(text: str, expected: str | None) -> None:
    assert find_placeholder(text) == expected


def test_text_heuristics() -> None:
    assert sentence_count("Uncapped liability is not insurable.") == 1
    assert sentence_count("Halcyon holds $10M of cover. An uncapped clause exceeds it.") == 2
    assert mentions_number("within thirty days of the invoice date")
    assert mentions_number("shall not exceed the Fees paid in the twelve (12) months")
    assert mentions_number("a credit of 10% of the monthly Fees")
    assert not mentions_number("as required by 45 C.F.R. 164.504 and Section 5.2 of this Agreement")
    assert not mentions_number("This Agreement is governed by the laws of the State of Delaware.")
