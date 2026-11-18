"""Load ``decisions.yaml`` into the database (task 5.3).

Command line::

    cd backend
    .venv/bin/python -m seed.history.load [file] [--dry-run]

``file`` defaults to ``seed/history/data/halcyon/decisions.yaml``. The file is
always loaded and validated first (:func:`load_valid_file`); a file with any
validation error is refused before anything is written.

``--dry-run`` never opens a database connection: it validates the file and
prints the counts a real run would write. Only a run without ``--dry-run``
touches the database, and it calls the namespace guard
(``seed.common.seed_session``) before writing anything.

Write order
-----------
1. Every counterparty becomes a ``party`` row (upsert by ``normalized_name``,
   using the counterparty's ``key``: stable, lower-case, matching
   ``contract_repo.upsert_party``'s natural key).
2. Each (counterparty, playbook) pair that actually appears in
   ``decision_events`` or ``exceptions`` gets one synthetic ``contract`` row
   on first use (a real upload is out of scope here — task 5.2 builds the
   corpus of real synthetic contract files; this loader only needs something
   for ``decision_event.contract_id`` and ``playbook_exception.contract_id``,
   both ``NOT NULL``, to point at).
3. Each ``decision_events`` entry resolves its rule and position against the
   **version named by its own ``playbook_version`` field** (default ``"1.0"``)
   — the version in force on ``event_date``, not whatever the "current"
   published version happens to be when this loader runs — and is written as
   ``count`` separate ``decision_event`` rows (see ``seed.history.models``
   module docstring for why one file entry can be many database rows).
4. Each ``exceptions`` entry resolves the same way plus its ``approver_role``,
   and is written as exactly one ``playbook_exception`` row.

A playbook named in the file that is not in the database (``seed.playbooks.load``
has not been run), or a ``rule_key``/version/approver role the file names that
does not exist, stops the whole load with :class:`MissingReferenceError` —
there is no partial-playbook savepoint recovery here, unlike
``seed.playbooks.load``, because this file is one cohesive negotiation
history rather than several independent playbooks.
"""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.db.models.contract import Contract
from app.db.models.exception import PlaybookException
from app.db.models.nms import DecisionEvent
from app.db.repositories import authority_repo, contract_repo, playbook_repo
from seed.common import SeedError, SeedFileError, build_parser, data_dir, run, seed_session
from seed.common.yaml_loader import load_yaml_mapping
from seed.history.models import H1_2026_END, H1_2026_START, DecisionHistoryFile

DEFAULT_FILE_NAME = "decisions.yaml"

# (playbook_key, playbook_version, rule_key) -> (rule_id, version_id, {rung: position_id})
RuleCacheKey = tuple[str, str, str]
RuleCacheValue = tuple[uuid.UUID, uuid.UUID, dict[int, uuid.UUID]]


class MissingReferenceError(SeedError):
    """A playbook, version, rule or approver role the file needs is not in the database."""


# ---------------------------------------------------------------------------
# Load + validate the file (no database)
# ---------------------------------------------------------------------------


def load_valid_file(path: Path | str) -> DecisionHistoryFile:
    """Parse ``decisions.yaml`` and run its cross-checks.

    Pydantic catches shape and enumeration errors. This adds the checks that
    need more than one field: every ``counterparty_key`` a decision event or
    exception names must be one of the file's own counterparties, every date
    must fall in H1 2026, and counterparty keys must be unique. Raises
    :class:`SeedFileError` on any problem; reports every one found, not just
    the first.
    """
    file_path = Path(path)
    data = load_yaml_mapping(file_path)
    try:
        history = DecisionHistoryFile.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError, deliberately broad
        raise SeedFileError(file_path, f"invalid: {exc}") from exc

    errors: list[str] = []
    cp_keys = [c.key for c in history.counterparties]
    if len(set(cp_keys)) != len(cp_keys):
        dupes = {k for k in cp_keys if cp_keys.count(k) > 1}
        errors.append(f"duplicate counterparty key(s): {', '.join(sorted(dupes))}")
    cp_key_set = set(cp_keys)

    for i, entry in enumerate(history.decision_events):
        if entry.counterparty_key not in cp_key_set:
            errors.append(
                f"decision_events[{i}]: unknown counterparty_key {entry.counterparty_key!r}"
            )
        if not (H1_2026_START <= entry.event_date <= H1_2026_END):
            errors.append(
                f"decision_events[{i}]: event_date {entry.event_date} is outside H1 2026"
            )

    for i, entry in enumerate(history.exceptions):
        if entry.counterparty_key not in cp_key_set:
            errors.append(
                f"exceptions[{i}]: unknown counterparty_key {entry.counterparty_key!r}"
            )
        if not (H1_2026_START <= entry.requested_at <= H1_2026_END):
            errors.append(
                f"exceptions[{i}]: requested_at {entry.requested_at} is outside H1 2026"
            )
        if entry.decided_at is not None and entry.decided_at < entry.requested_at:
            errors.append(f"exceptions[{i}]: decided_at precedes requested_at")

    if errors:
        raise SeedFileError(file_path, "; ".join(errors))
    return history


