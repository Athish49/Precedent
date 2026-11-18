"""Models for the playbook seed files.

Two groups:

* **File models** (Pydantic, unknown keys forbidden): one per YAML shape.
  ``Taxonomy`` for ``taxonomy.yaml``, ``Authority`` for ``authority.yaml``,
  ``PlaybookHeader`` for ``playbooks/<dir>/playbook.yaml`` and ``RuleFile`` /
  ``Rule`` for the rule files. They check shape, types and enumerations only.
  Everything that needs a second field, a second rule or a second file is a
  cross-check in :mod:`seed.playbooks.validate`, so that one run reports every
  problem in a rule instead of stopping at the first.
* **Containers** (dataclasses): ``SeedDirectory`` is a whole data directory
  loaded into typed objects, with the source file of every rule. ``Issue`` is
  one validator finding.

References between seed files are by key, never by id: ``owner_role``,
``approver_role``, ``parent``, ``recommended_position: {rule_key, rung}``.

These models belong to the seed and are not used by the application.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
)

# --------------------------------------------------------------------------
# Enumerations (playbook_plan.md section 3)
# --------------------------------------------------------------------------

PracticeArea = Literal["baseline", "nda", "saas_msa", "dpa", "hipaa", "gdpr", "vendor_msa"]
Layer = Literal["base", "agreement", "overlay"]
PartyRole = Literal["vendor", "customer", "mutual"]
PaperScope = Literal["own", "counterparty", "both"]
PlaybookStatus = Literal["draft", "active", "archived"]
VersionStatus = Literal["draft", "published", "superseded"]
Zone = Literal["green", "yellow", "red"]
PositionZone = Literal["green", "yellow"]
PolicyZone = Literal["yellow", "red"]
PositionKind = Literal["preferred", "fallback", "acceptable_variant"]
ParameterValueType = Literal[
    "number", "duration_days", "percent", "currency_usd", "enum", "boolean"
]
ParameterDirection = Literal["higher_is_better", "lower_is_better", "exact", "set_membership"]
ConditionType = Literal["phrase", "regex", "parameter", "semantic"]
RedLineAction = Literal["block", "escalate"]
ParameterOp = Literal[
    "is_absent", "is_present", "gt", "gte", "lt", "lte", "eq", "ne", "in", "not_in"
]
ObjectionFrequency = Literal["common", "occasional", "rare"]
DependencyRelation = Literal["read_with", "trade_against", "requires", "conflicts_with"]
ChangeType = Literal["added", "modified", "removed"]
ExpectedOutcome = Literal[
    "compliant", "acceptable_variant", "fallback", "deviation", "red_line", "missing"
]
DimensionValueType = Literal["enum", "multi_enum"]
DimensionSource = Literal["upload", "metadata", "derived"]
RoleFunction = Literal["legal", "security", "privacy", "finance", "sales", "delivery"]

NUMERIC_VALUE_TYPES: frozenset[str] = frozenset(
    {"number", "duration_days", "percent", "currency_usd"}
)
OPS_WITHOUT_VALUE: frozenset[str] = frozenset({"is_absent", "is_present"})

# --------------------------------------------------------------------------
# Field types
# --------------------------------------------------------------------------

# Required free text: stripped, not empty.
Text = Annotated[str, StringConstraints(min_length=1)]
# snake_case key: families, issues, roles, dimensions, dimension values, parameters.
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
# Playbook slug, e.g. halcyon-saas-msa-vendor.
PlaybookKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")]
# Red line or escalation policy key, e.g. lol-uncapped.
SlugKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]*$")]
# {family}.{issue}
RuleKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")]
# A file name inside the playbook folder, no sub-folders.
RuleFileName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*\.ya?ml$")]
# Context condition: dimension key -> the values it matches. All keys must match.
Condition = dict[Key, Annotated[list[Text], Field(min_length=1)]]
# Deal context of a test case: dimension key -> one value (enum) or a list (multi_enum).
Context = dict[Key, Any]


class SeedModel(BaseModel):
    """Base for every seed file model: unknown keys are an error."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------
