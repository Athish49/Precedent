"""Tests for ``seed.playbooks.load`` (task 2.1).

All database access goes through the in-memory doubles in
``seed/tests/fixtures/fake_repo.py`` — nothing here opens a real connection.
``seed.playbooks.load`` imports ``playbook_repo``/``taxonomy_repo`` at module
level, so a test monkeypatches those two names on the ``load`` module to the
fakes and calls ``load.run_load(seed, session=fake_session)`` directly,
bypassing ``seed_session`` (and the real namespace guard) entirely.

Five scenarios, matching the task's "Done when": upsert, the published-version
guard, rollback-and-continue on an error in one playbook, archiving of a
playbook no longer in the seed, and the missing-reference-data error for an
``agreement_type``/``clause_family`` row that migration 010 should have
provided.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from fake_repo import FakeDB, FakePlaybookRepo, make_fakes  # noqa: E402

from seed.playbooks import load  # noqa: E402
from seed.playbooks.models import (  # noqa: E402
    ApproverRole,
    Authority,
    ChangeLogEntry,
    ContextDimension,
    DimensionValue,
    LoadedPlaybook,
    LoadedRule,
    LoadedVersion,
    PlaybookHeader,
    PlaybookVersionHeader,
    Position,
    RecommendedPosition,
    Rule,
    SeedDirectory,
    Taxonomy,
    VersionChangeSet,
)

FAKE_ROOT = Path("/fake/halcyon")

# ---------------------------------------------------------------------------
# Builders: construct a SeedDirectory in memory, no YAML files involved.
# ---------------------------------------------------------------------------


def _version_header(
    version: str = "1.0", status: str = "published", **overrides
) -> PlaybookVersionHeader:
    base = {
        "version": version,
        "status": status,
        "effective_from": date(2026, 1, 15),
        "change_summary": "Initial version.",
        "created_by": "Senior Commercial Counsel",
        "approved_by": "General Counsel",
    }
    base.update(overrides)
    return PlaybookVersionHeader.model_validate(base)


def _header(
    key: str,
    *,
    practice_area: str = "saas_msa",
    owner_role: str = "commercial_counsel",
    parent: str | None = None,
    version: PlaybookVersionHeader | None = None,
) -> PlaybookHeader:
    return PlaybookHeader.model_validate(
        {
            "key": key,
            "name": f"Playbook {key}",
            "practice_area": practice_area,
            "layer": "agreement",
            "party_role": "vendor",
            "paper_scope": "both",
            "jurisdiction": "US",
            "precedence": 10,
            "owner_role": owner_role,
            "parent": parent,
            "review_cadence_days": 90,
            "description": "A test playbook.",
            "version": version or _version_header(),
            "rule_files": ["rules.yaml"],
        }
    )


def _rule(
    rule_key: str = "limitation_of_liability.cap_amount",
    *,
    title: str = "Aggregate liability cap",
    language: str = "Liability is capped at twelve months of Fees.",
    approver_role: str = "commercial_counsel",
    objections: list | None = None,
    extra_positions: list[Position] | None = None,
) -> Rule:
    positions = [
        Position.model_validate(
            {
                "kind": "preferred",
                "label": "Preferred",
                "zone": "green",
                "summary": "The preferred position.",
                "language": language,
            }
        ),
        Position.model_validate(
            {
                "kind": "fallback",
                "rung": 1,
                "label": "Fallback",
                "zone": "yellow",
                "approver_role": approver_role,
                "summary": "A fallback position.",
                "language": "A fallback version of the clause.",
            }
        ),
    ]
    if extra_positions:
        positions.extend(extra_positions)
    return Rule.model_validate(
        {
            "rule_key": rule_key,
            "title": title,
            "required": True,
            "risk_weight": 8,
            "negotiable": True,
            "position_summary": "Summary of the position.",
            "risk_rationale": "First reason it matters. Second reason it matters.",
            "detection_guidance": "Look for the relevant wording.",
            "authored_by": "Senior Commercial Counsel",
            "approved_by": "General Counsel",
            "last_reviewed_at": date(2026, 1, 10),
            "positions": positions,
            "objections": objections or [],
            "test_cases": [
                {
                    "name": "Compliant case",
                    "expected_outcome": "compliant",
                    "expected_zone": "green",
                    "sample_text": "Sample contract language.",
                }
            ],
        }
    )


def _loaded_playbook(header: PlaybookHeader, rules: list[Rule]) -> LoadedPlaybook:
    pb = LoadedPlaybook(
        directory=FAKE_ROOT / "playbooks" / header.key,
        header=header,
        header_source=FAKE_ROOT / "playbooks" / header.key / "playbook.yaml",
    )
    source = pb.directory / "rules.yaml"
    pb.rules = [
        LoadedRule(rule=r, source=source, index=i, playbook_dir=header.key)
        for i, r in enumerate(rules)
    ]
    pb.rule_files = [source]
    return pb


def _taxonomy(family: str = "limitation_of_liability", issue: str = "cap_amount") -> Taxonomy:
    return Taxonomy.model_validate(
        {
            "expected_families": [family],
            "issues": [
                {
                    "family": family,
                    "key": issue,
                    "name": "Aggregate liability cap",
                    "description": "The overall monetary limit on liability.",
                    "detection_hints": "Look for a cap.",
                }
            ],
        }
    )


def _authority(role: str = "commercial_counsel") -> Authority:
    return Authority(
        context_dimensions=[
            ContextDimension(
                key="region",
                name="Region",
                value_type="enum",
                source="upload",
                values=[DimensionValue(value="us", definition="United States")],
            )
        ],
        roles=[
            ApproverRole(
                key=role, name="Commercial Counsel", function="legal", level=2, default_sla_hours=24
            )
        ],
        global_red_lines=[],
        escalation_policies=[],
    )


def _seed(
    playbooks: list[LoadedPlaybook],
    *,
    taxonomy=None,
    authority=None,
    versions: list[LoadedVersion] | None = None,
) -> SeedDirectory:
    return SeedDirectory(
        root=FAKE_ROOT,
        taxonomy=taxonomy if taxonomy is not None else _taxonomy(),
        authority=authority if authority is not None else _authority(),
        playbooks=playbooks,
        versions=versions if versions is not None else [],
    )


def _loaded_version(
    playbook_key: str,
    *,
    based_on_version: str = "1.0",
    version: str = "1.1",
    status: str = "published",
    rules: list[Rule] | None = None,
) -> LoadedVersion:
    version_set = VersionChangeSet.model_validate(
        {
            "playbook_key": playbook_key,
            "based_on_version": based_on_version,
            "version": _version_header(version=version, status=status).model_dump(),
            "changes": [
                {
                    "field_path": "limitation_of_liability.cap_amount.positions[1]",
                    "change_type": "modified",
                    "old_value": "12 months of Fees",
                    "new_value": "6 months of Fees",
                    "reason": "Tightened the fallback cap.",
                },
                {
                    "field_path": "limitation_of_liability.cap_amount.parameters.cap_multiplier",
                    "change_type": "added",
                    "new_value": 6,
                    "reason": "New parameter introduced in this version.",
                },
            ],
            "rules": [r.model_dump() for r in (rules or [_rule()])],
        }
    )
    return LoadedVersion(
        version_set=version_set,
        source=FAKE_ROOT / "playbooks" / playbook_key / "versions" / f"{playbook_key}_{version}.yaml",
    )


def _db_with_references(
    *, agreement_types: set[str] | None = None, clause_families: set[str] | None = None
) -> FakeDB:
    db = FakeDB()
    db.agreement_types = agreement_types if agreement_types is not None else {"saas_msa"}
    db.clause_families = (
        clause_families if clause_families is not None else {"limitation_of_liability"}
    )
    return db


def _patch_repos(
    monkeypatch: pytest.MonkeyPatch, db: FakeDB, playbook_repo=None, taxonomy_repo=None
):
    _, session, default_playbook_repo, taxonomy_repo_fake = make_fakes(db)
    monkeypatch.setattr(load, "playbook_repo", playbook_repo or default_playbook_repo)
    monkeypatch.setattr(load, "taxonomy_repo", taxonomy_repo or taxonomy_repo_fake)
    return session


# ---------------------------------------------------------------------------
# 1. Upsert: a second load updates the existing rows instead of duplicating them
# ---------------------------------------------------------------------------


async def test_upsert_updates_existing_rows_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)

    # The first version is a draft, so the published-version guard does not
    # apply and a second load can freely rewrite it.
    header = _header("halcyon-saas-msa-vendor", version=_version_header(status="draft"))
    seed_v1 = _seed([_loaded_playbook(header, [_rule(title="Original title")])])

    report1 = await load.run_load(seed_v1, session=session)
    assert report1.ok
    assert len(db.playbooks) == 1
    assert len(db.rules) == 1
    rule_id_v1 = next(iter(db.rules))
    assert db.rules[rule_id_v1].title == "Original title"
    assert len(db.positions) == 2

    # Second load: same playbook key, same rule_key, different content.
    seed_v2 = _seed(
        [_loaded_playbook(header, [_rule(title="Updated title", language="Updated language.")])]
    )
    report2 = await load.run_load(seed_v2, session=session)

    assert report2.ok
    assert len(db.playbooks) == 1  # no duplicate playbook row
    assert len(db.rules) == 1  # the same rule row was updated, not duplicated
    assert next(iter(db.rules)) == rule_id_v1
    assert db.rules[rule_id_v1].title == "Updated title"
    assert len(db.positions) == 2  # old positions were replaced, not appended to
    assert any(p.language == "Updated language." for p in db.positions.values())


async def test_upsert_resolves_objection_recommended_position_within_playbook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second rule's objection can recommend a position on the first rule."""
    db = _db_with_references(clause_families={"limitation_of_liability", "payment"})
    session = _patch_repos(monkeypatch, db)
    taxonomy = Taxonomy.model_validate(
        {
            "expected_families": ["limitation_of_liability", "payment"],
            "issues": [
                {
                    "family": "limitation_of_liability",
                    "key": "cap_amount",
                    "name": "Cap",
                    "description": "Cap.",
                    "detection_hints": "x",
                },
                {
                    "family": "payment",
                    "key": "payment_terms",
                    "name": "Payment terms",
                    "description": "Terms.",
                    "detection_hints": "x",
                },
            ],
        }
    )
    other_rule = _rule(
        rule_key="payment.payment_terms",
        title="Payment terms",
        objections=[
            {
                "objection": "Net 30 is too fast.",
                "their_rationale": "Cash flow.",
                "response": "We can discuss.",
                "talking_points": ["Point one."],
                "recommended_position": RecommendedPosition(
                    rule_key="limitation_of_liability.cap_amount", rung=1
                ),
                "frequency": "common",
            }
        ],
    )
    header = _header("halcyon-saas-msa-vendor")
    seed = _seed([_loaded_playbook(header, [_rule(), other_rule])], taxonomy=taxonomy)

    report = await load.run_load(seed, session=session)

    assert report.ok, report.failed
    objection = next(iter(db.objections.values()))
    assert objection.recommended_position_id is not None
    fallback_position = next(
        p for p in db.positions.values() if p.rung == 1 and p.kind == "fallback"
    )
    assert objection.recommended_position_id == fallback_position.id


