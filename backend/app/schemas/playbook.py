"""Pydantic API schemas for S6 Playbook & Rules."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Playbook schemas
# ---------------------------------------------------------------------------

_VALID_PRACTICE_AREAS = frozenset({"hipaa", "gdpr", "saas_msa", "nda", "dpa"})


class PlaybookCreate(BaseModel):
    name: str
    practice_area: str
    precedence: int = 0


class PlaybookUpdate(BaseModel):
    name: str | None = None
    practice_area: str | None = None
    precedence: int | None = None


class PlaybookResponse(BaseModel):
    id: uuid.UUID
    name: str
    practice_area: str
    precedence: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Rule schemas (RuleCreate / RuleUpdate / RuleResponse) are defined further
# down, after the rule-child schemas they embed. See "Rule CRUD schemas".
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


class BootstrapRequest(BaseModel):
    """Body for POST /playbooks/bootstrap.

    Either *contract_ids* (explicit list) or *contract_type* (load all
    contracts of that type) must be provided.
    """

    playbook_id: uuid.UUID
    contract_ids: list[uuid.UUID] | None = None
    contract_type: str | None = None

    @model_validator(mode="after")
    def _check_corpus(self) -> BootstrapRequest:
        if not self.contract_ids and not self.contract_type:
            raise ValueError("Either contract_ids or contract_type must be provided")
        return self


class BootstrapResponse(BaseModel):
    created_rule_count: int


# ---------------------------------------------------------------------------
# Taxonomy schemas (task 1.1): agreement_type, clause_family, clause_issue,
# context_dimension. ``playbook_plan.md`` sections 3.1, 3.11.
# ---------------------------------------------------------------------------


class AgreementTypeResponse(BaseModel):
    key: str
    name: str
    kind: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClauseFamilyResponse(BaseModel):
    key: str
    name: str
    category: str
    description: str
    synonyms: list
    external_refs: dict
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClauseIssueResponse(BaseModel):
    id: uuid.UUID
    family_key: str
    key: str
    name: str
    description: str
    detection_hints: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContextDimensionResponse(BaseModel):
    key: str
    name: str
    value_type: str
    values: dict
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaxonomyListResponse(BaseModel):
    """Body for ``GET /playbooks/taxonomy`` (task 4.8 item 6): agreement
    types, clause families and clause issues in one read."""

    agreement_types: list[AgreementTypeResponse]
    clause_families: list[ClauseFamilyResponse]
    clause_issues: list[ClauseIssueResponse]


# ---------------------------------------------------------------------------
# Authority schemas (task 1.1): approver_role, escalation_policy.
# ``playbook_plan.md`` section 3.12.
# ---------------------------------------------------------------------------


class ApproverRoleResponse(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    function: str
    level: int
    default_sla_hours: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EscalationPolicyResponse(BaseModel):
    id: uuid.UUID
    playbook_id: uuid.UUID | None
    clause_type: str | None
    zone: str
    conditions: dict | None
    approver_role_id: uuid.UUID
    consult_role_ids: list
    sla_hours: int
    required_info: dict
    priority: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Version schemas (task 1.2): playbook_version, playbook_change_log.
# ``playbook_plan.md`` section 3.3.
# ---------------------------------------------------------------------------


class PlaybookVersionResponse(BaseModel):
    id: uuid.UUID
    playbook_id: uuid.UUID
    version: str
    status: str
    effective_from: datetime | None
    effective_to: datetime | None
    change_summary: str | None
    created_by: str | None
    approved_by: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlaybookChangeLogResponse(BaseModel):
    id: uuid.UUID
    playbook_version_id: uuid.UUID
    rule_key: str
    change_type: str
    field_path: str | None
    old_value: dict | list | None
    new_value: dict | list | None
    reason: str | None
    changed_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Rule-child schemas (task 1.2): rule_position, rule_parameter, red_line,
# rule_objection, rule_dependency, rule_test_case.
# ``playbook_plan.md`` sections 3.5 to 3.10.
# ---------------------------------------------------------------------------


class RulePositionResponse(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    kind: str
    rung: int | None
    label: str
    language: str
    summary: str | None
    zone: str
    approver_role_id: uuid.UUID | None
    conditions: dict | None
    give_get: str | None
    internal_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleParameterResponse(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    key: str
    label: str
    value_type: str
    unit: str | None
    direction: str
    preferred_value: dict | list | str | float | int | bool | None
    green_limit: dict | list | str | float | int | bool | None
    yellow_limit: dict | list | str | float | int | bool | None
    allowed_values: list | None
    extraction_hint: str | None
    context_overrides: dict | list | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RedLineResponse(BaseModel):
    id: uuid.UUID
    scope: str
    rule_id: uuid.UUID | None
    playbook_id: uuid.UUID | None
    key: str
    description: str
    condition_type: str
    condition: dict
    action: str
    approver_role_id: uuid.UUID | None
    rationale: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleObjectionResponse(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    objection: str
    their_rationale: str | None
    response: str
    talking_points: list | None
    recommended_position_id: uuid.UUID | None
    frequency: str | None
    counterparty_profile: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleDependencyResponse(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    related_rule_key: str
    relation: str
    note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleTestCaseResponse(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    name: str
    sample_text: str | None
    context: dict | None
    expected_outcome: str
    expected_zone: str | None
    expected_position_rung: int | None
    expected_red_line_key: str | None
    is_trap: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Rule-child create/update schemas (task 4.8): CRUD bodies for the six
# rule-child tables. These mirror the Response schemas above and the
# ``playbook_repo`` function signatures (task 1.4) field-for-field.
# ---------------------------------------------------------------------------


class RulePositionCreate(BaseModel):
    kind: str
    label: str
    language: str
    zone: str
    rung: int | None = None
    summary: str | None = None
    approver_role_id: uuid.UUID | None = None
    conditions: dict | None = None
    give_get: str | None = None
    internal_note: str | None = None


class RulePositionUpdate(BaseModel):
    kind: str | None = None
    label: str | None = None
    language: str | None = None
    zone: str | None = None
    rung: int | None = None
    summary: str | None = None
    approver_role_id: uuid.UUID | None = None
    conditions: dict | None = None
    give_get: str | None = None
    internal_note: str | None = None


class RuleParameterCreate(BaseModel):
    key: str
    label: str
    value_type: str
    direction: str
    unit: str | None = None
    preferred_value: dict | list | str | float | int | bool | None = None
    green_limit: dict | list | str | float | int | bool | None = None
    yellow_limit: dict | list | str | float | int | bool | None = None
    allowed_values: list | None = None
    extraction_hint: str | None = None
    context_overrides: dict | list | None = None


class RuleParameterUpdate(BaseModel):
    key: str | None = None
    label: str | None = None
    value_type: str | None = None
    direction: str | None = None
    unit: str | None = None
    preferred_value: dict | list | str | float | int | bool | None = None
    green_limit: dict | list | str | float | int | bool | None = None
    yellow_limit: dict | list | str | float | int | bool | None = None
    allowed_values: list | None = None
    extraction_hint: str | None = None
    context_overrides: dict | list | None = None


class RedLineCreate(BaseModel):
    scope: str
    key: str
    description: str
    condition_type: str
    condition: dict
    action: str
    rule_id: uuid.UUID | None = None
    playbook_id: uuid.UUID | None = None
    approver_role_id: uuid.UUID | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _check_scope(self) -> RedLineCreate:
        if self.scope == "rule" and self.rule_id is None:
            raise ValueError("scope 'rule' requires rule_id")
        if self.scope == "playbook" and self.playbook_id is None:
            raise ValueError("scope 'playbook' requires playbook_id")
        if self.scope == "global" and (self.rule_id is not None or self.playbook_id is not None):
            raise ValueError("scope 'global' must not set rule_id or playbook_id")
        return self


class RedLineUpdate(BaseModel):
    key: str | None = None
    description: str | None = None
    condition_type: str | None = None
    condition: dict | None = None
    action: str | None = None
    approver_role_id: uuid.UUID | None = None
    rationale: str | None = None


class RuleObjectionCreate(BaseModel):
    objection: str
    response: str
    their_rationale: str | None = None
    talking_points: list | None = None
    recommended_position_id: uuid.UUID | None = None
    frequency: str | None = None
    counterparty_profile: str | None = None


class RuleObjectionUpdate(BaseModel):
    objection: str | None = None
    response: str | None = None
    their_rationale: str | None = None
    talking_points: list | None = None
    recommended_position_id: uuid.UUID | None = None
    frequency: str | None = None
    counterparty_profile: str | None = None


class RuleDependencyCreate(BaseModel):
    related_rule_key: str
    relation: str
    note: str | None = None


class RuleDependencyUpdate(BaseModel):
    related_rule_key: str | None = None
    relation: str | None = None
    note: str | None = None


class RuleTestCaseCreate(BaseModel):
    name: str
    expected_outcome: str
    sample_text: str | None = None
    context: dict | None = None
    expected_zone: str | None = None
    expected_position_rung: int | None = None
    expected_red_line_key: str | None = None
    is_trap: bool = False


class RuleTestCaseUpdate(BaseModel):
    name: str | None = None
    expected_outcome: str | None = None
    sample_text: str | None = None
    context: dict | None = None
    expected_zone: str | None = None
    expected_position_rung: int | None = None
    expected_red_line_key: str | None = None
    is_trap: bool | None = None


# ---------------------------------------------------------------------------
# Version lifecycle request schemas (task 4.8): create a draft, publish a
# draft. ``playbook_plan.md`` section 6 ("Change control") requires a change
# summary and an approver at publish time; the pass-rate-threshold test run
# it also requires waits on task 4.10.
# ---------------------------------------------------------------------------


class VersionDraftCreate(BaseModel):
    """Body for ``POST /playbooks/{playbook_id}/versions``: create a draft by
    copying the playbook's current version (``playbook_repo.copy_version``)."""

    version: str
    created_by: str | None = None


