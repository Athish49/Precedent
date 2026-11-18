"""Tests for the playbook coverage report (task 2.2).

The report is run on ``fixtures/valid`` (two playbooks, three rules), on
edited temporary copies of it and on partly written directories. Expected
counts are worked out here from the raw YAML, not through the seed models.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml

from seed.playbooks import models, report
from seed.playbooks.report import TARGETS, Targets, VersionCounts, build_report, main, render_text

VALID = Path(__file__).parent / "fixtures" / "valid"
RISK = "playbooks/saas_msa_vendor/risk.yaml"
BASELINE_HEADER = "playbooks/baseline/playbook.yaml"

TOP_LEVEL_KEYS = {
    "directory",
    "ok",
    "missed",
    "tables",
    "reference_checks",
    "playbooks",
    "minimum_violations",
    "validation",
    "family_coverage",
    "issue_coverage",
    "fill_rates",
    "zone_distribution",
    "approver_distribution",
    "test_case_mix",
    "versions",
}


# -- helpers -----------------------------------------------------------------


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    """A writable copy of the valid fixture."""
    target = tmp_path / "data"
    shutil.copytree(VALID, target)
    return target


def read(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def edit(root: Path, relative: str, change) -> None:
    path = root / relative
    data = read(path)
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def raw_rules(root: Path) -> list[dict[str, Any]]:
    """Every rule in the directory, straight from the YAML."""
    rules: list[dict[str, Any]] = []
    for path in sorted((root / "playbooks").glob("*/*.yaml")):
        if path.name != "playbook.yaml":
            rules.extend(read(path)["rules"])
    return rules


def row(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(r for r in rows if r["name"] == name)


def fixture_targets(**changes: Any) -> Targets:
    """Targets the valid fixture meets exactly, so one change shows one miss."""
    values: dict[str, Any] = {
        "table_minimums": {
            "clause_issue": 4,
            "playbook": 2,
            "playbook_version": 2,
            "playbook_change_log": 0,
            "playbook_rule": 3,
            "rule_position": 12,
            "rule_parameter": 5,
            "red_line": 8,
            "rule_objection": 6,
            "rule_dependency": 2,
            "rule_test_case": 19,
            "context_dimension": 5,
            "approver_role": 4,
            "escalation_policy": 3,
        },
        "issues_used_by_rules": 3,
        "issues_reserved": 1,
        "red_lines_global": 2,
        "red_lines_on_rules": 6,
        "playbook_rules": {"halcyon-baseline": 1, "halcyon-saas-msa-vendor": 2},
        "expected_family_keys": 4,
    }
    values.update(changes)
    return Targets(**values)


# -- targets -------------------------------------------------------------------


def test_targets_match_the_plan() -> None:
    assert TARGETS.table_minimums == {
        "clause_issue": 95,
        "playbook": 7,
        "playbook_version": 9,
        "playbook_change_log": 20,
        "playbook_rule": 130,
        "rule_position": 520,
        "rule_parameter": 90,
        "red_line": 140,
        "rule_objection": 240,
        "rule_dependency": 60,
        "rule_test_case": 650,
        "context_dimension": 5,
        "approver_role": 9,
        "escalation_policy": 36,
    }
    assert TARGETS.playbook_rules == {
        "halcyon-baseline": 12,
        "halcyon-mutual-nda": 14,
        "halcyon-saas-msa-vendor": 36,
        "halcyon-dpa-processor": 18,
        "halcyon-vendor-msa-customer": 24,
        "halcyon-hipaa-overlay": 14,
        "halcyon-gdpr-overlay": 12,
    }
    assert sum(TARGETS.playbook_rules.values()) == TARGETS.table_minimums["playbook_rule"]
    assert len(TARGETS.playbook_rules) == TARGETS.table_minimums["playbook"]
    assert TARGETS.red_lines_global + TARGETS.red_lines_on_rules == 140
    assert TARGETS.issues_used_by_rules + TARGETS.issues_reserved == 95
    assert TARGETS.expected_family_keys == 29
    assert set(TARGETS.agreement_types) == set(get_args(models.PracticeArea))
    assert len(TARGETS.agreement_types) == 7


# -- the fixture -----------------------------------------------------------------


def test_fixture_table_counts_match_the_raw_files() -> None:
    result = build_report(VALID)
    rules = raw_rules(VALID)
    taxonomy = read(VALID / "taxonomy.yaml")
    authority = read(VALID / "authority.yaml")

    def total(child: str) -> int:
        return sum(len(r.get(child) or []) for r in rules)

    used = {r["rule_key"] for r in rules}
    defined = {f"{i['family']}.{i['key']}" for i in taxonomy["issues"]}
    expected = {
        "clause_issue": len(defined),
        "clause_issue: used by rules": len(defined & used),
        "clause_issue: reserved (no rule yet)": len(defined - used),
        "playbook": 2,
        "playbook_version": 2,
        "playbook_change_log": 0,
        "playbook_rule": len(rules),
        "rule_position": total("positions"),
        "rule_parameter": total("parameters"),
        "red_line": total("red_lines") + len(authority["global_red_lines"]),
        "red_line: global": len(authority["global_red_lines"]),
        "red_line: on rules": total("red_lines"),
        "rule_objection": total("objections"),
        "rule_dependency": total("dependencies"),
        "rule_test_case": total("test_cases"),
        "context_dimension": len(authority["context_dimensions"]),
        "approver_role": len(authority["roles"]),
        "escalation_policy": len(authority["escalation_policies"]),
    }
    assert {r["name"]: r["count"] for r in result["tables"]} == expected
    assert len(rules) == 3  # the fixture is what its README says it is


def test_fixture_shortfalls_are_flagged() -> None:
    result = build_report(VALID)
    assert result["ok"] is False
    met = {r["name"] for r in result["tables"] if r["met"]}
    assert met == {"context_dimension"}  # the only full-size part of the fixture
    assert row(result["tables"], "playbook_rule")["target"] == 130

    families, areas = result["reference_checks"]
    assert (families["count"], families["target"], families["met"]) == (4, 29, False)
    assert (areas["count"], areas["met"]) == (0, True)

    playbooks = {r["name"]: r for r in result["playbooks"]}
    assert list(playbooks) == list(TARGETS.playbook_rules)
    assert playbooks["halcyon-baseline"]["count"] == 1
    assert playbooks["halcyon-saas-msa-vendor"]["count"] == 2
    assert playbooks["halcyon-saas-msa-vendor"]["folder"] == "saas_msa_vendor"
    assert playbooks["halcyon-mutual-nda"]["note"] == "not written yet"
    assert not any(r["met"] for r in result["playbooks"])

    assert result["minimum_violations"]["errors"] == 0
    assert result["minimum_violations"]["check"]["met"] is True
    assert result["validation"] == {"errors": 0, "warnings": 0, "pending": 0}

    assert "context_dimension" not in result["missed"]
    assert "rules in halcyon-baseline" in result["missed"]
    assert "red_line: global" in result["missed"]
    assert "per-rule minimum violations" not in result["missed"]
    assert len(result["missed"]) == 25


def test_version_targets_are_missed_with_no_version_files() -> None:
    result = build_report(VALID)
    for name in ("playbook_version", "playbook_change_log"):
        entry = row(result["tables"], name)
        assert entry["met"] is False
        assert entry["note"] is None
    assert result["versions"] == {"modelled": True, "files_on_disk": 0}


def test_version_files_on_disk_are_mentioned_but_not_counted(seed_dir: Path) -> None:
    (seed_dir / "versions").mkdir()
    (seed_dir / "versions" / "saas_msa_vendor_1_1.yaml").write_text("changes: []\n")
    result = build_report(seed_dir)
    entry = row(result["tables"], "playbook_version")
    assert entry["count"] == 2
    assert entry["note"].startswith("1 file(s) in versions/")
    assert result["versions"]["files_on_disk"] == 1


def test_count_versions_is_the_only_hook_for_version_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        report,
        "count_versions",
        lambda seed: VersionCounts(
            versions=9, change_log_entries=21, modelled=True, files_on_disk=2
        ),
    )
    result = build_report(VALID)
    version = row(result["tables"], "playbook_version")
    log = row(result["tables"], "playbook_change_log")
    assert (version["count"], version["met"], version["note"]) == (9, True, None)
    assert (log["count"], log["met"], log["note"]) == (21, True, None)
    assert result["versions"]["modelled"] is True


def test_fixture_distributions() -> None:
    result = build_report(VALID)
    rules = raw_rules(VALID)
    positions = [p for r in rules for p in r["positions"]]
    cases = [t for r in rules for t in r["test_cases"]]

    zones = result["zone_distribution"]
    assert zones["total"] == len(positions)
    for kind in ("preferred", "fallback", "acceptable_variant"):
        for zone in ("green", "yellow"):
            expected = sum(1 for p in positions if p["kind"] == kind and p["zone"] == zone)
            assert zones["by_kind"][kind][zone] == expected
    assert sum(zones["by_zone"].values()) == len(positions)

    mix = result["test_case_mix"]
    assert mix["total"] == len(cases) == sum(mix["by_outcome"].values())
    assert list(mix["by_outcome"]) == list(get_args(models.ExpectedOutcome))
    for outcome, count in mix["by_outcome"].items():
        assert count == sum(1 for t in cases if t["expected_outcome"] == outcome)
    assert mix["traps"] == sum(1 for t in cases if t.get("is_trap"))
    assert sum(mix["by_zone"].values()) == len(cases)

    approvers = {r["role"]: r for r in result["approver_distribution"]}
    authority = read(VALID / "authority.yaml")
    assert list(approvers) == [r["key"] for r in authority["roles"]]
    assert all(r["defined"] for r in approvers.values())
    for role, entry in approvers.items():
        assert entry["positions"] == sum(1 for p in positions if p.get("approver_role") == role)
        assert entry["policies"] == sum(
            1 for p in authority["escalation_policies"] if p["approver_role"] == role
        )
    assert approvers["cfo"]["consulted"] == 1
    assert approvers["general_counsel"]["playbooks_owned"] == 1


def test_fixture_family_and_issue_coverage() -> None:
    result = build_report(VALID)
    families = {f["family"]: f for f in result["family_coverage"]}
    assert list(families) == read(VALID / "taxonomy.yaml")["expected_families"]
    assert families["limitation_of_liability"] == {
        "family": "limitation_of_liability",
        "expected": True,
        "issues": 2,
        "issues_used": 2,
        "rules": 2,
        "playbooks": 1,
    }
    assert families["other"]["rules"] == 0
    coverage = result["issue_coverage"]
    assert coverage["defined"] == 4
    assert coverage["used"] == 3
    assert coverage["reserved"] == ["payment.payment_terms"]
    assert coverage["used_but_not_in_taxonomy"] == []
    assert coverage["families_without_rules"] == ["payment", "other"]


def test_fill_rates_cover_every_optional_field() -> None:
    result = build_report(VALID)
    rates = {(r["model"], r["field"]): r for r in result["fill_rates"]}

    for label, model in (
        ("playbook", models.PlaybookHeader),
        ("playbook_version", models.PlaybookVersionHeader),
        ("playbook_rule", models.Rule),
        ("rule_position", models.Position),
        ("rule_parameter", models.Parameter),
        ("red_line (rule)", models.RedLine),
        ("rule_objection", models.Objection),
        ("rule_test_case", models.TestCase),
        ("escalation_policy", models.EscalationPolicy),
    ):
        optional = {n for n, f in model.model_fields.items() if not f.is_required()}
        assert optional, label
        assert {f for (m, f) in rates if m == label} == optional
    assert not any(m == "rule_dependency" for m, _ in rates)  # it has no optional field

    rules = raw_rules(VALID)
    positions = [p for r in rules for p in r["positions"]]
    give_get = rates[("rule_position", "give_get")]
    assert give_get["kind"] == "nullable"
    assert give_get["filled"] == sum(1 for p in positions if p.get("give_get"))
    assert give_get["total"] == len(positions)
    assert give_get["rate"] == round(give_get["filled"] / len(positions), 4)

    source_ref = rates[("playbook_rule", "source_ref")]
    assert (source_ref["filled"], source_ref["total"]) == (
        sum(1 for r in rules if r.get("source_ref")),
        len(rules),
    )
    # A field with a real default counts when the value differs from it.
    trap = rates[("rule_test_case", "is_trap")]
    assert trap["kind"] == "default"
    assert trap["filled"] == result["test_case_mix"]["traps"]
    assert rates[("playbook_rule", "default_zone")]["filled"] == sum(
        1 for r in rules if r.get("default_zone", "yellow") != "yellow"
    )
    assert rates[("playbook", "parent")]["filled"] == 1


# -- edited copies -----------------------------------------------------------------


def test_all_targets_met_gives_ok(seed_dir: Path) -> None:
    result = build_report(seed_dir, fixture_targets())
    assert result["missed"] == []
    assert result["ok"] is True
    assert "RESULT: all targets met" in render_text(result)


def test_per_playbook_rule_count_is_exact(seed_dir: Path) -> None:
    result = build_report(seed_dir, fixture_targets(playbook_rules={"halcyon-baseline": 1}))
    # One rule too many is as wrong as one too few; an unplanned playbook is flagged.
    assert result["missed"] == ["rules in halcyon-saas-msa-vendor"]
    extra = row(result["playbooks"], "halcyon-saas-msa-vendor")
    assert "not in the plan" in extra["note"]

    result = build_report(
        seed_dir,
        fixture_targets(playbook_rules={"halcyon-baseline": 1, "halcyon-saas-msa-vendor": 1}),
    )
    assert result["missed"] == ["rules in halcyon-saas-msa-vendor"]


def test_minimum_violations_come_from_the_validator(seed_dir: Path) -> None:
    def drop(data: dict[str, Any]) -> None:
        data["rules"][0]["objections"] = data["rules"][0]["objections"][:1]
        data["rules"][0]["test_cases"] = data["rules"][0]["test_cases"][:4]

    edit(seed_dir, RISK, drop)
    result = build_report(seed_dir, fixture_targets())
    minimums = result["minimum_violations"]
    assert minimums["check"]["met"] is False
    assert minimums["by_code"]["minimum.objections"] == 1
    assert minimums["by_code"]["minimum.test_cases"] == 1
    assert minimums["errors"] == sum(minimums["by_code"].values()) - minimums["warnings"]
    assert minimums["rules_affected"] == 1
    assert {i["rule_key"] for i in minimums["items"]} == {"limitation_of_liability.cap_amount"}
    assert {i["playbook"] for i in minimums["items"]} == {"halcyon-saas-msa-vendor"}
    assert all(i["code"].startswith("minimum.") for i in minimums["items"])
    assert "per-rule minimum violations" in result["missed"]
    assert result["ok"] is False

    text = render_text(result)
    assert "minimum.objections" in text
    assert "a negotiable rule needs at least 2 objections; found 1" in text


def test_rules_the_loader_would_not_load_are_not_counted(seed_dir: Path) -> None:
    saas = seed_dir / "playbooks" / "saas_msa_vendor"
    shutil.copy(saas / "risk.yaml", saas / "extra.yaml")  # not listed in rule_files
    orphan = seed_dir / "playbooks" / "orphan"
    orphan.mkdir()
    shutil.copy(seed_dir / "playbooks" / "baseline" / "rules.yaml", orphan / "rules.yaml")

    result = build_report(seed_dir)
    rules = row(result["tables"], "playbook_rule")
    assert rules["count"] == 3
    assert rules["note"] == "3 rule(s) found but not loadable"
    assert row(result["tables"], "playbook")["count"] == 2
    saas_row = row(result["playbooks"], "halcyon-saas-msa-vendor")
    assert saas_row["count"] == 2
    assert "not listed in rule_files" in saas_row["note"]
    orphan_row = row(result["playbooks"], "orphan")
    assert orphan_row["met"] is False
    assert "no valid playbook.yaml; 1 rule(s) found" in orphan_row["note"]


def test_unknown_practice_area_is_flagged_even_though_the_header_fails(seed_dir: Path) -> None:
    edit(seed_dir, BASELINE_HEADER, lambda d: d.update(practice_area="reseller"))
    result = build_report(seed_dir)
    areas = result["reference_checks"][1]
    assert (areas["count"], areas["met"]) == (1, False)
    assert areas["note"] == "unknown: reseller"
    assert areas["name"] in result["missed"]
    assert row(result["tables"], "playbook")["count"] == 1


def test_rule_key_outside_the_taxonomy_and_undefined_role_are_listed(seed_dir: Path) -> None:
    def change(data: dict[str, Any]) -> None:
        data["rules"][1]["rule_key"] = "warranties.disclaimer"
        for position in data["rules"][1]["positions"]:
            if position.get("approver_role"):
                position["approver_role"] = "vp_sales"

    edit(seed_dir, RISK, change)
    result = build_report(seed_dir)
    assert result["issue_coverage"]["used_but_not_in_taxonomy"] == ["warranties.disclaimer"]
    extra = next(f for f in result["family_coverage"] if f["family"] == "warranties")
    assert (extra["expected"], extra["rules"]) == (False, 1)
    role = next(r for r in result["approver_distribution"] if r["role"] == "vp_sales")
    assert role["defined"] is False and role["positions"] >= 1
    assert result["validation"]["errors"] >= 2
    text = render_text(result)
    assert "not in expected_families" in text
    assert "not in authority.yaml" in text


# -- partly written directories --------------------------------------------------------


def test_empty_directory_reports_zeros(tmp_path: Path) -> None:
    result = build_report(tmp_path)
    assert all(r["count"] == 0 and not r["met"] for r in result["tables"])
    assert all(r["count"] == 0 and not r["met"] for r in result["playbooks"])
    assert result["reference_checks"][0]["met"] is False
    assert result["reference_checks"][1]["met"] is True
    assert result["family_coverage"] == []
    assert result["approver_distribution"] == []
    assert result["test_case_mix"]["total"] == 0
    assert all(r["rate"] is None for r in result["fill_rates"])
    assert row(result["tables"], "clause_issue")["note"] == "taxonomy.yaml not loaded"
    assert row(result["tables"], "approver_role")["note"] == "authority.yaml not loaded"
    assert result["validation"]["pending"] == 3
    assert len(result["missed"]) == 26
    assert "RESULT: 26 target(s) missed" in render_text(result)


@pytest.mark.parametrize("removed", ["taxonomy.yaml", "authority.yaml", "playbooks"])
def test_one_part_missing_does_not_crash(seed_dir: Path, removed: str) -> None:
    target = seed_dir / removed
    shutil.rmtree(target) if target.is_dir() else target.unlink()
    result = build_report(seed_dir)
    counts = {r["name"]: r["count"] for r in result["tables"]}
    if removed == "taxonomy.yaml":
        assert counts["clause_issue"] == 0
        assert counts["playbook_rule"] == 3
        assert result["issue_coverage"]["used_but_not_in_taxonomy"] == sorted(
            r["rule_key"] for r in raw_rules(seed_dir)
        )
        assert [f["expected"] for f in result["family_coverage"]] == [False, False]
    elif removed == "authority.yaml":
        assert counts["context_dimension"] == counts["approver_role"] == 0
        assert counts["red_line: global"] == 0
        assert counts["red_line"] == counts["red_line: on rules"] == 6
        assert all(not r["defined"] for r in result["approver_distribution"])
    else:
        assert counts["playbook"] == counts["playbook_rule"] == counts["rule_test_case"] == 0
        assert counts["clause_issue"] == 4
        assert len(result["issue_coverage"]["reserved"]) == 4
    assert result["ok"] is False
    assert render_text(result)
    json.dumps(result)


def test_broken_and_half_written_files_do_not_crash(seed_dir: Path) -> None:
    (seed_dir / "taxonomy.yaml").write_text("expected_families: [a, a\n")  # not YAML
    (seed_dir / "authority.yaml").write_text("")  # empty
    (seed_dir / BASELINE_HEADER).unlink()
    (seed_dir / RISK).write_text("rules:\n  - rule_key: payment.payment_terms\n")
    result = build_report(seed_dir)
    counts = {r["name"]: r["count"] for r in result["tables"]}
    assert counts["clause_issue"] == counts["approver_role"] == counts["playbook_rule"] == 0
    assert counts["playbook"] == 1
    assert result["validation"]["errors"] > 0
    assert row(result["playbooks"], "baseline")["met"] is False
    assert render_text(result)


# -- command line --------------------------------------------------------------------


def test_cli_text_output_and_exit_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(VALID)]) == 1
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == f"Playbook seed coverage: {VALID}"
    for title in (
        "Tables (plan 7.3, seed-sourced rows)",
        "Reference data (plan 7.3, migration-sourced rows: checked, not created)",
        "Rules per playbook (plan 7.1)",
        "Per-rule minimums (plan 7.2)",
        "Family coverage",
        "Issue coverage",
        "Optional field fill rates (nullable: holds a value; default: differs from the default)",
        "Zone distribution of positions",
        "Approver distribution",
        "Test-case mix by expected outcome",
    ):
        assert title in lines
    # Aligned columns: every row of the first table has its status in the same column.
    start = lines.index("Tables (plan 7.3, seed-sourced rows)") + 3
    table = lines[start : start + 18]
    assert len(table) == 18
    column = table[0].index("MISSED")
    assert all(line[column:].startswith(("MISSED", "ok")) for line in table)
    assert "  playbook_rule                 3  >= 130  MISSED" in lines
    assert "  context_dimension             5  >= 5    ok" in lines
    assert "    global                      2  >= 12   MISSED" in lines
    assert any(
        line.startswith("  playbook_change_log") and "MISSED" in line for line in lines
    )
    assert "  halcyon-baseline                 1  = 12    MISSED" in lines
    assert lines[-26] == "RESULT: 25 target(s) missed"
    assert all(len(line) <= 120 for line in lines)


def test_cli_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(VALID), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert set(data) == TOP_LEVEL_KEYS
    assert data == json.loads(json.dumps(build_report(VALID)))
    assert data["ok"] is False
    for entry in data["tables"] + data["reference_checks"] + data["playbooks"]:
        assert {"name", "count", "target", "comparison", "met", "note"} <= set(entry)


def test_cli_exit_zero_when_every_target_is_met(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    targets = fixture_targets()
    monkeypatch.setattr(report, "build_report", lambda root: build_report(root, targets))
    assert main([str(VALID)]) == 0
    assert capsys.readouterr().out.rstrip().endswith("RESULT: all targets met")


def test_cli_default_directory_runs(capsys: pytest.CaptureFixture[str]) -> None:
    """The real data directory, however much of it is written, never crashes the report."""
    status = main(["--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["directory"].endswith("seed/playbooks/data/halcyon")
    assert status == (0 if data["ok"] else 1)


def test_cli_directory_not_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "nowhere")]) == 1
    assert "directory not found" in capsys.readouterr().err
