"""S6 Playbook bootstrap — batch LLM job (T-038).

Loads a corpus of contract clauses, groups them by clause_type, and uses the
Anthropic Message Batches API to extract preferred language + acceptable
variations for each type.  Creates PlaybookRule rows — with their
``preferred``/``acceptable_variant`` ``rule_position`` children — for clause
types not already present in the target draft version.

Seeding policy (SC-3, extended by task 4.11):
- Seeds a ``preferred`` ``rule_position`` row and ``acceptable_variant``
  ``rule_position`` rows ONLY. It never creates fallbacks, red lines or
  parameters — those need human judgement the mined sample can't supply.
- ``prohibited_terms`` is NOT mined from executed contracts; it comes from
  the template seed managed by humans post-bootstrap.
- Every rule bootstrap creates is stamped ``authored_by = "bootstrap"`` so a
  human reviewer can tell mined content from hand-authored content at a
  glance.
- Every rule gets a real ``issue_id`` and a ``{clause_type}.{issue_key}``
  ``rule_key`` (``playbook_plan.md`` section 3.4): the model picks the issue
  from the family's ``clause_issue`` rows, falling back to a per-family
  ``unclassified`` placeholder issue. See "Issue assignment" below.

Draft-only (task 4.11): bootstrap writes rules and positions into an
existing **draft** version of the playbook and never into a published one.
Unlike the versions API (task 4.8), which 409s on an *edit* to an existing
row under a published version, bootstrap has no specific version to edit —
it has to pick one. Rather than quietly creating a new draft on the
playbook's behalf (a version-lifecycle decision that belongs to the
versions API, task 4.8's ``create_draft``), bootstrap only ever looks for a
version that is *already* a draft and rejects with 409 if none exists. This
matches the task's "done when ... a test proves a published version is
rejected": the caller creates a draft first (``POST
.../playbook_versions/{id}/draft`` or equivalent), then calls bootstrap
again to seed it.
"""

from __future__ import annotations

import random
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.core.llm.schemas.playbook import PlaybookBootstrapOut
from app.db.models.clause import Clause
from app.db.models.playbook import PlaybookVersion
from app.db.models.taxonomy import ClauseIssue
from app.db.repositories import clause_repo, playbook_repo, taxonomy_repo

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_PATH = (
    Path(__file__).parent.parent.parent / "core" / "llm" / "prompts" / "playbook_bootstrap.md"
)
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

# Max clauses sampled per type and max chars per clause sent to the LLM.
_MAX_SAMPLES = 5
_MAX_CHARS = 1_000

# Who/what authored rules and change-log entries this job creates.
_AUTHORED_BY = "bootstrap"


# ---------------------------------------------------------------------------
# Issue assignment: rule_key = "{clause_type}.{issue_key}" (playbook_plan.md
# section 3.4), so a bootstrapped rule merges with / is overridden by a
# seeded rule for the same issue in ``routing.resolve`` (which merges by
# exact ``rule_key``).
#
# Strategy: each batch item lists the family's existing ``clause_issue``
# rows and asks the model to name the ONE issue the extracted language
# addresses (``issue_key``), or null if none clearly fits. The answer is only
# trusted if it is one of the listed keys. Otherwise — no confident match,
# a hallucinated key, or a family with no issues seeded yet — the rule is
# filed under a per-family placeholder issue ``unclassified`` (fetched, or
# created once per family). That keeps every bootstrapped rule on a real
# ``issue_id`` with a well-formed key, while making the unresolved cases
# easy to find (``rule_key LIKE '%.unclassified'``) for a human to re-file
# under the right issue before the draft is published.
#
# Known limitation: an ``unclassified`` rule never merges with a seeded
# rule, since no seeded rule uses that issue key. A family whose clause_type
# has no ``clause_family`` row at all cannot get an issue (FK), so it is
# skipped rather than written with an unqualified key.
# ---------------------------------------------------------------------------

_PLACEHOLDER_ISSUE_KEY = "unclassified"
_PLACEHOLDER_ISSUE_NAME = "Unclassified (bootstrap)"
_PLACEHOLDER_ISSUE_DESCRIPTION = (
    "Placeholder issue for playbook rules mined by bootstrap whose language "
    "could not be confidently matched to a specific issue in this family. "
    "Re-file such rules under the correct issue before publishing."
)


class _BootstrapIssueOut(PlaybookBootstrapOut):
    """``PlaybookBootstrapOut`` plus the issue the extracted language addresses.

    ``issue_key`` is optional with a null default so a response without it
    (or a test preset of the base model) is still valid — it then falls back
    to the placeholder issue.
    """

    issue_key: str | None = None