# taxonomy.yaml
# --------------------------------------------------------------------------


class TaxonomyIssue(SeedModel):
    family: Key
    key: Key
    name: Text
    description: Text
    detection_hints: Text

    @property
    def rule_key(self) -> str:
        return f"{self.family}.{self.key}"


class Taxonomy(SeedModel):
    """``taxonomy.yaml``. Families come from a migration; only their keys are listed here."""

    expected_families: Annotated[list[Key], Field(min_length=1)]
    issues: Annotated[list[TaxonomyIssue], Field(min_length=1)]


# --------------------------------------------------------------------------
# authority.yaml
# --------------------------------------------------------------------------


class DimensionValue(SeedModel):
    value: Key
    definition: Text
    label: Text | None = None


class ContextDimension(SeedModel):
    key: Key
    name: Text
    value_type: DimensionValueType
    source: DimensionSource
    values: Annotated[list[DimensionValue], Field(min_length=1)]

    def value_keys(self) -> list[str]:
        return [v.value for v in self.values]


class ApproverRole(SeedModel):
    key: Key
    name: Text
    function: RoleFunction
    level: Annotated[StrictInt, Field(ge=1, le=10)]
    default_sla_hours: Annotated[StrictInt, Field(ge=1)]


class RedLine(SeedModel):
    """A red line on a rule (``red_lines`` in a rule) or a global one (``authority.yaml``).

    ``condition`` is checked against ``condition_type`` by the validator; use
    :func:`parse_red_line_condition` to get it as a typed object.
    """

    key: SlugKey
    description: Text
    condition_type: ConditionType
    condition: dict[str, Any]
    action: RedLineAction
    approver_role: Key | None = None
    rationale: Text


class EscalationPolicy(SeedModel):
    key: SlugKey
    description: Text | None = None
    playbook: PlaybookKey | None = None  # null: all playbooks
    clause_type: Key | None = None  # family key; null: any clause
    zone: PolicyZone
    conditions: Condition | None = None
    approver_role: Key
    consult_roles: list[Key] = Field(default_factory=list)
    sla_hours: Annotated[StrictInt, Field(ge=1)]
    required_info: Annotated[list[Text], Field(min_length=1)]
    priority: StrictInt


class Authority(SeedModel):
    """``authority.yaml``."""

    context_dimensions: Annotated[list[ContextDimension], Field(min_length=1)]
    roles: Annotated[list[ApproverRole], Field(min_length=1)]
    global_red_lines: list[RedLine] = Field(default_factory=list)
    escalation_policies: list[EscalationPolicy] = Field(default_factory=list)

    def dimension(self, key: str) -> ContextDimension | None:
        return next((d for d in self.context_dimensions if d.key == key), None)

    def role_keys(self) -> set[str]:
        return {r.key for r in self.roles}


# Red line condition shapes (playbook_plan.md section 3.7).


class PhraseCondition(SeedModel):
    any: Annotated[list[Text], Field(min_length=1)]
    negation_guard: StrictBool = True


class RegexCondition(SeedModel):
    pattern: Text
    flags: Annotated[str, StringConstraints(pattern=r"^[imsx]*$")] = ""


class ParameterCondition(SeedModel):
    parameter_key: Key
    op: ParameterOp
    value: Any = None  # required unless op is is_absent / is_present


class SemanticCondition(SeedModel):
    test: Text


CONDITION_MODELS: dict[str, type[SeedModel]] = {
    "phrase": PhraseCondition,
    "regex": RegexCondition,
    "parameter": ParameterCondition,
    "semantic": SemanticCondition,
}

RedLineCondition = PhraseCondition | RegexCondition | ParameterCondition | SemanticCondition