class VersionPublishRequest(BaseModel):
    """Body for ``POST /playbooks/versions/{version_id}/publish``.

    ``skip_test_run`` (task 4.10 item 6) bypasses the pass-rate gate that
    runs the draft's test cases (deterministic mode) before publish — for
    callers that have already verified the draft some other way. Defaults to
    ``False``: the gate runs by default.
    """

    change_summary: str | None = None
    approved_by: str | None = None
    skip_test_run: bool = False


# ---------------------------------------------------------------------------
# Version diff (task 4.8 item 4; child-row diff added by task 5.5): differences
# between two versions' rule sets, matched by ``rule_key``. Rule-level scalar
# columns are diffed field by field (``field_changes``). Child rows get two
# views: ``child_counts`` (a count per child table, kept for existing callers)
# and ``child_changes`` (row-level added/removed/modified entries, matched
# across versions by a natural key, since ``copy_version`` gives every copied
# child row a fresh id).
# ---------------------------------------------------------------------------


class RuleFieldChange(BaseModel):
    field: str
    old_value: Any
    new_value: Any


class ChildCountDiff(BaseModel):
    count_a: int
    count_b: int


class ChildRowChange(BaseModel):
    """One child row that differs between two versions of the same rule.

    Child rows are matched across versions by a natural key, not by id:

    - ``positions``: ``"<kind>:<rung>"`` for a laddered position (for example
      ``"preferred:0"`` or ``"fallback:2"``), or ``"<kind>:<label>"`` when
      ``rung`` is null (acceptable variants).
    - ``parameters``: the parameter ``key``.
    - ``red_lines``: the red line ``key``.
    - ``objections``: the ``objection`` text.
    - ``dependencies``: ``"<relation>:<related_rule_key>"``.
    - ``test_cases``: the test case ``name``.

    When two rows of one rule share a natural key, the second and later ones
    get a ``#2``, ``#3`` suffix in list order.
    """

    child_type: str = Field(
        description=(
            "Which child table the row belongs to: positions, parameters, "
            "red_lines, objections, dependencies or test_cases."
        )
    )
    key: str = Field(description="Natural key the row was matched on (see the class docstring).")
    change_type: str = Field(description="One of 'added', 'removed' or 'modified'.")
    changed_fields: list[str] = Field(
        default_factory=list,
        description="For 'modified' only: the content fields whose values differ.",
    )
    old_value: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The row's content in version A (null for 'added'). Ids and "
            "timestamps are omitted. On objections, recommended_position_id "
            "is replaced by recommended_position_key."
        ),
    )
    new_value: dict[str, Any] | None = Field(
        default=None, description="The row's content in version B (null for 'removed')."
    )