# ---------------------------------------------------------------------------
# Reference-data resolution (playbook -> version -> rule -> position)
# ---------------------------------------------------------------------------


async def _resolve_rule(
    session: Any, playbook_key: str, playbook_version: str, rule_key: str
) -> RuleCacheValue:
    playbook = await playbook_repo.get_playbook_by_key(session, playbook_key)
    if playbook is None:
        raise MissingReferenceError(
            f"playbook {playbook_key!r} not found; run `python -m seed.playbooks.load` first"
        )
    versions = await playbook_repo.list_versions(session, playbook.id)
    version = next((v for v in versions if v.version == playbook_version), None)
    if version is None:
        raise MissingReferenceError(
            f"playbook {playbook_key!r} has no version {playbook_version!r}"
        )
    rules = await playbook_repo.list_rules_for_version(session, version.id)
    rule = next((r for r in rules if r.rule_key == rule_key), None)
    if rule is None:
        raise MissingReferenceError(
            f"playbook {playbook_key!r} version {playbook_version!r} has no rule {rule_key!r}"
        )
    positions = await playbook_repo.list_rule_positions(session, rule.id)
    by_rung = {p.rung: p.id for p in positions if p.rung is not None}
    return rule.id, version.id, by_rung


async def _rule_cache_get(
    session: Any,
    cache: dict[RuleCacheKey, RuleCacheValue],
    playbook_key: str,
    playbook_version: str,
    rule_key: str,
) -> RuleCacheValue:
    cache_key = (playbook_key, playbook_version, rule_key)
    if cache_key not in cache:
        cache[cache_key] = await _resolve_rule(session, playbook_key, playbook_version, rule_key)
    return cache[cache_key]


async def _get_or_create_contract(
    session: Any,
    cache: dict[tuple[str, str], uuid.UUID],
    history: DecisionHistoryFile,
    party_ids: dict[str, uuid.UUID],
    counterparty_key: str,
    playbook_key: str,
) -> uuid.UUID:
    cache_key = (counterparty_key, playbook_key)
    if cache_key in cache:
        return cache[cache_key]
    cp = history.counterparty(counterparty_key)
    assert cp is not None  # load_valid_file already checked this
    contract = Contract(
        title=f"{cp.display_name} — {playbook_key} (H1 2026 negotiation history)",
        object_key=f"seed/history/halcyon/{counterparty_key}/{playbook_key}.txt",
        source_format="docx",
        canonical_text=(
            f"Synthetic negotiation-history record for {cp.display_name} ({playbook_key}). "
            "No document body is stored here; see seed/history/data/halcyon/decisions.yaml."
        ),
        paper_origin="own",
        contract_type=playbook_key.removeprefix("halcyon-").replace("-", "_"),
        counterparty_id=party_ids[counterparty_key],
        status="executed",
        party_role="vendor",
        context=cp.context,
    )
    session.add(contract)
    await session.flush()
    cache[cache_key] = contract.id
    return contract.id


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


async def _write_decision_events(
    session: Any,
    history: DecisionHistoryFile,
    party_ids: dict[str, uuid.UUID],
    contract_cache: dict[tuple[str, str], uuid.UUID],
    rule_cache: dict[RuleCacheKey, RuleCacheValue],
) -> int:
    """Write every decision event entry, expanded by its ``count``. Returns rows written."""
    written = 0
    for entry in history.decision_events:
        rule_id, version_id, positions_by_rung = await _rule_cache_get(
            session, rule_cache, entry.playbook_key, entry.playbook_version, entry.rule_key
        )
        contract_id = await _get_or_create_contract(
            session, contract_cache, history, party_ids, entry.counterparty_key, entry.playbook_key
        )
        position_id = positions_by_rung.get(entry.rung)
        clause_type = entry.rule_key.split(".", 1)[0]
        for _ in range(entry.count):
            session.add(
                DecisionEvent(
                    contract_id=contract_id,
                    counterparty_id=party_ids[entry.counterparty_key],
                    clause_type=clause_type,
                    position_offered=entry.position_offered,
                    recommended_stance=entry.recommended_stance,
                    outcome=entry.outcome,
                    final_text=entry.final_text,
                    rule_id=rule_id,
                    rule_key=entry.rule_key,
                    position_id=position_id,
                    playbook_version_id=version_id,
                )
            )
            written += 1
    await session.flush()
    return written


