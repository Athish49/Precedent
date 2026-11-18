"""LLM output schema for S2 Layer 2 contract analysis (T-042; task 4.4).

Task 4.4 (``playbook_implementation.md``) changed what Layer 2 asks the model
for: instead of a single playbook-wide "preferred language" comparison, the
model receives — per clause — the full resolved-rule family for that clause's
``clause_type`` (every rule_key sharing it, e.g. ``limitation_of_liability``
carries ``cap_amount``, ``cap_carve_outs``, ``consequential_damages_exclusion``
and ``data_breach_super_cap`` as separate rules) with each rule's title,
summary, positions (labels), parameters (extraction hints) and *semantic*
red-line tests (``playbook_plan.md`` section 3.7 — ``phrase``/``regex``/
``parameter`` red lines are evaluated deterministically by Layer 1 / the zone
evaluator, never by the model).

For each rule in a clause's family the model returns one ``RuleExtractionOut``:
which position the text matches, extracted parameter values (each with a
verbatim supporting quote), and a yes/no judgment with a quote for each
semantic red line. This extraction is *not* the final zone — Layer 2
(``layer2_content.py``) feeds it to ``evaluate_finding`` (task 4.3's zone
evaluator); the model never assigns red/yellow/green itself.

``ClauseFlagOut`` is unchanged in shape but narrower in scope: ``non_standard``
and ``deviation`` are no longer requested from the model — those outcomes now
come from the evaluator's zone decision on a ``RuleExtractionOut``. The model
still free-assesses ``high_risk``, ``vague`` and (own-paper only)
``inconsistent``, exactly as before, including for ungoverned clauses (empty
rule family) on the counterparty path.

``ContractAnalysisOut.global_red_lines`` (bug 2b fix): playbook- and
global-scope red lines whose ``condition_type`` is ``semantic`` (e.g.
``global-governing-law-outside-lists`` in ``authority.yaml``) are never tied
to one clause's rule family, so they cannot be asked for per-clause like a
rule's own semantic red lines. Instead this is a *document-level* judgment —
asked once per ``call_structured``/``call_batch`` item alongside the
per-clause items, covering every clause text that particular call saw — and
reuses ``SemanticRedLineOut``'s shape (``red_line_key``/``triggered``/
``quote``) since the judgment itself is identical in kind, just scoped to the
whole prompt's clauses instead of one clause's rule.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClauseFlagOut(BaseModel):
    """A free-standing risk/vagueness/inconsistency flag for one clause.

    Unlike a ``RuleExtractionOut``, this is not matched against any playbook
    rule — it is the model's own-judgment flag, assessed for every clause
    (governed or not). ``offending_quote`` is a verbatim excerpt from the
    clause text; Layer 2 computes contract-level char offsets from it
    deterministically rather than trusting model-produced positions.
    """

    flag_type: Literal["high_risk", "vague", "inconsistent"]
    severity: Literal["low", "medium", "high"]
    detail: str
    offending_quote: str | None = None


class ExtractedPositionOut(BaseModel):
    """Which rung of a rule's position ladder the clause text matches.

    ``position_label`` must be one of the verbatim ``label`` values offered
    for this rule (``RulePositionResponse.label``) and is required whenever
    ``match_kind != "none"`` — it is how ``evaluate_finding`` looks up the
    matched ``rule_position`` row (and hence its zone, rung and approver).
    """

    match_kind: Literal["preferred", "acceptable_variant", "fallback", "none"]
    position_label: str | None = None
    quote: str | None = None


class ExtractedParameterOut(BaseModel):
    """One extracted value for a rule's parameter, with its supporting quote.

    ``value`` is the raw extracted representation (e.g. "18 months",
    "2x annual fees", "Delaware") — ``evaluate_finding`` / ``zone_for_parameter``
    (task 4.3) are responsible for parsing it against the parameter's
    ``value_type`` and comparing it to ``green_limit``/``yellow_limit``. The
    model is never asked to classify the zone itself.
    """

    parameter_key: str
    value: str
    quote: str


class SemanticRedLineOut(BaseModel):
    """A yes/no judgment for one rule's semantic red line (``condition_type ==
    "semantic"``; ``playbook_plan.md`` section 3.7). ``phrase``/``regex``/
    ``parameter`` red lines are structural and never appear here."""

    red_line_key: str
    triggered: bool
    quote: str | None = None


class RuleExtractionOut(BaseModel):
    """Extraction result for one resolved rule against one clause.

    ``rule_key`` identifies which rule in the clause's family this result is
    for (echoes the ``rule_key`` the prompt gave the model for that rule).
    """

    rule_key: str
    position: ExtractedPositionOut
    parameters: list[ExtractedParameterOut] = Field(default_factory=list)
    red_lines: list[SemanticRedLineOut] = Field(default_factory=list)


class ClauseAnalysisItem(BaseModel):
    """LLM analysis result for a single clause: one ``RuleExtractionOut`` per
    rule in the clause's resolved family, plus free-standing risk/vagueness
    flags. Ungoverned clauses (empty family) have ``rule_extractions == []``
    but may still carry ``flags``."""

    clause_id: str
    rule_extractions: list[RuleExtractionOut] = Field(default_factory=list)
    flags: list[ClauseFlagOut] = Field(default_factory=list)


class ContractAnalysisOut(BaseModel):
    """Full LLM analysis for a contract (or one batch of it — see
    ``layer2_content._run_batches``) — one item per clause submitted, plus
    (bug 2b) document-level judgments for any playbook/global-scope semantic
    red lines offered to this call."""

    items: list[ClauseAnalysisItem]
    global_red_lines: list[SemanticRedLineOut] = Field(default_factory=list)