def _issue_instructions(issues: list[ClauseIssue]) -> str:
    """User-message suffix asking the model to classify the issue."""
    if not issues:
        return (
            "\n\nAlso return `issue_key` as null: no issues are defined for this "
            "clause type yet."
        )
    listing = "\n".join(f"- {i.key}: {i.name} — {i.description}" for i in issues)
    return (
        "\n\nAlso return `issue_key`: the key of the ONE issue below that the "
        "preferred language you extracted primarily addresses. Use a key exactly "
        "as listed. If none of them clearly fits, return null rather than "
        f"guessing.\n\nIssues for this clause type:\n{listing}"
    )


async def _placeholder_issue(session: AsyncSession, family_key: str) -> ClauseIssue | None:
    """Fetch or create the family's ``unclassified`` placeholder issue.
    Returns None if the family itself does not exist."""
    issue = await taxonomy_repo.get_clause_issue_by_key(
        session, family_key, _PLACEHOLDER_ISSUE_KEY
    )
    if issue is not None:
        return issue
    if await taxonomy_repo.get_clause_family(session, family_key) is None:
        return None
    return await taxonomy_repo.create_clause_issue(
        session,
        family_key=family_key,
        key=_PLACEHOLDER_ISSUE_KEY,
        name=_PLACEHOLDER_ISSUE_NAME,
        description=_PLACEHOLDER_ISSUE_DESCRIPTION,
    )


# ---------------------------------------------------------------------------
# Sampling: spread the sample across distinct contracts instead of taking
# whatever the first N rows happen to be (the old bug — see
# playbook_status.md: "samples at most 5 clauses per type ... the first N
# found" could draw all 5 samples from one or two contracts if those
# contracts repeat a clause_type, giving the LLM no real diversity).
# ---------------------------------------------------------------------------


def _sample_across_contracts(clauses: list[Clause], max_samples: int) -> list[Clause]:
    """Pick up to *max_samples* clauses for one clause_type, round-robin
    across distinct contracts in random order.

    Round 0 takes one clause from each contract (contracts visited in random
    order, so no single contract is systematically favoured); only once
    every contract has contributed one sample does round 1 start pulling a
    second clause from any contract. This maximises how many distinct
    contracts the LLM sees before it ever sees the same contract twice.
    """
    if len(clauses) <= max_samples:
        return list(clauses)

    by_contract: dict[uuid.UUID, list[Clause]] = {}
    for clause in clauses:
        by_contract.setdefault(clause.contract_id, []).append(clause)

    contract_order = list(by_contract.keys())
    random.shuffle(contract_order)

    samples: list[Clause] = []
    round_idx = 0
    while len(samples) < max_samples:
        added_this_round = False
        for contract_id in contract_order:
            bucket = by_contract[contract_id]
            if round_idx < len(bucket):
                samples.append(bucket[round_idx])
                added_this_round = True
                if len(samples) >= max_samples:
                    break
        if not added_this_round:
            break
        round_idx += 1

    return samples


# ---------------------------------------------------------------------------
# Draft-version resolution (task 4.11: never write to a published version)
# ---------------------------------------------------------------------------


