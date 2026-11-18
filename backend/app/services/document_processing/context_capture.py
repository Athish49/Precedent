"""Contract type and context capture (task 4.1).

Four pieces of logic, all in one module because they share the same lookup
tables and the same tolerance for those tables being unpopulated
(``playbook_implementation.md`` section 4.1, item 6 — ``context_dimension``
is seed-or-user data and may have zero rows):

1. ``validate_contract_type`` / ``validate_party_role`` / ``validate_context``
   — used by the upload route and the repository PATCH route to turn a bad
   value into ``AppError(400, ...)`` before anything is persisted.
2. ``classify_contract_type`` — the one new structured LLM call (fast tier,
   task key ``contract_type_classify``), used by document processing when
   the caller did not supply ``contract_type``.
3. ``derive_regimes`` — deterministic keyword rules, no model call.
4. ``derive_deal_value_band`` — reads the band boundaries from the
   ``context_dimension`` row for ``deal_value_band`` when it exists and is
   well-formed, else falls back to the hardcoded defaults from
   ``playbook_implementation.md`` section 2.2.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.core.llm import gateway
from app.core.llm.schemas.classification import ContractTypeClassification
from app.db.models.taxonomy import AgreementType, ContextDimension

# ---------------------------------------------------------------------------
# Party role — a small fixed set (``app/db/models/contract.py`` docstring),
# not backed by a lookup table, so it is validated with a plain constant.
# ---------------------------------------------------------------------------

VALID_PARTY_ROLES: frozenset[str] = frozenset({"vendor", "customer", "mutual"})


def validate_party_role(party_role: str) -> None:
    if party_role not in VALID_PARTY_ROLES:
        raise AppError(
            400,
            "invalid_party_role",
            f"party_role must be one of {sorted(VALID_PARTY_ROLES)!r}, got {party_role!r}",
        )


# ---------------------------------------------------------------------------
# agreement_type — validation and the candidate list fed to the classifier.
#
# ``agreement_type`` holds both real contract types (``kind='agreement'``:
# nda, saas_msa, dpa, vendor_msa) and two other kinds that are not something
# an uploaded *contract* is typed as: ``baseline`` (the company-wide
# default, never an individual contract) and ``regime`` (hipaa/gdpr, which
# attach as overlays via ``context.regimes``, not as ``contract_type``).
# Both ``contract_type`` validation and classification are scoped to
# ``kind='agreement'`` for this reason (judgment call — the task text says
# "validate against agreement_type keys" without naming the ``kind``
# filter).
# ---------------------------------------------------------------------------


async def list_classifiable_agreement_types(session: AsyncSession) -> list[AgreementType]:
    result = await session.execute(select(AgreementType).where(AgreementType.kind == "agreement"))
    return list(result.scalars().all())


async def validate_contract_type(session: AsyncSession, contract_type: str) -> None:
    candidates = await list_classifiable_agreement_types(session)
    valid_keys = {c.key for c in candidates}
    if contract_type not in valid_keys:
        raise AppError(
            400,
            "invalid_contract_type",
            f"contract_type must be one of {sorted(valid_keys)!r}, got {contract_type!r}",
        )


# ---------------------------------------------------------------------------
# context_dimension — validation. Table may be entirely empty (seed not
# loaded yet) or may be missing rows for some keys (user-supplied context
# keys the seed hasn't caught up with); both are treated leniently per
# item 6: with no dimensions defined at all, skip validation entirely; with
# some dimensions defined, only the keys that have a matching dimension row
# are checked, everything else passes through as given.
# ---------------------------------------------------------------------------


def _allowed_values(dimension: ContextDimension) -> set[str] | None:
    """Return the set of allowed value strings for *dimension*, or ``None``
    if ``dimension.values`` is not in a shape this code can interpret
    (lenient fallback — an unrecognised shape skips validation rather than
    raising).
    """
    values = dimension.values
    if isinstance(values, dict):
        return set(values.keys())
    if isinstance(values, list):
        allowed: set[str] = set()
        for item in values:
            if isinstance(item, str):
                allowed.add(item)
            elif isinstance(item, dict):
                key = item.get("value") or item.get("key")
                if isinstance(key, str):
                    allowed.add(key)
        return allowed
    return None


async def validate_context(session: AsyncSession, context: dict[str, Any]) -> None:
    result = await session.execute(select(ContextDimension))
    dimensions = {d.key: d for d in result.scalars().all()}
    if not dimensions:
        # No dimensions defined anywhere — accept the context as given.
        return

    for key, value in context.items():
        if key == "deal_value":
            # Raw numeric input used to derive deal_value_band; not itself
            # a context dimension.
            continue
        dimension = dimensions.get(key)
        if dimension is None:
            # This key isn't a known dimension yet — accept as given.
            continue
        allowed = _allowed_values(dimension)
        if allowed is None:
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if candidate not in allowed:
                raise AppError(
                    400,
                    "invalid_context_value",
                    f"{key} value {candidate!r} is not one of {sorted(allowed)!r}",
                )


# ---------------------------------------------------------------------------
# Classification — one structured LLM call, fast tier, new prompt file.
# ---------------------------------------------------------------------------

_PROMPT_PATH = (
    Path(__file__).parent.parent.parent / "core" / "llm" / "prompts" / "contract_type_classify.md"
)
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_TASK = "contract_type_classify"

# Confidence threshold: below this, leave contract_type null rather than
# store a guess (task 4.1 item 2: "leave it null if confidence is low
# (define a reasonable confidence threshold)" — 0.6 is the threshold chosen
# here; it is above a coin flip but does not demand near-certainty, since
# false negatives (null) are cheap and false positives feed a stale type
# into playbook resolution).
CONFIDENCE_THRESHOLD = 0.6

_EXCERPT_CHARS = 3000


async def classify_contract_type(session: AsyncSession, title: str, text_excerpt: str) -> str | None:
    """Classify the document's contract type from its title and the first
    3,000 characters of its canonical text, with one structured LLM call.

    Returns the classified ``agreement_type`` key, or ``None`` if there are
    no classifiable candidates, the model could not decide, the model
    returned a key outside the candidate set, or confidence is below
    :data:`CONFIDENCE_THRESHOLD`.
    """
    candidates = await list_classifiable_agreement_types(session)
    if not candidates:
        return None

    candidate_lines = "\n".join(f"- {c.key}: {c.name}" for c in candidates)
    user_content = (
        f"Title: {title}\n\n"
        f"Candidate contract types:\n{candidate_lines}\n\n"
        f"Document excerpt (first {_EXCERPT_CHARS} characters):\n"
        f"{text_excerpt[:_EXCERPT_CHARS]}"
    )

    result: ContractTypeClassification = gateway.call_structured(
        task=_TASK,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_model=ContractTypeClassification,
    )

    valid_keys = {c.key for c in candidates}
    if result.contract_type not in valid_keys:
        return None
    if result.confidence < CONFIDENCE_THRESHOLD:
        return None
    return result.contract_type


# ---------------------------------------------------------------------------
# Regimes — deterministic keyword rules, no model call (task 4.1 item 3).
# ---------------------------------------------------------------------------

_HIPAA_PHRASES = (
    "protected health information",
    "business associate agreement",
    "business associate",
    "covered entity",
)
_HIPAA_WORD_RE = re.compile(r"\bphi\b", re.IGNORECASE)

_GDPR_CORE_RE = re.compile(r"\bgdpr\b|general data protection regulation", re.IGNORECASE)


def derive_regimes(text: str) -> list[str]:
    """Deterministic regulatory-regime detection from contract text.

    - ``hipaa``: the text mentions PHI (as a standalone word, not a
      substring of another word) or business-associate/covered-entity
      terms.
    - ``gdpr``: the text mentions GDPR *and* uses both controller and
      processor language. Requiring all three (judgment call — the task
      text, "gdpr if it mentions GDPR, controller and processor language",
      is read as one combined condition rather than three independent
      triggers) avoids flagging gdpr on a document that merely uses
      "processor" in an unrelated, e.g. hardware, sense.
    """
    lowered = text.lower()
    regimes: list[str] = []

    if _HIPAA_WORD_RE.search(lowered) or any(phrase in lowered for phrase in _HIPAA_PHRASES):
        regimes.append("hipaa")

    if (
        _GDPR_CORE_RE.search(lowered)
        and "controller" in lowered
        and "processor" in lowered
    ):
        regimes.append("gdpr")

    return regimes


# ---------------------------------------------------------------------------
# deal_value_band — read boundaries from context_dimension, else the
# documented defaults (task 4.1 item 4; playbook_implementation.md
# section 2.2).
# ---------------------------------------------------------------------------

# (band_key, lower_bound_inclusive_or_None, upper_bound_exclusive_or_None)
_DEFAULT_DEAL_VALUE_BANDS: tuple[tuple[str, float | None, float | None], ...] = (
    ("standard", None, 100_000.0),
    ("mid", 100_000.0, 500_000.0),
    ("enterprise", 500_000.0, 1_500_000.0),
    ("strategic", 1_500_000.0, None),
)


def _band_boundaries_from_dimension(
    dimension: ContextDimension | None,
) -> tuple[tuple[str, float | None, float | None], ...] | None:
    """Parse ``values`` on a ``deal_value_band`` ``context_dimension`` row
    into boundaries, expecting each entry to look like
    ``{"min": <number or null>, "max": <number or null>}``. Returns
    ``None`` (fall back to the hardcoded defaults) if the row is absent or
    not in this shape — the exact seeded shape is not fixed by
    ``playbook_plan.md`` section 3.11 ("Allowed values with definitions,
    e.g. band boundaries in dollars"), so this is a lenient, defensive
    parse rather than a hard schema.
    """
    if dimension is None or not isinstance(dimension.values, dict) or not dimension.values:
        return None

    boundaries: list[tuple[str, float | None, float | None]] = []
    for band_key, definition in dimension.values.items():
        if not isinstance(definition, dict):
            return None
        lo = definition.get("min")
        hi = definition.get("max")
        if lo is not None and not isinstance(lo, (int, float)):
            return None
        if hi is not None and not isinstance(hi, (int, float)):
            return None
        boundaries.append((band_key, lo, hi))

    if not boundaries:
        return None
    return tuple(boundaries)


def _band_for_value(
    value: float, boundaries: tuple[tuple[str, float | None, float | None], ...]
) -> str | None:
    for band_key, lo, hi in boundaries:
        if lo is not None and value < lo:
            continue
        if hi is not None and value >= hi:
            continue
        return band_key
    return None


async def derive_deal_value_band(session: AsyncSession, deal_value: float | int | None) -> str | None:
    """Derive the ``deal_value_band`` for a supplied deal value.

    Reads boundaries from the ``context_dimension`` row keyed
    ``deal_value_band`` when it exists and parses cleanly; otherwise falls
    back to the hardcoded defaults from ``playbook_implementation.md``
    section 2.2 (judgment call resolving an apparent tension between task
    4.1 items 4 and 6 — see the module report for the reasoning: item 4
    explicitly says to hardcode the documented defaults as a fallback
    "since the table may be empty", which is read as the concrete
    resolution for this one derivation, while item 6's general "skip band
    derivation" when no dimensions are defined is read as governing
    *validation*, not this fallback).
    """
    if deal_value is None:
        return None

    result = await session.execute(
        select(ContextDimension).where(ContextDimension.key == "deal_value_band")
    )
    dimension = result.scalar_one_or_none()
    boundaries = _band_boundaries_from_dimension(dimension) or _DEFAULT_DEAL_VALUE_BANDS
    return _band_for_value(float(deal_value), boundaries)
