"""Playbook version lifecycle and rule-child CRUD (task 4.8).

Builds on the repositories and schemas task 1.4 landed
(``app/db/repositories/playbook_repo.py``, ``app/schemas/playbook.py``):
this module adds the business rules the repository layer intentionally
leaves out — draft-only writes (409 on a published version), minimum-quota
validation at publish time (``playbook_plan.md`` section 7.2, standing in
for task 4.10's test-case runner, which does not exist yet), and a
``playbook_change_log`` entry on every edit to a draft.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.models.playbook import (
    PlaybookRule,
    PlaybookVersion,
    RedLine,
    RuleDependency,
    RuleObjection,
    RuleParameter,
    RulePosition,
    RuleTestCase,
)
from app.db.repositories import playbook_repo
from app.schemas.playbook import (
    ChildCountDiff,
    ChildRowChange,
    RedLineResponse,
    RuleDependencyResponse,
    RuleDiffEntry,
    RuleFieldChange,
    RuleObjectionResponse,
    RuleParameterResponse,
    RulePositionResponse,
    RuleTestCaseResponse,
    VersionDiffResponse,
)
from app.services.playbook import testing as test_runner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESPONSE_SCHEMAS: dict[type, type] = {
    RulePosition: RulePositionResponse,
    RuleParameter: RuleParameterResponse,
    RedLine: RedLineResponse,
    RuleObjection: RuleObjectionResponse,
    RuleDependency: RuleDependencyResponse,
    RuleTestCase: RuleTestCaseResponse,
}


def _serialize(obj: object) -> dict[str, Any]:
    """JSON-safe snapshot of a rule-child row, for change-log old/new values.

    Matched by ``isinstance`` rather than exact ``type(obj) is ...``: a test
    double built as ``MagicMock(spec=RulePosition)`` reports
    ``isinstance(obj, RulePosition) is True`` (mock's spec machinery patches
    ``__class__``), but its real ``type()`` is still ``MagicMock``.
    """
    for model_cls, schema_cls in _RESPONSE_SCHEMAS.items():
        if isinstance(obj, model_cls):
            return schema_cls.model_validate(obj).model_dump(mode="json")
    raise TypeError(f"No response schema registered for {type(obj)!r}")


async def _get_playbook_or_404(session: AsyncSession, playbook_id: uuid.UUID) -> Any:
    pb = await playbook_repo.get_playbook(session, playbook_id)
    if pb is None:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")
    return pb


async def _get_version_or_404(session: AsyncSession, version_id: uuid.UUID) -> PlaybookVersion:
    version = await playbook_repo.get_version(session, version_id)
    if version is None:
        raise AppError(404, "not_found", f"Playbook version {version_id} not found")
    return version


async def _require_draft_version(session: AsyncSession, version_id: uuid.UUID) -> PlaybookVersion:
    version = await _get_version_or_404(session, version_id)
    if version.status != "draft":
        raise AppError(
            409,
            "version_not_draft",
            f"Playbook version {version_id} is {version.status!r}, not a draft",
        )
    return version


async def _resolve_rule_draft(session: AsyncSession, rule_id: uuid.UUID) -> PlaybookRule:
    """Fetch the rule a child row belongs to, and 409 unless its version is a
    draft. A rule with no ``playbook_version_id`` (a legacy pre-task-1.2 row)
    is always editable: it predates the version model entirely.
    """
    rule = await playbook_repo.get_rule(session, rule_id)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    if rule.playbook_version_id is not None:
        await _require_draft_version(session, rule.playbook_version_id)
    return rule


async def _log_change(
    session: AsyncSession,
    rule: PlaybookRule,
    change_type: str,
    *,
    field_path: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    reason: str | None = None,
    changed_by: str | None = None,
) -> None:
    """Append one ``playbook_change_log`` row for an edit under *rule*'s version.

    No-op for a legacy rule with no ``playbook_version_id`` — there is no
    version row to attach the log entry to.
    """
    if rule.playbook_version_id is None:
        return
    await playbook_repo.create_change_log_entry(
        session,
        playbook_version_id=rule.playbook_version_id,
        rule_key=rule.rule_key or str(rule.id),
        change_type=change_type,
        field_path=field_path,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        changed_by=changed_by,
    )


# ---------------------------------------------------------------------------
# Version lifecycle: list, create draft, publish
# ---------------------------------------------------------------------------


async def list_versions(session: AsyncSession, playbook_id: uuid.UUID) -> list[PlaybookVersion]:
    await _get_playbook_or_404(session, playbook_id)
    return await playbook_repo.list_versions(session, playbook_id)


async def get_version(session: AsyncSession, version_id: uuid.UUID) -> PlaybookVersion:
    return await _get_version_or_404(session, version_id)


async def create_draft(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    version: str,
    created_by: str | None,
) -> PlaybookVersion:
    pb = await _get_playbook_or_404(session, playbook_id)
    if pb.current_version_id is None:
        raise AppError(
            400,
            "no_current_version",
            f"Playbook {playbook_id} has no current (published) version to copy from",
        )
    new_version = await playbook_repo.copy_version(
        session, pb.current_version_id, version, created_by=created_by
    )
    if new_version is None:
        raise AppError(404, "not_found", "Current version not found")
    await session.commit()
    await session.refresh(new_version)
    return new_version


# ---------------------------------------------------------------------------
# Rule test-case runner (task 4.10): load a version's rules paired with their
# owning playbook's key, for ``app/services/playbook/testing.py``.
# ---------------------------------------------------------------------------


def _rules_with_playbook_key(
    version: PlaybookVersion, rules: list[PlaybookRule]
) -> list[tuple[str, PlaybookRule]]:
    """Pair each of *version*'s rules with its playbook's id as a grouping
    key for ``testing.py``. Every rule in one version shares the same
    playbook, so this needs no extra lookup beyond ``version.playbook_id``
    (``testing.py`` only uses the key for display/grouping, not identity) —
    a caller that wants the human-readable ``playbook.key`` instead (the CLI
    already has it for free from loading playbooks by key) can just replace
    this pairing before calling ``run_rule_tests``."""
    key = str(version.playbook_id)
    return [(key, rule) for rule in rules]


async def run_tests_for_version(
    session: AsyncSession, version_id: uuid.UUID, *, deterministic: bool = True
) -> test_runner.TestRunSummary:
    """Run every test case on every rule in *version_id* and return the
    pass-rate summary (task 4.10 item 5, ``POST /playbooks/versions/{id}/test``).

    ``deterministic`` defaults to ``True`` so this never makes a model call
    unless a caller explicitly opts into the cost-bearing default mode — an
    API route has no interactive "--yes" to gate that spend the way the CLI
    does, so staying free-by-default is the safer choice here.
    """
    version = await _get_version_or_404(session, version_id)
    rules = await playbook_repo.get_rules_with_children(session, version_id)
    rows = _rules_with_playbook_key(version, rules)
    return test_runner.run_rule_tests(rows, deterministic=deterministic)


# ---------------------------------------------------------------------------
# Publish: minimum-quota validation (playbook_plan.md section 7.2) plus,
# since task 4.10 now exists, a pass-rate gate run through its test runner
# (task 4.10 item 6). The gate always runs in deterministic mode: publish is
# a synchronous call with no interactive "--yes" to authorize a possibly
# large, cost-bearing batch of model calls, so it checks only the cases
# decidable for free (phrase/regex red lines and ``missing`` cases) against
# *pass_threshold*. A version with no such decidable cases yet (common while
# most of a rule's cases are the model-only kinds) passes vacuously rather
# than blocking publish on a check that cannot run — see
# ``testing.TestRunSummary.pass_rate``, which is 1.0 whenever ``run_cases``
# is 0. ``skip_test_run`` exists for callers that intentionally bypass this
# (task 4.8's own pre-4.10 publish tests; a human override at point of
# publish is NOT what this is for and should not be wired to it later
# without a real approval trail).
# ---------------------------------------------------------------------------


def _minimum_violations_for_rule(rule: PlaybookRule) -> list[str]:
    violations: list[str] = []
    positions = list(getattr(rule, "positions", []) or [])

    if not any(p.kind == "preferred" for p in positions):
        violations.append("missing a 'preferred' position")
    if not any(p.kind == "acceptable_variant" for p in positions):
        violations.append("missing at least one 'acceptable_variant' position")

    fallback_count = sum(1 for p in positions if p.kind == "fallback")
    if rule.negotiable and fallback_count < 2:
        violations.append("negotiable rule needs at least 2 'fallback' positions")

    rationale = (rule.risk_rationale or "").strip()
    sentence_count = len([s for s in rationale.split(".") if s.strip()])
    if sentence_count < 2:
        violations.append("risk_rationale is required and must be at least two sentences")

    risk_weight = float(rule.risk_weight or 0)
    red_lines = list(getattr(rule, "red_lines", []) or [])
    if risk_weight >= 7 and not red_lines:
        violations.append("rules with risk_weight >= 7 need at least one red line")

    objections = list(getattr(rule, "objections", []) or [])
    if rule.negotiable and len(objections) < 2:
        violations.append("negotiable rule needs at least 2 objections")

    test_cases = list(getattr(rule, "test_cases", []) or [])
    if len(test_cases) < 5:
        violations.append("rule needs at least 5 test cases")

    return violations


async def publish_draft(
    session: AsyncSession,
    version_id: uuid.UUID,
    change_summary: str | None,
    approved_by: str | None,
    *,
    skip_test_run: bool = False,
    pass_threshold: float = test_runner.DEFAULT_PASS_THRESHOLD,
) -> PlaybookVersion:
    version = await _require_draft_version(session, version_id)

    summary = change_summary or version.change_summary
    if not summary:
        raise AppError(400, "change_summary_required", "A change summary is required to publish")
    if not approved_by:
        raise AppError(400, "approver_required", "An approver is required to publish")

    rules = await playbook_repo.get_rules_with_children(session, version_id)
    if not rules:
        raise AppError(400, "empty_version", "A version needs at least one rule to publish")

    failures: dict[str, list[str]] = {}
    for rule in rules:
        violations = _minimum_violations_for_rule(rule)
        if violations:
            failures[rule.rule_key or str(rule.id)] = violations
    if failures:
        raise AppError(
            400,
            "minimums_not_met",
            "Draft does not meet the minimum per-rule requirements",
            detail=failures,
        )

    if not skip_test_run:
        rows = _rules_with_playbook_key(version, rules)
        test_summary = test_runner.run_rule_tests(rows, deterministic=True)
        if test_summary.pass_rate < pass_threshold:
            raise AppError(
                400,
                "test_pass_rate_below_threshold",
                (
                    f"Draft's test-case pass rate {test_summary.pass_rate:.1%} is below "
                    f"the {pass_threshold:.0%} threshold required to publish"
                ),
                detail={
                    "pass_rate": test_summary.pass_rate,
                    "threshold": pass_threshold,
                    "failures": [
                        {"rule_key": f.rule_key, "test_case": f.test_case_name}
                        for f in test_summary.failures
                    ],
                },
            )

    if change_summary is not None:
        version.change_summary = change_summary

    published = await playbook_repo.publish_version(session, version_id, approved_by=approved_by)
    if published is None:
        raise AppError(404, "not_found", f"Playbook version {version_id} not found")
    await session.commit()
    await session.refresh(published)
    return published


# ---------------------------------------------------------------------------
# Diff two versions' rule sets, matched by rule_key (task 4.8 item 4).
# ---------------------------------------------------------------------------

_RULE_SCALAR_FIELDS = (
    "clause_type",
    "issue_id",
    "title",
    "required",
    "risk_weight",
    "position_summary",
    "risk_rationale",
    "negotiable",
    "default_zone",
    "needs_human_judgment",
    "judgment_note",
    "applies_when",
    "detection_guidance",
    "source_ref",
    "authored_by",
    "approved_by",
    "last_reviewed_at",
)

_CHILD_ATTRS = ("positions", "parameters", "red_lines", "objections", "dependencies", "test_cases")


def _rule_key_for(rule: PlaybookRule) -> str:
    return rule.rule_key or str(rule.id)


# Columns never compared when diffing child rows: row identity and
# timestamps differ on every copied row by construction.
_CHILD_IGNORED_FIELDS = frozenset({"id", "rule_id", "created_at", "updated_at"})


def _position_key(position: Any) -> str:
    if position.rung is not None:
        return f"{position.kind}:{position.rung}"
    return f"{position.kind}:{position.label}"


# Natural key per child table, used to match rows across versions (see
# ``ChildRowChange``'s docstring for the published contract).
_CHILD_NATURAL_KEYS: dict[str, Any] = {
    "positions": _position_key,
    "parameters": lambda p: p.key,
    "red_lines": lambda r: r.key,
    "objections": lambda o: o.objection,
    "dependencies": lambda d: f"{d.relation}:{d.related_rule_key}",
    "test_cases": lambda t: t.name,
}


def _child_content(row: Any, position_keys: dict[Any, str]) -> dict[str, Any]:
    """JSON-safe content of a child row, minus identity/timestamps.

    An objection's ``recommended_position_id`` is replaced by the natural
    key of the position it points at (``recommended_position_key``), since
    the id itself changes on every version copy.
    """
    data = {k: v for k, v in _serialize(row).items() if k not in _CHILD_IGNORED_FIELDS}
    if "recommended_position_id" in data:
        pos_id = getattr(row, "recommended_position_id", None)
        data.pop("recommended_position_id")
        data["recommended_position_key"] = position_keys.get(pos_id) if pos_id else None
    return data


def _keyed_children(rule: PlaybookRule, attr: str) -> dict[str, dict[str, Any]]:
    """``{natural_key: content}`` for one child list of *rule*. Duplicate
    keys get ``#2``, ``#3`` suffixes in list order."""
    positions = list(getattr(rule, "positions", []) or [])
    position_keys = {p.id: _position_key(p) for p in positions}
    key_fn = _CHILD_NATURAL_KEYS[attr]
    out: dict[str, dict[str, Any]] = {}
    for row in list(getattr(rule, attr, []) or []):
        base = str(key_fn(row))
        key, n = base, 1
        while key in out:
            n += 1
            key = f"{base}#{n}"
        out[key] = _child_content(row, position_keys)
    return out