async def _get_draft_version_or_409(
    session: AsyncSession, playbook_id: uuid.UUID
) -> PlaybookVersion:
    """Return the playbook's draft version, or 409 if it has none.

    Bootstrap never writes to a published version and never creates a draft
    on its own initiative — see the module docstring for why. A playbook may
    have at most one draft outstanding at a time in the current version
    lifecycle (task 4.8); if more than one somehow exists, the most recently
    created one is used.
    """
    versions = await playbook_repo.list_versions(session, playbook_id)
    drafts = [v for v in versions if v.status == "draft"]
    if not drafts:
        raise AppError(
            409,
            "no_draft_version",
            f"Playbook {playbook_id} has no draft version to bootstrap into. "
            "Create a draft version first; bootstrap never writes to a "
            "published version and will not create one for you.",
        )
    drafts.sort(key=lambda v: v.created_at)
    return drafts[-1]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_bootstrap(
    session: AsyncSession,
    playbook_id: uuid.UUID,
    contract_ids: list[uuid.UUID],
) -> int:
    """Seed *playbook_id*'s draft version with rules extracted from
    *contract_ids*.

    Skips clause types that already have a rule in the draft version
    (idempotent; also protects human edits made directly in the draft).

    Returns:
        Number of new PlaybookRule rows created.

    Raises:
        AppError: 404 if the playbook does not exist; 409 if the playbook
            has no draft version to write into.
    """
    pb = await playbook_repo.get_playbook(session, playbook_id)
    if pb is None:
        raise AppError(404, "not_found", f"Playbook {playbook_id} not found")

    if not contract_ids:
        return 0

    # Load all clauses for the corpus in one query.
    clauses = await clause_repo.get_clauses_for_contracts(session, contract_ids)
    if not clauses:
        return 0

    # Group by clause_type.
    by_type: dict[str, list[Clause]] = {}
    for clause in clauses:
        by_type.setdefault(clause.clause_type, []).append(clause)

    # Resolve the draft version before doing anything else that writes —
    # 404/409 here means no rule or position is ever created.
    draft = await _get_draft_version_or_409(session, playbook_id)

    # Skip types that already have a rule in this draft — protects human
    # edits and keeps the job idempotent per-version (task 1.2's
    # ``uq_playbook_rule_version_rule_key`` is scoped per version, not per
    # playbook, so the idempotency check must match).
    existing = await playbook_repo.list_rules_for_version(session, draft.id)
    existing_types = {r.clause_type for r in existing}
    new_types = {ct: cl for ct, cl in by_type.items() if ct not in existing_types}

    if not new_types:
        return 0

    # Build one batch item per new clause_type, sampled across contracts,
    # each listing the family's issues for the model to classify against.
    issues_by_type: dict[str, dict[str, ClauseIssue]] = {}
    items: list[dict] = []
    for clause_type, type_clauses in new_types.items():
        family_issues = [
            i
            for i in await taxonomy_repo.list_clause_issues(session, family_key=clause_type)
            if i.key != _PLACEHOLDER_ISSUE_KEY
        ]
        family_issues.sort(key=lambda i: i.key)
        if (
            not family_issues
            and await taxonomy_repo.get_clause_family(session, clause_type) is None
        ):
            # No clause_family row: no issue can be attached (FK), so no
            # well-formed rule_key either. Skip before spending an LLM call.
            continue
        issues_by_type[clause_type] = {i.key: i for i in family_issues}
        samples = _sample_across_contracts(type_clauses, _MAX_SAMPLES)
        clause_texts = "\n\n---\n\n".join(c.text[:_MAX_CHARS] for c in samples)
        items.append(
            {
                "id": clause_type,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Clause type: {clause_type}\n\n"
                            f"Analyze the following {len(samples)} sample(s) "
                            f"and extract preferred language and acceptable variations.\n\n"
                            f"{clause_texts}"
                            f"{_issue_instructions(family_issues)}"
                        ),
                    },
                ],
            }
        )

    if not items:
        return 0

    # Batch call — synchronous gateway (consistent with rest of codebase).
    results: dict[str, PlaybookBootstrapOut] = gateway.call_batch(
        task="playbook.bootstrap",
        items=items,
        response_model=_BootstrapIssueOut,
        cache_prefix="playbook_bootstrap",
    )

    # Persist rules and their preferred/acceptable_variant positions — use
    # the dict key (custom_id) as the authoritative clause_type so the fake
    # gateway's identical preset still creates distinct rules per type.
    created = 0
    for clause_type, parsed in results.items():
        # Trust the model's issue only if it is one we offered; otherwise
        # file under the family's placeholder (see the note at the top).
        offered = issues_by_type.get(clause_type, {})
        issue = offered.get(getattr(parsed, "issue_key", None) or "")
        if issue is None:
            issue = await _placeholder_issue(session, clause_type)
        if issue is None:
            # No clause_family row for this type: an issue (and so a
            # well-formed rule_key) is impossible. Skip rather than write an
            # unqualified key that could never merge correctly.
            continue
        rule = await playbook_repo.create_rule(
            session,
            playbook_id=playbook_id,
            clause_type=clause_type,
            playbook_version_id=draft.id,
            issue_id=issue.id,
            rule_key=f"{clause_type}.{issue.key}",
            authored_by=_AUTHORED_BY,
        )

        await playbook_repo.create_rule_position(
            session,
            rule_id=rule.id,
            kind="preferred",
            label="Preferred (bootstrap)",
            language=parsed.preferred_language,
            zone="green",
        )
        for idx, variation in enumerate(parsed.acceptable_variations or [], start=1):
            await playbook_repo.create_rule_position(
                session,
                rule_id=rule.id,
                kind="acceptable_variant",
                label=f"Acceptable variant {idx} (bootstrap)",
                language=variation,
                zone="green",
            )

        created += 1

    await session.commit()
    return created
