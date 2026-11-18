"""Tests for ``seed.history.load`` (task 5.3).

All database access goes through the in-memory doubles in
``seed/tests/fixtures/fake_history_repo.py`` — nothing here opens a real
connection. ``seed.history.load`` imports ``playbook_repo``/``authority_repo``/
``contract_repo`` at module level, so a test monkeypatches those three names
on the ``load`` module to the fakes and calls ``load.run_load(history,
session=fake_session)`` directly, bypassing ``seed_session`` (and the real
namespace guard) entirely.

Scenarios: a full load (parties, lazily-created contracts, decision events
expanded by ``count``, exceptions, position resolution), each missing-reference
error (playbook, version, rule, approver role), and the file-level cross-checks
in ``load_valid_file`` (unknown counterparty, date outside H1 2026, duplicate
counterparty key, ``decided_at`` before ``requested_at``).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from fake_history_repo import make_fakes  # noqa: E402

from seed.common.errors import SeedFileError  # noqa: E402
from seed.history import load  # noqa: E402
from seed.history.models import (  # noqa: E402
    Counterparty,
    DecisionEventEntry,
    DecisionHistoryFile,
    ExceptionEntry,
)

SAAS = "halcyon-saas-msa-vendor"
DPA = "halcyon-dpa-processor"


def _counterparty(key: str = "acme-health", **overrides) -> Counterparty:
    base = dict(
        key=key,
        display_name="Acme Health",
        tier="tier_2",
        deal_value_band="mid",
        region="us",
        data_sensitivity="phi",
        regimes=["hipaa"],
        description="A fictional regional health system.",
    )
    base.update(overrides)
    return Counterparty.model_validate(base)


def _event(**overrides) -> DecisionEventEntry:
    base = dict(
        playbook_key=SAAS,
        playbook_version="1.0",
        rule_key="payment.late_fees",
        counterparty_key="acme-health",
        event_date=date(2026, 3, 1),
        outcome="accepted",
        position_offered="fallback_1",
        recommended_stance="balanced",
        category="late_fee_fallback1_accepted",
        count=1,
        final_text="Settled at 1.0% per month.",
    )
    base.update(overrides)
    return DecisionEventEntry.model_validate(base)


def _exception(**overrides) -> ExceptionEntry:
    base = dict(
        playbook_key=SAAS,
        playbook_version="1.0",
        rule_key="payment.late_fees",
        rung=1,
        counterparty_key="acme-health",
        zone="yellow",
        approver_role="deal_desk",
        approved_by="Deal Desk",
        rationale="Standard fallback acceptance.",
        agreed_text="1.0% per month late fee.",
        status="approved",
        requested_at=date(2026, 3, 1),
        decided_at=date(2026, 3, 3),
        expires_at=date(2027, 3, 3),
    )
    base.update(overrides)
    return ExceptionEntry.model_validate(base)


def _history(events=None, exceptions=None, counterparties=None) -> DecisionHistoryFile:
    return DecisionHistoryFile.model_validate(
        {
            "counterparties": [c.model_dump() for c in (counterparties or [_counterparty()])],
            "decision_events": [e.model_dump() for e in (events or [_event()])],
            "exceptions": [x.model_dump() for x in (exceptions or [_exception()])],
        }
    )


def _wire(db):
    """Build fakes and monkeypatch ``load``'s three repo imports to them."""
    db, session, fake_playbooks, fake_authority, fake_contracts = make_fakes(db)
    load.playbook_repo = fake_playbooks
    load.authority_repo = fake_authority
    load.contract_repo = fake_contracts
    return db, session


def _seeded_db():
    """A FakeHistoryDB with one playbook/version/rule/position and one role."""
    from fake_history_repo import FakeHistoryDB

    db = FakeHistoryDB()
    pb = db.add_playbook(SAAS)
    v10 = db.add_version(SAAS, "1.0")
    rule = db.add_rule(v10, "payment.late_fees")
    db.add_position(rule, 0, kind="preferred")
    db.add_position(rule, 1, kind="fallback")
    db.add_approver_role("deal_desk")
    return db, pb, v10, rule


# ---------------------------------------------------------------------------
# run_load: the full path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_load_writes_parties_contract_event_and_exception():
    db, pb, v10, rule = _seeded_db()
    _, session = _wire(db)

    history = _history()
    report = await load.run_load(history, session=session)

    assert report.counterparties == 1
    assert report.decision_event_entries == 1
    assert report.decision_event_rows == 1
    assert report.exceptions == 1
    assert report.contracts == 1  # one (counterparty, playbook) pair
    assert "acme-health" in db.parties

    decision_events = [o for o in db.added if type(o).__name__ == "DecisionEvent"]
    exceptions = [o for o in db.added if type(o).__name__ == "PlaybookException"]
    contracts = [o for o in db.added if type(o).__name__ == "Contract"]
    assert len(decision_events) == 1
    assert len(exceptions) == 1
    assert len(contracts) == 1

    event = decision_events[0]
    assert event.rule_id == rule.id
    assert event.playbook_version_id == v10.id
    assert event.position_id is not None  # rung 1 resolved to the fallback position
    assert event.contract_id == contracts[0].id
    assert event.counterparty_id == db.parties["acme-health"].id

    exception = exceptions[0]
    assert exception.rule_id == rule.id
    assert exception.approver_role_id == db.approver_roles["deal_desk"].id
    assert exception.contract_id == contracts[0].id  # same contract, reused


