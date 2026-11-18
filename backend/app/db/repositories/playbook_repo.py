from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.authority import ApproverRole, EscalationPolicy
from app.db.models.playbook import (
    Playbook,
    PlaybookChangeLog,
    PlaybookRule,
    PlaybookVersion,
    RedLine,
    RuleDependency,
    RuleObjection,
    RuleParameter,
    RulePosition,
    RuleTestCase,
)
from app.db.models.taxonomy import ClauseFamily, ClauseIssue

# A SQLAlchemy model class for one of the six rule-child tables.
_ChildModel = (
    type[RulePosition]
    | type[RuleParameter]
    | type[RedLine]
    | type[RuleObjection]
    | type[RuleDependency]
    | type[RuleTestCase]
)

# The six rule-child tables, all cascading from ``playbook_rule`` (task 1.2).
# Used by ``get_rules_with_children`` to fetch every child type for a batch of
# rule ids in a fixed number of queries, and to size the lists it attaches.
_CHILD_MODELS: tuple[_ChildModel, ...] = (
    RulePosition,
    RuleParameter,
    RedLine,
    RuleObjection,
    RuleDependency,
    RuleTestCase,
)
# Attribute name each child model's rows are grouped under on the returned
# PlaybookRule objects (plain attribute, not a mapper relationship).
_CHILD_ATTR: dict[_ChildModel, str] = {
    RulePosition: "positions",
    RuleParameter: "parameters",
    RedLine: "red_lines",
    RuleObjection: "objections",
    RuleDependency: "dependencies",
    RuleTestCase: "test_cases",
}

# ---------------------------------------------------------------------------
# Playbook CRUD
# ---------------------------------------------------------------------------


async def create_playbook(
    session: AsyncSession,
    name: str,
    practice_area: str,
    precedence: int = 0,
    **kwargs: object,
) -> Playbook:
    """Create and persist a new Playbook.

    ``kwargs`` may include any of the new header columns from task 1.2:
    ``key``, ``layer``, ``party_role``, ``paper_scope``, ``jurisdiction``,
    ``business_unit``, ``owner_role_id``, ``parent_playbook_id``,
    ``applies_when``, ``description``, ``status``, ``review_cadence_days``,
    ``next_review_at``.
    """
    pb = Playbook(name=name, practice_area=practice_area, precedence=precedence, **kwargs)
    session.add(pb)
    await session.flush()
    return pb


async def get_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> Playbook | None:
    """Fetch a Playbook by id, or None if not found."""
    result = await session.execute(select(Playbook).where(Playbook.id == playbook_id))
    return result.scalar_one_or_none()


async def get_playbook_by_key(session: AsyncSession, key: str) -> Playbook | None:
    """Fetch a Playbook by its stable ``key``, or None if not found."""
    result = await session.execute(select(Playbook).where(Playbook.key == key))
    return result.scalar_one_or_none()


async def list_playbooks(session: AsyncSession) -> list[Playbook]:
    """Return all playbooks ordered by precedence descending."""
    result = await session.execute(select(Playbook).order_by(Playbook.precedence.desc()))
    return list(result.scalars().all())


async def list_playbooks_by_areas(
    session: AsyncSession,
    practice_areas: list[str],
) -> list[Playbook]:
    """Return playbooks whose practice_area is in *practice_areas*.

    Ordered by precedence DESC, then practice_area ASC for deterministic
    tie-breaking when two playbooks share the same precedence value.
    """
    if not practice_areas:
        return []
    result = await session.execute(
        select(Playbook)
        .where(Playbook.practice_area.in_(practice_areas))
        .order_by(Playbook.precedence.desc(), Playbook.practice_area.asc())
    )
    return list(result.scalars().all())


async def update_playbook(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    **kwargs: object,
) -> Playbook | None:
    """Update fields on a Playbook. Returns the updated Playbook, or None if not found."""
    pb = await get_playbook(session, playbook_id)
    if pb is None:
        return None
    for key, value in kwargs.items():
        setattr(pb, key, value)
    await session.flush()
    return pb