class RuleDiffEntry(BaseModel):
    rule_key: str
    change_type: str = "modified"
    field_changes: list[RuleFieldChange] = Field(default_factory=list)
    child_counts: dict[str, ChildCountDiff] = Field(default_factory=dict)
    child_changes: list[ChildRowChange] = Field(
        default_factory=list,
        description=(
            "Row-level differences in the rule's child tables. This is where "
            "a change to preferred, fallback or variant language, or to a "
            "prohibited-phrase red line, appears."
        ),
    )


class VersionDiffResponse(BaseModel):
    version_a_id: uuid.UUID
    version_b_id: uuid.UUID
    rules_added: list[str]
    rules_removed: list[str]
    rules_modified: list[RuleDiffEntry]


# ---------------------------------------------------------------------------
# Rule CRUD schemas (``POST /playbooks/{playbook_id}/rules``,
# ``PATCH /playbooks/rules/{rule_id}``, and every endpoint that returns a
# rule). Task 5.5 rebuilt these on the child-table model.
#
# A rule's negotiating language is not a field on the rule. It lives in
# child rows:
#
#   what the rule says                 where it lives
#   ---------------------------------  -----------------------------------------
#   preferred language                 positions[] with kind="preferred", rung=0
#   fallback language (ladder)         positions[] with kind="fallback", rung>=1
#   acceptable variants                positions[] with kind="acceptable_variant",
#                                      rung=null
#   prohibited phrasing                red_lines[] with condition_type="phrase",
#                                      condition={"any": [...],
#                                      "negation_guard": true}, action="block"
#
# Create and update can carry ``positions`` and ``red_lines`` inline. The
# other four child tables (parameters, objections, dependencies, test cases)
# are edited only through their own endpoints in
# ``app/api/routes/playbook_versions.py``, but every rule response includes
# all six lists.
# ---------------------------------------------------------------------------


