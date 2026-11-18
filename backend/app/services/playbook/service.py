"""S6 Playbook service — CRUD over playbooks and rules.

Thin orchestration layer: validates inputs, delegates to the repo, and
translates missing-row (None/False) into AppError(404).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.db.models.playbook import Playbook, PlaybookRule
from app.db.repositories import playbook_repo
from app.schemas.playbook import (
    _VALID_PRACTICE_AREAS,
    PlaybookCreate,
    PlaybookUpdate,
    RuleCreate,
    RuleUpdate,
)
from app.services.playbook import versions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_practice_area(practice_area: str) -> None:
    if practice_area not in _VALID_PRACTICE_AREAS:
        raise AppError(
            400,
            "invalid_practice_area",
            f"practice_area must be one of {sorted(_VALID_PRACTICE_AREAS)!r}, "
            f"got {practice_area!r}",
        )


def _jsonable(value: Any) -> Any:
    """JSON-safe form of a rule column value (UUID, Decimal, datetime, ...)
    for a ``playbook_change_log`` JSONB old/new value."""
    return to_jsonable_python(value)


# ---------------------------------------------------------------------------
# Playbook CRUD
# ---------------------------------------------------------------------------


async def create_playbook(session: AsyncSession, body: PlaybookCreate) -> Playbook:
    _validate_practice_area(body.practice_area)
    pb = await playbook_repo.create_playbook(
        session,
        name=body.name,
        practice_area=body.practice_area,
        precedence=body.precedence,
    )
    await session.commit()
    await session.refresh(pb)
    return pb


async def list_playbooks(session: AsyncSession) -> list[Playbook]:
    return await playbook_repo.list_playbooks(session)


async def get_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> Playbook:
    pb = await playbook_repo.get_playbook(session, playbook_id)
    if pb is None:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")
    return pb


async def update_playbook(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    body: PlaybookUpdate,
) -> Playbook:
    # ``exclude_unset=True``: a field the client omitted stays unchanged, but
    # one sent explicitly as ``null`` (e.g. to clear a nullable column) comes
    # through as ``None`` and is applied. Dropping every ``None`` regardless
    # of whether it was sent, as the previous version did, made a nullable
    # field impossible to clear via PATCH.
    kwargs = body.model_dump(exclude_unset=True)
    if "practice_area" in kwargs:
        _validate_practice_area(kwargs["practice_area"])
    pb = await playbook_repo.update_playbook(session, playbook_id, **kwargs)
    if pb is None:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")
    await session.commit()
    await session.refresh(pb)
    return pb


async def delete_playbook(session: AsyncSession, playbook_id: uuid.UUID) -> None:
    deleted = await playbook_repo.delete_playbook(session, playbook_id)
    if not deleted:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")
    await session.commit()


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------


async def create_rule(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    body: RuleCreate,
) -> PlaybookRule:
    """Create a rule plus its inline ``positions`` and ``red_lines`` in one
    transaction, and return it with all six child lists attached.

    A rule may only be added to a *draft* version (409 otherwise), the same
    gate the versions API applies to child rows. A published version's rules
    are what ``routing.resolve`` serves live. A rule with no
    ``playbook_version_id`` is ungated, like the versions API treats legacy
    unversioned rules.
    """
    # Verify parent exists.
    await get_playbook(session, playbook_id)
    if body.playbook_version_id is not None:
        await versions._require_draft_version(session, body.playbook_version_id)
    scalars = body.model_dump(exclude={"positions", "red_lines"})
    rule = await playbook_repo.create_rule(session, playbook_id=playbook_id, **scalars)
    if body.positions:
        await playbook_repo.sync_rule_positions(
            session, rule.id, [p.model_dump(exclude={"id"}) for p in body.positions]
        )
    if body.red_lines:
        await playbook_repo.sync_rule_red_lines(
            session, rule.id, [r.model_dump(exclude={"id"}) for r in body.red_lines]
        )
    await session.commit()
    return await _reload_rule(session, rule.id)


async def list_rules(
    session: AsyncSession,
    playbook_id: uuid.UUID,
) -> list[PlaybookRule]:
    """Every rule of the playbook, each with its six child lists attached."""
    # Verify parent exists so missing playbook → 404, not empty list.
    await get_playbook(session, playbook_id)
    return await playbook_repo.list_rules_with_children(session, playbook_id)


async def update_rule(
    session: AsyncSession,
    rule_id: uuid.UUID,
    body: RuleUpdate,
) -> PlaybookRule:
    """PATCH a rule's scalar fields and, when sent, sync its positions and
    rule-scoped red lines (see ``RuleUpdate``).

    The whole PATCH — scalar fields and child syncs alike — is draft-gated
    exactly like the versions API's child-row endpoints: 409
    ``version_not_draft`` if the rule belongs to a non-draft version. A
    published version's rule is what ``routing.resolve`` serves live, so
    editing ``risk_weight``, ``applies_when``, ``default_zone``,
    ``required``, positions etc. in place would change live scoring,
    redline and drafting output with no version bump. A legacy rule with no
    ``playbook_version_id`` stays ungated (see ``_resolve_rule_draft``).

    Every edit is logged to ``playbook_change_log``: one ``modified`` entry
    per scalar field whose value actually changed (``field_path`` = the
    field name), plus one ``positions_synced`` / ``red_lines_synced`` entry
    per child sync (old and new lists). Logging is a no-op for a legacy
    unversioned rule, which has no version row to attach the entry to.
    """
    # 404s for a missing rule, 409s for a non-draft version — before any write.
    existing = await versions._resolve_rule_draft(session, rule_id)
    # See the identical note in ``update_playbook`` above: ``exclude_unset``
    # is what lets a nullable field (e.g. ``title``, ``applies_when``) be
    # cleared by sending it as ``null``, while an omitted field is left alone.
    kwargs = body.model_dump(exclude_unset=True, exclude={"positions", "red_lines"})
    # Snapshot old scalar values before the repo mutates the (identity-mapped)
    # row in place. Skipped for a legacy rule: ``_log_change`` no-ops there.
    old_scalars: dict[str, Any] = {}
    if existing.playbook_version_id is not None:
        old_scalars = {f: getattr(existing, f) for f in kwargs}
    rule = await playbook_repo.update_rule(session, rule_id, **kwargs)
    if rule is None:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    if rule.playbook_version_id is not None:
        for field, old_value in old_scalars.items():
            # Compared raw (so e.g. Decimal("5") == 5.0 is "unchanged"), then
            # serialized for the JSONB columns.
            if kwargs[field] != old_value:
                await versions._log_change(
                    session, rule, "modified", field_path=field,
                    old_value=_jsonable(old_value), new_value=_jsonable(kwargs[field]),
                )
    if body.positions is not None:
        before = await playbook_repo.list_rule_positions(session, rule.id)
        old_value = [versions._serialize(p) for p in before]
        await playbook_repo.sync_rule_positions(
            session, rule.id, [p.model_dump() for p in body.positions]
        )
        # new_value is the validated request list rather than the flushed
        # rows: an updated row's ``updated_at`` is expired after flush, and
        # re-reading it would need a lazy load (not allowed under asyncio).
        await versions._log_change(
            session, rule, "positions_synced", field_path="positions",
            old_value=old_value, new_value=[p.model_dump(mode="json") for p in body.positions],
        )
    if body.red_lines is not None:
        before_rl = await playbook_repo.list_red_lines_for_rule(session, rule.id)
        old_value = [versions._serialize(r) for r in before_rl]
        await playbook_repo.sync_rule_red_lines(
            session, rule.id, [r.model_dump() for r in body.red_lines]
        )
        await versions._log_change(
            session, rule, "red_lines_synced", field_path="red_lines",
            old_value=old_value, new_value=[r.model_dump(mode="json") for r in body.red_lines],
        )
    await session.commit()
    return await _reload_rule(session, rule.id)


async def _reload_rule(session: AsyncSession, rule_id: uuid.UUID) -> PlaybookRule:
    """Re-read a just-committed rule with its children attached."""
    rule = await playbook_repo.get_rule_with_children(session, rule_id)
    if rule is None:  # pragma: no cover - deleted concurrently
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    return rule


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID) -> None:
    """Delete a rule (its children cascade).

    Draft-gated like ``update_rule``: 404 for a missing rule, 409
    ``version_not_draft`` if it belongs to a non-draft version (removing a
    rule from a published version would silently drop it from live
    resolution). Writes one ``playbook_change_log`` entry with
    ``change_type="removed"`` and the rule's scalar fields as ``old_value``
    (no-op for a legacy unversioned rule). The entry is written before the
    delete, while the row's attributes are still loaded; if the delete then
    fails, the 404 aborts the transaction and the entry is never committed.
    """
    rule = await versions._resolve_rule_draft(session, rule_id)
    if rule.playbook_version_id is not None:
        snapshot = {
            f: _jsonable(getattr(rule, f)) for f in ("rule_key", *versions._RULE_SCALAR_FIELDS)
        }
        await versions._log_change(session, rule, "removed", old_value=snapshot)
    deleted = await playbook_repo.delete_rule(session, rule_id)
    if not deleted:
        raise AppError(404, "not_found", f"Rule {rule_id} not found")
    await session.commit()