def parse_red_line_condition(red_line: RedLine) -> RedLineCondition:
    """Return ``red_line.condition`` as the model for its ``condition_type``.

    Raises ``pydantic.ValidationError`` if the shape does not match. On a
    directory that passed the validator it never raises.
    """
    return CONDITION_MODELS[red_line.condition_type].model_validate(red_line.condition)  # type: ignore[return-value]


# --------------------------------------------------------------------------
# playbooks/<dir>/playbook.yaml
# --------------------------------------------------------------------------


class PlaybookVersionHeader(SeedModel):
    version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+$")]
    status: VersionStatus = "published"
    effective_from: dt.date
    effective_to: dt.date | None = None
    change_summary: Text
    created_by: Text
    approved_by: Text
    published_at: dt.date | None = None

    @field_validator("version", mode="before")
    @classmethod
    def _version_is_quoted(cls, value: Any) -> Any:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            raise ValueError(f'write the version in quotes, e.g. version: "{value}"')
        return value


class PlaybookHeader(SeedModel):
    key: PlaybookKey
    name: Text
    practice_area: PracticeArea
    layer: Layer
    party_role: PartyRole
    paper_scope: PaperScope
    jurisdiction: Text
    business_unit: Text | None = None
    precedence: Annotated[StrictInt, Field(ge=0)]
    owner_role: Key
    parent: PlaybookKey | None = None
    applies_when: Condition | None = None
    review_cadence_days: Annotated[StrictInt, Field(ge=1)]
    next_review_at: dt.date | None = None
    status: PlaybookStatus = "active"
    description: Text
    version: PlaybookVersionHeader
    rule_files: Annotated[list[RuleFileName], Field(min_length=1)]


# --------------------------------------------------------------------------
# Rule files
# --------------------------------------------------------------------------


class Position(SeedModel):
    kind: PositionKind
    rung: Annotated[StrictInt, Field(ge=0)] | None = (
        None  # 0 preferred, 1..n fallbacks, none for variants
    )
    label: Text
    zone: PositionZone
    summary: Text
    language: Text
    approver_role: Key | None = None  # required when zone is yellow
    conditions: Condition | None = None
    give_get: Text | None = None
    internal_note: Text | None = None

    @property
    def effective_rung(self) -> int | None:
        """0 for the preferred position even when ``rung`` was left out."""
        if self.kind == "preferred":
            return 0
        return self.rung if self.kind == "fallback" else None


class ParameterOverride(SeedModel):
    when: Condition
    preferred_value: Any = None
    green_limit: Any = None
    yellow_limit: Any = None
    allowed_values: list[Any] | None = None


class Parameter(SeedModel):
    key: Key
    label: Text
    value_type: ParameterValueType
    unit: Text | None = None
    direction: ParameterDirection
    preferred_value: Any
    green_limit: Any = None
    yellow_limit: Any = None
    allowed_values: list[Any] | None = None
    extraction_hint: Text
    context_overrides: list[ParameterOverride] | None = None


class RecommendedPosition(SeedModel):
    rule_key: RuleKey
    rung: Annotated[StrictInt, Field(ge=0)]


class Objection(SeedModel):
    objection: Text
    their_rationale: Text
    response: Text
    talking_points: Annotated[list[Text], Field(min_length=1)]
    recommended_position: RecommendedPosition | None = None
    frequency: ObjectionFrequency
    counterparty_profile: Text | None = None


class Dependency(SeedModel):
    related_rule_key: RuleKey
    relation: DependencyRelation
    note: Text


class TestCase(SeedModel):
    __test__ = False  # not a pytest class

    name: Text
    sample_text: str = ""  # empty only for a missing-clause case
    context: Context | None = None
    expected_outcome: ExpectedOutcome
    expected_zone: Zone
    expected_position_rung: Annotated[StrictInt, Field(ge=1)] | None = None  # for fallback
    expected_red_line_key: SlugKey | None = None  # for red_line
    is_trap: StrictBool = False