async def _write_exceptions(
    session: Any,
    history: DecisionHistoryFile,
    party_ids: dict[str, uuid.UUID],
    contract_cache: dict[tuple[str, str], uuid.UUID],
    rule_cache: dict[RuleCacheKey, RuleCacheValue],
) -> int:
    written = 0
    for entry in history.exceptions:
        rule_id, _version_id, positions_by_rung = await _rule_cache_get(
            session, rule_cache, entry.playbook_key, entry.playbook_version, entry.rule_key
        )
        role = await authority_repo.get_approver_role_by_key(session, entry.approver_role)
        if role is None:
            raise MissingReferenceError(f"approver role {entry.approver_role!r} not found")
        contract_id = await _get_or_create_contract(
            session, contract_cache, history, party_ids, entry.counterparty_key, entry.playbook_key
        )
        session.add(
            PlaybookException(
                contract_id=contract_id,
                rule_id=rule_id,
                rule_key=entry.rule_key,
                position_id=positions_by_rung.get(entry.rung),
                zone=entry.zone,
                agreed_text=entry.agreed_text,
                parameter_values=entry.parameter_values,
                approver_role_id=role.id,
                approved_by=entry.approved_by,
                rationale=entry.rationale,
                give_get_obtained=entry.give_get_obtained,
                expires_at=entry.expires_at,
                status=entry.status,
            )
        )
        written += 1
    await session.flush()
    return written


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class HistoryLoadReport:
    dry_run: bool = False
    counterparties: int = 0
    decision_event_entries: int = 0  # file rows
    decision_event_rows: int = 0  # database rows written (entries expanded by `count`)
    exceptions: int = 0
    contracts: int = 0


async def run_load(history: DecisionHistoryFile, *, session: Any | None = None) -> HistoryLoadReport:
    """Write ``history`` to the database.

    With no ``session``, opens one through :func:`seed.common.seed_session`
    (which calls the namespace guard first) and commits it on a clean exit.
    Tests pass a mocked or in-memory ``session`` directly, bypassing the real
    connection and guard entirely — the orchestration below is the same
    either way.
    """
    if session is None:
        async with seed_session(dry_run=False) as real_session:
            return await _run_load_with_session(real_session, history)
    return await _run_load_with_session(session, history)


async def _run_load_with_session(session: Any, history: DecisionHistoryFile) -> HistoryLoadReport:
    party_ids: dict[str, uuid.UUID] = {}
    for cp in history.counterparties:
        party = await contract_repo.upsert_party(session, cp.key, cp.display_name)
        await session.flush()
        party_ids[cp.key] = party.id

    contract_cache: dict[tuple[str, str], uuid.UUID] = {}
    rule_cache: dict[RuleCacheKey, RuleCacheValue] = {}

    rows_written = await _write_decision_events(session, history, party_ids, contract_cache, rule_cache)
    exceptions_written = await _write_exceptions(session, history, party_ids, contract_cache, rule_cache)

    return HistoryLoadReport(
        dry_run=False,
        counterparties=len(history.counterparties),
        decision_event_entries=len(history.decision_events),
        decision_event_rows=rows_written,
        exceptions=exceptions_written,
        contracts=len(contract_cache),
    )


# ---------------------------------------------------------------------------
# --dry-run: file-only counts, no database
# ---------------------------------------------------------------------------


@dataclass
class DryRunCounts:
    counterparties: int = 0
    decision_event_entries: int = 0
    decision_event_rows: int = 0  # what a real load would write (entries expanded by `count`)
    exceptions: int = 0
    distinct_rule_keys: int = field(default=0)


def compute_dry_run_counts(history: DecisionHistoryFile) -> DryRunCounts:
    return DryRunCounts(
        counterparties=len(history.counterparties),
        decision_event_entries=len(history.decision_events),
        decision_event_rows=history.total_weighted_events(),
        exceptions=len(history.exceptions),
        distinct_rule_keys=len(
            {(e.playbook_key, e.rule_key) for e in history.decision_events}
            | {(e.playbook_key, e.rule_key) for e in history.exceptions}
        ),
    )


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _print_dry_run(path: Path, counts: DryRunCounts) -> None:
    print(f"{path}: dry run; nothing written")
    print(f"  counterparties: {counts.counterparties}")
    print(f"  decision_event_entries (file rows): {counts.decision_event_entries}")
    print(f"  decision_event_rows (a real load would write): {counts.decision_event_rows}")
    print(f"  exceptions: {counts.exceptions}")
    print(f"  distinct (playbook, rule_key) pairs: {counts.distinct_rule_keys}")


def _print_report(report: HistoryLoadReport) -> None:
    print(f"counterparties: {report.counterparties}")
    print(f"contracts created: {report.contracts}")
    print(
        f"decision_event rows: {report.decision_event_rows} "
        f"(from {report.decision_event_entries} file entries)"
    )
    print(f"exceptions: {report.exceptions}")
    print("RESULT: ok")


async def _main(args: argparse.Namespace) -> int:
    history = load_valid_file(args.file)
    if args.dry_run:
        counts = compute_dry_run_counts(history)
        _print_dry_run(args.file, counts)
        return 0
    report = await run_load(history)
    _print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Load the negotiation-history seed into the database. "
        "With --dry-run, only validates and counts; no database connection is made.",
        prog="python -m seed.history.load",
    )
    default_path = data_dir("history") / DEFAULT_FILE_NAME
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=default_path,
        help=f"decisions.yaml path (default: {default_path})",
    )
    return run(_main, parser, argv)


if __name__ == "__main__":
    raise SystemExit(main())