# ---------------------------------------------------------------------------
# 2. Published-version guard
# ---------------------------------------------------------------------------


async def test_published_version_is_never_modified(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    header = _header("halcyon-saas-msa-vendor")  # version header defaults to status="published"

    published = await load.run_load(
        _seed([_loaded_playbook(header, [_rule(title="Original title")])]), session=session
    )
    assert published.ok
    assert db.playbooks["halcyon-saas-msa-vendor"].current_version_id is not None
    original_rule = next(iter(db.rules.values()))
    assert original_rule.title == "Original title"

    # Loading the SAME version string again with DIFFERENT rule content must
    # stop with an error and change nothing.
    changed = await load.run_load(
        _seed([_loaded_playbook(header, [_rule(title="Edited after publishing")])]), session=session
    )

    assert not changed.ok
    [result] = changed.playbooks
    assert result.key == "halcyon-saas-msa-vendor"
    assert "published" in result.error.lower()
    assert "new version" in result.error.lower()
    # Nothing changed: still exactly the one, original rule.
    assert len(db.rules) == 1
    assert next(iter(db.rules.values())).title == "Original title"


async def test_published_version_reload_with_identical_content_is_a_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    header = _header("halcyon-saas-msa-vendor")
    seed = _seed([_loaded_playbook(header, [_rule(title="Same title")])])

    first = await load.run_load(seed, session=session)
    assert first.ok
    rule_count_after_first = len(db.rules)

    # Re-loading the identical directory is not an error.
    second = await load.run_load(seed, session=session)
    assert second.ok
    assert len(db.rules) == rule_count_after_first
    assert len(db.versions) == 1  # no second version row was created


# ---------------------------------------------------------------------------
# 2b. Change-log entries (versions/<playbook>_<version>.yaml): written once
#     when a version is newly created, never duplicated on a later run.
# ---------------------------------------------------------------------------


async def test_change_log_entries_are_not_duplicated_on_a_second_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the bug found during the live-DB load (task 5.1):
    `_load_one_playbook` wrote every `version_set.changes` entry unconditionally,
    even when the version it belonged to already existed in the database, so
    running the loader twice duplicated every `playbook_change_log` row."""
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    key = "halcyon-saas-msa-vendor"
    header = _header(key)  # current version "1.0", published
    loaded_version = _loaded_version(key, based_on_version="1.0", version="1.1")
    seed = _seed([_loaded_playbook(header, [_rule()])], versions=[loaded_version])

    first = await load.run_load(seed, session=session)
    assert first.ok, first.failed
    assert len(db.change_log) == 2  # the two changes in version 1.1
    assert len(db.versions) == 2  # 1.0 (header) + 1.1 (version file)
    [result] = first.playbooks
    assert result.counts.change_log_entries == 2

    # Re-loading the identical directory (both versions already exist) must
    # not write the change-log entries again.
    second = await load.run_load(seed, session=session)
    assert second.ok, second.failed
    assert len(db.change_log) == 2  # unchanged: not duplicated to 4
    assert len(db.versions) == 2  # no new version rows either
    [result2] = second.playbooks
    assert result2.counts.change_log_entries == 0  # nothing newly written this run


async def test_change_log_entries_written_for_a_genuinely_new_version_on_a_later_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A version that is new in a later run (not present on the first run)
    still gets its change-log entries written — the fix must gate on "this
    version is newly created in this run", not suppress change-log writes
    altogether on a second run."""
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    key = "halcyon-saas-msa-vendor"
    header = _header(key)
    seed_v1 = _seed([_loaded_playbook(header, [_rule()])], versions=[])

    first = await load.run_load(seed_v1, session=session)
    assert first.ok, first.failed
    assert len(db.change_log) == 0
    assert len(db.versions) == 1  # just the header's "1.0"

    # Second run adds a new version file ("1.1") that did not exist before.
    loaded_version = _loaded_version(key, based_on_version="1.0", version="1.1")
    seed_v2 = _seed([_loaded_playbook(header, [_rule()])], versions=[loaded_version])
    second = await load.run_load(seed_v2, session=session)

    assert second.ok, second.failed
    assert len(db.change_log) == 2  # the new version's two changes were written
    assert len(db.versions) == 2

    # A third run against the same (now unchanged) seed must not duplicate them.
    third = await load.run_load(seed_v2, session=session)
    assert third.ok, third.failed
    assert len(db.change_log) == 2


# ---------------------------------------------------------------------------
# 2c. Version lifecycle: a newer published version supersedes the older one
#     (playbook_plan.md section 3.3), on a fresh load and on a reload.
# ---------------------------------------------------------------------------


def _versions_by_string(db: FakeDB, key: str) -> dict:
    pb_id = db.playbooks[key].id
    return {v.version: v for v in db.versions.values() if v.playbook_id == pb_id}


def _loaded_version_effective(key: str, effective_from: date) -> LoadedVersion:
    lv = _loaded_version(key, based_on_version="1.0", version="1.1")
    lv.version_set.version.effective_from = effective_from
    return lv


async def test_newer_published_version_supersedes_the_base_version_on_fresh_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the loader inserted 1.1 as published without superseding
    1.0, leaving two published versions (seen live on halcyon-saas-msa-vendor
    and halcyon-dpa-processor)."""
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    key = "halcyon-saas-msa-vendor"
    seed = _seed(
        [_loaded_playbook(_header(key), [_rule()])],
        versions=[_loaded_version_effective(key, date(2026, 7, 1))],
    )

    report = await load.run_load(seed, session=session)
    assert report.ok, report.failed

    versions = _versions_by_string(db, key)
    assert versions["1.0"].status == "superseded"
    assert versions["1.0"].effective_to.date() == date(2026, 7, 1)
    assert versions["1.1"].status == "published"
    assert versions["1.1"].effective_to is None
    assert db.playbooks[key].current_version_id == versions["1.1"].id
    assert [v.version for v in versions.values() if v.status == "published"] == ["1.1"]

    # Idempotent: reloading the identical seed is a no-op (the superseded 1.0
    # is frozen like a published version, not rewritten or reset to published).
    rules_before = dict(db.rules)
    again = await load.run_load(seed, session=session)
    assert again.ok, again.failed
    versions = _versions_by_string(db, key)
    assert len(versions) == 2
    assert versions["1.0"].status == "superseded"
    assert versions["1.0"].effective_to.date() == date(2026, 7, 1)
    assert versions["1.1"].status == "published"
    assert db.playbooks[key].current_version_id == versions["1.1"].id
    assert db.rules.keys() == rules_before.keys()


async def test_reload_repairs_a_database_with_two_published_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live state: both 1.0 and 1.1 stored as published. A reload of the
    same seed marks 1.0 superseded without touching either version's rules."""
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    key = "halcyon-saas-msa-vendor"
    seed = _seed(
        [_loaded_playbook(_header(key), [_rule()])],
        versions=[_loaded_version_effective(key, date(2026, 7, 1))],
    )
    assert (await load.run_load(seed, session=session)).ok

    # Recreate the buggy live state the old loader produced.
    versions = _versions_by_string(db, key)
    versions["1.0"].status = "published"
    versions["1.0"].effective_to = None
    db.playbooks[key].current_version_id = versions["1.0"].id
    rules_before = {rid: dict(vars(r)) for rid, r in db.rules.items()}
    positions_before = set(db.positions)

    report = await load.run_load(seed, session=session)
    assert report.ok, report.failed
    versions = _versions_by_string(db, key)
    assert versions["1.0"].status == "superseded"
    assert versions["1.0"].effective_to.date() == date(2026, 7, 1)
    assert versions["1.1"].status == "published"
    assert db.playbooks[key].current_version_id == versions["1.1"].id
    # (list attributes are children the fake repo attaches on read, not columns)
    diffs = {
        (rid, k)
        for rid, r in db.rules.items()
        for k, v in vars(r).items()
        if not isinstance(v, list) and rules_before[rid].get(k) != v
    }
    assert diffs == set()
    assert set(db.positions) == positions_before  # children not rewritten
    assert len(db.change_log) == 2  # not duplicated


async def test_supersede_repair_does_not_bypass_the_published_content_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a published version's seed content was edited, the guard still
    stops that playbook and its savepoint (status repair included) rolls back."""
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    key = "halcyon-saas-msa-vendor"
    versions_files = [_loaded_version_effective(key, date(2026, 7, 1))]
    assert (
        await load.run_load(
            _seed([_loaded_playbook(_header(key), [_rule()])], versions=versions_files),
            session=session,
        )
    ).ok
    versions = _versions_by_string(db, key)
    versions["1.0"].status = "published"
    versions["1.0"].effective_to = None

    edited = _seed(
        [_loaded_playbook(_header(key), [_rule(title="Edited after publishing")])],
        versions=versions_files,
    )
    report = await load.run_load(edited, session=session)
    assert not report.ok
    assert "published" in report.playbooks[0].error.lower()
    assert _versions_by_string(db, key)["1.0"].status == "published"


async def test_newer_version_added_on_a_later_run_supersedes_the_stored_published_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    key = "halcyon-saas-msa-vendor"
    header = _header(key)
    assert (await load.run_load(_seed([_loaded_playbook(header, [_rule()])]), session=session)).ok
    v10 = _versions_by_string(db, key)["1.0"]
    assert v10.status == "published"
    assert db.playbooks[key].current_version_id == v10.id

    seed_v2 = _seed(
        [_loaded_playbook(header, [_rule()])],
        versions=[_loaded_version_effective(key, date(2026, 7, 1))],
    )
    assert (await load.run_load(seed_v2, session=session)).ok
    versions = _versions_by_string(db, key)
    assert versions["1.0"].status == "superseded"
    assert versions["1.0"].effective_to.date() == date(2026, 7, 1)
    assert versions["1.1"].status == "published"
    assert db.playbooks[key].current_version_id == versions["1.1"].id


def test_plan_version_statuses_without_a_newer_version_keeps_the_base_current() -> None:
    [only] = load.plan_version_statuses(_version_header(), [])
    assert (only.version, only.status, only.effective_to, only.current) == (
        "1.0",
        "published",
        None,
        True,
    )


def test_plan_version_statuses_ignores_a_newer_draft() -> None:
    plan = load.plan_version_statuses(
        _version_header(), [_loaded_version("halcyon-a", status="draft")]
    )
    by_version = {p.version: p for p in plan}
    assert by_version["1.0"].status == "published" and by_version["1.0"].current
    assert by_version["1.1"].status == "draft" and not by_version["1.1"].current


# ---------------------------------------------------------------------------
# 3. Rollback on error, continue with the rest
# ---------------------------------------------------------------------------


class _ExplodingPlaybookRepo(FakePlaybookRepo):
    """Raises while writing any position labelled "BOOM", to simulate an
    unexpected failure partway through one playbook's content."""

    async def create_rule_position(self, session, rule_id, kind, label, *args, **kwargs):
        if label == "BOOM":
            raise RuntimeError("simulated failure while writing a position")
        return await super().create_rule_position(session, rule_id, kind, label, *args, **kwargs)


async def test_error_in_one_playbook_rolls_back_only_that_playbook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_with_references()
    exploding_repo = _ExplodingPlaybookRepo(db)
    session = _patch_repos(monkeypatch, db, playbook_repo=exploding_repo)

    bad_header = _header("halcyon-bad")
    bad_rule = _rule(title="Bad rule")
    bad_rule.positions[1].label = "BOOM"  # trips the simulated failure
    good_header = _header("halcyon-good")
    good_rule = _rule(title="Good rule")

    seed = _seed(
        [
            _loaded_playbook(bad_header, [bad_rule]),  # processed first
            _loaded_playbook(good_header, [good_rule]),
        ]
    )

    report = await load.run_load(seed, session=session)

    assert not report.ok
    by_key = {r.key: r for r in report.playbooks}
    assert by_key["halcyon-bad"].ok is False
    assert "simulated failure" in by_key["halcyon-bad"].error
    assert by_key["halcyon-good"].ok is True

    # The failing playbook's header still exists (written before the
    # per-playbook savepoint) but has no version or rules: the savepoint
    # rolled those back.
    assert "halcyon-bad" in db.playbooks
    assert db.playbooks["halcyon-bad"].current_version_id is None
    assert not any(v.playbook_id == db.playbooks["halcyon-bad"].id for v in db.versions.values())

    # The other playbook's content is intact.
    good_pb = db.playbooks["halcyon-good"]
    assert good_pb.current_version_id is not None
    assert any(r.playbook_id == good_pb.id and r.title == "Good rule" for r in db.rules.values())


# ---------------------------------------------------------------------------
# 4. Archiving a playbook no longer in the seed directory
# ---------------------------------------------------------------------------


async def test_playbook_missing_from_seed_directory_is_archived_not_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)

    # A playbook already in "the database" from a previous load, whose key
    # will not appear in this run's seed directory.
    stale_repo = make_fakes(db)[2]
    await stale_repo.upsert_playbook(
        session,
        "halcyon-old-template",
        {
            "name": "Old template",
            "practice_area": "saas_msa",
            "precedence": 0,
            "layer": "agreement",
            "party_role": "vendor",
            "paper_scope": "both",
            "jurisdiction": "US",
            "business_unit": None,
            "owner_role_id": None,
            "applies_when": None,
            "description": None,
            "status": "active",
            "review_cadence_days": None,
            "next_review_at": None,
        },
    )

    header = _header("halcyon-saas-msa-vendor")
    seed = _seed([_loaded_playbook(header, [_rule()])])

    report = await load.run_load(seed, session=session)

    assert report.ok
    assert report.archived == ["halcyon-old-template"]
    assert db.playbooks["halcyon-old-template"].status == "archived"
    assert db.playbooks["halcyon-saas-msa-vendor"].status == "active"  # untouched, still active


