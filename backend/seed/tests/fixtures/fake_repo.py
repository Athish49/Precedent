"""An in-memory stand-in for the ``playbook_repo`` / ``taxonomy_repo`` modules,
used by ``seed/tests/test_playbook_load.py`` instead of a real database.

``FakeDB`` holds every table as a plain Python dict of :class:`Row` objects
(a mutable ``SimpleNamespace`` with an auto-assigned ``id``, the same shape a
real ORM instance would have for the attributes the loader reads). ``FakeSession``
provides ``begin_nested()`` as an async context manager that snapshots and, on
an exception, restores ``FakeDB``'s tables — the same rollback behaviour a
real ``SAVEPOINT`` gives ``seed.playbooks.load``'s per-playbook transaction.

``FakePlaybookRepo`` and ``FakeTaxonomyRepo`` implement the exact functions
``seed.playbooks.load`` calls, with the exact signatures, operating on one
``FakeDB``. A test monkeypatches ``load.playbook_repo`` / ``load.taxonomy_repo``
to these objects, so the loader's own orchestration code runs unmodified
against an in-memory database.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


class Row(SimpleNamespace):
    """A mutable record. Gets a random ``id`` unless one is given."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)


@dataclass
class FakeDB:
    """In-memory tables, keyed the way the real schema's natural keys work."""

    agreement_types: set[str] = field(default_factory=set)
    clause_families: set[str] = field(default_factory=set)
    clause_issues: dict[tuple[str, str], Row] = field(default_factory=dict)
    context_dimensions: dict[str, Row] = field(default_factory=dict)
    approver_roles: dict[str, Row] = field(default_factory=dict)
    escalation_policies: dict[tuple[Any, Any, str, int], Row] = field(default_factory=dict)
    global_red_lines: dict[str, Row] = field(default_factory=dict)
    playbooks: dict[str, Row] = field(default_factory=dict)  # by key
    playbooks_by_id: dict[uuid.UUID, Row] = field(default_factory=dict)
    versions: dict[uuid.UUID, Row] = field(default_factory=dict)  # by id
    rules: dict[uuid.UUID, Row] = field(default_factory=dict)  # by id
    positions: dict[uuid.UUID, Row] = field(default_factory=dict)
    parameters: dict[uuid.UUID, Row] = field(default_factory=dict)
    red_lines: dict[uuid.UUID, Row] = field(default_factory=dict)  # scope='rule'
    objections: dict[uuid.UUID, Row] = field(default_factory=dict)
    dependencies: dict[uuid.UUID, Row] = field(default_factory=dict)
    test_cases: dict[uuid.UUID, Row] = field(default_factory=dict)
    change_log: list[Row] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.__dict__)

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.__dict__.clear()
        self.__dict__.update(copy.deepcopy(snapshot))


class _Nested:
    """Mimics ``AsyncSession.begin_nested()``: a SAVEPOINT that rolls back the
    FakeDB's tables (not the whole session) if the body raises."""

    def __init__(self, db: FakeDB) -> None:
        self._db = db

    async def __aenter__(self) -> _Nested:
        self._snapshot = self._db.snapshot()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is not None:
            self._db.restore(self._snapshot)
        return False


class FakeSession:
    """Enough of ``AsyncSession`` for ``seed.playbooks.load`` to run against."""

    def __init__(self, db: FakeDB) -> None:
        self.db = db

    def begin_nested(self) -> _Nested:
        return _Nested(self.db)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


# ---------------------------------------------------------------------------
# taxonomy_repo
# ---------------------------------------------------------------------------


class FakeTaxonomyRepo:
    def __init__(self, db: FakeDB) -> None:
        self.db = db

    async def list_clause_families(self, session: Any) -> list[Row]:
        return [Row(key=k) for k in self.db.clause_families]

    async def list_agreement_types(self, session: Any) -> list[Row]:
        return [Row(key=k) for k in self.db.agreement_types]

    async def get_context_dimension(self, session: Any, key: str) -> Row | None:
        return self.db.context_dimensions.get(key)

    async def create_context_dimension(
        self, session: Any, key: str, name: str, value_type: str, source: str, **kwargs: Any
    ) -> Row:
        row = Row(key=key, name=name, value_type=value_type, source=source, **kwargs)
        self.db.context_dimensions[key] = row
        return row

    async def update_context_dimension(self, session: Any, key: str, **kwargs: Any) -> Row | None:
        row = self.db.context_dimensions.get(key)
        if row is None:
            return None
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row


# ---------------------------------------------------------------------------
# playbook_repo
# ---------------------------------------------------------------------------