async def delete_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> bool:
    """Delete a Playbook by id. Returns True if a row was deleted."""
    cursor = cast(CursorResult, await session.execute(
        delete(Playbook).where(Playbook.id == playbook_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# PlaybookRule CRUD
# ---------------------------------------------------------------------------


async def create_rule(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    clause_type: str,
    **kwargs: object,
) -> PlaybookRule:
    """Create and persist a new PlaybookRule (the rule row only).

    kwargs: required, risk_weight, playbook_version_id, issue_id, rule_key,
            title, position_summary, risk_rationale, negotiable,
            default_zone, needs_human_judgment, judgment_note, applies_when,
            detection_guidance, source_ref, authored_by, approved_by,
            last_reviewed_at.

    Negotiating language is not a rule column: create ``rule_position`` /
    ``red_line`` children with ``create_rule_position`` /
    ``create_red_line`` (or ``sync_rule_positions`` /
    ``sync_rule_red_lines``) after this.
    """
    rule = PlaybookRule(
        playbook_id=playbook_id,
        clause_type=clause_type,
        **kwargs,
    )
    session.add(rule)
    await session.flush()
    return rule


async def get_rule(session: AsyncSession, rule_id: uuid.UUID) -> PlaybookRule | None:
    """Fetch a PlaybookRule by id, or None if not found."""
    result = await session.execute(select(PlaybookRule).where(PlaybookRule.id == rule_id))
    return result.scalar_one_or_none()


async def list_rules(session: AsyncSession, playbook_id: uuid.UUID) -> list[PlaybookRule]:
    """Return all rules for a given playbook."""
    result = await session.execute(
        select(PlaybookRule).where(PlaybookRule.playbook_id == playbook_id)
    )
    return list(result.scalars().all())


async def list_rules_for_version(
    session: AsyncSession, playbook_version_id: uuid.UUID
) -> list[PlaybookRule]:
    """Return all rules that belong to a given playbook version."""
    result = await session.execute(
        select(PlaybookRule).where(PlaybookRule.playbook_version_id == playbook_version_id)
    )
    return list(result.scalars().all())


async def update_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    **kwargs: object,
) -> PlaybookRule | None:
    """Update fields on a PlaybookRule. Returns the updated rule, or None if not found."""
    rule = await get_rule(session, rule_id)
    if rule is None:
        return None
    for key, value in kwargs.items():
        setattr(rule, key, value)
    await session.flush()
    return rule


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID) -> bool:
    """Delete a PlaybookRule by id. Returns True if a row was deleted."""
    cursor = cast(CursorResult, await session.execute(
        delete(PlaybookRule).where(PlaybookRule.id == rule_id)
    ))
    return cursor.rowcount > 0


async def get_rules_by_clause_type(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    clause_type: str,
) -> list[PlaybookRule]:
    """Fetch rules for a playbook filtered by clause_type.

    Used by S2 (scoring stage) to retrieve matching rules per clause.
    """
    result = await session.execute(
        select(PlaybookRule).where(
            PlaybookRule.playbook_id == playbook_id,
            PlaybookRule.clause_type == clause_type,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Playbook version operations: create, copy, publish, get-current
# (playbook_plan.md section 3.3; task 1.4 item 1)
# ---------------------------------------------------------------------------


async def create_version(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    version: str,
    status: str = "draft",
    **kwargs: object,
) -> PlaybookVersion:
    """Create a new, empty PlaybookVersion row.

    ``kwargs``: effective_from, effective_to, change_summary, created_by,
    approved_by, published_at.
    """
    pv = PlaybookVersion(
        playbook_id=playbook_id,
        version=version,
        status=status,
        **kwargs,
    )
    session.add(pv)
    await session.flush()
    return pv


async def get_version(session: AsyncSession, version_id: uuid.UUID) -> PlaybookVersion | None:
    """Fetch a PlaybookVersion by id, or None if not found."""
    result = await session.execute(
        select(PlaybookVersion).where(PlaybookVersion.id == version_id)
    )
    return result.scalar_one_or_none()


async def list_versions(session: AsyncSession, playbook_id: uuid.UUID) -> list[PlaybookVersion]:
    """Return all versions of a playbook."""
    result = await session.execute(
        select(PlaybookVersion).where(PlaybookVersion.playbook_id == playbook_id)
    )
    return list(result.scalars().all())


async def get_current_version(
    session: AsyncSession, playbook_id: uuid.UUID
) -> PlaybookVersion | None:
    """Return the playbook's current (published, in-force) version, or None.

    Follows ``playbook.current_version_id`` rather than guessing from
    ``status``, since that column is the single source of truth for which
    version is in force (``playbook_plan.md`` section 3.2).
    """
    pb = await get_playbook(session, playbook_id)
    if pb is None or pb.current_version_id is None:
        return None
    return await get_version(session, pb.current_version_id)


async def copy_version(
    session: AsyncSession,
    source_version_id: uuid.UUID,
    new_version: str,
    created_by: str | None = None,
) -> PlaybookVersion | None:
    """Create a new ``draft`` version by deep-copying a source version's rules
    and all six child tables (``playbook_plan.md`` section 3.3: "a new draft
    is created by copying the current version").

    Returns None if the source version does not exist. Runs a fixed number of
    queries regardless of rule count, via ``get_rules_with_children``.
    """
    source = await get_version(session, source_version_id)
    if source is None:
        return None

    new_pv = PlaybookVersion(
        playbook_id=source.playbook_id,
        version=new_version,
        status="draft",
        created_by=created_by,
    )
    session.add(new_pv)
    await session.flush()

    rules = await get_rules_with_children(session, source_version_id)
    for rule in rules:
        new_rule = PlaybookRule(
            playbook_id=rule.playbook_id,
            playbook_version_id=new_pv.id,
            clause_type=rule.clause_type,
            issue_id=rule.issue_id,
            rule_key=rule.rule_key,
            title=rule.title,
            required=rule.required,
            risk_weight=rule.risk_weight,
            position_summary=rule.position_summary,
            risk_rationale=rule.risk_rationale,
            negotiable=rule.negotiable,
            default_zone=rule.default_zone,
            needs_human_judgment=rule.needs_human_judgment,
            judgment_note=rule.judgment_note,
            applies_when=rule.applies_when,
            detection_guidance=rule.detection_guidance,
            source_ref=rule.source_ref,
            authored_by=rule.authored_by,
            approved_by=rule.approved_by,
            last_reviewed_at=rule.last_reviewed_at,
        )
        session.add(new_rule)
        await session.flush()

        # Recommended-position references are remapped by position *index*
        # within the rule (positions carry no other stable key), so the
        # objection copy below can point at the matching copied position.
        old_position_ids: list[uuid.UUID] = []
        new_positions: list[RulePosition] = []
        for pos in getattr(rule, "positions", []):
            old_position_ids.append(pos.id)
            new_pos = RulePosition(
                rule_id=new_rule.id,
                kind=pos.kind,
                rung=pos.rung,
                label=pos.label,
                language=pos.language,
                summary=pos.summary,
                zone=pos.zone,
                approver_role_id=pos.approver_role_id,
                conditions=pos.conditions,
                give_get=pos.give_get,
                internal_note=pos.internal_note,
            )
            session.add(new_pos)
            new_positions.append(new_pos)
        if new_positions:
            await session.flush()
        position_id_map = dict(zip(old_position_ids, (p.id for p in new_positions), strict=True))

        for param in getattr(rule, "parameters", []):
            session.add(
                RuleParameter(
                    rule_id=new_rule.id,
                    key=param.key,
                    label=param.label,
                    value_type=param.value_type,
                    unit=param.unit,
                    direction=param.direction,
                    preferred_value=param.preferred_value,
                    green_limit=param.green_limit,
                    yellow_limit=param.yellow_limit,
                    allowed_values=param.allowed_values,
                    extraction_hint=param.extraction_hint,
                    context_overrides=param.context_overrides,
                )
            )

        for red_line in getattr(rule, "red_lines", []):
            session.add(
                RedLine(
                    scope=red_line.scope,
                    rule_id=new_rule.id,
                    playbook_id=None,
                    key=red_line.key,
                    description=red_line.description,
                    condition_type=red_line.condition_type,
                    condition=red_line.condition,
                    action=red_line.action,
                    approver_role_id=red_line.approver_role_id,
                    rationale=red_line.rationale,
                )
            )

        for objection in getattr(rule, "objections", []):
            session.add(
                RuleObjection(
                    rule_id=new_rule.id,
                    objection=objection.objection,
                    their_rationale=objection.their_rationale,
                    response=objection.response,
                    talking_points=objection.talking_points,
                    recommended_position_id=position_id_map.get(
                        objection.recommended_position_id
                    ),
                    frequency=objection.frequency,
                    counterparty_profile=objection.counterparty_profile,
                )
            )

        for dependency in getattr(rule, "dependencies", []):
            session.add(
                RuleDependency(
                    rule_id=new_rule.id,
                    related_rule_key=dependency.related_rule_key,
                    relation=dependency.relation,
                    note=dependency.note,
                )
            )

        for test_case in getattr(rule, "test_cases", []):
            session.add(
                RuleTestCase(
                    rule_id=new_rule.id,
                    name=test_case.name,
                    sample_text=test_case.sample_text,
                    context=test_case.context,
                    expected_outcome=test_case.expected_outcome,
                    expected_zone=test_case.expected_zone,
                    expected_position_rung=test_case.expected_position_rung,
                    expected_red_line_key=test_case.expected_red_line_key,
                    is_trap=test_case.is_trap,
                )
            )

    await session.flush()
    return new_pv


async def publish_version(
    session: AsyncSession,
    version_id: uuid.UUID,
    approved_by: str | None = None,
) -> PlaybookVersion | None:
    """Publish a draft version: freeze it, supersede the previous current
    version, and point ``playbook.current_version_id`` at it
    (``playbook_plan.md`` section 3.3).

    Returns None if the version does not exist.
    """
    version = await get_version(session, version_id)
    if version is None:
        return None

    now = datetime.now(UTC)
    pb = await get_playbook(session, version.playbook_id)

    if pb is not None and pb.current_version_id is not None and pb.current_version_id != version_id:
        previous = await get_version(session, pb.current_version_id)
        if previous is not None:
            previous.status = "superseded"
            previous.effective_to = now

    version.status = "published"
    version.published_at = now
    if version.effective_from is None:
        version.effective_from = now
    if approved_by is not None:
        version.approved_by = approved_by

    if pb is not None:
        pb.current_version_id = version.id

    await session.flush()
    return version


# ---------------------------------------------------------------------------
# Playbook change log
# ---------------------------------------------------------------------------


async def create_change_log_entry(
    session: AsyncSession,
    playbook_version_id: uuid.UUID,
    rule_key: str,
    change_type: str,
    **kwargs: object,
) -> PlaybookChangeLog:
    """Record one rule-level change (field_path, old_value, new_value, reason, changed_by)."""
    entry = PlaybookChangeLog(
        playbook_version_id=playbook_version_id,
        rule_key=rule_key,
        change_type=change_type,
        **kwargs,
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_change_log(
    session: AsyncSession, playbook_version_id: uuid.UUID
) -> list[PlaybookChangeLog]:
    """Return all change-log rows for a version."""
    result = await session.execute(
        select(PlaybookChangeLog).where(
            PlaybookChangeLog.playbook_version_id == playbook_version_id
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_position
# ---------------------------------------------------------------------------


async def create_rule_position(
    session: AsyncSession, rule_id: uuid.UUID, kind: str, label: str, language: str, zone: str,
    **kwargs: object,
) -> RulePosition:
    """kwargs: rung, summary, approver_role_id, conditions, give_get, internal_note."""
    position = RulePosition(
        rule_id=rule_id, kind=kind, label=label, language=language, zone=zone, **kwargs
    )
    session.add(position)
    await session.flush()
    return position


async def get_rule_position(session: AsyncSession, position_id: uuid.UUID) -> RulePosition | None:
    result = await session.execute(select(RulePosition).where(RulePosition.id == position_id))
    return result.scalar_one_or_none()


async def list_rule_positions(session: AsyncSession, rule_id: uuid.UUID) -> list[RulePosition]:
    result = await session.execute(select(RulePosition).where(RulePosition.rule_id == rule_id))
    return list(result.scalars().all())


async def update_rule_position(
    session: AsyncSession, position_id: uuid.UUID, **kwargs: object
) -> RulePosition | None:
    position = await get_rule_position(session, position_id)
    if position is None:
        return None
    for key, value in kwargs.items():
        setattr(position, key, value)
    await session.flush()
    return position


async def delete_rule_position(session: AsyncSession, position_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(RulePosition).where(RulePosition.id == position_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_parameter
# ---------------------------------------------------------------------------


async def create_rule_parameter(
    session: AsyncSession, rule_id: uuid.UUID, key: str, label: str, value_type: str,
    direction: str, **kwargs: object,
) -> RuleParameter:
    """kwargs: unit, preferred_value, green_limit, yellow_limit, allowed_values,
    extraction_hint, context_overrides."""
    parameter = RuleParameter(
        rule_id=rule_id, key=key, label=label, value_type=value_type, direction=direction,
        **kwargs,
    )
    session.add(parameter)
    await session.flush()
    return parameter


async def get_rule_parameter(
    session: AsyncSession, parameter_id: uuid.UUID
) -> RuleParameter | None:
    result = await session.execute(select(RuleParameter).where(RuleParameter.id == parameter_id))
    return result.scalar_one_or_none()


async def list_rule_parameters(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleParameter]:
    result = await session.execute(select(RuleParameter).where(RuleParameter.rule_id == rule_id))
    return list(result.scalars().all())


async def update_rule_parameter(
    session: AsyncSession, parameter_id: uuid.UUID, **kwargs: object
) -> RuleParameter | None:
    parameter = await get_rule_parameter(session, parameter_id)
    if parameter is None:
        return None
    for key, value in kwargs.items():
        setattr(parameter, key, value)
    await session.flush()
    return parameter


async def delete_rule_parameter(session: AsyncSession, parameter_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(RuleParameter).where(RuleParameter.id == parameter_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Rule-children CRUD: red_line (scope 'rule', 'playbook' or 'global')
# ---------------------------------------------------------------------------


async def create_red_line(
    session: AsyncSession, scope: str, key: str, description: str, condition_type: str,
    condition: dict, action: str, **kwargs: object,
) -> RedLine:
    """kwargs: rule_id, playbook_id, approver_role_id, rationale.

    ``scope`` decides which of ``rule_id``/``playbook_id`` is set; neither is
    set for ``scope='global'``.
    """
    red_line = RedLine(
        scope=scope, key=key, description=description, condition_type=condition_type,
        condition=condition, action=action, **kwargs,
    )
    session.add(red_line)
    await session.flush()
    return red_line


async def get_red_line(session: AsyncSession, red_line_id: uuid.UUID) -> RedLine | None:
    result = await session.execute(select(RedLine).where(RedLine.id == red_line_id))
    return result.scalar_one_or_none()


async def list_red_lines_for_rule(session: AsyncSession, rule_id: uuid.UUID) -> list[RedLine]:
    result = await session.execute(select(RedLine).where(RedLine.rule_id == rule_id))
    return list(result.scalars().all())


async def list_red_lines_for_playbook(
    session: AsyncSession, playbook_id: uuid.UUID
) -> list[RedLine]:
    """Red lines with ``scope='playbook'`` scoped to this playbook."""
    result = await session.execute(select(RedLine).where(RedLine.playbook_id == playbook_id))
    return list(result.scalars().all())


async def list_global_red_lines(session: AsyncSession) -> list[RedLine]:
    """Red lines with ``scope='global'`` (apply to every playbook)."""
    result = await session.execute(select(RedLine).where(RedLine.scope == "global"))
    return list(result.scalars().all())


async def update_red_line(
    session: AsyncSession, red_line_id: uuid.UUID, **kwargs: object
) -> RedLine | None:
    red_line = await get_red_line(session, red_line_id)
    if red_line is None:
        return None
    for key, value in kwargs.items():
        setattr(red_line, key, value)
    await session.flush()
    return red_line


async def delete_red_line(session: AsyncSession, red_line_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(RedLine).where(RedLine.id == red_line_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_objection
# ---------------------------------------------------------------------------


async def create_rule_objection(
    session: AsyncSession, rule_id: uuid.UUID, objection: str, response: str, **kwargs: object,
) -> RuleObjection:
    """kwargs: their_rationale, talking_points, recommended_position_id,
    frequency, counterparty_profile."""
    obj = RuleObjection(rule_id=rule_id, objection=objection, response=response, **kwargs)
    session.add(obj)
    await session.flush()
    return obj


async def get_rule_objection(
    session: AsyncSession, objection_id: uuid.UUID
) -> RuleObjection | None:
    result = await session.execute(select(RuleObjection).where(RuleObjection.id == objection_id))
    return result.scalar_one_or_none()


async def list_rule_objections(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleObjection]:
    result = await session.execute(select(RuleObjection).where(RuleObjection.rule_id == rule_id))
    return list(result.scalars().all())


async def update_rule_objection(
    session: AsyncSession, objection_id: uuid.UUID, **kwargs: object
) -> RuleObjection | None:
    obj = await get_rule_objection(session, objection_id)
    if obj is None:
        return None
    for key, value in kwargs.items():
        setattr(obj, key, value)
    await session.flush()
    return obj


async def delete_rule_objection(session: AsyncSession, objection_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(RuleObjection).where(RuleObjection.id == objection_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_dependency
# ---------------------------------------------------------------------------


async def create_rule_dependency(
    session: AsyncSession, rule_id: uuid.UUID, related_rule_key: str, relation: str,
    **kwargs: object,
) -> RuleDependency:
    """kwargs: note."""
    dependency = RuleDependency(
        rule_id=rule_id, related_rule_key=related_rule_key, relation=relation, **kwargs
    )
    session.add(dependency)
    await session.flush()
    return dependency


async def get_rule_dependency(
    session: AsyncSession, dependency_id: uuid.UUID
) -> RuleDependency | None:
    result = await session.execute(
        select(RuleDependency).where(RuleDependency.id == dependency_id)
    )
    return result.scalar_one_or_none()


async def list_rule_dependencies(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleDependency]:
    result = await session.execute(select(RuleDependency).where(RuleDependency.rule_id == rule_id))
    return list(result.scalars().all())


async def update_rule_dependency(
    session: AsyncSession, dependency_id: uuid.UUID, **kwargs: object
) -> RuleDependency | None:
    dependency = await get_rule_dependency(session, dependency_id)
    if dependency is None:
        return None
    for key, value in kwargs.items():
        setattr(dependency, key, value)
    await session.flush()
    return dependency


async def delete_rule_dependency(session: AsyncSession, dependency_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(RuleDependency).where(RuleDependency.id == dependency_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Rule-children CRUD: rule_test_case
# ---------------------------------------------------------------------------


async def create_rule_test_case(
    session: AsyncSession, rule_id: uuid.UUID, name: str, expected_outcome: str, **kwargs: object,
) -> RuleTestCase:
    """kwargs: sample_text, context, expected_zone, expected_position_rung,
    expected_red_line_key, is_trap."""
    test_case = RuleTestCase(
        rule_id=rule_id, name=name, expected_outcome=expected_outcome, **kwargs
    )
    session.add(test_case)
    await session.flush()
    return test_case


async def get_rule_test_case(session: AsyncSession, test_case_id: uuid.UUID) -> RuleTestCase | None:
    result = await session.execute(select(RuleTestCase).where(RuleTestCase.id == test_case_id))
    return result.scalar_one_or_none()


async def list_rule_test_cases(session: AsyncSession, rule_id: uuid.UUID) -> list[RuleTestCase]:
    result = await session.execute(select(RuleTestCase).where(RuleTestCase.rule_id == rule_id))
    return list(result.scalars().all())


async def update_rule_test_case(
    session: AsyncSession, test_case_id: uuid.UUID, **kwargs: object
) -> RuleTestCase | None:
    test_case = await get_rule_test_case(session, test_case_id)
    if test_case is None:
        return None
    for key, value in kwargs.items():
        setattr(test_case, key, value)
    await session.flush()
    return test_case


async def delete_rule_test_case(session: AsyncSession, test_case_id: uuid.UUID) -> bool:
    cursor = cast(CursorResult, await session.execute(
        delete(RuleTestCase).where(RuleTestCase.id == test_case_id)
    ))
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# get_rules_with_children: bulk-load a version's rules and all child rows in
# a fixed number of queries (1 for rules + 1 per child table = 7 total),
# independent of how many rules or children exist. This is the shape the
# resolution engine (task 4.2 / playbook_plan.md section 5.1) needs: "Return
# the merged rules with children, plus the source playbook and version for
# each rule."
# ---------------------------------------------------------------------------


async def get_rules_with_children(
    session: AsyncSession, version_id: uuid.UUID
) -> list[PlaybookRule]:
    """Return every PlaybookRule for *version_id*, each with its six child
    lists attached as plain attributes: ``positions``, ``parameters``,
    ``red_lines``, ``objections``, ``dependencies``, ``test_cases``.

    Runs exactly one query for the rules and one query per child table
    (filtered with ``IN``), for a fixed total of 7 queries regardless of how
    many rules the version has — never N+1.
    """
    rules = await list_rules_for_version(session, version_id)
    return await attach_children(session, rules)


async def list_rules_with_children(
    session: AsyncSession, playbook_id: uuid.UUID
) -> list[PlaybookRule]:
    """Like ``get_rules_with_children`` but keyed by playbook (every rule of
    the playbook, across all its versions). Same fixed 7 queries."""
    rules = await list_rules(session, playbook_id)
    return await attach_children(session, rules)


async def get_rule_with_children(
    session: AsyncSession, rule_id: uuid.UUID
) -> PlaybookRule | None:
    """One rule with its six child lists attached, or None if not found."""
    rule = await get_rule(session, rule_id)
    if rule is None:
        return None
    await attach_children(session, [rule])
    return rule


async def attach_children(
    session: AsyncSession, rules: list[PlaybookRule]
) -> list[PlaybookRule]:
    """Attach the six child lists to each rule in *rules* as plain attributes
    (``positions``, ``parameters``, ``red_lines``, ``objections``,
    ``dependencies``, ``test_cases``), in one query per child table. Returns
    *rules*.
    """
    for model in _CHILD_MODELS:
        setattr_name = _CHILD_ATTR[model]
        for rule in rules:
            setattr(rule, setattr_name, [])

    if not rules:
        return rules

    rule_ids = [rule.id for rule in rules]
    rules_by_id = {rule.id: rule for rule in rules}

    for model in _CHILD_MODELS:
        result: Any = await session.execute(select(model).where(model.rule_id.in_(rule_ids)))
        children = result.scalars().all()
        attr_name = _CHILD_ATTR[model]
        for child in children:
            owner_rule = rules_by_id.get(child.rule_id)
            if owner_rule is not None:
                getattr(owner_rule, attr_name).append(child)

    return rules


# ---------------------------------------------------------------------------
# Child-set sync for rule CRUD (task 5.5): write a rule's full set of
# positions / rule-scoped red lines from an inline list, the way the rule
# create/update API carries them. Each input is a mapping of column values,
# optionally with an ``id`` naming an existing row of this rule to update in
# place. Inputs without a (matching) id are created, and existing rows not
# named are deleted.
# ---------------------------------------------------------------------------

_POSITION_FIELDS = (
    "kind", "rung", "label", "language", "summary", "zone", "approver_role_id",
    "conditions", "give_get", "internal_note",
)
_RED_LINE_FIELDS = (
    "key", "description", "condition_type", "condition", "action", "approver_role_id",
    "rationale",
)


async def sync_rule_positions(
    session: AsyncSession, rule_id: uuid.UUID, positions: list[dict[str, Any]]
) -> list[RulePosition]:
    """Make *rule_id*'s ``rule_position`` rows match *positions* exactly.

    ``rule_objection.recommended_position_id`` references ``rule_position``
    with no ``ON DELETE`` action, so before deleting a position this clears
    any objection reference to it. Otherwise the delete would fail with a
    foreign-key violation.
    """
    existing = {p.id: p for p in await list_rule_positions(session, rule_id)}
    kept: set[uuid.UUID] = set()
    result: list[RulePosition] = []
    for data in positions:
        values = {f: data.get(f) for f in _POSITION_FIELDS}
        row = existing.get(data.get("id"))  # type: ignore[arg-type]
        if row is not None and row.id not in kept:
            for field, value in values.items():
                setattr(row, field, value)
            kept.add(row.id)
        else:
            row = RulePosition(rule_id=rule_id, **values)
            session.add(row)
        result.append(row)

    removed = [pid for pid in existing if pid not in kept]
    if removed:
        for objection in await list_rule_objections(session, rule_id):
            if objection.recommended_position_id in removed:
                objection.recommended_position_id = None
        await session.flush()
        await session.execute(delete(RulePosition).where(RulePosition.id.in_(removed)))
    await session.flush()
    return result


async def sync_rule_red_lines(
    session: AsyncSession, rule_id: uuid.UUID, red_lines: list[dict[str, Any]]
) -> list[RedLine]:
    """Make *rule_id*'s rule-scoped ``red_line`` rows match *red_lines* exactly.

    Every row written gets ``scope='rule'``, ``rule_id=rule_id`` and
    ``playbook_id=None``.
    """
    existing = {r.id: r for r in await list_red_lines_for_rule(session, rule_id)}
    kept: set[uuid.UUID] = set()
    result: list[RedLine] = []
    for data in red_lines:
        values = {f: data.get(f) for f in _RED_LINE_FIELDS}
        row = existing.get(data.get("id"))  # type: ignore[arg-type]
        if row is not None and row.id not in kept:
            for field, value in values.items():
                setattr(row, field, value)
            kept.add(row.id)
        else:
            row = RedLine(scope="rule", rule_id=rule_id, playbook_id=None, **values)
            session.add(row)
        result.append(row)

    removed = [rid for rid in existing if rid not in kept]
    if removed:
        await session.execute(delete(RedLine).where(RedLine.id.in_(removed)))
    await session.flush()
    return result


# ---------------------------------------------------------------------------
# Upsert-by-key helpers for the seed loader (task 2.1), which upserts a
# whole playbook — header, family/issue/role/policy references, rules and
# children — by stable key inside one transaction per playbook
# (playbook_implementation.md task 2.1 item 2: "Upsert by stable key").
# ---------------------------------------------------------------------------


async def upsert_playbook(
    session: AsyncSession, key: str, defaults: dict[str, Any]
) -> tuple[Playbook, bool]:
    """Insert or update a Playbook by its stable ``key``.

    Returns ``(playbook, created)``.
    """
    pb = await get_playbook_by_key(session, key)
    if pb is not None:
        for field, value in defaults.items():
            setattr(pb, field, value)
        await session.flush()
        return pb, False
    pb = Playbook(key=key, **defaults)
    session.add(pb)
    await session.flush()
    return pb, True


async def upsert_clause_family(
    session: AsyncSession, key: str, defaults: dict[str, Any]
) -> tuple[ClauseFamily, bool]:
    """Insert or update a ClauseFamily by its text primary key.

    Note: ``clause_family`` rows are application reference data inserted by
    migration 010 (task 1.1), not by the seed. This helper exists for
    completeness and for tests/tools that manage families directly; the seed
    loader (task 2.1) is expected to treat a missing family as an error,
    per ``playbook_implementation.md`` task 2.1 item 1.
    """
    result = await session.execute(select(ClauseFamily).where(ClauseFamily.key == key))
    family = result.scalar_one_or_none()
    if family is not None:
        for field, value in defaults.items():
            setattr(family, field, value)
        await session.flush()
        return family, False
    family = ClauseFamily(key=key, **defaults)
    session.add(family)
    await session.flush()
    return family, True


async def upsert_clause_issue(
    session: AsyncSession, family_key: str, key: str, defaults: dict[str, Any]
) -> tuple[ClauseIssue, bool]:
    """Insert or update a ClauseIssue by its stable ``(family_key, key)`` pair."""
    result = await session.execute(
        select(ClauseIssue).where(
            ClauseIssue.family_key == family_key, ClauseIssue.key == key
        )
    )
    issue = result.scalar_one_or_none()
    if issue is not None:
        for field, value in defaults.items():
            setattr(issue, field, value)
        await session.flush()
        return issue, False
    issue = ClauseIssue(family_key=family_key, key=key, **defaults)
    session.add(issue)
    await session.flush()
    return issue, True


async def upsert_approver_role(
    session: AsyncSession, key: str, defaults: dict[str, Any]
) -> tuple[ApproverRole, bool]:
    """Insert or update an ApproverRole by its stable ``key``."""
    result = await session.execute(select(ApproverRole).where(ApproverRole.key == key))
    role = result.scalar_one_or_none()
    if role is not None:
        for field, value in defaults.items():
            setattr(role, field, value)
        await session.flush()
        return role, False
    role = ApproverRole(key=key, **defaults)
    session.add(role)
    await session.flush()
    return role, True


async def upsert_escalation_policy(
    session: AsyncSession,
    playbook_id: uuid.UUID | None,
    clause_type: str | None,
    zone: str,
    priority: int,
    defaults: dict[str, Any],
) -> tuple[EscalationPolicy, bool]:
    """Insert or update an EscalationPolicy by a composite natural key.

    ``escalation_policy`` (``playbook_plan.md`` section 3.12) has no stable
    text ``key`` column of its own, unlike the seed file's ``key`` field
    (``seed/playbooks/models.py::EscalationPolicy``) — see this task's report
    for the gap this leaves. In its absence, ``(playbook_id, clause_type,
    zone, priority)`` is the closest thing the table has to a natural key:
    the plan's own tie-break rule ("most specific match wins; ties broken by
    priority") already treats that tuple as what distinguishes one policy row
    from another within the same scope.
    """
    result = await session.execute(
        select(EscalationPolicy).where(
            EscalationPolicy.playbook_id == playbook_id,
            EscalationPolicy.clause_type == clause_type,
            EscalationPolicy.zone == zone,
            EscalationPolicy.priority == priority,
        )
    )
    policy = result.scalar_one_or_none()
    if policy is not None:
        for field, value in defaults.items():
            setattr(policy, field, value)
        await session.flush()
        return policy, False
    policy = EscalationPolicy(
        playbook_id=playbook_id, clause_type=clause_type, zone=zone, priority=priority, **defaults
    )
    session.add(policy)
    await session.flush()
    return policy, True
