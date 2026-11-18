# ruff: noqa: E501  (finding messages are written as single long strings)
"""Load and validate a playbook seed directory. No database, no settings.

Command line::

    cd backend
    .venv/bin/python -m seed.playbooks.validate [dir] [--only PATH_OR_GLOB ...] [--strict] [--quiet]

``dir`` defaults to ``seed/playbooks/data/halcyon``. Exit status is 1 if any
error is reported, otherwise 0. Warnings never fail the run, except that
``--strict`` turns the *pending* warnings (something is not written yet) into
errors; use it once the whole directory is meant to be complete.

Layout read::

    <dir>/taxonomy.yaml
    <dir>/authority.yaml
    <dir>/playbooks/<folder>/playbook.yaml      header, lists rule_files
    <dir>/playbooks/<folder>/<rule file>.yaml   every other YAML file in the folder
    <dir>/versions/<playbook>_<version>.yaml    a full rule set for a later version, plus a
                                                 change log (task 3.14); each file's rules are
                                                 checked exactly like a playbook's own rule file

The directory may be partly written. A missing ``taxonomy.yaml`` or
``authority.yaml`` is a warning and the checks that need it are skipped; a
rule file listed in ``playbook.yaml`` but not written yet is a warning; a
rule file with no ``playbook.yaml`` beside it is still validated.

``--only`` limits which files are *reported on*. Everything is still loaded,
so references into other files resolve.

Programmatic use (loader 2.1, report 2.2)::

    from seed.playbooks.validate import load_directory, check_directory
    from seed.playbooks.validate import validate_directory, load_valid_directory

    seed = load_valid_directory(path)            # raises SeedValidationError on any error
    seed, issues = validate_directory(path)      # never raises for content problems
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from seed.common import (
    SeedError,
    SeedFileError,
    add_data_dir_argument,
    build_parser,
    data_dir,
    load_yaml,
    run,
)
from seed.playbooks.models import (
    CONDITION_MODELS,
    NUMERIC_VALUE_TYPES,
    OPS_WITHOUT_VALUE,
    Authority,
    ChangeLogEntry,
    Issue,
    LoadedPlaybook,
    LoadedRule,
    LoadedVersion,
    Parameter,
    PlaybookHeader,
    RedLine,
    Rule,
    SeedDirectory,
    SeedModel,
    Taxonomy,
    VersionChangeSet,
)

TAXONOMY_FILE = "taxonomy.yaml"
AUTHORITY_FILE = "authority.yaml"
PLAYBOOKS_DIR = "playbooks"
PLAYBOOK_FILE = "playbook.yaml"
VERSIONS_DIR = "versions"
YAML_SUFFIXES = (".yaml", ".yml")

# Per-rule minimums (playbook_plan.md section 7.2).
MIN_FALLBACKS_NEGOTIABLE = 2
MIN_VARIANTS = 1
MIN_OBJECTIONS_NEGOTIABLE = 2
MIN_TEST_CASES = 5
MIN_RATIONALE_SENTENCES = 2
RED_LINE_RISK_WEIGHT = 7

# Change-log totals across every file under versions/ together (task 3.14).
MIN_CHANGE_LOG_ENTRIES = 20
MIN_CHANGE_LOG_MODIFIED = 14
MIN_CHANGE_LOG_ADDED = 3
MIN_CHANGE_LOG_REMOVED = 3

# Warnings that exist only because the directory is unfinished. --strict makes them errors.
PENDING_CODES: frozenset[str] = frozenset(
    {
        "taxonomy.missing",
        "authority.missing",
        "playbooks.missing",
        "playbook.header_missing",
        "playbook.rule_file_missing",
        "playbook.rule_file_unlisted",
        "playbook.parent_pending",
        "authority.playbook_pending",
        "objection.recommended_position_pending",
        "dependency.pending",
        "test_case.red_line_pending",
    }
)
# Shown even when --only filters their file out, because they change what was checked.
ALWAYS_SHOWN_CODES: frozenset[str] = frozenset(
    {"taxonomy.missing", "authority.missing", "taxonomy.invalid", "authority.invalid"}
)


class SeedValidationError(SeedError):
    """The directory has validation errors. ``issues`` holds all findings."""

    def __init__(self, root: Path, issues: list[Issue]) -> None:
        self.root = root
        self.issues = issues
        errors = [i for i in issues if i.is_error]
        lines = [f"{root}: {len(errors)} validation error(s)"]
        lines.extend(i.format(root) for i in errors)
        super().__init__("\n".join(lines))


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _format_loc(loc: Sequence[Any]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def _schema_issues(
    exc: ValidationError, file: Path, *, rule_key: str | None = None, prefix: str = ""
) -> list[Issue]:
    issues = []
    for err in exc.errors():
        loc = _format_loc(err["loc"])
        if prefix:
            loc = f"{prefix}.{loc}" if loc and not loc.startswith("[") else f"{prefix}{loc}"
        kind = err["type"]
        if kind == "extra_forbidden":
            message = "unknown field; it is not part of the seed file format"
        elif kind == "missing":
            message = "required field is missing"
        else:
            message = err["msg"]
            if kind not in {"literal_error", "missing"} and "input" in err:
                shown = repr(err["input"])
                if len(shown) <= 60:
                    message += f" (found {shown})"
        issues.append(
            Issue("error", "schema", file, message, rule_key=rule_key, location=loc or None)
        )
    return issues


def _read_mapping(path: Path, seed: SeedDirectory) -> dict[str, Any] | None:
    seed.files.append(path)
    try:
        data = load_yaml(path)
    except SeedFileError as exc:
        seed.issues.append(Issue("error", "file.unreadable", path, exc.message))
        return None
    if not isinstance(data, dict):
        found = "an empty file" if data is None else type(data).__name__
        seed.issues.append(
            Issue("error", "file.unreadable", path, f"top level must be a mapping, found {found}")
        )
        return None
    return data


def _load_model(path: Path, model: type[SeedModel], seed: SeedDirectory) -> Any:
    data = _read_mapping(path, seed)
    if data is None:
        return None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        seed.issues.extend(_schema_issues(exc, path))
        return None


def _yaml_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in YAML_SUFFIXES)


def _load_reference_file(seed: SeedDirectory, name: str, model: type[SeedModel], needs: str) -> Any:
    path = seed.root / name
    stem = name.split(".")[0]
    if not path.is_file():
        seed.issues.append(
            Issue(
                "warning",
                f"{stem}.missing",
                path,
                f"{name} is not written yet; {needs} are skipped",
                pending=True,
            )
        )
        return None
    loaded = _load_model(path, model, seed)
    if loaded is None:
        seed.issues.append(
            Issue("warning", f"{stem}.invalid", path, f"{name} has errors; {needs} are skipped")
        )
    return loaded


def _load_rule_file(path: Path, playbook: LoadedPlaybook, seed: SeedDirectory) -> None:
    data = _read_mapping(path, seed)
    if data is None:
        return
    extra = sorted(k for k in data if k != "rules")
    for key in extra:
        seed.issues.append(
            Issue(
                "error",
                "schema",
                path,
                "unknown field; a rule file has only `rules`",
                location=str(key),
            )
        )
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        seed.issues.append(
            Issue("error", "schema", path, "must be a non-empty list of rules", location="rules")
        )
        return
    for index, raw in enumerate(rules):
        raw_key = raw.get("rule_key") if isinstance(raw, dict) else None
        rule_key = raw_key if isinstance(raw_key, str) else None
        try:
            rule = Rule.model_validate(raw)
        except ValidationError as exc:
            if rule_key:
                playbook.invalid_rule_keys.add(rule_key)
            seed.issues.extend(
                _schema_issues(exc, path, rule_key=rule_key, prefix=f"rules[{index}]")
            )
            continue
        playbook.rules.append(
            LoadedRule(rule=rule, source=path, index=index, playbook_dir=playbook.dir_name)
        )


def _load_playbook_folder(folder: Path, seed: SeedDirectory) -> LoadedPlaybook | None:
    files = _yaml_files(folder)
    if not files:
        return None
    header_path = folder / PLAYBOOK_FILE
    playbook = LoadedPlaybook(directory=folder, header=None, header_source=header_path)
    present = {p.name: p for p in files if p.name != PLAYBOOK_FILE}

    if header_path.is_file():
        playbook.header = _load_model(header_path, PlaybookHeader, seed)
    else:
        seed.issues.append(
            Issue(
                "warning",
                "playbook.header_missing",
                header_path,
                "playbook.yaml is not written yet; the rule files in this folder are validated without it",
                pending=True,
            )
        )

    ordered: list[Path] = []
    if playbook.header is not None:
        seen: set[str] = set()
        for name in playbook.header.rule_files:
            if name in seen:
                seed.issues.append(
                    Issue(
                        "error",
                        "playbook.rule_file_duplicate",
                        header_path,
                        f"rule file {name!r} is listed twice",
                        location="rule_files",
                    )
                )
                continue
            seen.add(name)
            if name == PLAYBOOK_FILE:
                seed.issues.append(
                    Issue(
                        "error",
                        "schema",
                        header_path,
                        "playbook.yaml cannot be a rule file",
                        location="rule_files",
                    )
                )
            elif name in present:
                ordered.append(present[name])
            else:
                playbook.missing_rule_files.append(name)
                seed.issues.append(
                    Issue(
                        "warning",
                        "playbook.rule_file_missing",
                        header_path,
                        f"rule file {name!r} is listed but not written yet",
                        location="rule_files",
                        pending=True,
                    )
                )
        for name, path in present.items():
            if name not in seen:
                playbook.unlisted_rule_files.append(path)
                ordered.append(path)
                seed.issues.append(
                    Issue(
                        "warning",
                        "playbook.rule_file_unlisted",
                        path,
                        "file is not listed in playbook.yaml rule_files; it is validated, but the loader will not load it",
                        pending=True,
                    )
                )
    else:
        ordered = list(present.values())

    playbook.rule_files = ordered
    for path in ordered:
        _load_rule_file(path, playbook, seed)
    return playbook


def load_directory(root: Path | str) -> SeedDirectory:
    """Read every seed file under ``root`` into typed objects.

    Never raises for content problems: unreadable files, model errors and
    files not written yet are recorded in ``SeedDirectory.issues``, and
    whatever did parse is returned. Raises :class:`SeedFileError` only if
    ``root`` is not a directory. Run :func:`check_directory` for cross-checks.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        raise SeedFileError(root_path, "directory not found")
    seed = SeedDirectory(root=root_path)

    seed.taxonomy_source = root_path / TAXONOMY_FILE
    seed.taxonomy = _load_reference_file(
        seed, TAXONOMY_FILE, Taxonomy, "family and issue checks on rule keys"
    )
    seed.authority_source = root_path / AUTHORITY_FILE
    seed.authority = _load_reference_file(
        seed, AUTHORITY_FILE, Authority, "role, context and global red line checks"
    )

    for path in _yaml_files(root_path):
        if path.name not in {TAXONOMY_FILE, AUTHORITY_FILE}:
            seed.issues.append(
                Issue(
                    "warning",
                    "file.unexpected",
                    path,
                    "file is not part of the seed layout and was not read",
                )
            )

    playbooks_dir = root_path / PLAYBOOKS_DIR
    if playbooks_dir.is_dir():
        for path in _yaml_files(playbooks_dir):
            seed.issues.append(
                Issue(
                    "warning",
                    "file.unexpected",
                    path,
                    "expected playbooks/<folder>/<file>.yaml; file was not read",
                )
            )
        for folder in sorted(p for p in playbooks_dir.iterdir() if p.is_dir()):
            playbook = _load_playbook_folder(folder, seed)
            if playbook is not None:
                seed.playbooks.append(playbook)
    if not seed.playbooks:
        seed.issues.append(
            Issue(
                "warning",
                "playbooks.missing",
                playbooks_dir,
                "no playbook folders are written yet",
                pending=True,
            )
        )

    versions_dir = root_path / VERSIONS_DIR
    if versions_dir.is_dir():
        for path in versions_dir.iterdir():
            if path.is_dir():
                seed.issues.append(
                    Issue(
                        "warning",
                        "file.unexpected",
                        path,
                        "expected versions/<file>.yaml; sub-folders are not read",
                    )
                )
        for path in _yaml_files(versions_dir):
            version_set = _load_model(path, VersionChangeSet, seed)
            if version_set is not None:
                seed.versions.append(LoadedVersion(version_set=version_set, source=path))
    return seed