class RulePositionInput(BaseModel):
    """A position written inline with a rule create or update.

    On update the ``positions`` list is a full sync of the rule's positions.
    An entry with an ``id`` of one of this rule's existing positions updates
    that row in place. An entry without an ``id`` creates a new row. Existing
    positions not in the list are deleted.
    """

    model_config = {"extra": "forbid"}

    id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Id of an existing position of this rule, to update it in place. "
            "Omit to create a new one. Ignored on rule create."
        ),
    )
    kind: str = Field(description="'preferred', 'fallback' or 'acceptable_variant'.")
    rung: int | None = Field(
        default=None,
        description=(
            "Position on the concession ladder: 0 for the preferred position, "
            "1, 2, ... for fallbacks in the order they may be offered, null "
            "for acceptable variants."
        ),
    )
    label: str = Field(description="Short human-readable name for the position.")
    language: str = Field(description="The clause language for this position.")
    zone: str = Field(description="Risk zone this position sits in: 'green', 'yellow' or 'red'.")
    summary: str | None = Field(default=None, description="One-line plain-English summary.")
    approver_role_id: uuid.UUID | None = Field(
        default=None, description="Approver role needed before this position may be offered."
    )
    conditions: dict | None = Field(
        default=None,
        description=(
            "Context condition under which this position may be offered, as "
            "{dimension: [allowed values]}. Null means always."
        ),
    )
    give_get: str | None = Field(
        default=None, description="What we ask for in return when conceding to this position."
    )
    internal_note: str | None = Field(default=None, description="Internal-only note.")


