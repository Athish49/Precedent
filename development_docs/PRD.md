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
- Issue detection: missing/prohibited clauses (deterministic), non-standard/high-risk/vague/inconsistent language (LLM), per-clause + per-contract risk scoring (deterministic, severity-weighted).
- Paper-origin-aware analysis: own paper → standard analysis; counterparty paper → deviation-vs-playbook analysis (plus risk/vague detection).
- Redline generation: preferred-position redline as surgical tracked changes, 2–3 alternatives, plain-language explanation, counterparty-ready comment, deterministic rationale field. Stance modes (Light/Balanced/Firm). Fallback toggle. On-demand multi-pass refinement.
- Character-level citations traceable to source text on every flag and redline.

### 3.2 Playbook & standards (S6)
- Unified playbook store keyed by clause type: preferred language, acceptable variations, prohibited terms, fallback language.
- Practice-area routing (HIPAA, GDPR, SaaS MSA, NDA, DPA), selecting **all applicable** rule-sets merged by precedence.
- Self-service CRUD over playbooks and rules.
- One-time LLM **bootstrap**: derive preferred language + acceptable variations from a corpus of executed agreements. Prohibited terms come from template defaults + human edits (not mined from executed contracts).

### 3.3 Drafting (S4)
- Cost-tiered cascade: playbook lookup → frequency-tracker reuse → LLM (only when both miss).
- Modes: single-clause draft/rewrite, first-draft document from template, precedent-matched drafting (vector search + style-matched generation), memo/letter drafting, novel-clause generation.

### 3.4 Document intelligence (S5)
- Risk-aware contract summarization (grounded on S1 metadata + S2 risk flags).
- Redline-thread summarization.
- Natural-language Q&A over the current document with character-level citations (reads the clause array directly — no vector RAG for a single doc).
- Easy Prompt (NL → structured legal prompt, routed into S3/S4).
- Chat2 Research (web search synthesized with contract context).
- Deterministic clause-navigation index.

### 3.5 Repository & search (S7)
- Central contract repository (object storage = source of truth; metadata in Postgres).
- Full-text search (Postgres `tsvector`), faceted metadata filtering, amendment/version parent-child links, redline-history index.
- Smart Search: one LLM call translates NL → structured filters + optional semantic query; execution is deterministic.
- Version-aware storage powering the Version Comparison workflow and the shared diff engine.

### 3.6 Agentic review workflows (Review Pipeline + Autonomous Review Trigger)
- Event-triggered, **code-orchestrated** pipeline: S1 → S6 → S2 → S3, then a deterministic threshold gate auto-applies redlines or escalates to human.
- The gate uses hard-stops (any prohibited/missing clause, quality-check failure, or single high-risk clause forces escalation), not just an aggregate score.
- "Autonomous" = event-driven, not LLM-directed. Code controls all flow. **Zero true agents.**

### 3.7 Negotiation memory (NMS)
- Append-only decision log (recommended stance, position offered, accept/reject outcome, final agreed text) keyed by normalized counterparty + clause type.
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
- **FR-4** Risk scoring weights live in playbook config, are applied by S2 per-clause, and are rolled up severity-weighted by S9.
- **FR-5** The autonomous gate must never auto-apply when a hard-stop condition is present.
- **FR-6** LLM calls go through a single **LLM gateway** abstraction (see Tech_Stack.md) — no service calls the Anthropic SDK directly.
- **FR-7** All LLM structured outputs are schema-validated (Pydantic); a malformed/refused response is surfaced as an error, never silently passed downstream.
- **FR-8** Determinism where claimed: deterministic services must produce identical output for identical input. LLM temperature/effort is fixed per task; outputs are treated as non-deterministic and never used for control flow.

## 5. Non-functional requirements

- **NFR-1 Free-tier deployability** — must run on the free tiers named in Tech_Stack.md (Neon, Render/Vercel, object storage). No component may require paid infra.
- **NFR-2 Cost minimization** — deterministic path preferred; LLM calls batched/cached where possible; model tier configurable per task.
- **NFR-3 Explainability** — every AI decision carries a rationale and citations.
- **NFR-4 Modularity** — services are independently buildable and testable; the folder structure (Backend_Structure.md) enforces boundaries.
- **NFR-5 Portability of secrets** — all credentials (DB URL, Anthropic key, object-storage keys) come from environment variables.

## 6. Non-goals (explicitly out of scope)

Deferred entirely for this project — do **not** build them, and do not add hooks that assume them:

- Authentication / authorization / SSO / RBAC.
- Multi-user, real-time collaboration, comment @mentions, external counterparty portals.
- User accounts, per-user data isolation, tenancy.
- Security/compliance certifications, audit logs for compliance, encryption-at-rest configuration, data-residency.
- Traffic scaling, rate limiting, high-availability, DR.
- E-signature, CRM/ERP integrations, email/Slack/Teams add-ins.
- OCR for scanned PDFs (digital PDFs + DOCX only); multilingual (English only).
- The **frontend** — deferred to a later phase; this build is backend + database only.

## 7. Success criteria

- **SC-1** A contract (PDF or DOCX) can be uploaded and fully processed (S1) with clauses, offsets, metadata, and clause types, with zero LLM calls.
- **SC-2** A counterparty contract can be run end-to-end through the Review Pipeline and produce redlines with rationale + citations, gated correctly by the threshold logic.
- **SC-3** A playbook can be bootstrapped from a corpus and then edited via CRUD; S2/S3 consume it.
- **SC-4** NL Q&A returns a cited answer over the current document without a vector index.
- **SC-5** Obligations extract at ingest; the daily monitor fires deadline/renewal alerts; compliance verification runs on demand.
- **SC-6** Analytics endpoints return severity-weighted portfolio risk and the other dashboards as SQL-view reads.
- **SC-7** Two contract versions diff into clause-aligned tracked changes; the same diff engine backs S3 redline rendering.
- **SC-8** Every service has passing unit tests; deterministic services have determinism tests (same input → same output).

## 8. Traceability

Feature suites → services → API → data → tasks are traceable through: this PRD (§3) → Architecture.md (diagrams) → API_Spec.md (endpoints) → Data_Model.md (tables) → Implementation_Plan_Backend.md (tasks, each tagged with its service and the FR/SC it satisfies).