# --------------------------------------------------------------------------
# Text heuristics
# --------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\.\.\.|…|\[\s*(?:TBD|TODO)\s*\]|\bTBD\b", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]?(?:\s+|$)")
_REFERENCE_NUMBER_RE = re.compile(
    r"(?:\b(?:sections?|articles?|clauses?|parts?|schedules?|exhibits?|annex(?:es)?|appendix|paragraphs?|c\.f\.r\.|u\.s\.c\.|iso|soc|type|hl7)|§+)\s*[\dIVX][\w.()-]*(?:\s*(?:and|or|,)\s*\d[\w.()-]*)*",
    re.IGNORECASE,
)
_STATUTE_TITLE_RE = re.compile(r"\b\d+\s+(?=(?:C\.F\.R\.|U\.S\.C\.))", re.IGNORECASE)
_NUMBER_WORD_RE = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|eighteen|twenty|"
    r"twenty-four|thirty|thirty-six|forty-five|forty-eight|sixty|seventy-two|ninety|hundred)\b"
    r"(?:\s*\(\d+\))?\s+(?:business\s+|calendar\s+)?(?:day|month|year|hour|week|percent)s?\b",
    re.IGNORECASE,
)


def find_placeholder(text: str) -> str | None:
    """Return the first "...", "[TBD]"-style marker in ``text``, if any.

    Bracketed blanks such as ``US$[amount]`` are legitimate in clause language
    and are not reported.
    """
    match = _PLACEHOLDER_RE.search(text)
    return match.group(0) if match else None