class Rule(SeedModel):
    rule_key: RuleKey
    title: Text
    required: StrictBool
    risk_weight: Annotated[StrictInt, Field(ge=1, le=10)]
    negotiable: StrictBool
    default_zone: Zone = "yellow"
    needs_human_judgment: StrictBool = False
    judgment_note: Text | None = None
    applies_when: Condition | None = None
    position_summary: Text
    risk_rationale: Text
    detection_guidance: Text
    source_ref: Text | None = None
    authored_by: Text
    approved_by: Text
    last_reviewed_at: dt.date
    positions: Annotated[list[Position], Field(min_length=1)]
    parameters: list[Parameter] = Field(default_factory=list)
    red_lines: list[RedLine] = Field(default_factory=list)
    objections: list[Objection] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    test_cases: Annotated[list[TestCase], Field(min_length=1)]

    @property
    def family(self) -> str:
        return self.rule_key.split(".", 1)[0]

    @property
    def issue(self) -> str:
        return self.rule_key.split(".", 1)[1]

    @property
    def preferred(self) -> Position | None:
        return next((p for p in self.positions if p.kind == "preferred"), None)

    @property
    def fallbacks(self) -> list[Position]:
        return sorted(
            (p for p in self.positions if p.kind == "fallback"),
            key=lambda p: -1 if p.rung is None else p.rung,
        )

    @property
    def variants(self) -> list[Position]:
        return [p for p in self.positions if p.kind == "acceptable_variant"]

    def position_at(self, rung: int) -> Position | None:
        """The preferred position (rung 0) or the fallback at ``rung``."""
        return next(
            (
                p
                for p in self.positions
                if p.kind != "acceptable_variant" and p.effective_rung == rung
            ),
            None,
        )


class RuleFile(SeedModel):
    rules: Annotated[list[Rule], Field(min_length=1)]


# --------------------------------------------------------------------------
# versions/<playbook>_<version>.yaml (task 3.14)
# --------------------------------------------------------------------------


class ChangeLogEntry(SeedModel):
    """One ``playbook_change_log`` row: what changed from the prior version and why.

    ``old_value``/``new_value`` are free-form (a number, a string summary, a
    short structure, or null) since a change can touch anything from a single
    parameter limit to a whole position. ``added`` entries normally leave
    ``old_value`` null; ``removed`` entries normally leave ``new_value`` null.
    The validator does not enforce that shape, since a "removed, replaced by"
    entry legitimately sets both.
    """

    field_path: Text
    change_type: ChangeType
    old_value: Any = None
    new_value: Any = None
    reason: Text


class VersionChangeSet(SeedModel):
    """``versions/<playbook>_<version>.yaml``: a full rule set for a later version.

    ``rules`` is the complete rule set for ``version`` (not a diff): every
    rule of the playbook, carried forward unchanged or with the edits
    ``changes`` describes. It is validated exactly like a playbook's own rule
    file (same per-rule minimums, same cross-checks), so a version file reads
    as a real, standalone playbook snapshot.
    """

    playbook_key: PlaybookKey
    based_on_version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+$")]
    version: PlaybookVersionHeader
    changes: Annotated[list[ChangeLogEntry], Field(min_length=1)]
    rules: Annotated[list[Rule], Field(min_length=1)]


# --------------------------------------------------------------------------
# Containers
# --------------------------------------------------------------------------

Level = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    """One validator finding.

    ``pending`` marks a warning that exists only because the directory is not
    finished (a file or a referenced rule is not written yet). ``--strict``
    turns pending warnings into errors.
    """

    level: Level
    code: str
    file: Path
    message: str
    rule_key: str | None = None
    location: str | None = None
    pending: bool = False

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    def format(self, root: Path | None = None) -> str:
        """``ERROR   <file> [<rule_key>] <location>: <message>  (<code>)``"""
        shown = self.file
        if root is not None:
            try:
                shown = self.file.relative_to(root)
            except ValueError:
                pass
        parts = [f"{self.level.upper():<7}", shown.as_posix()]
        if self.rule_key:
            parts.append(f"[{self.rule_key}]")
        text = f"{self.location}: {self.message}" if self.location else self.message
        return f"{' '.join(parts)} {text}  ({self.code})"


