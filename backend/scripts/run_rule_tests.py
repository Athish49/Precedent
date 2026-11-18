#!/usr/bin/env python3
"""Rule test-case runner CLI (task 4.10).

Runs every rule_test_case row (``playbook_plan.md`` section 3.10) for one or
more playbooks through ``app/services/playbook/testing.py`` and prints a
pass-rate report.

Usage (from ``backend/``)::

    python -m scripts.run_rule_tests [--deterministic] [--yes]
        [--playbook KEY ...] [--version-id UUID]

``--deterministic`` runs only cases decidable without a model call (phrase/
regex red lines and ``missing`` cases) — fast, free, and never calls
``app.core.llm.gateway``.

The default mode calls the real model once per case that needs it (batched
in a single ``gateway.call_batch`` request) — this is cost-bearing. The
script prints how many calls it is about to make and refuses to proceed
without ``--yes``, prompting for interactive confirmation when the session
is a terminal and there is no ``--yes``.

With neither ``--playbook`` nor ``--version-id``, every playbook's current
(published) version is tested. ``--playbook KEY`` (repeatable) restricts to
specific playbooks by their stable key; ``--version-id`` tests one exact
version regardless of which playbook it belongs to or whether it is current.

Exit codes: 0 if every case that ran passed, 1 if any failed, 2 on a setup
error (bad arguments, nothing to test, or the user declined to proceed).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import get_session_factory, init_db
from app.db.models.playbook import PlaybookRule
from app.db.repositories import playbook_repo
from app.services.playbook import testing as test_runner


@dataclass
class _LoadResult:
    rows: list[tuple[str, PlaybookRule]]
    notes: list[str]


async def _rules_for_version(
    session: AsyncSession, playbook_key: str, version_id: uuid.UUID
) -> list[tuple[str, PlaybookRule]]:
    rules = await playbook_repo.get_rules_with_children(session, version_id)
    return [(playbook_key, rule) for rule in rules]


async def _load_rows(
    session: AsyncSession, *, playbook_keys: list[str], version_id: uuid.UUID | None
) -> _LoadResult:
    notes: list[str] = []

    if version_id is not None:
        version = await playbook_repo.get_version(session, version_id)
        if version is None:
            notes.append(f"version {version_id} not found")
            return _LoadResult([], notes)
        pb = await playbook_repo.get_playbook(session, version.playbook_id)
        key = (pb.key if pb is not None else None) or str(version.playbook_id)
        return _LoadResult(await _rules_for_version(session, key, version_id), notes)

    if playbook_keys:
        playbooks = []
        for key in playbook_keys:
            pb = await playbook_repo.get_playbook_by_key(session, key)
            if pb is None:
                notes.append(f"playbook {key!r} not found; skipped")
                continue
            playbooks.append(pb)
    else:
        playbooks = await playbook_repo.list_playbooks(session)

    rows: list[tuple[str, PlaybookRule]] = []
    for pb in playbooks:
        if pb.current_version_id is None:
            notes.append(f"playbook {pb.key or pb.id!r} has no current version; skipped")
            continue
        key = pb.key or str(pb.id)
        rows.extend(await _rules_for_version(session, key, pb.current_version_id))
    return _LoadResult(rows, notes)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Run only cases decidable without a model call. Free, no gateway calls.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the cost-bearing default-mode model calls without an interactive prompt.",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        dest="playbook_keys",
        metavar="KEY",
        help="Restrict to this playbook (repeatable). Default: every playbook's current version.",
    )
    parser.add_argument(
        "--version-id",
        type=uuid.UUID,
        default=None,
        help="Test one exact playbook version id instead of selecting by playbook.",
    )
    return parser.parse_args(argv)


def _confirm_model_calls(required: int, *, yes: bool) -> bool:
    if required == 0:
        return True
    print(
        f"This run will make {required} model call(s) against the real LLM gateway "
        "(app.core.llm.gateway) — this is cost-bearing."
    )
    if yes:
        return True
    if not sys.stdin.isatty():
        print("Refusing to proceed without --yes in a non-interactive session.")
        return False
    answer = input(f"Proceed with {required} model call(s)? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    init_db(settings.database_url)
    factory = get_session_factory()

    async with factory() as session:
        loaded = await _load_rows(
            session, playbook_keys=args.playbook_keys or [], version_id=args.version_id
        )

    for note in loaded.notes:
        print(f"note: {note}")

    if not loaded.rows:
        print("Nothing to test — no rules found for the given selection.")
        return 2

    required = test_runner.count_required_model_calls(loaded.rows)
    if not args.deterministic:
        if not _confirm_model_calls(required, yes=args.yes):
            print("Aborted: declined to make the required model call(s).")
            return 2

    summary = test_runner.run_rule_tests(loaded.rows, deterministic=args.deterministic)
    print(test_runner.format_report(summary))
    return 0 if summary.failed_cases == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Aborted.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