# ---------------------------------------------------------------------------
# 5. Missing reference data (agreement_type / clause_family from migration 010)
# ---------------------------------------------------------------------------


async def test_missing_clause_family_stops_with_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_with_references(clause_families=set())  # "limitation_of_liability" is missing
    session = _patch_repos(monkeypatch, db)
    header = _header("halcyon-saas-msa-vendor")
    seed = _seed([_loaded_playbook(header, [_rule()])])

    with pytest.raises(load.MissingReferenceDataError) as excinfo:
        await load.run_load(seed, session=session)

    message = str(excinfo.value).lower()
    assert "migration 010" in message
    assert "limitation_of_liability" in message
    # Nothing was written: the check runs before any write.
    assert db.playbooks == {}
    assert db.approver_roles == {}


async def test_missing_agreement_type_stops_with_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_with_references(agreement_types=set())  # "saas_msa" is missing
    session = _patch_repos(monkeypatch, db)
    header = _header("halcyon-saas-msa-vendor", practice_area="saas_msa")
    seed = _seed([_loaded_playbook(header, [_rule()])])

    with pytest.raises(load.MissingReferenceDataError) as excinfo:
        await load.run_load(seed, session=session)

    message = str(excinfo.value).lower()
    assert "migration 010" in message
    assert "saas_msa" in message
    assert db.playbooks == {}