@pytest.mark.asyncio
async def test_decision_event_count_expands_to_that_many_rows():
    db, pb, v10, rule = _seeded_db()
    _, session = _wire(db)

    history = _history(events=[_event(count=7)])
    report = await load.run_load(history, session=session)

    assert report.decision_event_entries == 1
    assert report.decision_event_rows == 7
    decision_events = [o for o in db.added if type(o).__name__ == "DecisionEvent"]
    assert len(decision_events) == 7
    # Every expanded row carries its own id, but shares contract/rule/position.
    assert len({e.id for e in decision_events}) == 7


@pytest.mark.asyncio
async def test_same_counterparty_two_playbooks_gets_two_contracts():
    db, pb, v10, rule = _seeded_db()
    dpa_pb = db.add_playbook(DPA)
    dpa_v10 = db.add_version(DPA, "1.0")
    dpa_rule = db.add_rule(dpa_v10, "audit.customer_audit_rights")
    db.add_position(dpa_rule, 0, kind="preferred")
    _, session = _wire(db)

    history = _history(
        events=[
            _event(),
            _event(
                playbook_key=DPA,
                rule_key="audit.customer_audit_rights",
                position_offered="preferred",
                category="dpa_audit_standard",
            ),
        ]
    )
    report = await load.run_load(history, session=session)

    assert report.contracts == 2
    contracts = [o for o in db.added if type(o).__name__ == "Contract"]
    assert {c.contract_type for c in contracts} == {"saas_msa_vendor", "dpa_processor"}


@pytest.mark.asyncio
async def test_missing_rung_resolves_to_no_position_not_an_error():
    db, pb, v10, rule = _seeded_db()
    _, session = _wire(db)

    # rung 3 was never added to the fixture's rule.
    history = _history(events=[_event(position_offered="fallback_3")])
    report = await load.run_load(history, session=session)

    assert report.decision_event_rows == 1
    event = next(o for o in db.added if type(o).__name__ == "DecisionEvent")
    assert event.position_id is None


# ---------------------------------------------------------------------------
# Missing-reference errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_playbook_raises():
    db, pb, v10, rule = _seeded_db()
    _, session = _wire(db)
    history = _history(events=[_event(playbook_key="halcyon-nonexistent")])
    with pytest.raises(load.MissingReferenceError, match="halcyon-nonexistent"):
        await load.run_load(history, session=session)


@pytest.mark.asyncio
async def test_missing_version_raises():
    db, pb, v10, rule = _seeded_db()
    _, session = _wire(db)
    history = _history(events=[_event(playbook_version="9.9")])
    with pytest.raises(load.MissingReferenceError, match="9.9"):
        await load.run_load(history, session=session)


@pytest.mark.asyncio
async def test_missing_rule_key_raises():
    db, pb, v10, rule = _seeded_db()
    _, session = _wire(db)
    history = _history(events=[_event(rule_key="payment.taxes")])
    with pytest.raises(load.MissingReferenceError, match="payment.taxes"):
        await load.run_load(history, session=session)


@pytest.mark.asyncio
async def test_missing_approver_role_raises():
    db, pb, v10, rule = _seeded_db()
    _, session = _wire(db)
    history = _history(exceptions=[_exception(approver_role="cfo")])
    with pytest.raises(load.MissingReferenceError, match="cfo"):
        await load.run_load(history, session=session)


# ---------------------------------------------------------------------------
# load_valid_file cross-checks (no database; built from dicts, not files, to
# keep this fast — ``test_history_statistics.py`` exercises the real file)
# ---------------------------------------------------------------------------


def _write_and_load(tmp_path: Path, data: dict) -> DecisionHistoryFile:
    import yaml

    path = tmp_path / "decisions.yaml"
    path.write_text(yaml.safe_dump(data))
    return load.load_valid_file(path)


def _minimal_doc() -> dict:
    return {
        "counterparties": [_counterparty().model_dump()],
        "decision_events": [_event().model_dump()],
        "exceptions": [_exception().model_dump()],
    }


def test_load_valid_file_accepts_minimal_doc(tmp_path: Path):
    history = _write_and_load(tmp_path, _minimal_doc())
    assert history.counterparty_keys() == {"acme-health"}


def test_load_valid_file_rejects_unknown_counterparty(tmp_path: Path):
    doc = _minimal_doc()
    doc["decision_events"][0]["counterparty_key"] = "nobody"
    with pytest.raises(SeedFileError, match="unknown counterparty_key"):
        _write_and_load(tmp_path, doc)


def test_load_valid_file_rejects_date_outside_h1_2026(tmp_path: Path):
    doc = _minimal_doc()
    doc["decision_events"][0]["event_date"] = date(2026, 7, 1)
    with pytest.raises(SeedFileError, match="outside H1 2026"):
        _write_and_load(tmp_path, doc)


def test_load_valid_file_rejects_duplicate_counterparty_key(tmp_path: Path):
    doc = _minimal_doc()
    doc["counterparties"].append(_counterparty().model_dump())
    with pytest.raises(SeedFileError, match="duplicate counterparty key"):
        _write_and_load(tmp_path, doc)


def test_load_valid_file_rejects_decided_before_requested(tmp_path: Path):
    doc = _minimal_doc()
    doc["exceptions"][0]["requested_at"] = date(2026, 3, 10)
    doc["exceptions"][0]["decided_at"] = date(2026, 3, 1)
    with pytest.raises(SeedFileError, match="precedes"):
        _write_and_load(tmp_path, doc)


# ---------------------------------------------------------------------------
# --dry-run counts (file-only, no database)
# ---------------------------------------------------------------------------


def test_compute_dry_run_counts_weights_by_count_field():
    history = _history(events=[_event(count=1), _event(count=44), _event(count=20)])
    counts = load.compute_dry_run_counts(history)
    assert counts.counterparties == 1
    assert counts.decision_event_entries == 3
    assert counts.decision_event_rows == 65
    assert counts.exceptions == 1