def _diff_children(rule_a: PlaybookRule, rule_b: PlaybookRule) -> list[ChildRowChange]:
    """Row-level added/removed/modified changes across all six child tables."""
    changes: list[ChildRowChange] = []
    for attr in _CHILD_ATTRS:
        rows_a = _keyed_children(rule_a, attr)
        rows_b = _keyed_children(rule_b, attr)
        for key in sorted(set(rows_a) | set(rows_b)):
            old, new = rows_a.get(key), rows_b.get(key)
            if old is None:
                changes.append(
                    ChildRowChange(child_type=attr, key=key, change_type="added", new_value=new)
                )
            elif new is None:
                changes.append(
                    ChildRowChange(child_type=attr, key=key, change_type="removed", old_value=old)
                )
            elif old != new:
                changed = sorted(f for f in set(old) | set(new) if old.get(f) != new.get(f))
                changes.append(
                    ChildRowChange(
                        child_type=attr,
                        key=key,
                        change_type="modified",
                        changed_fields=changed,
                        old_value=old,
                        new_value=new,
                    )
                )
    return changes


async def diff_versions(
    session: AsyncSession, version_a_id: uuid.UUID, version_b_id: uuid.UUID
) -> VersionDiffResponse:
    await _get_version_or_404(session, version_a_id)
    await _get_version_or_404(session, version_b_id)

    rules_a = await playbook_repo.get_rules_with_children(session, version_a_id)
    rules_b = await playbook_repo.get_rules_with_children(session, version_b_id)

    by_key_a = {_rule_key_for(r): r for r in rules_a}
    by_key_b = {_rule_key_for(r): r for r in rules_b}

    rules_added = sorted(k for k in by_key_b if k not in by_key_a)
    rules_removed = sorted(k for k in by_key_a if k not in by_key_b)

    modified: list[RuleDiffEntry] = []
    for key in sorted(set(by_key_a) & set(by_key_b)):
        rule_a, rule_b = by_key_a[key], by_key_b[key]
        field_changes = [
            RuleFieldChange(field=f, old_value=getattr(rule_a, f), new_value=getattr(rule_b, f))
            for f in _RULE_SCALAR_FIELDS
            if getattr(rule_a, f) != getattr(rule_b, f)
        ]
        child_counts: dict[str, ChildCountDiff] = {}
        for attr in _CHILD_ATTRS:
            count_a = len(getattr(rule_a, attr, []) or [])
            count_b = len(getattr(rule_b, attr, []) or [])
            if count_a != count_b:
                child_counts[attr] = ChildCountDiff(count_a=count_a, count_b=count_b)
        child_changes = _diff_children(rule_a, rule_b)
        if field_changes or child_counts or child_changes:
            modified.append(
                RuleDiffEntry(
                    rule_key=key,
                    change_type="modified",
                    field_changes=field_changes,
                    child_counts=child_counts,
                    child_changes=child_changes,
                )
            )

    return VersionDiffResponse(
        version_a_id=version_a_id,
        version_b_id=version_b_id,
        rules_added=rules_added,
        rules_removed=rules_removed,
        rules_modified=modified,
    )


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_position (draft-only; logs on every write)
# ---------------------------------------------------------------------------