# ---------------------------------------------------------------------------
# Bonus: --only and the file-only dry-run counter
# ---------------------------------------------------------------------------


async def test_only_limits_which_playbook_is_written_but_archiving_still_runs_on_the_full_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_with_references()
    session = _patch_repos(monkeypatch, db)
    rule_key = "limitation_of_liability.cap_amount"
    seed = _seed(
        [
            _loaded_playbook(_header("halcyon-a"), [_rule(rule_key=rule_key)]),
            _loaded_playbook(_header("halcyon-b"), [_rule(rule_key=rule_key)]),
        ]
    )

    report = await load.run_load(seed, session=session, only={"halcyon-a"})

    assert [r.key for r in report.playbooks] == ["halcyon-a"]
    # Both playbook headers exist (the header pre-pass is not filtered by
    # --only), but only "halcyon-a" got a version/rules written.
    assert "halcyon-a" in db.playbooks and "halcyon-b" in db.playbooks
    assert db.playbooks["halcyon-a"].current_version_id is not None
    assert db.playbooks["halcyon-b"].current_version_id is None


def test_dry_run_counts_are_computed_from_files_only_no_only_filter() -> None:
    header_a = _header("halcyon-a")
    header_b = _header("halcyon-b")
    seed = _seed(
        [
            _loaded_playbook(header_a, [_rule()]),
            _loaded_playbook(header_b, [_rule(rule_key="limitation_of_liability.cap_amount")]),
        ]
    )

    counts = load.compute_dry_run_counts(seed)
    assert counts.playbooks == 2
    assert counts.rules == 2
    assert counts.positions == 4  # two positions per rule

    filtered = load.compute_dry_run_counts(seed, only={"halcyon-a"})
    assert filtered.playbooks == 1
    assert filtered.rules == 1
    # Shared counts are never filtered by --only.
    assert filtered.roles == counts.roles