class RuleRedLineInput(BaseModel):
    """A rule-scoped red line written inline with a rule create or update.

    ``scope`` is always ``"rule"`` and ``rule_id`` is the rule being written,
    so neither is accepted here. On update, ``red_lines`` is a full sync of
    the rule's red lines, with the same ``id`` rules as
    :class:`RulePositionInput`.
    """

    model_config = {"extra": "forbid"}

    id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Id of an existing red line of this rule, to update it in place. "
            "Omit to create a new one. Ignored on rule create."
        ),
    )
    key: str = Field(description="Stable key for the red line; kept across version copies.")
    description: str = Field(description="What is never acceptable, in plain English.")
    condition_type: str = Field(
        description=(
            "How the condition is evaluated. A prohibited phrase is 'phrase', "
            "with condition {'any': [phrases...], 'negation_guard': true}."
        )
    )
    condition: dict = Field(
        description="The condition payload; its shape depends on condition_type."
    )
    action: str = Field(description="What happens on a hit, e.g. 'block' or 'escalate'.")
    approver_role_id: uuid.UUID | None = Field(
        default=None, description="Approver role that may waive this red line, if any."
    )
    rationale: str | None = Field(default=None, description="Why this is a red line.")


class _RuleScalarFields(BaseModel):
    """Optional rule-level scalar fields shared by create and update."""

    issue_id: uuid.UUID | None = Field(default=None, description="Clause issue this rule governs.")
    rule_key: str | None = Field(
        default=None,
        description=(
            "Stable key for the rule, unique within a version. Rules are "
            "merged across playbooks and matched across versions by this key."
        ),
    )
    title: str | None = Field(default=None, description="Human-readable rule title.")
    position_summary: str | None = Field(
        default=None, description="Plain-English summary of our position on this issue."
    )
    risk_rationale: str | None = Field(default=None, description="Why this issue matters.")
    negotiable: bool | None = Field(default=None, description="Whether we will move off rung 0.")
    default_zone: str | None = Field(
        default=None, description="Zone for a clause that matches no position: green/yellow/red."
    )
    needs_human_judgment: bool | None = Field(
        default=None, description="Always route this rule's findings to a human."
    )
    judgment_note: str | None = Field(default=None, description="Guidance for that human.")
    applies_when: dict | None = Field(
        default=None,
        description="Context condition for the rule to apply at all. Null means always.",
    )
    detection_guidance: str | None = Field(
        default=None, description="Hints for finding this issue in a contract."
    )
    source_ref: str | None = Field(default=None, description="Where this rule came from.")
    authored_by: str | None = Field(default=None)
    approved_by: str | None = Field(default=None)
    last_reviewed_at: date | None = Field(default=None)


class RuleCreate(_RuleScalarFields):
    """Body for ``POST /playbooks/{playbook_id}/rules``.

    Creates the rule plus any inline ``positions`` and ``red_lines`` in one
    transaction. Unknown fields, including the five removed legacy fields
    (``preferred_language`` and the rest), are rejected with 422. If
    ``playbook_version_id`` names a version that is not a ``draft``, the
    request fails with 409 ``version_not_draft``.
    """

    model_config = {"extra": "forbid"}

    clause_type: str = Field(description="Clause family key (clause_family.key).")
    playbook_version_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Version to put the rule in. The resolution engine only sees "
            "rules attached to a playbook's current version."
        ),
    )
    required: bool = Field(default=False, description="The clause must be present in the contract.")
    risk_weight: float = Field(default=1.0, ge=0.0, description="Relative weight in risk scoring.")
    positions: list[RulePositionInput] = Field(
        default_factory=list,
        description="Positions to create with the rule (any id is ignored).",
    )
    red_lines: list[RuleRedLineInput] = Field(
        default_factory=list,
        description="Rule-scoped red lines to create with the rule (any id is ignored).",
    )


