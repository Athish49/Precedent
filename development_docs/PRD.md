# Product Requirements Document — Precedent

## 1. Vision

Precedent is a personal portfolio project and AI-native **contract intelligence platform**: it ingests contracts, reviews them against a firm's playbook, generates surgical redlines with rationale, drafts language, answers questions, tracks obligations and renewals, and reports portfolio-level risk. It targets parity with the *core* capabilities of enterprise CLM/redlining tools (Ironclad, Luminance, Workday/Evisort, Sirion) while running entirely on free-tier cloud infrastructure.

The differentiator is **honest, deterministic-first engineering**: LLMs are used only where semantic understanding is genuinely required; every structural operation is deterministic code. This keeps the system fast, cheap, explainable, and — importantly for a portfolio piece — a demonstration of *judgment* about when AI is and isn't the right tool.

## 2. Users & context

Since there is no auth or multi-user (see Non-Goals), there is a single implicit user: an **in-house counsel / legal ops persona** operating on their organization's contracts. All data belongs to one notional organization. Use cases are framed from that persona's needs:

- *"Review this incoming counterparty contract against our positions and mark it up."*
- *"Where does this draft deviate from our playbook, and how badly?"*
- *"Draft a mutual indemnification clause in our house style."*
- *"What's our liability cap in the Acme MSA?"* (natural-language Q&A)
- *"Which contracts auto-renew in the next 60 days, and are any non-compliant?"*
- *"Show me portfolio risk across all active contracts."*

## 3. Feature suites (scope for the backend build)

Each suite maps to one or more services (see Architecture.md). All are **in scope** for the backend.

### 3.1 Contract review & redlining (S1, S2, S3)
- Deterministic ingestion: PDF/DOCX → clauses with character offsets + ~50 metadata fields + clause-type tags.
- Issue detection: missing required clauses and phrase/regex red lines (deterministic), position matching, parameter extraction, semantic red lines and non-standard/high-risk/vague/inconsistent language (LLM extraction), per-clause + per-contract risk scoring (deterministic, severity-weighted, normalised to 0–1).
- Every governed finding cites its playbook rule and carries a **zone** — green, yellow or red — assigned by deterministic code from the extracted facts, never by the model.
- Paper-origin-aware analysis: own paper → standard analysis; counterparty paper → deviation-vs-playbook analysis (plus risk/vague detection).
- Redline generation: preferred-position redline as surgical tracked changes, alternatives taken from the playbook's fallback ladder (the model adapts defined terms; it does not invent positions), plain-language explanation, counterparty-ready comment grounded in the playbook's objection responses, deterministic rationale field. Stance modes (Light/Balanced/Firm). Fallback toggle that steps one rung at a time. On-demand multi-pass refinement.
- Character-level citations traceable to source text on every flag and redline.

### 3.2 Playbook & standards (S6)

The playbook is a structured, versioned policy dataset. Every rule is a record a lawyer can read and the review pipeline can execute, and every finding, redline and approval cites the exact rule, position and version that produced it.

Design principles:

1. **Data, not prose.** Thresholds are numbers, red lines are testable conditions, and approvers are roles.
2. **Positions are a ladder.** A rule has one preferred position and an ordered set of fallbacks, each with its own approval level.
3. **Context changes the answer.** Deal value, data sensitivity, region and counterparty tier can change which rung is allowed and who approves.
4. **Three zones.** Every finding is green, yellow or red. The zone decides routing; the numeric score is for reporting.
5. **Layered.** A company baseline, an agreement playbook and regulatory overlays merge into one resolved rule set.
6. **Immutable once published.** A review pins the playbook versions it ran against, so results are reproducible.
7. **Testable.** Each rule carries example clauses with expected outcomes, so a change can be regression-tested before it is published.
8. **Closed loop.** Every negotiated outcome records the rule and rung, so the data shows which fallbacks are used and which positions are out of step.

Capabilities:

- **Taxonomy.** Clause families (the canonical clause types) and, inside each, the issues that are actually negotiated. Rules attach to issues.
- **Playbook header.** Agreement type, layer (base, agreement, overlay), party role (vendor, customer, mutual), paper scope, jurisdiction, owner and review cadence.
- **Rules.** Per issue: position summary, risk rationale, required flag, risk weight (1–10), negotiability, default zone and detection guidance.
- **Position ladder.** Preferred language, ordered fallback rungs with zone, approver, usage conditions and give-get, plus acceptable variants the other side may propose.
- **Parameters.** Structured numeric limits (preferred value, green limit, yellow limit) with per-context overrides.
- **Red lines.** Phrase, regex, parameter and semantic conditions at rule, playbook and global scope; `block` or `escalate`. Phrase matches ignore negated wording.
- **Objections and dependencies.** Anticipated counterparty objections with sendable responses and talking points; links between rules that trade against or require each other.
- **Test cases.** Sample clauses with expected outcome and zone, including traps.
- **Context and authority.** Deal-context dimensions, approver roles and an escalation matrix with time limits.
- **Resolution.** Deterministic: baseline + the agreement playbook matching type, party role and paper scope + **all** overlays whose conditions match the deal context, merged by rule key and precedence. Replaces practice-area routing.
- **Versioning and audit.** Edits happen in a draft; publishing requires a change summary, an approver and a passing run of the version's test cases (95% by default). Published versions are immutable; a change log records every rule-level change with its reason.
- **Self-service CRUD** over playbooks, rules and all rule children, on draft versions.
- **LLM bootstrap.** Mines preferred language and acceptable variants from executed agreements into a draft version. It never creates fallbacks, red lines or parameters; those are authored.
- **Outcomes.** Approved exceptions and decision events are recorded per rule and rung, and reported back to the playbook owner.