def sentence_count(text: str) -> int:
    """Rough count of sentences: pieces of three or more words ending in . ! or ?"""
    return sum(1 for piece in _SENTENCE_END_RE.split(text.strip()) if len(piece.split()) >= 3)


def mentions_number(text: str) -> bool:
    """Heuristic: does clause language state a number, period, percentage or amount?

    Digits that only number a section, statute or standard are ignored.
    """
    stripped = _STATUTE_TITLE_RE.sub(" ", text)
    stripped = _REFERENCE_NUMBER_RE.sub(" ", stripped)
    return bool(re.search(r"\d", stripped) or _NUMBER_WORD_RE.search(stripped))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _walk_strings(value: Any, loc: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield loc, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, f"{loc}.{key}" if loc else str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{loc}[{index}]")


# --------------------------------------------------------------------------
# Cross-checks
# --------------------------------------------------------------------------


class _Checker:
    def __init__(self, seed: SeedDirectory) -> None:
        self.seed = seed
        self.issues: list[Issue] = []
        tax, auth = seed.taxonomy, seed.authority
        self.families: set[str] | None = set(tax.expected_families) if tax else None
        self.issue_keys: set[str] | None = {i.rule_key for i in tax.issues} if tax else None
        self.roles: set[str] | None = auth.role_keys() if auth else None
        self.dimensions: dict[str, tuple[str, set[str]]] | None = (
            {d.key: (d.value_type, set(d.value_keys())) for d in auth.context_dimensions}
            if auth
            else None
        )
        self.global_red_lines: dict[str, RedLine] | None = (
            {r.key: r for r in auth.global_red_lines} if auth else None
        )
        self.rules_by_key = seed.rules_by_key()
        self.invalid_rule_keys: set[str] = set().union(
            *(pb.invalid_rule_keys for pb in seed.playbooks)
        )

    # -- reporting -----------------------------------------------------

    def error(
        self,
        code: str,
        file: Path,
        message: str,
        rule_key: str | None = None,
        loc: str | None = None,
    ) -> None:
        self.issues.append(Issue("error", code, file, message, rule_key=rule_key, location=loc))

    def warn(
        self,
        code: str,
        file: Path,
        message: str,
        rule_key: str | None = None,
        loc: str | None = None,
    ) -> None:
        self.issues.append(
            Issue(
                "warning",
                code,
                file,
                message,
                rule_key=rule_key,
                location=loc,
                pending=code in PENDING_CODES,
            )
        )

    # -- shared pieces ---------------------------------------------------

    def check_role(self, role: str | None, file: Path, rule_key: str | None, loc: str) -> None:
        if role is None or self.roles is None or role in self.roles:
            return
        self.error(
            "role.unknown",
            file,
            f"role {role!r} is not defined in authority.yaml (known: {', '.join(sorted(self.roles))})",
            rule_key,
            loc,
        )

    def check_condition(
        self, condition: dict[str, list[str]] | None, file: Path, rule_key: str | None, loc: str
    ) -> None:
        """``conditions`` / ``applies_when`` / ``when``: dimension key -> list of values."""
        if not condition or self.dimensions is None:
            return
        for key, values in condition.items():
            if key not in self.dimensions:
                self.error(
                    "context.unknown_dimension",
                    file,
                    f"context dimension {key!r} is not defined in authority.yaml (known: {', '.join(sorted(self.dimensions))})",
                    rule_key,
                    loc,
                )
                continue
            allowed = self.dimensions[key][1]
            for value in values:
                if value not in allowed:
                    self.error(
                        "context.unknown_value",
                        file,
                        f"{value!r} is not a value of dimension {key!r} (allowed: {', '.join(sorted(allowed))})",
                        rule_key,
                        f"{loc}.{key}",
                    )

    def check_context(
        self, context: dict[str, Any] | None, file: Path, rule_key: str | None, loc: str
    ) -> None:
        """Test-case ``context``: one value for an enum dimension, a list for a multi_enum one."""
        if not context:
            return
        for key, value in context.items():
            is_list = isinstance(value, list)
            values = value if is_list else [value]
            if not values or not all(isinstance(v, str) for v in values):
                self.error(
                    "context.value_shape",
                    file,
                    "must be a value key, or a list of value keys for a multi-value dimension",
                    rule_key,
                    f"{loc}.{key}",
                )
                continue
            if self.dimensions is None:
                continue
            if key not in self.dimensions:
                self.error(
                    "context.unknown_dimension",
                    file,
                    f"context dimension {key!r} is not defined in authority.yaml (known: {', '.join(sorted(self.dimensions))})",
                    rule_key,
                    loc,
                )
                continue
            value_type, allowed = self.dimensions[key]
            if value_type == "enum" and is_list:
                self.error(
                    "context.value_shape",
                    file,
                    f"dimension {key!r} takes a single value here, not a list",
                    rule_key,
                    f"{loc}.{key}",
                )
            elif value_type == "multi_enum" and not is_list:
                self.error(
                    "context.value_shape",
                    file,
                    f"dimension {key!r} is multi-value; write a list, e.g. [{value}]",
                    rule_key,
                    f"{loc}.{key}",
                )
            for item in values:
                if item not in allowed:
                    self.error(
                        "context.unknown_value",
                        file,
                        f"{item!r} is not a value of dimension {key!r} (allowed: {', '.join(sorted(allowed))})",
                        rule_key,
                        f"{loc}.{key}",
                    )

    def check_text(
        self, model: SeedModel, file: Path, rule_key: str | None, prefix: str = ""
    ) -> None:
        """No "..." or "[TBD]" in any text. Regex patterns are exempt."""
        data = model.model_dump()
        for red_line in _red_line_dicts(data):
            if red_line.get("condition_type") == "regex":
                red_line["condition"] = {}
        for loc, text in _walk_strings(data, prefix):
            marker = find_placeholder(text)
            if marker:
                self.error(
                    "text.placeholder",
                    file,
                    f"text contains the placeholder {marker!r}; write it out in full",
                    rule_key,
                    loc,
                )

    def check_red_line(
        self,
        red_line: RedLine,
        file: Path,
        rule_key: str | None,
        loc: str,
        parameter_keys: set[str] | None,
    ) -> None:
        """``parameter_keys`` is None for a global red line."""
        try:
            condition = CONDITION_MODELS[red_line.condition_type].model_validate(red_line.condition)
        except ValidationError as exc:
            for err in exc.errors():
                field = _format_loc(err["loc"])
                detail = (
                    "unknown field"
                    if err["type"] == "extra_forbidden"
                    else "required field is missing"
                    if err["type"] == "missing"
                    else err["msg"]
                )
                self.error(
                    "red_line.condition",
                    file,
                    f"{detail}; a `{red_line.condition_type}` condition is {_CONDITION_SHAPES[red_line.condition_type]}",
                    rule_key,
                    f"{loc}.condition.{field}" if field else f"{loc}.condition",
                )
            condition = None
        if condition is not None:
            if red_line.condition_type == "regex":
                try:
                    re.compile(condition.pattern)
                except re.error as exc:
                    self.error(
                        "red_line.condition",
                        file,
                        f"pattern is not a valid regular expression: {exc}",
                        rule_key,
                        f"{loc}.condition.pattern",
                    )
            elif red_line.condition_type == "parameter":
                has_value = condition.value is not None
                if condition.op in OPS_WITHOUT_VALUE and has_value:
                    self.error(
                        "red_line.condition",
                        file,
                        f"op `{condition.op}` takes no `value`",
                        rule_key,
                        f"{loc}.condition",
                    )
                elif condition.op not in OPS_WITHOUT_VALUE and not has_value:
                    self.error(
                        "red_line.condition",
                        file,
                        f"op `{condition.op}` needs a `value`",
                        rule_key,
                        f"{loc}.condition",
                    )
                elif condition.op in {"in", "not_in"} and not isinstance(condition.value, list):
                    self.error(
                        "red_line.condition",
                        file,
                        f"op `{condition.op}` needs a list `value`",
                        rule_key,
                        f"{loc}.condition",
                    )
                if parameter_keys is None:
                    self.error(
                        "red_line.global_parameter",
                        file,
                        "a global red line has no rule, so it cannot use a `parameter` condition; use `semantic`",
                        rule_key,
                        f"{loc}.condition_type",
                    )
                elif condition.parameter_key not in parameter_keys:
                    known = ", ".join(sorted(parameter_keys)) or "none"
                    self.error(
                        "red_line.unknown_parameter",
                        file,
                        f"parameter_key {condition.parameter_key!r} is not a parameter of this rule (parameters: {known})",
                        rule_key,
                        f"{loc}.condition.parameter_key",
                    )
        if red_line.action == "escalate" and red_line.approver_role is None:
            self.error(
                "red_line.approver_missing",
                file,
                "action `escalate` needs an approver_role",
                rule_key,
                loc,
            )
        self.check_role(red_line.approver_role, file, rule_key, f"{loc}.approver_role")

    def resolve_rule(self, target: str, playbook: LoadedPlaybook) -> tuple[str, list[LoadedRule]]:
        """Resolve a rule key referenced from ``playbook``.

        Returns one of ``("found", rules)``, ``("skip", [])`` (the target is in
        a rule that failed its own validation), ``("pending", [])`` (not written
        yet, but a known issue or no taxonomy to tell) or ``("unknown", [])``.
        The same playbook is preferred; otherwise every playbook that has the key.
        """
        local = [r for r in playbook.rules if r.rule_key == target]
        if local:
            return "found", local
        if target in playbook.invalid_rule_keys:
            return "skip", []
        everywhere = self.rules_by_key.get(target, [])
        if everywhere:
            return "found", everywhere
        if target in self.invalid_rule_keys:
            return "skip", []
        if self.issue_keys is None or target in self.issue_keys:
            return "pending", []
        return "unknown", []

    # -- files -----------------------------------------------------------

    def check_taxonomy(self) -> None:
        tax, file = self.seed.taxonomy, self.seed.taxonomy_source
        if tax is None or file is None:
            return
        for key, count in Counter(tax.expected_families).items():
            if count > 1:
                self.error(
                    "taxonomy.duplicate_family",
                    file,
                    f"family {key!r} is listed {count} times",
                    loc="expected_families",
                )
        families = set(tax.expected_families)
        seen: set[str] = set()
        for index, issue in enumerate(tax.issues):
            loc = f"issues[{index}]"
            if issue.family not in families:
                self.error(
                    "taxonomy.unknown_family",
                    file,
                    f"family {issue.family!r} is not in expected_families",
                    issue.rule_key,
                    loc,
                )
            if issue.rule_key in seen:
                self.error(
                    "taxonomy.duplicate_issue",
                    file,
                    f"issue {issue.rule_key!r} is defined twice",
                    issue.rule_key,
                    loc,
                )
            seen.add(issue.rule_key)
        self.check_text(tax, file, None)

    def check_authority(self) -> None:
        auth, file = self.seed.authority, self.seed.authority_source
        if auth is None or file is None:
            return

        def duplicates(keys: list[str], what: str, loc: str) -> None:
            for key, count in Counter(keys).items():
                if count > 1:
                    self.error(
                        "authority.duplicate_key",
                        file,
                        f"{what} {key!r} is defined {count} times",
                        loc=loc,
                    )

        duplicates(
            [d.key for d in auth.context_dimensions], "context dimension", "context_dimensions"
        )
        for index, dimension in enumerate(auth.context_dimensions):
            duplicates(
                dimension.value_keys(),
                f"value of dimension {dimension.key!r}",
                f"context_dimensions[{index}].values",
            )
        duplicates([r.key for r in auth.roles], "role", "roles")
        duplicates([r.key for r in auth.global_red_lines], "global red line", "global_red_lines")
        duplicates(
            [p.key for p in auth.escalation_policies], "escalation policy", "escalation_policies"
        )

        for index, red_line in enumerate(auth.global_red_lines):
            self.check_red_line(
                red_line, file, None, f"global_red_lines[{index}] ({red_line.key})", None
            )

        playbook_keys = {pb.header.key for pb in self.seed.playbooks if pb.header}
        for index, policy in enumerate(auth.escalation_policies):
            loc = f"escalation_policies[{index}] ({policy.key})"
            self.check_role(policy.approver_role, file, None, f"{loc}.approver_role")
            for role in policy.consult_roles:
                self.check_role(role, file, None, f"{loc}.consult_roles")
            if policy.approver_role in policy.consult_roles:
                self.error(
                    "authority.consult_is_approver",
                    file,
                    f"role {policy.approver_role!r} is the approver and cannot also be consulted",
                    loc=f"{loc}.consult_roles",
                )
            self.check_condition(policy.conditions, file, None, f"{loc}.conditions")
            if (
                policy.clause_type
                and self.families is not None
                and policy.clause_type not in self.families
            ):
                self.error(
                    "authority.unknown_family",
                    file,
                    f"clause_type {policy.clause_type!r} is not in taxonomy.yaml expected_families",
                    loc=f"{loc}.clause_type",
                )
            if policy.playbook and policy.playbook not in playbook_keys:
                self.warn(
                    "authority.playbook_pending",
                    file,
                    f"playbook {policy.playbook!r} is not written yet (or the key is wrong)",
                    loc=f"{loc}.playbook",
                )
        self.check_text(auth, file, None)

    def check_playbooks(self) -> None:
        headers = [pb for pb in self.seed.playbooks if pb.header]
        counts = Counter(pb.header.key for pb in headers)  # type: ignore[union-attr]
        for playbook in self.seed.playbooks:
            header, file = playbook.header, playbook.header_source
            if header is not None:
                if counts[header.key] > 1:
                    self.error(
                        "playbook.duplicate_key",
                        file,
                        f"playbook key {header.key!r} is used by {counts[header.key]} folders",
                        loc="key",
                    )
                self.check_role(header.owner_role, file, None, "owner_role")
                self.check_condition(header.applies_when, file, None, "applies_when")
                if header.parent == header.key:
                    self.error(
                        "playbook.parent_self",
                        file,
                        "a playbook cannot be its own parent",
                        loc="parent",
                    )
                elif header.parent and header.parent not in counts:
                    self.warn(
                        "playbook.parent_pending",
                        file,
                        f"parent playbook {header.parent!r} is not written yet (or the key is wrong)",
                        loc="parent",
                    )
                version = header.version
                if version.effective_to and version.effective_to < version.effective_from:
                    self.error(
                        "playbook.version_dates",
                        file,
                        "effective_to is before effective_from",
                        loc="version",
                    )
                self.check_text(header, file, None)

            seen: dict[str, LoadedRule] = {}
            for loaded in playbook.rules:
                first = seen.get(loaded.rule_key)
                if first is not None:
                    where = (
                        "earlier in this file"
                        if first.source == loaded.source
                        else f"in {first.source.name}"
                    )
                    self.error(
                        "rule.duplicate_key",
                        loaded.source,
                        f"rule_key is already used in this playbook ({where}, rules[{first.index}])",
                        loaded.rule_key,
                        f"rules[{loaded.index}]",
                    )
                else:
                    seen[loaded.rule_key] = loaded
                self.check_rule(loaded, playbook)

    # -- versions/*.yaml (task 3.14) ----------------------------------------

    def check_versions(self) -> None:
        """Validate every file under ``versions/`` and the change-log totals together.

        Each file's ``rules`` are checked exactly like a playbook's own rule
        file: duplicate keys within the file, and every per-rule cross-check
        and minimum in :meth:`check_rule`. References from a version's rules
        (``objections[].recommended_position``, ``dependencies``) resolve
        against the same playbook's current rules, so a version that only
        edits a few rules does not need to repeat untouched ones' targets.
        The change-log quota (task 3.14) is checked once, across every
        version file together, not per file.
        """
        playbooks_by_key = {pb.header.key: pb for pb in self.seed.playbooks if pb.header}
        all_changes: list[ChangeLogEntry] = []
        for loaded in self.seed.versions:
            version_set, file = loaded.version_set, loaded.source
            all_changes.extend(version_set.changes)
            target = playbooks_by_key.get(version_set.playbook_key)
            if target is None:
                self.error(
                    "version.unknown_playbook",
                    file,
                    f"playbook_key {version_set.playbook_key!r} does not match any loaded playbook "
                    f"(known: {', '.join(sorted(playbooks_by_key)) or 'none'})",
                    loc="playbook_key",
                )
            synthetic = LoadedPlaybook(
                directory=file.parent,
                header=target.header if target else None,
                header_source=file,
            )
            synthetic.rules = [
                LoadedRule(
                    rule=rule,
                    source=file,
                    index=index,
                    playbook_dir=target.dir_name if target else file.stem,
                )
                for index, rule in enumerate(version_set.rules)
            ]
            seen: dict[str, LoadedRule] = {}
            for loaded_rule in synthetic.rules:
                first = seen.get(loaded_rule.rule_key)
                if first is not None:
                    self.error(
                        "rule.duplicate_key",
                        file,
                        f"rule_key is already used in this version file (rules[{first.index}])",
                        loaded_rule.rule_key,
                        f"rules[{loaded_rule.index}]",
                    )
                else:
                    seen[loaded_rule.rule_key] = loaded_rule
                self.check_rule(loaded_rule, synthetic)
            for index, change in enumerate(version_set.changes):
                loc = f"changes[{index}]"
                for field_name, text in (("field_path", change.field_path), ("reason", change.reason)):
                    marker = find_placeholder(text)
                    if marker:
                        self.error(
                            "text.placeholder",
                            file,
                            f"text contains the placeholder {marker!r}; write it out in full",
                            loc=f"{loc}.{field_name}",
                        )
        if self.seed.versions:
            counts = Counter(c.change_type for c in all_changes)
            total = len(all_changes)
            root_file = self.seed.root / VERSIONS_DIR
            if total < MIN_CHANGE_LOG_ENTRIES:
                self.error(
                    "version.change_log_minimum",
                    root_file,
                    f"versions/*.yaml together need at least {MIN_CHANGE_LOG_ENTRIES} change-log entries; found {total}",
                )
            for change_type, minimum in (
                ("modified", MIN_CHANGE_LOG_MODIFIED),
                ("added", MIN_CHANGE_LOG_ADDED),
                ("removed", MIN_CHANGE_LOG_REMOVED),
            ):
                if counts[change_type] < minimum:
                    self.error(
                        "version.change_log_minimum",
                        root_file,
                        f"versions/*.yaml together need at least {minimum} {change_type!r} change-log entries; found {counts[change_type]}",
                    )

    # -- one rule ----------------------------------------------------------

    def check_rule(self, loaded: LoadedRule, playbook: LoadedPlaybook) -> None:
        rule, file, key = loaded.rule, loaded.source, loaded.rule_key

        def error(code: str, message: str, loc: str | None = None) -> None:
            self.error(code, file, message, key, loc)

        def warn(code: str, message: str, loc: str | None = None) -> None:
            self.warn(code, file, message, key, loc)

        # Taxonomy.
        if self.families is not None and self.issue_keys is not None:
            if rule.family not in self.families:
                error(
                    "rule.unknown_family",
                    f"family {rule.family!r} is not in taxonomy.yaml expected_families",
                    "rule_key",
                )
            elif key not in self.issue_keys:
                known = sorted(
                    k.split(".", 1)[1] for k in self.issue_keys if k.startswith(rule.family + ".")
                )
                error(
                    "rule.unknown_issue",
                    f"issue {rule.issue!r} is not defined for family {rule.family!r} in taxonomy.yaml (defined: {', '.join(known) or 'none'})",
                    "rule_key",
                )

        if rule.needs_human_judgment and not rule.judgment_note:
            error(
                "rule.judgment_note_missing",
                "needs_human_judgment is true, so judgment_note must say what the human weighs",
                "judgment_note",
            )
        self.check_condition(rule.applies_when, file, key, "applies_when")

        # Positions: one preferred, fallback rungs 1..n, yellow needs an approver.
        preferred = [p for p in rule.positions if p.kind == "preferred"]
        fallbacks = [p for p in rule.positions if p.kind == "fallback"]
        variants = [p for p in rule.positions if p.kind == "acceptable_variant"]
        if len(preferred) != 1:
            error(
                "position.preferred_count",
                f"exactly one position must have kind `preferred`; found {len(preferred)}",
                "positions",
            )
        for index, position in enumerate(rule.positions):
            loc = f"positions[{index}]"
            if position.kind == "preferred" and position.rung not in (None, 0):
                error(
                    "position.rung",
                    f"the preferred position is rung 0, not {position.rung}",
                    f"{loc}.rung",
                )
            elif position.kind == "fallback" and (position.rung is None or position.rung < 1):
                error("position.rung", "a fallback needs a rung of 1 or more", f"{loc}.rung")
            elif position.kind == "acceptable_variant" and position.rung is not None:
                error(
                    "position.rung", "an acceptable variant has no rung; remove it", f"{loc}.rung"
                )
            if position.zone == "yellow" and position.approver_role is None:
                error("position.approver_missing", "a yellow position needs an approver_role", loc)
            self.check_role(position.approver_role, file, key, f"{loc}.approver_role")
            self.check_condition(position.conditions, file, key, f"{loc}.conditions")
        rungs = sorted(p.rung for p in fallbacks if p.rung is not None and p.rung >= 1)
        if rungs and rungs != list(range(1, len(rungs) + 1)):
            error(
                "position.rung_sequence",
                f"fallback rungs must run 1..n with no gap or repeat; found {rungs}",
                "positions",
            )

        # Parameters.
        for name, count in Counter(p.key for p in rule.parameters).items():
            if count > 1:
                error(
                    "parameter.duplicate_key",
                    f"parameter key {name!r} is used {count} times",
                    "parameters",
                )
        for index, parameter in enumerate(rule.parameters):
            self.check_parameter(parameter, file, key, f"parameters[{index}] ({parameter.key})")
        parameter_keys = {p.key for p in rule.parameters}

        # Red lines.
        for name, count in Counter(r.key for r in rule.red_lines).items():
            if count > 1:
                error(
                    "red_line.duplicate_key",
                    f"red line key {name!r} is used {count} times in this rule",
                    "red_lines",
                )
        for index, red_line in enumerate(rule.red_lines):
            loc = f"red_lines[{index}] ({red_line.key})"
            if self.global_red_lines is not None and red_line.key in self.global_red_lines:
                error(
                    "red_line.shadows_global",
                    f"key {red_line.key!r} is already a global red line in authority.yaml; choose another key",
                    f"{loc}.key",
                )
            self.check_red_line(red_line, file, key, loc, parameter_keys)
        red_lines = {r.key: r for r in rule.red_lines}

        # Objections.
        for index, objection in enumerate(rule.objections):
            target = objection.recommended_position
            if target is None:
                continue
            loc = f"objections[{index}].recommended_position"
            if target.rule_key == key:
                state, found = "found", [loaded]
            else:
                state, found = self.resolve_rule(target.rule_key, playbook)
            if state == "unknown":
                error(
                    "objection.recommended_position",
                    f"rule {target.rule_key!r} does not exist in this directory and is not an issue in taxonomy.yaml",
                    loc,
                )
            elif state == "pending":
                warn(
                    "objection.recommended_position_pending",
                    f"target rule {target.rule_key!r} is not written yet; rung {target.rung} cannot be checked",
                    loc,
                )
            elif state == "found" and not any(r.rule.position_at(target.rung) for r in found):
                have = sorted(
                    {
                        p.effective_rung
                        for r in found
                        for p in r.rule.positions
                        if p.effective_rung is not None
                    }
                )
                error(
                    "objection.recommended_position",
                    f"rule {target.rule_key!r} has no position at rung {target.rung} (rungs: {have})",
                    loc,
                )

        # Dependencies.
        for index, dependency in enumerate(rule.dependencies):
            loc = f"dependencies[{index}].related_rule_key"
            if dependency.related_rule_key == key:
                error("dependency.self", "a rule cannot depend on itself", loc)
                continue
            state, _ = self.resolve_rule(dependency.related_rule_key, playbook)
            if state == "unknown":
                error(
                    "dependency.unknown_rule",
                    f"rule {dependency.related_rule_key!r} does not exist in this directory and is not an issue in taxonomy.yaml",
                    loc,
                )
            elif state == "pending":
                warn(
                    "dependency.pending",
                    f"related rule {dependency.related_rule_key!r} is not written yet",
                    loc,
                )

        # Test cases.
        fallback_by_rung = {p.rung: p for p in fallbacks if p.rung is not None}
        for name, count in Counter(t.name for t in rule.test_cases).items():
            if count > 1:
                error(
                    "test_case.duplicate_name",
                    f"test case name {name!r} is used {count} times",
                    "test_cases",
                )
        for index, case in enumerate(rule.test_cases):
            loc = f"test_cases[{index}] ({case.name})"
            if case.expected_outcome != "missing" and not case.sample_text.strip():
                error(
                    "test_case.sample_text_missing",
                    "sample_text is empty; only a `missing` case may have no text",
                    f"{loc}.sample_text",
                )
            self.check_context(case.context, file, key, f"{loc}.context")

            if case.expected_outcome == "fallback":
                if case.expected_position_rung is None:
                    error("test_case.rung", "a `fallback` case needs expected_position_rung", loc)
                elif case.expected_position_rung not in fallback_by_rung:
                    error(
                        "test_case.rung",
                        f"expected_position_rung {case.expected_position_rung} is not a fallback rung of this rule (rungs: {sorted(fallback_by_rung)})",
                        f"{loc}.expected_position_rung",
                    )
                elif fallback_by_rung[case.expected_position_rung].zone != case.expected_zone:
                    warn(
                        "test_case.zone_mismatch",
                        f"expected_zone is {case.expected_zone} but fallback rung {case.expected_position_rung} is {fallback_by_rung[case.expected_position_rung].zone}",
                        f"{loc}.expected_zone",
                    )
            elif case.expected_position_rung is not None:
                error(
                    "test_case.rung",
                    f"expected_position_rung is only for `fallback` cases, not `{case.expected_outcome}`",
                    f"{loc}.expected_position_rung",
                )

            if case.expected_outcome == "red_line":
                line_key = case.expected_red_line_key
                if line_key is None:
                    error(
                        "test_case.red_line", "a `red_line` case needs expected_red_line_key", loc
                    )
                else:
                    line = red_lines.get(line_key) or (self.global_red_lines or {}).get(line_key)
                    if line is None and self.global_red_lines is None:
                        warn(
                            "test_case.red_line_pending",
                            f"red line {line_key!r} is not on this rule; it cannot be checked as a global red line until authority.yaml exists",
                            f"{loc}.expected_red_line_key",
                        )
                    elif line is None:
                        known = ", ".join(sorted(red_lines)) or "none"
                        error(
                            "test_case.red_line",
                            f"red line {line_key!r} is neither on this rule (has: {known}) nor a global red line in authority.yaml",
                            f"{loc}.expected_red_line_key",
                        )
                    elif line.action == "block" and case.expected_zone != "red":
                        error(
                            "test_case.zone",
                            f"red line {line_key!r} blocks, so expected_zone must be red",
                            f"{loc}.expected_zone",
                        )
            elif case.expected_red_line_key is not None:
                error(
                    "test_case.red_line",
                    f"expected_red_line_key is only for `red_line` cases, not `{case.expected_outcome}`",
                    f"{loc}.expected_red_line_key",
                )

            if case.expected_outcome == "compliant" and case.expected_zone != "green":
                error("test_case.zone", "a `compliant` case is green", f"{loc}.expected_zone")

        # Per-rule minimums.
        if rule.negotiable and len(fallbacks) < MIN_FALLBACKS_NEGOTIABLE:
            error(
                "minimum.fallbacks",
                f"a negotiable rule needs at least {MIN_FALLBACKS_NEGOTIABLE} fallback positions; found {len(fallbacks)}",
                "positions",
            )
        if len(variants) < MIN_VARIANTS:
            error(
                "minimum.variants",
                f"a rule needs at least {MIN_VARIANTS} acceptable_variant position; found {len(variants)}",
                "positions",
            )
        sentences = sentence_count(rule.risk_rationale)
        if sentences < MIN_RATIONALE_SENTENCES:
            error(
                "minimum.risk_rationale",
                f"risk_rationale needs at least {MIN_RATIONALE_SENTENCES} sentences; found {sentences}",
                "risk_rationale",
            )
        if rule.risk_weight >= RED_LINE_RISK_WEIGHT and not rule.red_lines:
            error(
                "minimum.red_lines",
                f"risk_weight is {rule.risk_weight}; a rule at {RED_LINE_RISK_WEIGHT} or more needs at least one red line",
                "red_lines",
            )
        if rule.negotiable and len(rule.objections) < MIN_OBJECTIONS_NEGOTIABLE:
            error(
                "minimum.objections",
                f"a negotiable rule needs at least {MIN_OBJECTIONS_NEGOTIABLE} objections; found {len(rule.objections)}",
                "objections",
            )
        if len(rule.test_cases) < MIN_TEST_CASES:
            error(
                "minimum.test_cases",
                f"a rule needs at least {MIN_TEST_CASES} test cases; found {len(rule.test_cases)}",
                "test_cases",
            )
        outcomes = Counter(t.expected_outcome for t in rule.test_cases)
        missing_mix = [
            name for name in ("compliant", "acceptable_variant", "deviation") if not outcomes[name]
        ]
        if not outcomes["red_line"] and not any(t.is_trap for t in rule.test_cases):
            missing_mix.append("red_line or a trap (is_trap: true)")
        if rule.negotiable and not outcomes["fallback"]:
            missing_mix.append("fallback")
        elif not rule.negotiable and not (
            outcomes["fallback"] or outcomes["missing"] or outcomes["deviation"] >= 2
        ):
            missing_mix.append("missing or a second deviation (in place of the fallback case)")
        if missing_mix:
            error(
                "minimum.test_case_mix",
                f"test cases must include: {'; '.join(missing_mix)}",
                "test_cases",
            )
        if not rule.parameters and len(preferred) == 1 and mentions_number(preferred[0].language):
            warn(
                "minimum.parameters",
                "the preferred language states a number, period or amount but the rule has no parameter; add one, or ignore this if the number is not a negotiated value",
                "parameters",
            )

        self.check_text(rule, file, key)

    def check_parameter(self, parameter: Parameter, file: Path, rule_key: str, loc: str) -> None:
        def error(code: str, message: str, where: str = "") -> None:
            self.error(code, file, message, rule_key, f"{loc}.{where}" if where else loc)

        numeric = parameter.value_type in NUMERIC_VALUE_TYPES
        ordered = parameter.direction in {"lower_is_better", "higher_is_better"}
        if parameter.value_type == "enum":
            if not parameter.allowed_values:
                error(
                    "parameter.allowed_values",
                    "an `enum` parameter needs allowed_values",
                    "allowed_values",
                )
            elif not all(isinstance(v, str) for v in parameter.allowed_values):
                error(
                    "parameter.allowed_values",
                    "allowed_values must be a list of strings",
                    "allowed_values",
                )
            if ordered:
                error(
                    "parameter.direction",
                    "an `enum` parameter uses direction `exact` or `set_membership`",
                    "direction",
                )
        elif parameter.value_type == "boolean" and parameter.direction != "exact":
            error(
                "parameter.direction", "a `boolean` parameter uses direction `exact`", "direction"
            )
        if parameter.preferred_value is None:
            error("parameter.value", "preferred_value must not be null", "preferred_value")

        def check_values(values: dict[str, Any], allowed: list[Any] | None, where: str) -> None:
            prefix = f"{where}." if where else ""
            for name, value in values.items():
                if value is None:
                    if numeric and ordered and not where:
                        error(
                            "parameter.value",
                            f"a {parameter.value_type} parameter with direction {parameter.direction} needs a number here",
                            f"{prefix}{name}",
                        )
                    continue
                items = value if isinstance(value, list) else [value]
                if numeric:
                    if not all(_is_number(v) for v in items) or (
                        ordered and isinstance(value, list)
                    ):
                        error(
                            "parameter.value",
                            f"must be a number for value_type {parameter.value_type} (found {value!r})",
                            f"{prefix}{name}",
                        )
                elif parameter.value_type == "boolean":
                    if not isinstance(value, bool):
                        error(
                            "parameter.value",
                            f"must be true or false (found {value!r})",
                            f"{prefix}{name}",
                        )
                elif allowed and all(isinstance(v, str) for v in allowed):
                    bad = [v for v in items if v not in allowed]
                    if bad:
                        error(
                            "parameter.value",
                            f"{bad!r} not in allowed_values {allowed!r}",
                            f"{prefix}{name}",
                        )
            if numeric and ordered:
                trio = [values.get(n) for n in ("preferred_value", "green_limit", "yellow_limit")]
                if all(_is_number(v) for v in trio):
                    low_first = parameter.direction == "lower_is_better"
                    good = (
                        trio[0] <= trio[1] <= trio[2]
                        if low_first
                        else trio[0] >= trio[1] >= trio[2]
                    )
                    if not good:
                        sign = "<=" if low_first else ">="
                        error(
                            "parameter.order",
                            f"direction {parameter.direction} needs preferred_value {sign} green_limit {sign} yellow_limit; found {trio[0]}, {trio[1]}, {trio[2]}",
                            where,
                        )

        base = {
            "preferred_value": parameter.preferred_value,
            "green_limit": parameter.green_limit,
            "yellow_limit": parameter.yellow_limit,
        }
        check_values(base, parameter.allowed_values, "")
        for index, override in enumerate(parameter.context_overrides or []):
            where = f"context_overrides[{index}]"
            self.check_condition(override.when, file, rule_key, f"{loc}.{where}.when")
            changed = {n: getattr(override, n) for n in base if getattr(override, n) is not None}
            if not changed and override.allowed_values is None:
                error(
                    "parameter.override_empty",
                    "an override must set at least one of preferred_value, green_limit, yellow_limit, allowed_values",
                    where,
                )
                continue
            check_values(
                {**base, **changed}, override.allowed_values or parameter.allowed_values, where
            )


_CONDITION_SHAPES = {
    "phrase": "{any: [phrase, ...], negation_guard: true|false}",
    "regex": "{pattern: <regex>, flags: <optional letters from imsx>}",
    "parameter": "{parameter_key: <key>, op: <op>, value: <only for comparisons>}",
    "semantic": "{test: <yes/no statement about the clause>}",
}


def _red_line_dicts(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("red_lines") or []) + list(data.get("global_red_lines") or [])


def check_directory(seed: SeedDirectory) -> list[Issue]:
    """Run every cross-check on a loaded directory and return the findings.

    Does not include ``seed.issues`` (what went wrong while loading); use
    :func:`validate_directory` for both.
    """
    checker = _Checker(seed)
    checker.check_taxonomy()
    checker.check_authority()
    checker.check_playbooks()
    checker.check_versions()
    return checker.issues


def validate_directory(
    root: Path | str, *, strict: bool = False
) -> tuple[SeedDirectory, list[Issue]]:
    """Load ``root`` and return it with every finding (loading and cross-checks).

    With ``strict`` the pending warnings become errors. Findings are ordered by
    file, in the order the files were read.
    """
    seed = load_directory(root)
    issues = seed.issues + check_directory(seed)
    if strict:
        issues = [dataclasses.replace(i, level="error") if i.pending else i for i in issues]
    order = {path: index for index, path in enumerate(seed.files)}
    issues.sort(key=lambda i: order.get(i.file, len(order)))
    return seed, issues


def load_valid_directory(root: Path | str, *, strict: bool = False) -> SeedDirectory:
    """Load ``root`` and return it, or raise :class:`SeedValidationError` if it has any error."""
    seed, issues = validate_directory(root, strict=strict)
    if any(i.is_error for i in issues):
        raise SeedValidationError(seed.root, issues)
    return seed


def has_errors(issues: Iterable[Issue]) -> bool:
    return any(i.is_error for i in issues)


# --------------------------------------------------------------------------
# --only
# --------------------------------------------------------------------------


def _matches(file: Path, pattern: str, root: Path) -> bool:
    resolved = file.resolve()
    given = Path(pattern)
    for base in [given] if given.is_absolute() else [Path.cwd() / given, root / given]:
        target = base.resolve()
        if resolved == target or target in resolved.parents:
            return True
    names = [resolved.as_posix(), file.name]
    for base in (root.resolve(), Path.cwd().resolve()):
        try:
            names.append(resolved.relative_to(base).as_posix())
        except ValueError:
            pass
    return any(fnmatch.fnmatch(name, pattern) for name in names)


def select_issues(issues: Iterable[Issue], seed: SeedDirectory, only: Sequence[str]) -> list[Issue]:
    """Keep the findings for files matching any ``only`` entry.

    An entry is a file, a folder (everything under it) or a glob. A relative
    entry is tried against the current directory and against the data
    directory; a glob is matched against the absolute path, the path relative
    to either, and the bare file name. Raises :class:`SeedError` if an entry
    matches no seed file. Notices that a reference file is missing or broken
    are always kept, because they change what was checked.
    """
    if not only:
        return list(issues)
    issues = list(issues)
    known = set(seed.files) | {i.file for i in issues}
    for pattern in only:
        if not any(_matches(path, pattern, seed.root) for path in known):
            raise SeedError(f"--only {pattern!r} matches no seed file under {seed.root}")
    return [
        i
        for i in issues
        if i.code in ALWAYS_SHOWN_CODES
        or any(_matches(i.file, pattern, seed.root) for pattern in only)
    ]


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _main(args: argparse.Namespace) -> int:
    seed, issues = validate_directory(args.data_dir, strict=args.strict)
    issues = select_issues(issues, seed, args.only or [])
    errors = [i for i in issues if i.is_error]
    warnings = [i for i in issues if not i.is_error]
    for issue in issues:
        if issue.is_error or not args.quiet:
            print(issue.format(seed.root))
    rules = seed.all_rules()
    scope = f"; reporting only on {', '.join(args.only)}" if args.only else ""
    print(
        f"{seed.root}: {len(seed.files)} file(s), {len(seed.playbooks)} playbook(s), {len(rules)} rule(s) loaded{scope}"
    )
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Validate the playbook seed files and run the cross-checks. Reads files only; no database.",
        prog="python -m seed.playbooks.validate",
    )
    add_data_dir_argument(parser, data_dir("playbooks"))
    parser.add_argument(
        "--only",
        action="append",
        metavar="PATH_OR_GLOB",
        help="report only on matching files (a file, a folder or a glob; repeatable). "
        "All files are still loaded so references resolve.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat 'not written yet' warnings as errors; use when the directory should be complete",
    )
    parser.add_argument("--quiet", action="store_true", help="do not print warnings")
    return run(_main, parser, argv)


if __name__ == "__main__":
    raise SystemExit(main())