async def list_positions(session: AsyncSession, rule_id: uuid.UUID) -> list[RulePosition]:
    rule = await playbook_repo.get_rule(session, rule_id)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    return await playbook_repo.list_rule_positions(session, rule_id)


async def create_position(session: AsyncSession, rule_id: uuid.UUID, body: Any) -> RulePosition:
    rule = await _resolve_rule_draft(session, rule_id)
    position = await playbook_repo.create_rule_position(
        session,
        rule_id=rule_id,
        kind=body.kind,
        label=body.label,
        language=body.language,
        zone=body.zone,
        rung=body.rung,
        summary=body.summary,
        approver_role_id=body.approver_role_id,
        conditions=body.conditions,
        give_get=body.give_get,
        internal_note=body.internal_note,
    )
    await _log_change(
        session,
        rule,
        "position_created",
        field_path=f"positions/{position.id}",
        new_value=_serialize(position),
    )
    await session.commit()
    await session.refresh(position)
    return position


async def update_position(session: AsyncSession, position_id: uuid.UUID, body: Any) -> RulePosition:
    position = await playbook_repo.get_rule_position(session, position_id)
    if position is None:
        raise AppError(404, "not_found", f"Position {position_id} not found")
    rule = await _resolve_rule_draft(session, position.rule_id)
    old_value = _serialize(position)
    kwargs = body.model_dump(exclude_unset=True)
    updated = await playbook_repo.update_rule_position(session, position_id, **kwargs)
    if updated is None:
        raise AppError(404, "not_found", f"Position {position_id} not found")
    await _log_change(
        session,
        rule,
        "position_updated",
        field_path=f"positions/{position_id}",
        old_value=old_value,
        new_value=_serialize(updated),
    )
    await session.commit()
    await session.refresh(updated)
    return updated


