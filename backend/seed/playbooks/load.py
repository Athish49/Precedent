"""Load a playbook seed directory into the database (task 2.1).

Command line::

    cd backend
    .venv/bin/python -m seed.playbooks.load [dir] [--dry-run] [--only PLAYBOOK_KEY ...]

``dir`` defaults to ``seed/playbooks/data/halcyon``. The directory is always
loaded and validated first (:func:`seed.playbooks.validate.load_valid_directory`);
a directory with any validation error is refused before anything is written.

``--dry-run`` never opens a database connection: it validates the directory
and prints the counts a real run would write. Only a run without
``--dry-run`` touches the database, and it calls the namespace guard
(``seed.common.seed_session``) before writing anything.

Write order
-----------
Shared reference content is written once: clause issues (``taxonomy.yaml``),
context dimensions, approver roles, playbook headers (so escalation policies
and a playbook's own ``parent`` can resolve a playbook key to an id),
escalation policies, then global red lines. ``agreement_type`` and
``clause_family`` are never written here — they come from migration ``010``;
if a practice area or clause family named in the seed files has no matching
row, :func:`run_load` raises :class:`MissingReferenceDataError` before
anything else is written.

Each playbook is then loaded in its own transaction (a ``SAVEPOINT`` taken
with ``session.begin_nested()``): its current version (from ``playbook.yaml``)
and any later versions (``versions/<playbook>_<version>.yaml``, task 3.14),
each with its rules and the six child tables, then that version's change-log
entries. An error while loading one playbook rolls back only that playbook's
savepoint; the loader moves on to the next one and reports the error.

A published version (``playbook_version.status == 'published'``) is never
rewritten: if the seed content for a version that is already published in
the database differs from what is stored, loading that playbook stops with
:class:`PublishedVersionImmutableError` telling the author to add a new
version file instead of editing the published one. A draft version (or a
version not yet in the database) is replaced in full: the rule's own columns
are updated and every child row is deleted and rewritten from the file, since
none of the six child tables has a natural key of its own to upsert by
(``rule_parameter`` is the one exception, unique on ``(rule_id, key)``, but
even it is simplest to replace alongside the rest). This is the "upsert by
stable key" called for by this task: the stable key is the playbook's
``key``, the version string, and each rule's ``rule_key`` — not a key on
every child row, which the schema does not provide. A ``superseded`` version
is frozen the same way as a published one.

After a playbook's versions are written, the newest published version
becomes ``playbook.current_version_id`` and every earlier published version
is marked ``superseded`` with ``effective_to`` set to its successor's
``effective_from`` (``playbook_plan.md`` section 3.3, mirroring
``playbook_repo.publish_version``). This runs on every load, so a reload also
repairs a database where an older version was left ``published``.
``--dry-run`` prints these planned statuses.

Finally, any playbook already in the database whose ``key`` is not in the
seed directory is set to ``status = 'archived'`` (never deleted). This uses
the full directory's playbook keys, independent of ``--only``, since
``--only`` selects what to *write* this run, not which playbooks still exist
in the seed.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.db.repositories import playbook_repo, taxonomy_repo
from seed.common import SeedError, add_data_dir_argument, build_parser, data_dir, run, seed_session
from seed.playbooks.models import (
    Authority,
    LoadedPlaybook,
    LoadedVersion,
    PlaybookVersionHeader,
    Rule,
    SeedDirectory,
    Taxonomy,
)
from seed.playbooks.validate import load_valid_directory

MIGRATION_010 = "migration 010 (backend/migrations/versions/010_playbook_lookups.py)"
_RULE_KEY_PREFIX_RE = re.compile(r"^([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)")
# Version statuses whose rule content is frozen (never rewritten by a reload).
_FROZEN_STATUSES = frozenset({"published", "superseded"})


class MissingReferenceDataError(SeedError):
    """``agreement_type`` or ``clause_family`` rows the seed needs are not in the database."""


class PublishedVersionImmutableError(SeedError):
    """A published ``playbook_version``'s content differs from the seed file."""


# ---------------------------------------------------------------------------
# Counts and results
# ---------------------------------------------------------------------------


@dataclass
class RuleCounts:
    rules: int = 0
    positions: int = 0
    parameters: int = 0
    red_lines: int = 0
    objections: int = 0
    dependencies: int = 0
    test_cases: int = 0
    versions: int = 0
    change_log_entries: int = 0

    def __add__(self, other: RuleCounts) -> RuleCounts:
        return RuleCounts(
            **{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)}
        )


@dataclass
class PlaybookLoadResult:
    key: str
    ok: bool
    error: str | None = None
    counts: RuleCounts = field(default_factory=RuleCounts)