class FakePlaybookRepo:
    def __init__(self, db: FakeDB) -> None:
        self.db = db

    # -- approver_role ------------------------------------------------------

    async def upsert_approver_role(
        self, session: Any, key: str, defaults: dict[str, Any]
    ) -> tuple[Row, bool]:
        existing = self.db.approver_roles.get(key)
        if existing is not None:
            for k, v in defaults.items():
                setattr(existing, k, v)
            return existing, False
        row = Row(key=key, **defaults)
        self.db.approver_roles[key] = row
        return row, True

    # -- clause_issue ---------------------------------------------------------

    async def upsert_clause_issue(
        self, session: Any, family_key: str, key: str, defaults: dict[str, Any]
    ) -> tuple[Row, bool]:
        existing = self.db.clause_issues.get((family_key, key))
        if existing is not None:
            for k, v in defaults.items():
                setattr(existing, k, v)
            return existing, False
        row = Row(family_key=family_key, key=key, **defaults)
        self.db.clause_issues[(family_key, key)] = row
        return row, True

    # -- playbook ------------------------------------------------------------

    async def upsert_playbook(
        self, session: Any, key: str, defaults: dict[str, Any]
    ) -> tuple[Row, bool]:
        existing = self.db.playbooks.get(key)
        if existing is not None:
            for k, v in defaults.items():
                setattr(existing, k, v)
            return existing, False
        row = Row(key=key, current_version_id=None, parent_playbook_id=None, **defaults)
        self.db.playbooks[key] = row
        self.db.playbooks_by_id[row.id] = row
        return row, True

    async def update_playbook(
        self, session: Any, playbook_id: uuid.UUID, **kwargs: Any
    ) -> Row | None:
        row = self.db.playbooks_by_id.get(playbook_id)
        if row is None:
            return None
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row

    async def list_playbooks(self, session: Any) -> list[Row]:
        return list(self.db.playbooks.values())

    # -- escalation_policy -----------------------------------------------------

    async def upsert_escalation_policy(
        self,
        session: Any,
        playbook_id: uuid.UUID | None,
        clause_type: str | None,
        zone: str,
        priority: int,
        defaults: dict[str, Any],
    ) -> tuple[Row, bool]:
        natural_key = (playbook_id, clause_type, zone, priority)
        existing = self.db.escalation_policies.get(natural_key)
        if existing is not None:
            for k, v in defaults.items():
                setattr(existing, k, v)
            return existing, False
        row = Row(
            playbook_id=playbook_id,
            clause_type=clause_type,
            zone=zone,
            priority=priority,
            **defaults,
        )
        self.db.escalation_policies[natural_key] = row
        return row, True

    # -- red_line (global and rule-scoped) ------------------------------------

    async def list_global_red_lines(self, session: Any) -> list[Row]:
        return list(self.db.global_red_lines.values())

    async def create_red_line(
        self,
        session: Any,
        scope: str,
        key: str,
        description: str,
        condition_type: str,
        condition: dict,
        action: str,
        **kwargs: Any,
    ) -> Row:
        row = Row(
            scope=scope,
            key=key,
            description=description,
            condition_type=condition_type,
            condition=condition,
            action=action,
            rule_id=None,
            playbook_id=None,
            approver_role_id=None,
            **kwargs,
        )
        if scope == "global":
            self.db.global_red_lines[key] = row
        else:
            self.db.red_lines[row.id] = row
        return row

    async def update_red_line(
        self, session: Any, red_line_id: uuid.UUID, **kwargs: Any
    ) -> Row | None:
        # `global_red_lines` is keyed by the red line's text `key`, and
        # `red_lines` (rule-scoped) by its `id`; search both by `id`.
        row = self.db.red_lines.get(red_line_id)
        if row is None:
            row = next(
                (c for c in self.db.global_red_lines.values() if c.id == red_line_id), None
            )
        if row is None:
            return None
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row

    async def list_red_lines_for_rule(self, session: Any, rule_id: uuid.UUID) -> list[Row]:
        return [r for r in self.db.red_lines.values() if r.rule_id == rule_id]

    async def delete_red_line(self, session: Any, red_line_id: uuid.UUID) -> bool:
        if red_line_id in self.db.red_lines:
            del self.db.red_lines[red_line_id]
            return True
        return False

    # -- playbook_version -------------------------------------------------------

    async def create_version(
        self,
        session: Any,
        playbook_id: uuid.UUID,
        version: str,
        status: str = "draft",
        **kwargs: Any,
    ) -> Row:
        row = Row(playbook_id=playbook_id, version=version, status=status, **kwargs)
        self.db.versions[row.id] = row
        return row

    async def list_versions(self, session: Any, playbook_id: uuid.UUID) -> list[Row]:
        return [v for v in self.db.versions.values() if v.playbook_id == playbook_id]

    # -- playbook_rule ----------------------------------------------------------

    async def create_rule(
        self,
        session: Any,
        playbook_id: uuid.UUID,
        clause_type: str,
        **kwargs: Any,
    ) -> Row:
        row = Row(
            playbook_id=playbook_id,
            clause_type=clause_type,
            **kwargs,
        )
        self.db.rules[row.id] = row
        return row

    async def update_rule(self, session: Any, rule_id: uuid.UUID, **kwargs: Any) -> Row | None:
        row = self.db.rules.get(rule_id)
        if row is None:
            return None
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row

    async def list_rules_for_version(
        self, session: Any, playbook_version_id: uuid.UUID
    ) -> list[Row]:
        return [r for r in self.db.rules.values() if r.playbook_version_id == playbook_version_id]

    async def get_rules_with_children(self, session: Any, version_id: uuid.UUID) -> list[Row]:
        rules = await self.list_rules_for_version(session, version_id)
        for rule in rules:
            rule.positions = [p for p in self.db.positions.values() if p.rule_id == rule.id]
            rule.parameters = [p for p in self.db.parameters.values() if p.rule_id == rule.id]
            rule.red_lines = [r for r in self.db.red_lines.values() if r.rule_id == rule.id]
            rule.objections = [o for o in self.db.objections.values() if o.rule_id == rule.id]
            rule.dependencies = [d for d in self.db.dependencies.values() if d.rule_id == rule.id]
            rule.test_cases = [t for t in self.db.test_cases.values() if t.rule_id == rule.id]
        return rules

    # -- rule_position ------------------------------------------------------

    async def create_rule_position(
        self,
        session: Any,
        rule_id: uuid.UUID,
        kind: str,
        label: str,
        language: str,
        zone: str,
        **kwargs: Any,
    ) -> Row:
        row = Row(rule_id=rule_id, kind=kind, label=label, language=language, zone=zone, **kwargs)
        self.db.positions[row.id] = row
        return row

    async def list_rule_positions(self, session: Any, rule_id: uuid.UUID) -> list[Row]:
        return [p for p in self.db.positions.values() if p.rule_id == rule_id]

    async def delete_rule_position(self, session: Any, position_id: uuid.UUID) -> bool:
        return self.db.positions.pop(position_id, None) is not None

    # -- rule_parameter -------------------------------------------------------

    async def create_rule_parameter(
        self,
        session: Any,
        rule_id: uuid.UUID,
        key: str,
        label: str,
        value_type: str,
        direction: str,
        **kwargs: Any,
    ) -> Row:
        row = Row(
            rule_id=rule_id,
            key=key,
            label=label,
            value_type=value_type,
            direction=direction,
            **kwargs,
        )
        self.db.parameters[row.id] = row
        return row

    async def list_rule_parameters(self, session: Any, rule_id: uuid.UUID) -> list[Row]:
        return [p for p in self.db.parameters.values() if p.rule_id == rule_id]

    async def delete_rule_parameter(self, session: Any, parameter_id: uuid.UUID) -> bool:
        return self.db.parameters.pop(parameter_id, None) is not None

    # -- rule_objection -------------------------------------------------------

    async def create_rule_objection(
        self, session: Any, rule_id: uuid.UUID, objection: str, response: str, **kwargs: Any
    ) -> Row:
        row = Row(rule_id=rule_id, objection=objection, response=response, **kwargs)
        self.db.objections[row.id] = row
        return row

    async def list_rule_objections(self, session: Any, rule_id: uuid.UUID) -> list[Row]:
        return [o for o in self.db.objections.values() if o.rule_id == rule_id]

    async def delete_rule_objection(self, session: Any, objection_id: uuid.UUID) -> bool:
        return self.db.objections.pop(objection_id, None) is not None

    # -- rule_dependency ------------------------------------------------------

    async def create_rule_dependency(
        self, session: Any, rule_id: uuid.UUID, related_rule_key: str, relation: str, **kwargs: Any
    ) -> Row:
        row = Row(rule_id=rule_id, related_rule_key=related_rule_key, relation=relation, **kwargs)
        self.db.dependencies[row.id] = row
        return row

    async def list_rule_dependencies(self, session: Any, rule_id: uuid.UUID) -> list[Row]:
        return [d for d in self.db.dependencies.values() if d.rule_id == rule_id]

    async def delete_rule_dependency(self, session: Any, dependency_id: uuid.UUID) -> bool:
        return self.db.dependencies.pop(dependency_id, None) is not None

    # -- rule_test_case -------------------------------------------------------

    async def create_rule_test_case(
        self, session: Any, rule_id: uuid.UUID, name: str, expected_outcome: str, **kwargs: Any
    ) -> Row:
        row = Row(rule_id=rule_id, name=name, expected_outcome=expected_outcome, **kwargs)
        self.db.test_cases[row.id] = row
        return row

    async def list_rule_test_cases(self, session: Any, rule_id: uuid.UUID) -> list[Row]:
        return [t for t in self.db.test_cases.values() if t.rule_id == rule_id]

    async def delete_rule_test_case(self, session: Any, test_case_id: uuid.UUID) -> bool:
        return self.db.test_cases.pop(test_case_id, None) is not None

    # -- playbook_change_log --------------------------------------------------

    async def create_change_log_entry(
        self,
        session: Any,
        playbook_version_id: uuid.UUID,
        rule_key: str,
        change_type: str,
        **kwargs: Any,
    ) -> Row:
        row = Row(
            playbook_version_id=playbook_version_id,
            rule_key=rule_key,
            change_type=change_type,
            **kwargs,
        )
        self.db.change_log.append(row)
        return row


def make_fakes(
    db: FakeDB | None = None,
) -> tuple[FakeDB, FakeSession, FakePlaybookRepo, FakeTaxonomyRepo]:
    """Build a fresh (or given) FakeDB with its session and repo doubles."""
    db = db if db is not None else FakeDB()
    return db, FakeSession(db), FakePlaybookRepo(db), FakeTaxonomyRepo(db)