Seed content is separate from the product. A demonstration playbook for a fictional healthcare SaaS vendor (Halcyon Care, Inc.: 7 playbooks, 130 rules) lives in `backend/seed/` and is optional; the platform runs with no playbook loaded.

### 3.3 Drafting (S4)
- Cost-tiered cascade: playbook lookup → frequency-tracker reuse → LLM (only when both miss). The playbook step resolves the rule set for the request's contract type, party role and deal context and returns the preferred (rung 0) language.
- Modes: single-clause draft/rewrite, first-draft document from template, precedent-matched drafting (vector search + style-matched generation), memo/letter drafting, novel-clause generation.

### 3.4 Document intelligence (S5)
- Risk-aware contract summarization (grounded on S1 metadata + S2 risk flags).
- Redline-thread summarization.
- Natural-language Q&A over the current document with character-level citations (reads the clause array directly — no vector RAG for a single doc).
- Easy Prompt (NL → structured legal prompt, routed into S3/S4).
- Chat2 Research (web search synthesized with contract context).
- Deterministic clause-navigation index.

### 3.5 Repository & search (S7)
- Central contract repository (cloud object storage = source of truth; metadata in Postgres).
- Each contract records its type, the organization's party role and its deal context (deal value band, counterparty tier, data sensitivity, region, regulatory regimes), supplied at upload or derived, and editable afterwards.
- Full-text search (Postgres `tsvector`), faceted metadata filtering, amendment/version parent-child links, redline-history index.
- Smart Search: one LLM call translates NL → structured filters + optional semantic query; execution is deterministic.
- Version-aware storage powering the Version Comparison workflow and the shared diff engine.

### 3.6 Agentic review workflows (Review Pipeline + Autonomous Review Trigger)
- Event-triggered, **code-orchestrated** pipeline: S1 → S6 → S2 → S3, then a deterministic three-zone gate.
- The gate is driven by the worst zone, not an aggregate score: none or green → auto-apply; yellow → `needs_approval`, routed to the approver named on the matched position or else by the escalation matrix; red → escalate. A redline quality-check failure always escalates. A `block` red line cannot be approved below the top legal role.
- Each review run records the playbook versions it was pinned to.
- "Autonomous" = event-driven, not LLM-directed. Code controls all flow. **Zero true agents.**

### 3.7 Negotiation memory (NMS)
- Append-only decision log (recommended stance, position offered, accept/reject outcome, final agreed text) keyed by normalized counterparty + clause type, and recording the playbook rule, ladder rung and playbook version behind each offer.
- Accepting a yellow rung creates a playbook exception awaiting the named approver.
- Counterparty patterns derived at read time (GROUP BY), injected into S3 before its LLM call.

### 3.8 Obligation & monitoring (S8)
- LLM obligation extraction once at ingest (grounded on S1 metadata).
- Single daily deterministic monitor: deadline alerts + renewal-window checks.
- Bundled renewal-recommendation + compliance-verification LLM call; on-demand compliance checks.

### 3.9 Analytics (S9)
- Deterministic SQL views over shared Postgres: contract-intelligence dashboard, severity-weighted portfolio risk, contract-value tracking, tabular review (with optional S5-cached NL columns), renewal dashboard.

### 3.10 Cross-cutting
- Version comparison: clause-aligned character-level diff → tracked changes; optional LLM semantic-change summary. Diff engine is shared with S3.

## 4. Functional requirements (backend)

- **FR-1** Every service is exposed via a documented REST API (see API_Spec.md).
- **FR-2** Character offsets (`charStart`/`charEnd`) produced by S1 propagate unchanged through S2/S3/S5 to power citations.
- **FR-3** Clause-type tags produced by S1 are the join key for S2 rule-matching, S5 navigation, S7 redline history, and the Version Comparison workflow's diff alignment.
- **FR-4** Risk scoring weights live on playbook rules (1–10), are applied by S2 per-clause, and are rolled up severity-weighted by S9. The contract score is normalised to 0–1.
- **FR-5** The autonomous gate must never auto-apply when a hard-stop condition is present: any yellow or red finding, or a redline quality failure.
- **FR-6** LLM calls go through a single **LLM gateway** abstraction (see Tech_Stack.md) — no service calls the Anthropic SDK directly.
- **FR-7** All LLM structured outputs are schema-validated (Pydantic); a malformed/refused response is surfaced as an error, never silently passed downstream.
- **FR-8** Determinism where claimed: deterministic services must produce identical output for identical input. LLM temperature/effort is fixed per task; outputs are treated as non-deterministic and never used for control flow.
- **FR-9** Zones are assigned by deterministic code. The model extracts facts (matched position, parameter values, semantic red-line answers) with quotes; it never assigns a zone or a gate decision.
- **FR-10** A published playbook version is immutable. Every finding, redline, decision event and exception records the rule key and playbook version it came from; every review run records its pinned versions.
- **FR-11** Playbook changes go through draft, test and publish, and every rule-level change is written to the change log.
- **FR-12** Every feature works with no seed data loaded. Empty playbook, role and policy tables are a valid state.

