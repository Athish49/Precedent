"""Coverage report for a playbook seed directory. Reads files only; no database.

Command line::

    cd backend
    .venv/bin/python -m seed.playbooks.report [dir] [--json]

``dir`` defaults to ``seed/playbooks/data/halcyon``. Exit status is 1 if any
target is missed, otherwise 0.

What it prints:

* row counts per table against the seed-sourced minimums of
  ``playbook_plan.md`` section 7.3;
* the two migration-sourced rows as reference checks only: ``expected_families``
  lists 29 keys, and every ``practice_area`` used is one of the seven
  agreement types;
* rules per playbook against section 7.1;
* per-rule minimum violations (the validator's ``minimum.*`` findings);
* family and issue coverage, the fill rate of every optional field, the zone
  distribution of positions, the approver distribution and the test-case mix.

Every number the report is held to lives in :data:`TARGETS`.

The directory may be partly written. A missing taxonomy, authority file or
playbook folder gives counts of 0 and missed targets, never a crash.

What is counted is what the loader would load: rules in a folder with a valid
``playbook.yaml``, from files that header lists. Rules found elsewhere are
reported as not counted.

Versions (task 3.14): ``playbook_version`` counts one row per playbook header
plus one per file under ``versions/`` that loaded; ``playbook_change_log``
sums the ``changes`` list of every loaded version file. See
:func:`count_versions`.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from seed.common import SeedError, add_data_dir_argument, build_parser, data_dir, load_yaml, run
from seed.playbooks import models
from seed.playbooks.models import Issue, LoadedPlaybook, LoadedRule, SeedDirectory, SeedModel
from seed.playbooks.validate import VERSIONS_DIR, YAML_SUFFIXES, check_directory, load_directory

# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Targets:
    """Every number the report checks. Sources: ``playbook_plan.md`` section 7."""

    # Section 7.3, seed-sourced rows: table -> minimum row count.
    table_minimums: dict[str, int] = field(
        default_factory=lambda: {
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
    )
    # Section 7.3, the breakdowns stated beside two of the rows above.
    issues_used_by_rules: int = 90
    issues_reserved: int = 5
    red_lines_global: int = 12
    red_lines_on_rules: int = 128
    # Section 7.1: playbook key -> exact number of rules.
    playbook_rules: dict[str, int] = field(
        default_factory=lambda: {
            "halcyon-baseline": 12,
            "halcyon-mutual-nda": 14,
            "halcyon-saas-msa-vendor": 36,
            "halcyon-dpa-processor": 18,
            "halcyon-vendor-msa-customer": 24,
            "halcyon-hipaa-overlay": 14,
            "halcyon-gdpr-overlay": 12,
        }
    )
    # Section 7.3, migration-sourced rows. The seed does not create these; the
    # report only checks what the seed files say about them.
    expected_family_keys: int = 29
    agreement_types: tuple[str, ...] = (
        "baseline",
        "nda",
        "saas_msa",
        "dpa",
        "hipaa",
        "gdpr",
        "vendor_msa",
    )
    # Section 7.2 is enforced by the validator; the report allows none of its errors.
    minimum_violations: int = 0


TARGETS = Targets()

MINIMUM_PREFIX = "minimum."


# --------------------------------------------------------------------------
# Versions: the one place task 3.14 extends
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionCounts:
    versions: int  # playbook_version rows
    change_log_entries: int  # playbook_change_log rows
    modelled: bool  # True once seed.versions can hold loaded version files (task 3.14)
    files_on_disk: int  # YAML files under versions/, whether or not they loaded


def count_versions(seed: SeedDirectory) -> VersionCounts:
    """Count ``playbook_version`` and ``playbook_change_log`` rows.

    Each ``playbook.yaml`` carries one version (``playbook_version`` row),
    and each file under ``versions/`` that loaded into ``seed.versions`` is
    one more. ``playbook_change_log`` sums the ``changes`` list of every
    loaded version file.
    """
    headers = sum(1 for pb in seed.playbooks if pb.header is not None)
    folder = seed.root / VERSIONS_DIR
    on_disk = (
        sum(1 for p in folder.rglob("*") if p.is_file() and p.suffix in YAML_SUFFIXES)
        if folder.is_dir()
        else 0
    )
    change_log_entries = sum(len(v.version_set.changes) for v in seed.versions)
    return VersionCounts(
        versions=headers + len(seed.versions),
        change_log_entries=change_log_entries,
        modelled=True,
        files_on_disk=on_disk,
    )


# --------------------------------------------------------------------------
# Building the report
# --------------------------------------------------------------------------


def _check(
    name: str, count: int, target: int, *, exact: bool = False, note: str | None = None
) -> dict[str, Any]:
    met = count == target if exact else count >= target
    return {
        "name": name,
        "count": count,
        "target": target,
        "comparison": "exact" if exact else "minimum",
        "met": met,
        "note": note,
    }


def _loadable_rules(playbook: LoadedPlaybook) -> list[LoadedRule]:
    """The rules the loader would load: header present, file listed in ``rule_files``."""
    if playbook.header is None:
        return []
    unlisted = set(playbook.unlisted_rule_files)
    return [r for r in playbook.rules if r.source not in unlisted]


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, (str, list, dict, tuple)) and len(value) == 0)


def _fill_rates(groups: Sequence[tuple[str, type[SeedModel], list[Any]]]) -> list[dict[str, Any]]:
    """Fill rate of every optional field of each model, found by introspection.

    A field whose default is empty (null, "", []) is ``nullable`` and counts
    as filled when it holds something. A field with a real default (for
    example ``default_zone: yellow``, ``is_trap: false``) is ``default`` and
    counts as filled when the value differs from that default.
    """
    rows: list[dict[str, Any]] = []
    for label, model, items in groups:
        for name, info in model.model_fields.items():
            if info.is_required():
                continue
            default = info.get_default(call_default_factory=True)
            nullable = _is_empty(default)
            if nullable:
                filled = sum(1 for item in items if not _is_empty(getattr(item, name)))
            else:
                filled = sum(1 for item in items if getattr(item, name) != default)
            total = len(items)
            rows.append(
                {
                    "model": label,
                    "field": name,
                    "kind": "nullable" if nullable else "default",
                    "filled": filled,
                    "total": total,
                    "rate": round(filled / total, 4) if total else None,
                }
            )
    return rows


def _raw_practice_area(playbook: LoadedPlaybook) -> str | None:
    """``practice_area`` of a header that failed its model, read straight from the file."""
    if not playbook.header_source.is_file():
        return None
    try:
        data = load_yaml(playbook.header_source)
    except SeedError:
        return None
    value = data.get("practice_area") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def _issue_dict(issue: Issue, seed: SeedDirectory, playbook_by_file: dict[Path, str]) -> dict:
    try:
        shown = issue.file.relative_to(seed.root).as_posix()
    except ValueError:
        shown = issue.file.as_posix()
    return {
        "code": issue.code,
        "level": issue.level,
        "playbook": playbook_by_file.get(issue.file),
        "rule_key": issue.rule_key,
        "file": shown,
        "message": issue.message,
    }


def build_report(root: Path | str, targets: Targets = TARGETS) -> dict[str, Any]:
    """Load ``root`` and return the whole report as plain JSON-ready data.

    Raises :class:`seed.common.SeedFileError` only if ``root`` is not a directory.
    """
    seed = load_directory(root)
    findings = seed.issues + check_directory(seed)
    tax, auth = seed.taxonomy, seed.authority

    with_header = [pb for pb in seed.playbooks if pb.header is not None]
    rules: list[LoadedRule] = [r for pb in seed.playbooks for r in _loadable_rules(pb)]
    not_counted = len(seed.all_rules()) - len(rules)
    bare = [r.rule for r in rules]

    positions = [p for r in bare for p in r.positions]
    parameters = [p for r in bare for p in r.parameters]
    rule_red_lines = [x for r in bare for x in r.red_lines]
    objections = [o for r in bare for o in r.objections]
    dependencies = [d for r in bare for d in r.dependencies]
    test_cases = [t for r in bare for t in r.test_cases]
    global_red_lines = list(auth.global_red_lines) if auth else []
    policies = list(auth.escalation_policies) if auth else []
    dimensions = list(auth.context_dimensions) if auth else []
    roles = list(auth.roles) if auth else []

    issue_keys = sorted({i.rule_key for i in tax.issues}) if tax else []
    used_keys = {r.rule_key for r in rules}
    used_defined = sorted(k for k in issue_keys if k in used_keys)
    reserved = sorted(k for k in issue_keys if k not in used_keys)
    unknown = sorted(used_keys - set(issue_keys))

    # -- tables (section 7.3) ---------------------------------------------
    versions = count_versions(seed)
    header_count = len({pb.key for pb in with_header})
    loaded_version_files = versions.versions - header_count
    version_note = None
    if versions.files_on_disk > loaded_version_files:
        version_note = (
            f"{versions.files_on_disk - loaded_version_files} file(s) in versions/ did not load "
            "(see the validator); not counted"
        )
    counts = {
        "clause_issue": len(issue_keys),
        "playbook": len({pb.key for pb in with_header}),
        "playbook_version": versions.versions,
        "playbook_change_log": versions.change_log_entries,
        "playbook_rule": len(rules),
        "rule_position": len(positions),
        "rule_parameter": len(parameters),
        "red_line": len(rule_red_lines) + len(global_red_lines),
        "rule_objection": len(objections),
        "rule_dependency": len(dependencies),
        "rule_test_case": len(test_cases),
        "context_dimension": len(dimensions),
        "approver_role": len(roles),
        "escalation_policy": len(policies),
    }
    notes = {
        "clause_issue": None if tax else "taxonomy.yaml not loaded",
        "playbook_version": version_note,
        "playbook_change_log": version_note,
        "playbook_rule": f"{not_counted} rule(s) found but not loadable" if not_counted else None,
        "context_dimension": None if auth else "authority.yaml not loaded",
        "approver_role": None if auth else "authority.yaml not loaded",
        "escalation_policy": None if auth else "authority.yaml not loaded",
    }
    breakdowns = {
        "clause_issue": [
            _check("clause_issue: used by rules", len(used_defined), targets.issues_used_by_rules),
            _check("clause_issue: reserved (no rule yet)", len(reserved), targets.issues_reserved),
        ],
        "red_line": [
            _check("red_line: global", len(global_red_lines), targets.red_lines_global),
            _check("red_line: on rules", len(rule_red_lines), targets.red_lines_on_rules),
        ],
    }
    tables: list[dict[str, Any]] = []
    for table, minimum in targets.table_minimums.items():
        tables.append(_check(table, counts.get(table, 0), minimum, note=notes.get(table)))
        for part in breakdowns.get(table, []):
            part["part_of"] = table
            tables.append(part)

    # -- reference checks (migration-sourced rows) ------------------------
    families = list(dict.fromkeys(tax.expected_families)) if tax else []
    areas = Counter(pb.header.practice_area for pb in with_header)  # type: ignore[union-attr]
    for pb in seed.playbooks:
        if pb.header is None:
            raw = _raw_practice_area(pb)
            if raw is not None:
                areas[raw] += 1
    bad_areas = sorted(a for a in areas if a not in targets.agreement_types)
    reference_checks = [
        _check(
            "clause_family: expected_families keys",
            len(families),
            targets.expected_family_keys,
            exact=True,
            note=None if tax else "taxonomy.yaml not loaded",
        ),
        _check(
            "agreement_type: practice_area values not among the seven",
            len(bad_areas),
            0,
            exact=True,
            note=(
                f"unknown: {', '.join(bad_areas)}"
                if bad_areas
                else f"{len(areas)} of {len(targets.agreement_types)} types in use"
            ),
        ),
    ]

    # -- rules per playbook (section 7.1) ---------------------------------
    by_key: dict[str, list[LoadedPlaybook]] = {}
    for pb in seed.playbooks:
        by_key.setdefault(pb.key, []).append(pb)
    playbook_rows: list[dict[str, Any]] = []
    for key, target in targets.playbook_rules.items():
        found = by_key.pop(key, [])
        loadable = sum(len(_loadable_rules(pb)) for pb in found)
        extra = sum(len(pb.rules) for pb in found) - loadable
        pending = sorted(n for pb in found for n in pb.missing_rule_files)
        if not found:
            note = "not written yet"
        elif pending:
            note = f"rule file(s) not written yet: {', '.join(pending)}"
        elif extra:
            note = f"{extra} rule(s) in files not listed in rule_files"
        else:
            note = None
        row = _check(key, loadable, target, exact=True, note=note)
        row["folder"] = found[0].dir_name if found else None
        playbook_rows.append(row)
    for key, found in by_key.items():
        for pb in found:
            if pb.header is None:
                note = f"no valid playbook.yaml; {len(pb.rules)} rule(s) found, not loadable"
            else:
                note = "playbook key is not in the plan (section 7.1)"
            row = _check(key, len(_loadable_rules(pb)), 0, exact=True, note=note)
            row["met"] = False
            row["folder"] = pb.dir_name
            playbook_rows.append(row)

    # -- per-rule minimums (validator findings) ---------------------------
    playbook_by_file = {r.source: pb.key for pb in seed.playbooks for r in pb.rules}
    minimum_findings = [i for i in findings if i.code.startswith(MINIMUM_PREFIX)]
    minimum_errors = [i for i in minimum_findings if i.is_error]
    minimums = {
        "check": _check(
            "per-rule minimum violations",
            len(minimum_errors),
            targets.minimum_violations,
            exact=True,
        ),
        "errors": len(minimum_errors),
        "warnings": len(minimum_findings) - len(minimum_errors),
        "by_code": dict(sorted(Counter(i.code for i in minimum_findings).items())),
        "rules_affected": len({(i.file, i.rule_key) for i in minimum_errors}),
        "items": [_issue_dict(i, seed, playbook_by_file) for i in minimum_findings],
    }
    other = [i for i in findings if not i.code.startswith(MINIMUM_PREFIX)]
    validation = {
        "errors": sum(1 for i in other if i.is_error),
        "warnings": sum(1 for i in other if not i.is_error),
        "pending": sum(1 for i in other if i.pending),
    }

    # -- family and issue coverage ----------------------------------------
    defined_by_family = Counter(k.split(".", 1)[0] for k in issue_keys)
    used_by_family = Counter(k.split(".", 1)[0] for k in used_keys)
    rules_by_family = Counter(r.family for r in bare)
    playbooks_by_family: dict[str, set[str]] = {}
    for pb in seed.playbooks:
        for loaded in _loadable_rules(pb):
            playbooks_by_family.setdefault(loaded.rule.family, set()).add(pb.key)
    family_rows = [
        {
            "family": family,
            "expected": family in families,
            "issues": defined_by_family[family],
            "issues_used": used_by_family[family],
            "rules": rules_by_family[family],
            "playbooks": len(playbooks_by_family.get(family, ())),
        }
        for family in families + sorted(set(rules_by_family) - set(families))
    ]
    issue_coverage = {
        "defined": len(issue_keys),
        "used": len(used_defined),
        "reserved": reserved,
        "used_but_not_in_taxonomy": unknown,
        "used_in_more_than_one_playbook": sorted(
            k for k, n in Counter(r.rule_key for r in rules).items() if n > 1
        ),
        "families_expected": len(families),
        "families_with_issues": sum(1 for f in families if defined_by_family[f]),
        "families_with_rules": sum(1 for f in families if rules_by_family[f]),
        "families_without_rules": [f for f in families if not rules_by_family[f]],
    }

    # -- fill rates --------------------------------------------------------
    headers = [pb.header for pb in with_header]
    fill_rates = _fill_rates(
        [
            ("playbook", models.PlaybookHeader, headers),
            ("playbook_version", models.PlaybookVersionHeader, [h.version for h in headers]),  # type: ignore[union-attr]
            ("playbook_rule", models.Rule, bare),
            ("rule_position", models.Position, positions),
            ("rule_parameter", models.Parameter, parameters),
            (
                "rule_parameter.override",
                models.ParameterOverride,
                [o for p in parameters for o in (p.context_overrides or [])],
            ),
            ("red_line (rule)", models.RedLine, rule_red_lines),
            ("red_line (global)", models.RedLine, global_red_lines),
            ("rule_objection", models.Objection, objections),
            ("rule_dependency", models.Dependency, dependencies),
            ("rule_test_case", models.TestCase, test_cases),
            ("clause_issue", models.TaxonomyIssue, list(tax.issues) if tax else []),
            ("context_dimension", models.ContextDimension, dimensions),
            (
                "context_dimension.value",
                models.DimensionValue,
                [v for d in dimensions for v in d.values],
            ),
            ("approver_role", models.ApproverRole, roles),
            ("escalation_policy", models.EscalationPolicy, policies),
        ]
    )

    # -- zone distribution of positions -------------------------------------
    zone_by_kind = {
        kind: dict.fromkeys(("green", "yellow"), 0)
        for kind in ("preferred", "fallback", "acceptable_variant")
    }
    for position in positions:
        zone_by_kind[position.kind][position.zone] += 1
    zone_distribution = {
        "total": len(positions),
        "by_zone": {
            zone: sum(row[zone] for row in zone_by_kind.values()) for zone in ("green", "yellow")
        },
        "by_kind": zone_by_kind,
    }

    # -- approver distribution -----------------------------------------------
    uses = {
        "positions": Counter(p.approver_role for p in positions if p.approver_role),
        "red_lines": Counter(
            x.approver_role for x in rule_red_lines + global_red_lines if x.approver_role
        ),
        "policies": Counter(p.approver_role for p in policies),
        "consulted": Counter(role for p in policies for role in p.consult_roles),
        "playbooks_owned": Counter(h.owner_role for h in headers),  # type: ignore[union-attr]
    }
    defined_roles = [r.key for r in roles]
    referenced = set().union(*(set(c) for c in uses.values()))
    approver_rows = [
        {
            "role": role,
            "defined": role in defined_roles,
            **{name: counter[role] for name, counter in uses.items()},
        }
        for role in defined_roles + sorted(referenced - set(defined_roles))
    ]

    # -- test-case mix ---------------------------------------------------------
    outcomes = Counter(t.expected_outcome for t in test_cases)
    zones = Counter(t.expected_zone for t in test_cases)
    test_case_mix = {
        "total": len(test_cases),
        "by_outcome": {
            name: outcomes[name]
            for name in (
                "compliant",
                "acceptable_variant",
                "fallback",
                "deviation",
                "red_line",
                "missing",
            )
        },
        "by_zone": {zone: zones[zone] for zone in ("green", "yellow", "red")},
        "traps": sum(1 for t in test_cases if t.is_trap),
        "rules_with_a_trap": sum(1 for r in bare if any(t.is_trap for t in r.test_cases)),
        "with_context": sum(1 for t in test_cases if t.context),
    }

    all_checks = tables + reference_checks + playbook_rows + [minimums["check"]]
    missed = [
        f"rules in {c['name']}" if c in playbook_rows else c["name"]
        for c in all_checks
        if not c["met"]
    ]
    return {
        "directory": str(seed.root),
        "ok": not missed,
        "missed": missed,
        "tables": tables,
        "reference_checks": reference_checks,
        "playbooks": playbook_rows,
        "minimum_violations": minimums,
        "validation": validation,
        "family_coverage": family_rows,
        "issue_coverage": issue_coverage,
        "fill_rates": fill_rates,
        "zone_distribution": zone_distribution,
        "approver_distribution": approver_rows,
        "test_case_mix": test_case_mix,
        "versions": {
            "modelled": versions.modelled,
            "files_on_disk": versions.files_on_disk,
        },
    }


# --------------------------------------------------------------------------
# Text output
# --------------------------------------------------------------------------

MAX_LISTED = 40  # findings shown in the text report
MAX_INLINE = 8  # keys shown in a one-line list; --json has them all


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]], right: Sequence[int] = ()) -> str:
    """Aligned columns. ``right`` lists the column indexes to right-align."""
    text_rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    widths = [max([len(h)] + [len(r[i]) for r in text_rows]) for i, h in enumerate(headers)]

    def line(cells: Sequence[str]) -> str:
        parts = [
            cell.rjust(widths[i]) if i in right else cell.ljust(widths[i])
            for i, cell in enumerate(cells)
        ]
        return ("  " + "  ".join(parts)).rstrip()

    out = [line(headers), line(["-" * w for w in widths])]
    out.extend(line(r) for r in text_rows)
    return "\n".join(out)


def _status(met: bool) -> str:
    return "ok" if met else "MISSED"


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _check_rows(checks: Iterable[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            "  " + c["name"].split(": ", 1)[1] if c.get("part_of") else c["name"],
            c["count"],
            ("= " if c["comparison"] == "exact" else ">= ") + str(c["target"]),
            _status(c["met"]),
            c["note"],
        ]
        for c in checks
    ]


def _listed(items: Sequence[str]) -> str:
    if not items:
        return "none"
    shown = ", ".join(items[:MAX_INLINE])
    more = len(items) - MAX_INLINE
    return f"{shown}, and {more} more" if more > 0 else shown


def render_text(report: dict[str, Any]) -> str:
    """The human-readable report."""
    out: list[str] = [f"Playbook seed coverage: {report['directory']}"]

    def section(title: str, body: str) -> None:
        out.extend(["", title, body])

    check_headers = ["", "count", "target", "", "note"]
    section(
        "Tables (plan 7.3, seed-sourced rows)",
        _table(["table", *check_headers[1:]], _check_rows(report["tables"]), right=(1,)),
    )
    section(
        "Reference data (plan 7.3, migration-sourced rows: checked, not created)",
        _table(["check", *check_headers[1:]], _check_rows(report["reference_checks"]), right=(1,)),
    )
    section(
        "Rules per playbook (plan 7.1)",
        _table(["playbook", *check_headers[1:]], _check_rows(report["playbooks"]), right=(1,)),
    )

    minimums = report["minimum_violations"]
    lines = [
        f"  {minimums['errors']} error(s) on {minimums['rules_affected']} rule(s), "
        f"{minimums['warnings']} warning(s)  [{_status(minimums['check']['met'])}]"
    ]
    if minimums["by_code"]:
        lines.append(_table(["code", "count"], minimums["by_code"].items(), right=(1,)))
        items = minimums["items"]
        lines.append(
            _table(
                ["level", "playbook", "rule", "finding"],
                [
                    [i["level"], i["playbook"] or i["file"], i["rule_key"], i["message"]]
                    for i in items[:MAX_LISTED]
                ],
            )
        )
        if len(items) > MAX_LISTED:
            lines.append(f"  and {len(items) - MAX_LISTED} more; see --json or the validator")
    validation = report["validation"]
    lines.append(
        f"  other validator findings: {validation['errors']} error(s), "
        f"{validation['warnings']} warning(s), of which {validation['pending']} not written yet "
        "(run python -m seed.playbooks.validate)"
    )
    section("Per-rule minimums (plan 7.2)", "\n".join(lines))

    coverage = report["issue_coverage"]
    section(
        "Family coverage",
        _table(
            ["family", "issues", "used", "rules", "playbooks", ""],
            [
                [
                    f["family"],
                    f["issues"],
                    f["issues_used"],
                    f["rules"],
                    f["playbooks"],
                    "" if f["expected"] else "not in expected_families",
                ]
                for f in report["family_coverage"]
            ],
            right=(1, 2, 3, 4),
        )
        + f"\n  {coverage['families_with_rules']} of {coverage['families_expected']} expected "
        f"families have a rule; {coverage['families_with_issues']} have an issue"
        + f"\n  without rules: {_listed(coverage['families_without_rules'])}",
    )
    section(
        "Issue coverage",
        "\n".join(
            [
                f"  defined {coverage['defined']}, used by rules {coverage['used']}, "
                f"reserved {len(coverage['reserved'])}",
                f"  reserved: {_listed(coverage['reserved'])}",
                f"  rule keys not in the taxonomy: {_listed(coverage['used_but_not_in_taxonomy'])}",
                "  in more than one playbook (overrides): "
                f"{len(coverage['used_in_more_than_one_playbook'])}",
            ]
        ),
    )

    section(
        "Optional field fill rates (nullable: holds a value; default: differs from the default)",
        _table(
            ["table", "field", "kind", "filled", "of", "rate"],
            [
                [r["model"], r["field"], r["kind"], r["filled"], r["total"]]
                + [_pct(r["filled"], r["total"])]
                for r in report["fill_rates"]
                if r["total"]
            ],
            right=(3, 4, 5),
        )
        + "\n  nothing loaded yet for: "
        + _listed(list(dict.fromkeys(r["model"] for r in report["fill_rates"] if not r["total"]))),
    )

    zones = report["zone_distribution"]
    zone_rows = [
        [kind, row["green"], row["yellow"], _pct(row["yellow"], row["green"] + row["yellow"])]
        for kind, row in zones["by_kind"].items()
    ]
    zone_rows.append(
        [
            "total",
            zones["by_zone"]["green"],
            zones["by_zone"]["yellow"],
            _pct(zones["by_zone"]["yellow"], zones["total"]),
        ]
    )
    section(
        "Zone distribution of positions",
        _table(["kind", "green", "yellow", "yellow share"], zone_rows, right=(1, 2, 3)),
    )

    section(
        "Approver distribution",
        _table(
            ["role", "positions", "red lines", "policies", "consulted", "playbooks owned", ""],
            [
                [
                    r["role"],
                    r["positions"],
                    r["red_lines"],
                    r["policies"],
                    r["consulted"],
                    r["playbooks_owned"],
                    "" if r["defined"] else "not in authority.yaml",
                ]
                for r in report["approver_distribution"]
            ],
            right=(1, 2, 3, 4, 5),
        )
        if report["approver_distribution"]
        else "  no roles",
    )

    mix = report["test_case_mix"]
    mix_rows = [[name, n, _pct(n, mix["total"])] for name, n in mix["by_outcome"].items()]
    mix_rows.append(["total", mix["total"], ""])
    section(
        "Test-case mix by expected outcome",
        _table(["outcome", "cases", "share"], mix_rows, right=(1, 2))
        + "\n  expected zone: "
        + ", ".join(f"{zone} {n}" for zone, n in mix["by_zone"].items())
        + f"\n  traps: {mix['traps']} on {mix['rules_with_a_trap']} rule(s); "
        f"with a deal context: {mix['with_context']}",
    )

    out.append("")
    if report["ok"]:
        out.append("RESULT: all targets met")
    else:
        out.append(f"RESULT: {len(report['missed'])} target(s) missed")
        out.extend(f"  - {name}" for name in report["missed"])
    return "\n".join(out)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _main(args: argparse.Namespace, emit: Callable[[str], None] = print) -> int:
    report = build_report(args.data_dir)
    emit(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0 if report["ok"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Report the playbook seed's coverage against its targets. Reads files only; no database.",
        prog="python -m seed.playbooks.report",
    )
    add_data_dir_argument(parser, data_dir("playbooks"))
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return run(_main, parser, argv)


if __name__ == "__main__":
    raise SystemExit(main())