@dataclass
class LoadReport:
    dry_run: bool = False
    issues: int = 0
    context_dimensions: int = 0
    roles: int = 0
    escalation_policies: int = 0
    global_red_lines: int = 0
    playbooks: list[PlaybookLoadResult] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)

    @property
    def failed(self) -> list[PlaybookLoadResult]:
        return [p for p in self.playbooks if not p.ok]

    @property
    def ok(self) -> bool:
        return not self.failed


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _num(value: Any) -> Any:
    """Normalize a possibly-``Decimal`` number for comparison."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return value


def _canon(value: Any) -> str:
    """A stable string form of JSON-ish content, for equality comparison."""
    return json.dumps(value, sort_keys=True, default=str)


def _as_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _loadable_rules(playbook: LoadedPlaybook) -> list[Rule]:
    """The rules the loader writes for one playbook folder: header present,
    rule file listed in ``rule_files`` (matches ``seed.playbooks.report``)."""
    if playbook.header is None:
        return []
    unlisted = set(playbook.unlisted_rule_files)
    return [r.rule for r in playbook.rules if r.source not in unlisted]


def _version_sort_key(loaded: LoadedVersion) -> tuple[int, int]:
    major, minor = loaded.version_set.version.version.split(".", 1)
    return int(major), int(minor)


def _change_log_rule_key(field_path: str, fallback: str) -> str:
    """The ``rule_key`` a change-log entry belongs to, read off the front of
    ``field_path`` (e.g. ``limitation_of_liability.cap_amount.positions[1]``).
    Falls back to the playbook key if ``field_path`` does not start with one."""
    match = _RULE_KEY_PREFIX_RE.match(field_path)
    return match.group(1) if match else fallback


def _add(total: RuleCounts, extra: RuleCounts) -> RuleCounts:
    return total + extra


# ---------------------------------------------------------------------------
# Reference-data preflight (agreement_type, clause_family: migration 010)
# ---------------------------------------------------------------------------


async def _check_reference_data(session: Any, seed: SeedDirectory) -> None:
    family_keys = {f.key for f in await taxonomy_repo.list_clause_families(session)}
    agreement_keys = {a.key for a in await taxonomy_repo.list_agreement_types(session)}

    missing_families = (
        {i.family for i in seed.taxonomy.issues if i.family not in family_keys}
        if seed.taxonomy
        else set()
    )
    missing_agreement_types = {
        pb.header.practice_area
        for pb in seed.playbooks
        if pb.header is not None and pb.header.practice_area not in agreement_keys
    }
    if not missing_families and not missing_agreement_types:
        return
    parts = []
    if missing_families:
        parts.append(f"clause_family row(s) missing: {', '.join(sorted(missing_families))}")
    if missing_agreement_types:
        parts.append(
            f"agreement_type row(s) missing: {', '.join(sorted(missing_agreement_types))}"
        )
    raise MissingReferenceDataError(
        f"the database is missing reference data that {MIGRATION_010} provides: "
        + "; ".join(parts)
    )


# ---------------------------------------------------------------------------
# Shared content: issues, context dimensions, roles, playbook headers,
# escalation policies, global red lines
# ---------------------------------------------------------------------------


async def _load_issues(session: Any, taxonomy: Taxonomy) -> dict[str, uuid.UUID]:
    issue_map: dict[str, uuid.UUID] = {}
    for issue in taxonomy.issues:
        obj, _ = await playbook_repo.upsert_clause_issue(
            session,
            issue.family,
            issue.key,
            {
                "name": issue.name,
                "description": issue.description,
                "detection_hints": issue.detection_hints,
            },
        )
        issue_map[issue.rule_key] = obj.id
    return issue_map


async def _load_context_dimensions(session: Any, authority: Authority) -> int:
    count = 0
    for dimension in authority.context_dimensions:
        values = [v.model_dump() for v in dimension.values]
        existing = await taxonomy_repo.get_context_dimension(session, dimension.key)
        if existing is not None:
            await taxonomy_repo.update_context_dimension(
                session,
                dimension.key,
                name=dimension.name,
                value_type=dimension.value_type,
                source=dimension.source,
                values=values,
            )
        else:
            await taxonomy_repo.create_context_dimension(
                session,
                dimension.key,
                dimension.name,
                dimension.value_type,
                dimension.source,
                values=values,
            )
        count += 1
    return count


async def _load_roles(session: Any, authority: Authority) -> dict[str, uuid.UUID]:
    role_map: dict[str, uuid.UUID] = {}
    for role in authority.roles:
        obj, _ = await playbook_repo.upsert_approver_role(
            session,
            role.key,
            {
                "name": role.name,
                "function": role.function,
                "level": role.level,
                "default_sla_hours": role.default_sla_hours,
            },
        )
        role_map[role.key] = obj.id
    return role_map


async def _load_playbook_headers(
    session: Any, headers: list[LoadedPlaybook], role_map: dict[str, uuid.UUID]
) -> dict[str, uuid.UUID]:

    id_map: dict[str, uuid.UUID] = {}
    for pb in headers:
        header = pb.header
        assert header is not None
        defaults = {
            "name": header.name,
            "practice_area": header.practice_area,
            "precedence": header.precedence,
            "layer": header.layer,
            "party_role": header.party_role,
            "paper_scope": header.paper_scope,
            "jurisdiction": header.jurisdiction,
            "business_unit": header.business_unit,
            "owner_role_id": role_map.get(header.owner_role),
            "applies_when": header.applies_when,
            "description": header.description,
            "status": header.status,
            "review_cadence_days": header.review_cadence_days,
            "next_review_at": header.next_review_at,
        }
        obj, _ = await playbook_repo.upsert_playbook(session, header.key, defaults)
        id_map[header.key] = obj.id

    # Second pass: `parent` is a playbook key, which may be defined later in
    # the directory than the child that names it.
    for pb in headers:
        header = pb.header
        assert header is not None
        if header.parent and header.parent in id_map:
            await playbook_repo.update_playbook(
                session, id_map[header.key], parent_playbook_id=id_map[header.parent]
            )
    return id_map


async def _load_escalation_policies(
    session: Any,
    authority: Authority,
    role_map: dict[str, uuid.UUID],
    playbook_id_map: dict[str, uuid.UUID],
) -> int:

    count = 0
    for policy in authority.escalation_policies:
        approver_id = role_map[policy.approver_role]
        consult_ids = [str(role_map[key]) for key in policy.consult_roles if key in role_map]
        playbook_id = playbook_id_map.get(policy.playbook) if policy.playbook else None
        defaults = {
            "approver_role_id": approver_id,
            "consult_role_ids": consult_ids,
            "sla_hours": policy.sla_hours,
            "required_info": list(policy.required_info),
            "conditions": policy.conditions,
        }
        await playbook_repo.upsert_escalation_policy(
            session, playbook_id, policy.clause_type, policy.zone, policy.priority, defaults
        )
        count += 1
    return count


async def _load_global_red_lines(
    session: Any, authority: Authority, role_map: dict[str, uuid.UUID]
) -> int:

    existing = {rl.key: rl for rl in await playbook_repo.list_global_red_lines(session)}
    count = 0
    for red_line in authority.global_red_lines:
        approver_id = role_map.get(red_line.approver_role) if red_line.approver_role else None
        if red_line.key in existing:
            await playbook_repo.update_red_line(
                session,
                existing[red_line.key].id,
                description=red_line.description,
                condition_type=red_line.condition_type,
                condition=red_line.condition,
                action=red_line.action,
                approver_role_id=approver_id,
                rationale=red_line.rationale,
            )
        else:
            await playbook_repo.create_red_line(
                session,
                "global",
                red_line.key,
                red_line.description,
                red_line.condition_type,
                red_line.condition,
                red_line.action,
                approver_role_id=approver_id,
                rationale=red_line.rationale,
            )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Published-version guard: compare seed rules to what is already stored
# ---------------------------------------------------------------------------


def _seed_rule_snapshot(rule: Rule) -> tuple:
    return (
        rule.title,
        rule.required,
        _num(rule.risk_weight),
        rule.negotiable,
        rule.default_zone,
        rule.needs_human_judgment,
        rule.judgment_note,
        _canon(rule.applies_when),
        rule.position_summary,
        rule.risk_rationale,
        rule.detection_guidance,
        rule.source_ref,
        tuple(
            sorted(
                (
                    p.kind,
                    p.effective_rung if p.kind != "acceptable_variant" else None,
                    p.label,
                    p.zone,
                    p.summary,
                    p.language,
                    p.approver_role,
                    _canon(p.conditions),
                    p.give_get,
                )
                for p in rule.positions
            )
        ),
        tuple(
            sorted(
                (
                    p.key,
                    p.label,
                    p.value_type,
                    p.unit,
                    p.direction,
                    _canon(_num(p.preferred_value)),
                    _canon(_num(p.green_limit)),
                    _canon(_num(p.yellow_limit)),
                    _canon(p.allowed_values),
                )
                for p in rule.parameters
            )
        ),
        tuple(
            sorted(
                (
                    r.key,
                    r.description,
                    r.condition_type,
                    _canon(r.condition),
                    r.action,
                    r.approver_role,
                )
                for r in rule.red_lines
            )
        ),
        tuple(sorted((o.objection, o.response) for o in rule.objections)),
        tuple(sorted((d.related_rule_key, d.relation) for d in rule.dependencies)),
        tuple(
            sorted(
                (t.name, t.expected_outcome, t.expected_zone, t.sample_text)
                for t in rule.test_cases
            )
        ),
    )


def _db_rule_snapshot(db_rule: Any, reverse_role_map: dict[uuid.UUID, str]) -> tuple:
    def role_key(role_id: uuid.UUID | None) -> str | None:
        return reverse_role_map.get(role_id) if role_id else None

    return (
        db_rule.title,
        db_rule.required,
        _num(db_rule.risk_weight),
        db_rule.negotiable,
        db_rule.default_zone,
        db_rule.needs_human_judgment,
        db_rule.judgment_note,
        _canon(db_rule.applies_when),
        db_rule.position_summary,
        db_rule.risk_rationale,
        db_rule.detection_guidance,
        db_rule.source_ref,
        tuple(
            sorted(
                (
                    p.kind,
                    p.rung,
                    p.label,
                    p.zone,
                    p.summary,
                    p.language,
                    role_key(p.approver_role_id),
                    _canon(p.conditions),
                    p.give_get,
                )
                for p in getattr(db_rule, "positions", [])
            )
        ),
        tuple(
            sorted(
                (
                    p.key,
                    p.label,
                    p.value_type,
                    p.unit,
                    p.direction,
                    _canon(_num(p.preferred_value)),
                    _canon(_num(p.green_limit)),
                    _canon(_num(p.yellow_limit)),
                    _canon(p.allowed_values),
                )
                for p in getattr(db_rule, "parameters", [])
            )
        ),
        tuple(
            sorted(
                (
                    r.key,
                    r.description,
                    r.condition_type,
                    _canon(r.condition),
                    r.action,
                    role_key(r.approver_role_id),
                )
                for r in getattr(db_rule, "red_lines", [])
            )
        ),
        tuple(
            sorted(
                (o.objection, o.response) for o in getattr(db_rule, "objections", [])
            )
        ),
        tuple(
            sorted(
                (d.related_rule_key, d.relation) for d in getattr(db_rule, "dependencies", [])
            )
        ),
        tuple(
            sorted(
                (t.name, t.expected_outcome, t.expected_zone, t.sample_text or "")
                for t in getattr(db_rule, "test_cases", [])
            )
        ),
    )


def _rules_differ(
    db_rules: list[Any], seed_rules: list[Rule], reverse_role_map: dict[uuid.UUID, str]
) -> bool:
    db_by_key = {r.rule_key: r for r in db_rules if r.rule_key}
    seed_by_key = {r.rule_key: r for r in seed_rules}
    if set(db_by_key) != set(seed_by_key):
        return True
    return any(
        _db_rule_snapshot(db_by_key[key], reverse_role_map) != _seed_rule_snapshot(seed_by_key[key])
        for key in seed_by_key
    )


# ---------------------------------------------------------------------------
# Rule and child writers (within one playbook version)
# ---------------------------------------------------------------------------


async def _write_rule_set(
    session: Any,
    playbook_id: uuid.UUID,
    version_id: uuid.UUID,
    rules: list[Rule],
    role_map: dict[str, uuid.UUID],
    issue_map: dict[str, uuid.UUID],
) -> RuleCounts:

    counts = RuleCounts()
    existing_by_key = {
        r.rule_key: r
        for r in await playbook_repo.list_rules_for_version(session, version_id)
        if r.rule_key
    }
    db_rule_by_key: dict[str, uuid.UUID] = {}
    position_index: dict[tuple[str, int | None], uuid.UUID] = {}

    # Subphase A: the rule row and its positions, so a later objection in any
    # rule of this playbook can resolve a `recommended_position` by rule_key.
    for rule in rules:
        defaults: dict[str, Any] = {
            "playbook_version_id": version_id,
            "issue_id": issue_map.get(rule.rule_key),
            "rule_key": rule.rule_key,
            "title": rule.title,
            "position_summary": rule.position_summary,
            "risk_rationale": rule.risk_rationale,
            "required": rule.required,
            "risk_weight": rule.risk_weight,
            "negotiable": rule.negotiable,
            "default_zone": rule.default_zone,
            "needs_human_judgment": rule.needs_human_judgment,
            "judgment_note": rule.judgment_note,
            "applies_when": rule.applies_when,
            "detection_guidance": rule.detection_guidance,
            "source_ref": rule.source_ref,
            "authored_by": rule.authored_by,
            "approved_by": rule.approved_by,
            "last_reviewed_at": rule.last_reviewed_at,
        }
        existing = existing_by_key.get(rule.rule_key)
        if existing is not None:
            await playbook_repo.update_rule(
                session,
                existing.id,
                clause_type=rule.family,
                **defaults,
            )
            db_rule_id = existing.id
            # No child table has a natural key of its own (`rule_parameter`
            # is the one exception). Replacing them in full is the simplest
            # correct "upsert" available on this schema.
            for child in await playbook_repo.list_rule_positions(session, db_rule_id):
                await playbook_repo.delete_rule_position(session, child.id)
            for child in await playbook_repo.list_rule_parameters(session, db_rule_id):
                await playbook_repo.delete_rule_parameter(session, child.id)
            for child in await playbook_repo.list_red_lines_for_rule(session, db_rule_id):
                await playbook_repo.delete_red_line(session, child.id)
            for child in await playbook_repo.list_rule_objections(session, db_rule_id):
                await playbook_repo.delete_rule_objection(session, child.id)
            for child in await playbook_repo.list_rule_dependencies(session, db_rule_id):
                await playbook_repo.delete_rule_dependency(session, child.id)
            for child in await playbook_repo.list_rule_test_cases(session, db_rule_id):
                await playbook_repo.delete_rule_test_case(session, child.id)
        else:
            created = await playbook_repo.create_rule(
                session, playbook_id, rule.family, **defaults
            )
            db_rule_id = created.id
        db_rule_by_key[rule.rule_key] = db_rule_id
        counts.rules += 1

        for position in rule.positions:
            role_id = role_map.get(position.approver_role) if position.approver_role else None
            created_pos = await playbook_repo.create_rule_position(
                session,
                db_rule_id,
                position.kind,
                position.label,
                position.language,
                position.zone,
                rung=position.effective_rung,
                summary=position.summary,
                approver_role_id=role_id,
                conditions=position.conditions,
                give_get=position.give_get,
                internal_note=position.internal_note,
            )
            if position.kind != "acceptable_variant":
                position_index[(rule.rule_key, position.effective_rung)] = created_pos.id
            counts.positions += 1

    # Subphase B: everything that may reference a position by (rule_key, rung).
    for rule in rules:
        db_rule_id = db_rule_by_key[rule.rule_key]

        for parameter in rule.parameters:
            await playbook_repo.create_rule_parameter(
                session,
                db_rule_id,
                parameter.key,
                parameter.label,
                parameter.value_type,
                parameter.direction,
                unit=parameter.unit,
                preferred_value=parameter.preferred_value,
                green_limit=parameter.green_limit,
                yellow_limit=parameter.yellow_limit,
                allowed_values=parameter.allowed_values,
                extraction_hint=parameter.extraction_hint,
                context_overrides=(
                    [o.model_dump() for o in parameter.context_overrides]
                    if parameter.context_overrides
                    else None
                ),
            )
            counts.parameters += 1

        for red_line in rule.red_lines:
            role_id = role_map.get(red_line.approver_role) if red_line.approver_role else None
            await playbook_repo.create_red_line(
                session,
                "rule",
                red_line.key,
                red_line.description,
                red_line.condition_type,
                red_line.condition,
                red_line.action,
                rule_id=db_rule_id,
                approver_role_id=role_id,
                rationale=red_line.rationale,
            )
            counts.red_lines += 1

        for objection in rule.objections:
            recommended_id = None
            if objection.recommended_position is not None:
                recommended_id = position_index.get(
                    (
                        objection.recommended_position.rule_key,
                        objection.recommended_position.rung,
                    )
                )
            await playbook_repo.create_rule_objection(
                session,
                db_rule_id,
                objection.objection,
                objection.response,
                their_rationale=objection.their_rationale,
                talking_points=list(objection.talking_points),
                recommended_position_id=recommended_id,
                frequency=objection.frequency,
                counterparty_profile=objection.counterparty_profile,
            )
            counts.objections += 1

        for dependency in rule.dependencies:
            await playbook_repo.create_rule_dependency(
                session,
                db_rule_id,
                dependency.related_rule_key,
                dependency.relation,
                note=dependency.note,
            )
            counts.dependencies += 1

        for test_case in rule.test_cases:
            await playbook_repo.create_rule_test_case(
                session,
                db_rule_id,
                test_case.name,
                test_case.expected_outcome,
                sample_text=test_case.sample_text,
                context=test_case.context,
                expected_zone=test_case.expected_zone,
                expected_position_rung=test_case.expected_position_rung,
                expected_red_line_key=test_case.expected_red_line_key,
                is_trap=test_case.is_trap,
            )
            counts.test_cases += 1

    return counts


async def _write_version(
    session: Any,
    playbook_id: uuid.UUID,
    playbook_key: str,
    version_header: PlaybookVersionHeader,
    rules: list[Rule],
    role_map: dict[str, uuid.UUID],
    issue_map: dict[str, uuid.UUID],
) -> tuple[uuid.UUID, RuleCounts, bool]:
    """Write one ``playbook_version`` and its rules.

    Returns ``(version_id, counts, version_is_new)``. ``version_is_new`` is
    ``True`` only when this call created the ``playbook_version`` row for the
    first time in this run; it is ``False`` when the version already existed
    (whether published-and-unchanged, or draft-and-rewritten). Callers that
    write version-scoped content keyed off "this version was just created" —
    such as change-log entries, which describe the change that produced the
    version — must gate on this flag so a second run against an
    already-loaded version does not duplicate that content.

    Raises :class:`PublishedVersionImmutableError` if the version is already
    published in the database and its content differs from ``rules``.
    """

    reverse_role_map = {v: k for k, v in role_map.items()}
    existing_versions = {
        v.version: v for v in await playbook_repo.list_versions(session, playbook_id)
    }
    existing = existing_versions.get(version_header.version)

    # A superseded version was published once and is just as frozen: its
    # rules must never be rewritten (and its status must not be reset to the
    # seed header's "published"; :func:`_reconcile_version_statuses` owns the
    # published/superseded transition).
    if existing is not None and existing.status in _FROZEN_STATUSES:
        db_rules = await playbook_repo.get_rules_with_children(session, existing.id)
        if _rules_differ(db_rules, rules, reverse_role_map):
            raise PublishedVersionImmutableError(
                f"playbook {playbook_key!r} version {version_header.version!r} is already "
                "published and the seed file's content for it differs from the database; "
                "add a new version file under versions/ instead of editing a published version"
            )
        counts = RuleCounts(versions=0)
        return existing.id, counts, False

    if existing is not None:
        version = existing
        version.change_summary = version_header.change_summary
        version.created_by = version_header.created_by
        version.approved_by = version_header.approved_by
        version.status = version_header.status
        version.effective_from = _as_datetime(version_header.effective_from)
        version.effective_to = _as_datetime(version_header.effective_to)
        version.published_at = _as_datetime(version_header.published_at)
        await session.flush()
        version_is_new = False
    else:
        version = await playbook_repo.create_version(
            session,
            playbook_id,
            version_header.version,
            status=version_header.status,
            effective_from=_as_datetime(version_header.effective_from),
            effective_to=_as_datetime(version_header.effective_to),
            change_summary=version_header.change_summary,
            created_by=version_header.created_by,
            approved_by=version_header.approved_by,
            published_at=_as_datetime(version_header.published_at),
        )
        version_is_new = True

    rule_counts = await _write_rule_set(
        session, playbook_id, version.id, rules, role_map, issue_map
    )
    rule_counts.versions = 1 if version_is_new else 0

    # ``playbook.current_version_id`` is set once per playbook, after every
    # version is written, by :func:`_reconcile_version_statuses`.
    return version.id, rule_counts, version_is_new


# ---------------------------------------------------------------------------
# Version lifecycle: published -> superseded (playbook_plan.md section 3.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedVersionStatus:
    """The status a seed version should end up with after a load."""

    version: str
    status: str
    effective_from: date | None
    effective_to: date | None
    current: bool = False


def plan_version_statuses(
    base: PlaybookVersionHeader, version_files: Sequence[LoadedVersion]
) -> list[PlannedVersionStatus]:
    """Resolve the final status of every seed version of one playbook.

    The seed files declare each version's own status (``published`` for both
    ``playbook.yaml``'s base version and a ``versions/`` file's later one), but
    only one version can be current. Mirroring ``publish_draft`` /
    ``playbook_repo.publish_version``: the newest published version is
    current; every earlier published version becomes ``superseded`` with
    ``effective_to`` set to the ``effective_from`` of the published version
    that replaced it (unless the seed file already states an
    ``effective_to``). Drafts and versions declared ``superseded`` keep their
    declared status.
    """
    headers = [base] + [
        lv.version_set.version for lv in sorted(version_files, key=_version_sort_key)
    ]
    headers.sort(key=lambda h: tuple(int(p) for p in h.version.split(".", 1)))

    published = [h for h in headers if h.status == "published"]
    successor: dict[str, PlaybookVersionHeader] = {
        prev.version: nxt for prev, nxt in zip(published, published[1:], strict=False)
    }
    current = published[-1].version if published else None

    plan: list[PlannedVersionStatus] = []
    for h in headers:
        if h.status == "published" and h.version in successor:
            plan.append(
                PlannedVersionStatus(
                    version=h.version,
                    status="superseded",
                    effective_from=h.effective_from,
                    effective_to=h.effective_to or successor[h.version].effective_from,
                )
            )
        else:
            plan.append(
                PlannedVersionStatus(
                    version=h.version,
                    status=h.status,
                    effective_from=h.effective_from,
                    effective_to=h.effective_to,
                    current=h.version == current,
                )
            )
    return plan


async def _reconcile_version_statuses(
    session: Any,
    playbook_id: uuid.UUID,
    plan: list[PlannedVersionStatus],
) -> None:
    """Apply ``plan`` to the stored ``playbook_version`` rows (idempotent).

    Marks every published version the plan supersedes as ``superseded`` with
    its ``effective_to``, and points ``playbook.current_version_id`` at the
    newest published version. Only a ``published -> superseded`` transition
    (or filling in a missing ``effective_to`` on an already superseded row) is
    made here; rule content is untouched, so a frozen version stays frozen.
    """
    rows = {v.version: v for v in await playbook_repo.list_versions(session, playbook_id)}
    changed = False
    current_id: uuid.UUID | None = None
    for planned in plan:
        row = rows.get(planned.version)
        if row is None:
            continue
        if planned.current:
            current_id = row.id
        if planned.status != "superseded" or row.status not in _FROZEN_STATUSES:
            continue
        if row.status != "superseded":
            row.status = "superseded"
            changed = True
        stored = row.effective_to
        stored_date = stored.date() if isinstance(stored, datetime) else stored
        if planned.effective_to is not None and stored_date != planned.effective_to:
            row.effective_to = _as_datetime(planned.effective_to)
            changed = True
    if changed:
        await session.flush()
    if current_id is not None:
        await playbook_repo.update_playbook(session, playbook_id, current_version_id=current_id)


# ---------------------------------------------------------------------------
# One playbook (its own transaction)
# ---------------------------------------------------------------------------


async def _load_one_playbook(
    session: Any,
    pb: LoadedPlaybook,
    version_files: list[LoadedVersion],
    playbook_id: uuid.UUID,
    role_map: dict[str, uuid.UUID],
    issue_map: dict[str, uuid.UUID],
) -> PlaybookLoadResult:

    header = pb.header
    assert header is not None
    total = RuleCounts()

    _, counts, _ = await _write_version(
        session, playbook_id, header.key, header.version, _loadable_rules(pb), role_map, issue_map
    )
    total = _add(total, counts)

    for loaded_version in sorted(version_files, key=_version_sort_key):
        version_set = loaded_version.version_set
        version_id, counts, version_is_new = await _write_version(
            session,
            playbook_id,
            header.key,
            version_set.version,
            version_set.rules,
            role_map,
            issue_map,
        )
        total = _add(total, counts)
        # Change-log entries describe the change that produced this version,
        # so they belong only to the run that first creates it: writing them
        # again on a later run (when the version already exists, published
        # or draft) would duplicate every row in `playbook_change_log`.
        if version_is_new:
            for change in version_set.changes:
                await playbook_repo.create_change_log_entry(
                    session,
                    version_id,
                    _change_log_rule_key(change.field_path, header.key),
                    change.change_type,
                    field_path=change.field_path,
                    old_value=change.old_value,
                    new_value=change.new_value,
                    reason=change.reason,
                )
                total.change_log_entries += 1

    # Every version is now written; settle which one is current and mark the
    # ones it replaced as superseded (a fresh load and a reload alike).
    await _reconcile_version_statuses(
        session, playbook_id, plan_version_statuses(header.version, version_files)
    )

    return PlaybookLoadResult(key=header.key, ok=True, counts=total)


async def _archive_stale_playbooks(session: Any, seed_keys: set[str]) -> list[str]:
    archived = []
    for pb in await playbook_repo.list_playbooks(session):
        if pb.key and pb.key not in seed_keys and pb.status != "archived":
            await playbook_repo.update_playbook(session, pb.id, status="archived")
            archived.append(pb.key)
    return archived


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_load(
    seed: SeedDirectory, *, only: set[str] | None = None, session: Any | None = None
) -> LoadReport:
    """Write ``seed`` to the database.

    With no ``session``, opens one through :func:`seed.common.seed_session`
    (which calls the namespace guard first) and commits it on a clean exit.
    Tests pass a mocked or in-memory ``session`` directly, bypassing the
    real connection and guard entirely — the orchestration below is the same
    either way.

    Each playbook runs in its own ``SAVEPOINT``: an error during one playbook
    rolls back only that playbook and is recorded on the report; the loader
    continues with the rest. Everything else — shared reference content,
    the reference-data preflight and archiving — runs once, outside any
    per-playbook savepoint, so a failure there aborts the whole run (and, with
    a real session, the whole session is rolled back by ``seed_session``).
    """
    if session is None:
        async with seed_session(dry_run=False) as real_session:
            return await _run_load_with_session(real_session, seed, only)
    return await _run_load_with_session(session, seed, only)


async def _run_load_with_session(
    session: Any, seed: SeedDirectory, only: set[str] | None
) -> LoadReport:
    report = LoadReport(dry_run=False)
    await _check_reference_data(session, seed)

    role_map = await _load_roles(session, seed.authority) if seed.authority else {}
    report.roles = len(seed.authority.roles) if seed.authority else 0

    report.context_dimensions = (
        await _load_context_dimensions(session, seed.authority) if seed.authority else 0
    )

    issue_map = await _load_issues(session, seed.taxonomy) if seed.taxonomy else {}
    report.issues = len(issue_map)

    headers = [pb for pb in seed.playbooks if pb.header is not None]
    playbook_id_map = await _load_playbook_headers(session, headers, role_map)

    report.escalation_policies = (
        await _load_escalation_policies(session, seed.authority, role_map, playbook_id_map)
        if seed.authority
        else 0
    )
    report.global_red_lines = (
        await _load_global_red_lines(session, seed.authority, role_map) if seed.authority else 0
    )

    versions_by_playbook: dict[str, list[LoadedVersion]] = {}
    for loaded_version in seed.versions:
        versions_by_playbook.setdefault(loaded_version.version_set.playbook_key, []).append(
            loaded_version
        )

    for pb in headers:
        assert pb.header is not None
        if only and pb.header.key not in only:
            continue
        try:
            async with session.begin_nested():
                result = await _load_one_playbook(
                    session,
                    pb,
                    versions_by_playbook.get(pb.header.key, []),
                    playbook_id_map[pb.header.key],
                    role_map,
                    issue_map,
                )
        except Exception as exc:  # noqa: BLE001 - recorded per playbook; loader continues
            report.playbooks.append(PlaybookLoadResult(key=pb.header.key, ok=False, error=str(exc)))
        else:
            report.playbooks.append(result)

    report.archived = await _archive_stale_playbooks(session, {pb.header.key for pb in headers})

    return report


# ---------------------------------------------------------------------------
# --dry-run: file-only counts, no database
# ---------------------------------------------------------------------------


@dataclass
class DryRunCounts:
    issues: int = 0
    context_dimensions: int = 0
    roles: int = 0
    escalation_policies: int = 0
    global_red_lines: int = 0
    playbooks: int = 0
    versions: int = 0
    rules: int = 0
    positions: int = 0
    parameters: int = 0
    red_lines: int = 0
    objections: int = 0
    dependencies: int = 0
    test_cases: int = 0
    change_log_entries: int = 0


def compute_dry_run_counts(seed: SeedDirectory, only: set[str] | None = None) -> DryRunCounts:
    """Counts a real run would write, read from the seed files only.

    ``only`` filters the playbook-specific counts (``playbooks`` and
    everything under a playbook); the shared counts (issues, context
    dimensions, roles, escalation policies, global red lines) are not
    filtered, since a real run always writes all of them.
    """
    counts = DryRunCounts()
    if seed.taxonomy:
        counts.issues = len(seed.taxonomy.issues)
    if seed.authority:
        counts.context_dimensions = len(seed.authority.context_dimensions)
        counts.roles = len(seed.authority.roles)
        counts.escalation_policies = len(seed.authority.escalation_policies)
        counts.global_red_lines = len(seed.authority.global_red_lines)

    headers = [pb for pb in seed.playbooks if pb.header is not None]
    selected = [pb for pb in headers if not only or pb.header.key in only]  # type: ignore[union-attr]
    counts.playbooks = len(selected)
    counts.versions = len(selected)

    all_rules: list[Rule] = []
    for pb in selected:
        all_rules.extend(_loadable_rules(pb))
    selected_keys = {pb.header.key for pb in selected}  # type: ignore[union-attr]
    for loaded_version in seed.versions:
        if loaded_version.version_set.playbook_key in selected_keys:
            counts.versions += 1
            all_rules.extend(loaded_version.version_set.rules)
            counts.change_log_entries += len(loaded_version.version_set.changes)

    counts.rules = len(all_rules)
    counts.positions = sum(len(r.positions) for r in all_rules)
    counts.parameters = sum(len(r.parameters) for r in all_rules)
    counts.red_lines = sum(len(r.red_lines) for r in all_rules)
    counts.objections = sum(len(r.objections) for r in all_rules)
    counts.dependencies = sum(len(r.dependencies) for r in all_rules)
    counts.test_cases = sum(len(r.test_cases) for r in all_rules)
    return counts


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _print_dry_run(root: Any, counts: DryRunCounts, only: Sequence[str]) -> None:
    scope = f" (--only {', '.join(only)})" if only else ""
    print(f"{root}: dry run{scope}; nothing written")
    for f in fields(counts):
        print(f"  {f.name}: {getattr(counts, f.name)}")


def _print_version_plan(seed: SeedDirectory, only: set[str] | None) -> None:
    """Print the final version statuses a real run would leave in the database."""
    versions_by_playbook: dict[str, list[LoadedVersion]] = {}
    for loaded_version in seed.versions:
        versions_by_playbook.setdefault(loaded_version.version_set.playbook_key, []).append(
            loaded_version
        )
    print("version statuses after load:")
    for pb in seed.playbooks:
        if pb.header is None or (only and pb.header.key not in only):
            continue
        for planned in plan_version_statuses(
            pb.header.version, versions_by_playbook.get(pb.header.key, [])
        ):
            print(
                f"  {pb.header.key} {planned.version}: {planned.status}"
                f" effective_from={planned.effective_from}"
                f" effective_to={planned.effective_to}"
                + (" [current_version_id]" if planned.current else "")
            )


def _print_report(report: LoadReport) -> None:
    print(f"issues: {report.issues}")
    print(f"context_dimensions: {report.context_dimensions}")
    print(f"roles: {report.roles}")
    print(f"escalation_policies: {report.escalation_policies}")
    print(f"global_red_lines: {report.global_red_lines}")
    for result in report.playbooks:
        if result.ok:
            c = result.counts
            print(
                f"playbook {result.key}: ok "
                f"(versions={c.versions}, rules={c.rules}, positions={c.positions}, "
                f"parameters={c.parameters}, red_lines={c.red_lines}, objections={c.objections}, "
                f"dependencies={c.dependencies}, test_cases={c.test_cases}, "
                f"change_log_entries={c.change_log_entries})"
            )
        else:
            print(f"playbook {result.key}: ERROR rolled back: {result.error}")
    if report.archived:
        print(f"archived: {', '.join(report.archived)}")
    print("RESULT: ok" if report.ok else f"RESULT: {len(report.failed)} playbook(s) failed")


async def _main(args: argparse.Namespace) -> int:
    seed = load_valid_directory(args.data_dir)
    only = set(args.only) if args.only else None
    if args.dry_run:
        counts = compute_dry_run_counts(seed, only)
        _print_dry_run(seed.root, counts, args.only or [])
        _print_version_plan(seed, only)
        return 0
    report = await run_load(seed, only=only)
    _print_report(report)
    return 0 if report.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Load the playbook seed into the database. "
        "With --dry-run, only validates and counts; no database connection is made.",
        prog="python -m seed.playbooks.load",
    )
    add_data_dir_argument(parser, data_dir("playbooks"))
    parser.add_argument(
        "--only",
        action="append",
        metavar="PLAYBOOK_KEY",
        help="load only this playbook key (repeatable); shared data and archiving still run",
    )
    return run(_main, parser, argv)


if __name__ == "__main__":
    raise SystemExit(main())