## 5. Non-functional requirements

- **NFR-1 Free-tier deployability** — must run on the free tiers named in Tech_Stack.md (Neon, Render/Vercel, object storage). No component may require paid infra.
- **NFR-2 Cost minimization** — deterministic path preferred; LLM calls batched/cached where possible; model tier configurable per task.
- **NFR-3 Explainability** — every AI decision carries a rationale and citations.
- **NFR-4 Modularity** — services are independently buildable and testable; the folder structure (Backend_Structure.md) enforces boundaries.
- **NFR-5 Portability of secrets** — all credentials (DB URL, Anthropic key, object-storage keys) come from environment variables.
- **NFR-6 Project partitioning** — the free-tier database and storage accounts are shared with other projects. Everything this project creates lives in its own namespace: a dedicated Postgres schema and a dedicated object-key prefix, both driven by one setting. Nothing of this project sits in `public`.
- **NFR-7 Cloud only** — all persistent project data lives in the cloud from the first day. No local database, no local file storage, no browser storage; the application refuses to start without its database and storage settings.
- **NFR-8 Seed isolation** — all seed code, content and seed tests live in `backend/seed/`. The application never imports from it, and deleting it changes nothing about the application.

## 6. Non-goals (explicitly out of scope)

Deferred entirely for this project — do **not** build them, and do not add hooks that assume them:

- Authentication / authorization / SSO / RBAC.
- Multi-user, real-time collaboration, comment @mentions, external counterparty portals.
- User accounts, per-user data isolation, tenancy.
- Security/compliance certifications, audit logs for compliance, encryption-at-rest configuration, data-residency. (The playbook change log is in scope: it is a product feature recording rule changes, not a compliance audit trail of user activity.)
- A user table: playbook authors and approvers are recorded as text or role keys.
- Traffic scaling, rate limiting, high-availability, DR.
- E-signature, CRM/ERP integrations, email/Slack/Teams add-ins.
- OCR for scanned PDFs (digital PDFs + DOCX only); multilingual (English only).
- The **frontend** — covered by Implementation_Plan_Frontend.md, not by this document.

## 7. Success criteria

- **SC-1** A contract (PDF or DOCX) can be uploaded and fully processed (S1) with clauses, offsets, metadata, and clause types, with zero LLM calls.
- **SC-2** A counterparty contract can be run end-to-end through the Review Pipeline and produce redlines with rationale + citations, gated correctly by the three-zone logic.
- **SC-3** A playbook can be bootstrapped from a corpus into a draft and then edited via CRUD; S2/S3 consume it.
- **SC-9** An uploaded contract resolves a non-empty, version-pinned rule set.
- **SC-10** Every governed finding carries a rule key, a zone and, where relevant, a position or red line; redline alternatives come from the playbook ladder.
- **SC-11** The gate returns one of three decisions and, with a playbook loaded, names an approver for yellow and red.
- **SC-12** A playbook change goes through draft, test and publish, and appears in the change log.
- **SC-13** The partition check passes: nothing of this project exists outside its schema or storage prefix, and no local database or storage folder exists.
- **SC-14** With `backend/seed/` removed, the application suite passes and the application starts.
- **SC-4** NL Q&A returns a cited answer over the current document without a vector index.
- **SC-5** Obligations extract at ingest; the daily monitor fires deadline/renewal alerts; compliance verification runs on demand.
- **SC-6** Analytics endpoints return severity-weighted portfolio risk and the other dashboards as SQL-view reads.
- **SC-7** Two contract versions diff into clause-aligned tracked changes; the same diff engine backs S3 redline rendering.
- **SC-8** Every service has passing unit tests; deterministic services have determinism tests (same input → same output).

## 8. Playbook build status (2026-11-16)

Section 3.2 and the playbook-related lines above describe the agreed design (`playbook_plan.md`). The schema, repositories, partitioning, cloud-only storage and the seed content are built. The wiring that makes the review pipeline use them — contract type capture, resolution, zones, the three-zone gate, ladder redlines, the versions API and the rule test runner — is phase 4 of `playbook_implementation.md` and is not built yet, so SC-9 to SC-12 are not yet met. Architecture.md carries the detailed status table.

## 9. Traceability

Feature suites → services → API → data → tasks are traceable through: this PRD (§3) → Architecture.md (diagrams) → API_Spec.md (endpoints) → Data_Model.md (tables) → Implementation_Plan_Backend.md (tasks, each tagged with its service and the FR/SC it satisfies).