@dataclass
class LoadedRule:
    """A rule with where it came from."""

    rule: Rule
    source: Path  # the rule file
    index: int  # position in that file's ``rules`` list
    playbook_dir: str  # folder name under playbooks/

    @property
    def rule_key(self) -> str:
        return self.rule.rule_key


@dataclass
class LoadedPlaybook:
    """One folder under ``playbooks/``."""

    directory: Path
    header: PlaybookHeader | None  # None if playbook.yaml is missing or invalid
    header_source: Path
    rules: list[LoadedRule] = field(default_factory=list)
    rule_files: list[Path] = field(default_factory=list)  # files found, listed ones first
    missing_rule_files: list[str] = field(default_factory=list)  # listed, not written yet
    unlisted_rule_files: list[Path] = field(default_factory=list)  # found, not in rule_files
    invalid_rule_keys: set[str] = field(default_factory=set)  # rules that failed the model

    @property
    def dir_name(self) -> str:
        return self.directory.name

    @property
    def key(self) -> str:
        """The playbook key, or the folder name when there is no valid header."""
        return self.header.key if self.header else self.directory.name

    def rule(self, rule_key: str) -> LoadedRule | None:
        return next((r for r in self.rules if r.rule_key == rule_key), None)


@dataclass
class LoadedVersion:
    """One file under ``versions/``: a full rule set for a later version."""

    version_set: VersionChangeSet
    source: Path


@dataclass
class SeedDirectory:
    """A playbook data directory loaded into typed objects.

    ``issues`` holds what went wrong while reading and parsing (unreadable
    files, model errors, files not written yet). Cross-checks are added by
    :func:`seed.playbooks.validate.check_directory`.
    """

    root: Path
    taxonomy: Taxonomy | None = None
    taxonomy_source: Path | None = None
    authority: Authority | None = None
    authority_source: Path | None = None
    playbooks: list[LoadedPlaybook] = field(default_factory=list)
    versions: list[LoadedVersion] = field(default_factory=list)  # versions/*.yaml (task 3.14)
    files: list[Path] = field(default_factory=list)  # every YAML file read
    issues: list[Issue] = field(default_factory=list)

    def all_rules(self) -> list[LoadedRule]:
        return [r for pb in self.playbooks for r in pb.rules]

    def playbook(self, key: str) -> LoadedPlaybook | None:
        """Look a playbook up by its key (or by folder name if it has no header)."""
        return next((pb for pb in self.playbooks if pb.key == key), None)

    def rules_by_key(self) -> dict[str, list[LoadedRule]]:
        index: dict[str, list[LoadedRule]] = {}
        for loaded in self.all_rules():
            index.setdefault(loaded.rule_key, []).append(loaded)
        return index


__all__ = [
    "CONDITION_MODELS",
    "NUMERIC_VALUE_TYPES",
    "OPS_WITHOUT_VALUE",
    "ApproverRole",
    "Authority",
    "ChangeLogEntry",
    "ContextDimension",
    "Dependency",
    "DimensionValue",
    "EscalationPolicy",
    "Issue",
    "LoadedPlaybook",
    "LoadedRule",
    "LoadedVersion",
    "Objection",
    "Parameter",
    "ParameterCondition",
    "ParameterOverride",
    "PhraseCondition",
    "PlaybookHeader",
    "PlaybookVersionHeader",
    "Position",
    "RecommendedPosition",
    "RedLine",
    "RegexCondition",
    "Rule",
    "RuleFile",
    "SeedDirectory",
    "SeedModel",
    "SemanticCondition",
    "Taxonomy",
    "TaxonomyIssue",
    "TestCase",
    "VersionChangeSet",
    "parse_red_line_condition",
]