async def delete_position(session: AsyncSession, position_id: uuid.UUID) -> None:
    position = await playbook_repo.get_rule_position(session, position_id)
    if position is None:
        raise AppError(404, "not_found", f"Position {position_id} not found")
    rule = await _resolve_rule_draft(session, position.rule_id)
    old_value = _serialize(position)
    deleted = await playbook_repo.delete_rule_position(session, position_id)
    if not deleted:
        raise AppError(404, "not_found", f"Position {position_id} not found")
    await _log_change(
        session,
        rule,
        "position_deleted",
        field_path=f"positions/{position_id}",
        old_value=old_value,
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_parameter
# ---------------------------------------------------------------------------


async def list_parameters(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleParameter]:
    rule = await playbook_repo.get_rule(session, rule_id)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    return await playbook_repo.list_rule_parameters(session, rule_id)


async def create_parameter(session: AsyncSession, rule_id: uuid.UUID, body: Any) -> RuleParameter:
    rule = await _resolve_rule_draft(session, rule_id)
    parameter = await playbook_repo.create_rule_parameter(
        session,
        rule_id=rule_id,
        key=body.key,
        label=body.label,
        value_type=body.value_type,
        direction=body.direction,
        unit=body.unit,
        preferred_value=body.preferred_value,
        green_limit=body.green_limit,
        yellow_limit=body.yellow_limit,
        allowed_values=body.allowed_values,
        extraction_hint=body.extraction_hint,
        context_overrides=body.context_overrides,
    )
    await _log_change(
        session,
        rule,
        "parameter_created",
        field_path=f"parameters/{parameter.id}",
        new_value=_serialize(parameter),
    )
    await session.commit()
    await session.refresh(parameter)
    return parameter


async def update_parameter(
    session: AsyncSession, parameter_id: uuid.UUID, body: Any
) -> RuleParameter:
    parameter = await playbook_repo.get_rule_parameter(session, parameter_id)
    if parameter is None:
        raise AppError(404, "not_found", f"Parameter {parameter_id} not found")
    rule = await _resolve_rule_draft(session, parameter.rule_id)
    old_value = _serialize(parameter)
    kwargs = body.model_dump(exclude_unset=True)
    updated = await playbook_repo.update_rule_parameter(session, parameter_id, **kwargs)
    if updated is None:
        raise AppError(404, "not_found", f"Parameter {parameter_id} not found")
    await _log_change(
        session,
        rule,
        "parameter_updated",
        field_path=f"parameters/{parameter_id}",
        old_value=old_value,
        new_value=_serialize(updated),
    )
    await session.commit()
    await session.refresh(updated)
    return updated


async def delete_parameter(session: AsyncSession, parameter_id: uuid.UUID) -> None:
    parameter = await playbook_repo.get_rule_parameter(session, parameter_id)
    if parameter is None:
        raise AppError(404, "not_found", f"Parameter {parameter_id} not found")
    rule = await _resolve_rule_draft(session, parameter.rule_id)
    old_value = _serialize(parameter)
    deleted = await playbook_repo.delete_rule_parameter(session, parameter_id)
    if not deleted:
        raise AppError(404, "not_found", f"Parameter {parameter_id} not found")
    await _log_change(
        session,
        rule,
        "parameter_deleted",
        field_path=f"parameters/{parameter_id}",
        old_value=old_value,
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Rule-children CRUD: red_line (scope 'rule' is draft-gated and logged;
# scope 'playbook'/'global' are not version-bound, so neither applies)
# ---------------------------------------------------------------------------


async def list_red_lines_for_rule(session: AsyncSession, rule_id: uuid.UUID) -> list[RedLine]:
    rule = await playbook_repo.get_rule(session, rule_id)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    return await playbook_repo.list_red_lines_for_rule(session, rule_id)


async def list_red_lines_for_playbook(
    session: AsyncSession, playbook_id: uuid.UUID
) -> list[RedLine]:
    await _get_playbook_or_404(session, playbook_id)
    return await playbook_repo.list_red_lines_for_playbook(session, playbook_id)


async def list_global_red_lines(session: AsyncSession) -> list[RedLine]:
    return await playbook_repo.list_global_red_lines(session)


async def _rule_for_red_line(session: AsyncSession, red_line: RedLine) -> PlaybookRule | None:
    if red_line.scope != "rule" or red_line.rule_id is None:
        return None
    return await _resolve_rule_draft(session, red_line.rule_id)


async def create_red_line(session: AsyncSession, body: Any) -> RedLine:
    rule = None
    if body.scope == "rule":
        rule = await _resolve_rule_draft(session, body.rule_id)
    red_line = await playbook_repo.create_red_line(
        session,
        scope=body.scope,
        key=body.key,
        description=body.description,
        condition_type=body.condition_type,
        condition=body.condition,
        action=body.action,
        rule_id=body.rule_id,
        playbook_id=body.playbook_id,
        approver_role_id=body.approver_role_id,
        rationale=body.rationale,
    )
    if rule is not None:
        await _log_change(
            session,
            rule,
            "red_line_created",
            field_path=f"red_lines/{red_line.id}",
            new_value=_serialize(red_line),
        )
    await session.commit()
    await session.refresh(red_line)
    return red_line


async def update_red_line(session: AsyncSession, red_line_id: uuid.UUID, body: Any) -> RedLine:
    red_line = await playbook_repo.get_red_line(session, red_line_id)
    if red_line is None:
        raise AppError(404, "not_found", f"Red line {red_line_id} not found")
    rule = await _rule_for_red_line(session, red_line)
    old_value = _serialize(red_line)
    kwargs = body.model_dump(exclude_unset=True)
    updated = await playbook_repo.update_red_line(session, red_line_id, **kwargs)
    if updated is None:
        raise AppError(404, "not_found", f"Red line {red_line_id} not found")
    if rule is not None:
        await _log_change(
            session,
            rule,
            "red_line_updated",
            field_path=f"red_lines/{red_line_id}",
            old_value=old_value,
            new_value=_serialize(updated),
        )
    await session.commit()
    await session.refresh(updated)
    return updated


async def delete_red_line(session: AsyncSession, red_line_id: uuid.UUID) -> None:
    red_line = await playbook_repo.get_red_line(session, red_line_id)
    if red_line is None:
        raise AppError(404, "not_found", f"Red line {red_line_id} not found")
    rule = await _rule_for_red_line(session, red_line)
    old_value = _serialize(red_line)
    deleted = await playbook_repo.delete_red_line(session, red_line_id)
    if not deleted:
        raise AppError(404, "not_found", f"Red line {red_line_id} not found")
    if rule is not None:
        await _log_change(
            session,
            rule,
            "red_line_deleted",
            field_path=f"red_lines/{red_line_id}",
            old_value=old_value,
        )
    await session.commit()


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_objection
# ---------------------------------------------------------------------------


async def list_objections(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleObjection]:
    rule = await playbook_repo.get_rule(session, rule_id)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    return await playbook_repo.list_rule_objections(session, rule_id)


async def create_objection(session: AsyncSession, rule_id: uuid.UUID, body: Any) -> RuleObjection:
    rule = await _resolve_rule_draft(session, rule_id)
    objection = await playbook_repo.create_rule_objection(
        session,
        rule_id=rule_id,
        objection=body.objection,
        response=body.response,
        their_rationale=body.their_rationale,
        talking_points=body.talking_points,
        recommended_position_id=body.recommended_position_id,
        frequency=body.frequency,
        counterparty_profile=body.counterparty_profile,
    )
    await _log_change(
        session,
        rule,
        "objection_created",
        field_path=f"objections/{objection.id}",
        new_value=_serialize(objection),
    )
    await session.commit()
    await session.refresh(objection)
    return objection


async def update_objection(
    session: AsyncSession, objection_id: uuid.UUID, body: Any
) -> RuleObjection:
    objection = await playbook_repo.get_rule_objection(session, objection_id)
    if objection is None:
        raise AppError(404, "not_found", f"Objection {objection_id} not found")
    rule = await _resolve_rule_draft(session, objection.rule_id)
    old_value = _serialize(objection)
    kwargs = body.model_dump(exclude_unset=True)
    updated = await playbook_repo.update_rule_objection(session, objection_id, **kwargs)
    if updated is None:
        raise AppError(404, "not_found", f"Objection {objection_id} not found")
    await _log_change(
        session,
        rule,
        "objection_updated",
        field_path=f"objections/{objection_id}",
        old_value=old_value,
        new_value=_serialize(updated),
    )
    await session.commit()
    await session.refresh(updated)
    return updated


async def delete_objection(session: AsyncSession, objection_id: uuid.UUID) -> None:
    objection = await playbook_repo.get_rule_objection(session, objection_id)
    if objection is None:
        raise AppError(404, "not_found", f"Objection {objection_id} not found")
    rule = await _resolve_rule_draft(session, objection.rule_id)
    old_value = _serialize(objection)
    deleted = await playbook_repo.delete_rule_objection(session, objection_id)
    if not deleted:
        raise AppError(404, "not_found", f"Objection {objection_id} not found")
    await _log_change(
        session,
        rule,
        "objection_deleted",
        field_path=f"objections/{objection_id}",
        old_value=old_value,
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_dependency
# ---------------------------------------------------------------------------


async def list_dependencies(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleDependency]:
    rule = await playbook_repo.get_rule(session, rule_id)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    return await playbook_repo.list_rule_dependencies(session, rule_id)


async def create_dependency(session: AsyncSession, rule_id: uuid.UUID, body: Any) -> RuleDependency:
    rule = await _resolve_rule_draft(session, rule_id)
    dependency = await playbook_repo.create_rule_dependency(
        session,
        rule_id=rule_id,
        related_rule_key=body.related_rule_key,
        relation=body.relation,
        note=body.note,
    )
    await _log_change(
        session,
        rule,
        "dependency_created",
        field_path=f"dependencies/{dependency.id}",
        new_value=_serialize(dependency),
    )
    await session.commit()
    await session.refresh(dependency)
    return dependency


async def update_dependency(
    session: AsyncSession, dependency_id: uuid.UUID, body: Any
) -> RuleDependency:
    dependency = await playbook_repo.get_rule_dependency(session, dependency_id)
    if dependency is None:
        raise AppError(404, "not_found", f"Dependency {dependency_id} not found")
    rule = await _resolve_rule_draft(session, dependency.rule_id)
    old_value = _serialize(dependency)
    kwargs = body.model_dump(exclude_unset=True)
    updated = await playbook_repo.update_rule_dependency(session, dependency_id, **kwargs)
    if updated is None:
        raise AppError(404, "not_found", f"Dependency {dependency_id} not found")
    await _log_change(
        session,
        rule,
        "dependency_updated",
        field_path=f"dependencies/{dependency_id}",
        old_value=old_value,
        new_value=_serialize(updated),
    )
    await session.commit()
    await session.refresh(updated)
    return updated


async def delete_dependency(session: AsyncSession, dependency_id: uuid.UUID) -> None:
    dependency = await playbook_repo.get_rule_dependency(session, dependency_id)
    if dependency is None:
        raise AppError(404, "not_found", f"Dependency {dependency_id} not found")
    rule = await _resolve_rule_draft(session, dependency.rule_id)
    old_value = _serialize(dependency)
    deleted = await playbook_repo.delete_rule_dependency(session, dependency_id)
    if not deleted:
        raise AppError(404, "not_found", f"Dependency {dependency_id} not found")
    await _log_change(
        session,
        rule,
        "dependency_deleted",
        field_path=f"dependencies/{dependency_id}",
        old_value=old_value,
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_test_case
# ---------------------------------------------------------------------------


async def list_test_cases(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleTestCase]:
    rule = await playbook_repo.get_rule(session, rule_id)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    return await playbook_repo.list_rule_test_cases(session, rule_id)


async def create_test_case(session: AsyncSession, rule_id: uuid.UUID, body: Any) -> RuleTestCase:
    rule = await _resolve_rule_draft(session, rule_id)
    test_case = await playbook_repo.create_rule_test_case(
        session,
        rule_id=rule_id,
        name=body.name,
        expected_outcome=body.expected_outcome,
        sample_text=body.sample_text,
        context=body.context,
        expected_zone=body.expected_zone,
        expected_position_rung=body.expected_position_rung,
        expected_red_line_key=body.expected_red_line_key,
        is_trap=body.is_trap,
    )
    await _log_change(
        session,
        rule,
        "test_case_created",
        field_path=f"test_cases/{test_case.id}",
        new_value=_serialize(test_case),
    )
    await session.commit()
    await session.refresh(test_case)
    return test_case


async def update_test_case(
    session: AsyncSession, test_case_id: uuid.UUID, body: Any
) -> RuleTestCase:
    test_case = await playbook_repo.get_rule_test_case(session, test_case_id)
    if test_case is None:
        raise AppError(404, "not_found", f"Test case {test_case_id} not found")
    rule = await _resolve_rule_draft(session, test_case.rule_id)
    old_value = _serialize(test_case)
    kwargs = body.model_dump(exclude_unset=True)
    updated = await playbook_repo.update_rule_test_case(session, test_case_id, **kwargs)
    if updated is None:
        raise AppError(404, "not_found", f"Test case {test_case_id} not found")
    await _log_change(
        session,
        rule,
        "test_case_updated",
        field_path=f"test_cases/{test_case_id}",
        old_value=old_value,
        new_value=_serialize(updated),
    )
    await session.commit()
    await session.refresh(updated)
    return updated


async def delete_test_case(session: AsyncSession, test_case_id: uuid.UUID) -> None:
    test_case = await playbook_repo.get_rule_test_case(session, test_case_id)
    if test_case is None:
        raise AppError(404, "not_found", f"Test case {test_case_id} not found")
    rule = await _resolve_rule_draft(session, test_case.rule_id)
    old_value = _serialize(test_case)
    deleted = await playbook_repo.delete_rule_test_case(session, test_case_id)
    if not deleted:
        raise AppError(404, "not_found", f"Test case {test_case_id} not found")
    await _log_change(
        session,
        rule,
        "test_case_deleted",
        field_path=f"test_cases/{test_case_id}",
        old_value=old_value,
    )
    await session.commit()
