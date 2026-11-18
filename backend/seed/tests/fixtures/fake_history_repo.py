"""In-memory stand-ins for ``playbook_repo`` / ``authority_repo`` / ``contract_repo``,
used by ``seed/tests/test_history_load.py`` instead of a real database.

Unlike ``seed.playbooks.load``, ``seed.history.load`` also constructs real ORM
model instances directly (``Contract``, ``DecisionEvent``, ``PlaybookException``
from ``app.db.models``) rather than going through repository functions for
every write — there is no repository layer for creating a ``contract`` or a
``decision_event`` row outside the application's own services. ``FakeSession``
therefore does what a real ``AsyncSession.flush()`` does for a client-side
``default=uuid.uuid4`` primary key: assign an ``id`` to any object passed to
``add()`` that does not have one yet. Everything else here mirrors
``fake_repo.py``'s shape.
"""

from __future__ import annotations

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
class FakeHistoryDB:
    playbooks: dict[str, Row] = field(default_factory=dict)  # key -> Row(id)
    versions: dict[uuid.UUID, list[Row]] = field(default_factory=dict)  # playbook_id -> [Row(id, version)]
    rules: dict[uuid.UUID, list[Row]] = field(default_factory=dict)  # version_id -> [Row(id, rule_key)]
    positions: dict[uuid.UUID, list[Row]] = field(default_factory=dict)  # rule_id -> [Row(id, rung)]
    approver_roles: dict[str, Row] = field(default_factory=dict)  # key -> Row(id)
    parties: dict[str, Row] = field(default_factory=dict)  # normalized_name -> Row(id)

    # What got written, for assertions.
    added: list[Any] = field(default_factory=list)

    # -- fixture-building helpers --------------------------------------------

    def add_playbook(self, key: str) -> Row:
        row = Row(key=key)
        self.playbooks[key] = row
        self.versions[row.id] = []
        return row

    def add_version(self, playbook_key: str, version: str) -> Row:
        pb = self.playbooks[playbook_key]
        row = Row(playbook_id=pb.id, version=version)
        self.versions[pb.id].append(row)
        self.rules[row.id] = []
        return row

    def add_rule(self, version_row: Row, rule_key: str) -> Row:
        row = Row(playbook_version_id=version_row.id, rule_key=rule_key)
        self.rules[version_row.id].append(row)
        self.positions[row.id] = []
        return row

    def add_position(self, rule_row: Row, rung: int | None, kind: str = "fallback") -> Row:
        row = Row(rule_id=rule_row.id, rung=rung, kind=kind)
        self.positions[rule_row.id].append(row)
        return row

    def add_approver_role(self, key: str) -> Row:
        row = Row(key=key)
        self.approver_roles[key] = row
        return row


class FakeSession:
    """Enough of ``AsyncSession`` for ``seed.history.load`` to run against."""

    def __init__(self, db: FakeHistoryDB) -> None:
        self.db = db
        self._pending: list[Any] = []

    def add(self, obj: Any) -> None:
        self._pending.append(obj)

    async def flush(self) -> None:
        for obj in self._pending:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            self.db.added.append(obj)
        self._pending.clear()

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakePlaybookRepo:
    def __init__(self, db: FakeHistoryDB) -> None:
        self.db = db

    async def get_playbook_by_key(self, session: Any, key: str) -> Row | None:
        return self.db.playbooks.get(key)

    async def list_versions(self, session: Any, playbook_id: uuid.UUID) -> list[Row]:
        return list(self.db.versions.get(playbook_id, []))

    async def list_rules_for_version(self, session: Any, playbook_version_id: uuid.UUID) -> list[Row]:
        return list(self.db.rules.get(playbook_version_id, []))

    async def list_rule_positions(self, session: Any, rule_id: uuid.UUID) -> list[Row]:
        return list(self.db.positions.get(rule_id, []))


class FakeAuthorityRepo:
    def __init__(self, db: FakeHistoryDB) -> None:
        self.db = db

    async def get_approver_role_by_key(self, session: Any, key: str) -> Row | None:
        return self.db.approver_roles.get(key)


class FakeContractRepo:
    def __init__(self, db: FakeHistoryDB) -> None:
        self.db = db

    async def upsert_party(self, session: Any, normalized_name: str, display_name: str) -> Row:
        existing = self.db.parties.get(normalized_name)
        if existing is not None:
            return existing
        row = Row(normalized_name=normalized_name, display_name=display_name)
        self.db.parties[normalized_name] = row
        return row


def make_fakes(
    db: FakeHistoryDB | None = None,
) -> tuple[FakeHistoryDB, FakeSession, FakePlaybookRepo, FakeAuthorityRepo, FakeContractRepo]:
    db = db if db is not None else FakeHistoryDB()
    return db, FakeSession(db), FakePlaybookRepo(db), FakeAuthorityRepo(db), FakeContractRepo(db)