class RuleUpdate(_RuleScalarFields):
    """Body for ``PATCH /playbooks/rules/{rule_id}``.

    PATCH semantics apply per field. An omitted field is left unchanged. A
    field sent as ``null`` is cleared, for nullable columns. ``positions`` and
    ``red_lines``, when present (even as ``[]``), replace the rule's full set
    of that child type by id-sync (see :class:`RulePositionInput`). When they
    are omitted, those children are not touched.

    Deleting a position that an objection's ``recommended_position_id``
    points at clears that reference instead of failing.

    Sending ``positions`` or ``red_lines`` for a rule in a non-draft version
    fails with 409 ``version_not_draft``, the same gate as the per-child
    endpoints. On a draft, each synced list writes one ``playbook_change_log``
    entry (``positions_synced`` / ``red_lines_synced``). A PATCH of scalar
    fields only is not gated. Sending ``positions: null`` is the same as
    omitting it.
    """

    model_config = {"extra": "forbid"}

    clause_type: str | None = None
    required: bool | None = None
    risk_weight: float | None = Field(default=None, ge=0.0)
    positions: list[RulePositionInput] | None = Field(
        default=None, description="If present, the complete new set of positions."
    )
    red_lines: list[RuleRedLineInput] | None = Field(
        default=None, description="If present, the complete new set of rule-scoped red lines."
    )


class RuleResponse(BaseModel):
    """One rule with every child row attached.

    Returned by every rule CRUD endpoint and by ``GET /playbooks/{id}``. For
    the rule's preferred language, read the ``positions`` entry with
    ``kind == "preferred"`` (or, failing that, ``rung == 0``). For fallbacks,
    read the ``kind == "fallback"`` entries in ``rung`` order.
    """

    # Rule identity and content (playbook_plan.md section 3.4).
    id: uuid.UUID
    playbook_id: uuid.UUID
    playbook_version_id: uuid.UUID | None
    clause_type: str
    issue_id: uuid.UUID | None
    rule_key: str | None
    title: str | None
    position_summary: str | None
    risk_rationale: str | None
    required: bool
    negotiable: bool | None
    risk_weight: float
    default_zone: str | None
    needs_human_judgment: bool | None
    judgment_note: str | None
    applies_when: dict | None
    detection_guidance: str | None
    source_ref: str | None
    authored_by: str | None
    approved_by: str | None
    last_reviewed_at: date | None

    # Children (playbook_plan.md sections 3.5 to 3.10).
    positions: list[RulePositionResponse] = Field(
        default_factory=list,
        description="Preferred (rung 0), fallback (rung 1+) and acceptable-variant positions.",
    )
    parameters: list[RuleParameterResponse] = Field(default_factory=list)
    red_lines: list[RedLineResponse] = Field(
        default_factory=list, description="Rule-scoped red lines, including prohibited phrases."
    )
    objections: list[RuleObjectionResponse] = Field(default_factory=list)
    dependencies: list[RuleDependencyResponse] = Field(default_factory=list)
    test_cases: list[RuleTestCaseResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PlaybookWithRulesResponse(PlaybookResponse):
    rules: list[RuleResponse] = []


# ---------------------------------------------------------------------------
# ResolvedRule: the shape the resolution engine (task 4.2;
# ``playbook_plan.md`` section 5.1) returns per merged rule. "The response is
# a list. Each item carries source_playbook_id, source_playbook_name and
# source_version." It is exactly a RuleResponse plus that provenance.
# ---------------------------------------------------------------------------


class ResolvedRule(RuleResponse):
    """A :class:`RuleResponse` plus the playbook and version it was resolved from."""

    # Provenance, required by playbook_plan.md section 5.1.
    source_playbook_id: uuid.UUID
    source_playbook_name: str
    source_version: str


# ---------------------------------------------------------------------------
# Resolve response (task 4.2; playbook_plan.md section 5.1). Defined after
# ResolvedRule, which it embeds.
# ---------------------------------------------------------------------------


class ResolveResponse(BaseModel):
    """Result of resolving every applicable playbook for one deal's facts.

    ``rules`` is the merged list of :class:`ResolvedRule`, one per surviving
    ``rule_key``, sorted deterministically by ``rule_key``. ``pinned_version_ids``
    and ``applied_playbook_keys`` record which playbook versions were pulled
    from and which playbook ``key``s contributed, in the same order, so a
    review run can cite exactly what it ran against (section 3.3: "a review
    pins the playbook versions it ran against, so results are reproducible").
    """

    contract_type: str
    party_role: str
    paper_origin: str
    rules: list[ResolvedRule]
    pinned_version_ids: list[uuid.UUID]
    applied_playbook_keys: list[str]
