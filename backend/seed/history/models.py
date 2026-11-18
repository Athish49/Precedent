"""Models for ``decisions.yaml`` (task 5.3).

One file, three lists: ``counterparties`` (the 15 fictional negotiating
parties, "Outcomes" context per ``playbook_implementation.md`` section 2.2),
``decision_events`` (append-only negotiation outcomes — the seed-side
equivalent of ``decision_event``) and ``exceptions`` (approved yellow-zone
departures — the seed-side equivalent of ``playbook_exception``).

**The ``count`` field.** ``decision_event`` has no multiplicity column: one
row is one negotiated outcome on one contract. The change logs this file
must reproduce (``playbooks/data/halcyon/versions/*_1_1.yaml``, task 3.14)
cite population sizes in the dozens ("72 late-fee negotiations", "61
initial-term negotiations", ...) that, summed across every cited rule_key,
run past 500 — far more than the 150 decision events task 5.3 asks this file
to hold. ``DecisionEventEntry.count`` (default 1) is a seed-file-only
multiplier: one YAML entry with ``count: 44`` stands for 44 identical,
already-closed real negotiations the statistic lumps together, so the file
stays at exactly 150 *entries* while still reproducing every cited N and k
through weighted counting (``seed/tests/test_history_statistics.py``). A
real load (not run by this task) replicates such an entry into ``count``
separate ``decision_event`` rows — see ``seed.history.load.iter_db_rows``.
This is a judgment call flagged in task 5.3's report: the alternative (one
row per cited negotiation) would need roughly 3-4x the mandated 150 events.

**The ``category`` field.** A free-text, seed-only tag (not a
``decision_event`` column) that names which statistic an entry feeds, so the
reproducibility proof matches by intent instead of re-deriving it from
``outcome``/``position_offered`` text. It is not persisted on load.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------

# playbook_implementation.md section 2.2.
CounterpartyTier = Literal["tier_1", "tier_2", "tier_3"]
DealValueBand = Literal["standard", "mid", "enterprise", "strategic"]
DataSensitivity = Literal["none", "personal_data", "phi", "special_category"]
Region = Literal["us", "eu", "uk", "other"]
Regime = Literal["hipaa", "gdpr"]

# app/db/models/nms.py: ck_decision_event_outcome.
Outcome = Literal["pending", "accepted", "rejected", "countered"]
# app/services/redline/stance.py: light | balanced | firm.
RecommendedStance = Literal["light", "balanced", "firm"]
# app/db/models/exception.py: requested -> approved / rejected / expired.
ExceptionStatus = Literal["requested", "approved", "rejected", "expired"]
ExceptionZone = Literal["yellow", "red"]

H1_2026_START = dt.date(2026, 1, 1)
H1_2026_END = dt.date(2026, 6, 30)

# --------------------------------------------------------------------------
# Field types (same conventions as seed/playbooks/models.py)
# --------------------------------------------------------------------------

Text = Annotated[str, StringConstraints(min_length=1)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
PlaybookKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")]
# A counterparty's key: slug-cased like a playbook key (hyphens), not an
# underscore-cased `Key` like `category`/`approver_role` (there is no dotted
# family.issue structure to a counterparty name).
CounterpartyKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")]
RuleKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")]
# "preferred" (rung 0) or "fallback_<n>" (app/db/models/redline.py: ck_redline_position).
PositionOffered = Annotated[str, StringConstraints(pattern=r"^(preferred|fallback_[0-9]+)$")]


def position_rung(position_offered: str) -> int:
    """0 for ``"preferred"``, else the integer after ``fallback_``."""
    if position_offered == "preferred":
        return 0
    return int(position_offered.removeprefix("fallback_"))


class HistoryModel(BaseModel):
    """Base for every ``decisions.yaml`` model: unknown keys are an error."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------
# counterparties
# --------------------------------------------------------------------------


class Counterparty(HistoryModel):
    """One fictional negotiating party (``playbook_implementation.md`` section 1:
    synthetic content only — no real company names)."""

    key: CounterpartyKey
    display_name: Text
    tier: CounterpartyTier
    deal_value_band: DealValueBand
    region: Region
    data_sensitivity: DataSensitivity
    regimes: list[Regime] = Field(default_factory=list)
    description: Text

    @property
    def context(self) -> dict[str, Any]:
        """The ``contract.context`` JSONB shape (``playbook_implementation.md`` 2.2)."""
        return {
            "deal_value_band": self.deal_value_band,
            "counterparty_tier": self.tier,
            "data_sensitivity": self.data_sensitivity,
            "region": self.region,
            "regimes": list(self.regimes),
        }


# --------------------------------------------------------------------------
# decision_events
# --------------------------------------------------------------------------


class DecisionEventEntry(HistoryModel):
    """One ``decisions.yaml`` entry; becomes ``count`` ``decision_event`` rows on load."""

    playbook_key: PlaybookKey
    playbook_version: Text = "1.0"  # the version in force when the negotiation closed
    rule_key: RuleKey
    counterparty_key: CounterpartyKey
    event_date: dt.date
    outcome: Outcome
    position_offered: PositionOffered
    recommended_stance: RecommendedStance
    category: Key  # statistics tag (seed-only; see module docstring)
    count: Annotated[int, Field(ge=1, le=100)] = 1
    final_text: Text | None = None

    @property
    def rung(self) -> int:
        return position_rung(self.position_offered)


# --------------------------------------------------------------------------
# exceptions
# --------------------------------------------------------------------------


class ExceptionEntry(HistoryModel):
    """One approved (usually) departure from a rule's preferred position.

    Mirrors ``playbook_exception`` (task 1.3; ``app/db/models/exception.py``).
    Unlike decision events, exceptions are not weighted: each entry is one row.
    """

    playbook_key: PlaybookKey
    playbook_version: Text = "1.0"
    rule_key: RuleKey
    rung: Annotated[int, Field(ge=0)]
    counterparty_key: CounterpartyKey
    zone: ExceptionZone
    approver_role: Key
    approved_by: Text
    rationale: Text
    agreed_text: Text
    give_get_obtained: Text | None = None
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    status: ExceptionStatus
    requested_at: dt.date
    decided_at: dt.date | None = None
    expires_at: dt.date | None = None


# --------------------------------------------------------------------------
# Top-level file
# --------------------------------------------------------------------------


class DecisionHistoryFile(HistoryModel):
    """``history/data/halcyon/decisions.yaml``."""

    counterparties: Annotated[list[Counterparty], Field(min_length=1)]
    decision_events: Annotated[list[DecisionEventEntry], Field(min_length=1)]
    exceptions: Annotated[list[ExceptionEntry], Field(min_length=1)]

    def counterparty(self, key: str) -> Counterparty | None:
        return next((c for c in self.counterparties if c.key == key), None)

    def counterparty_keys(self) -> set[str]:
        return {c.key for c in self.counterparties}

    def total_weighted_events(self) -> int:
        """Sum of ``count`` across every decision event (what a real load writes)."""
        return sum(e.count for e in self.decision_events)


# --------------------------------------------------------------------------
# Containers
# --------------------------------------------------------------------------


@dataclass
class LoadedHistory:
    """``decisions.yaml`` loaded and cross-checked."""

    file: DecisionHistoryFile
    source: Path


__all__ = [
    "H1_2026_END",
    "H1_2026_START",
    "Counterparty",
    "DecisionEventEntry",
    "DecisionHistoryFile",
    "ExceptionEntry",
    "HistoryModel",
    "LoadedHistory",
    "position_rung",
]
