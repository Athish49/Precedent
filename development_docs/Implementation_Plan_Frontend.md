# Precedent — Frontend Implementation Plan (Phase 2)

**This file is self-contained.** To implement any task, read *only this file*. It carries everything
needed: the tech stack, the project structure, the shared design-system primitives, every page task,
and the complete backend API contract (Appendix A). You do **not** need to open any other file in
this folder or in `development_docs/`.

> Recovery note (not a required read): the canonical backend contract also lives in
> `development_docs/API_Spec.md` and `development_docs/Data_Model.md`. Consult them **only** if
> Appendix A here appears to have a gap.

---

## How to use this document

- **Pick any task by ID.** Each task lists its **Prerequisites** (earlier tasks that must exist).
  If a prerequisite isn't built yet, build it first — the Foundation (F-tasks) and Primitives
  (P-tasks) are prerequisites for most pages.
- **Never duplicate.** Endpoints are defined once in Appendix A; primitives once in Part 1; the file
  structure once in Part 0. Tasks reference them by name — they do not re-paste schemas.
- **`#N`** refers to a backend feature/endpoint. Every `#N` resolves to an entry in **Appendix A**.
- **Build order** is the task numbering: F → P → application pages (T) → marketing pages (M).

## Definition of Done (applies to every task unless the task overrides)

Because the plan assumes a live backend that may not be running yet, "done" is defined at a level you
can verify without live data:

1. TypeScript compiles with no errors; the page/component is typed against the response types in
   Appendix A (no `any` on API data).
2. The component renders in all four states: **loading** (skeleton), **empty**, **error**, and
   **populated** (verified with a typed fixture object shaped like the Appendix A response).
3. Every interaction is wired to the correct endpoint via the typed client + TanStack Query hook
   (Part 0.3), with the correct method, path, params, and body.
4. The page composes **only** primitives defined in Part 1 and shadcn/ui; no bespoke re-implementations
   of an existing primitive.
5. Route and file location match Part 0.2 exactly.
6. `npm run lint` and `npm run typecheck` pass.

---

# PART 0 — Foundation (shared by all tasks)

## 0.1 Tech stack (locked)

- **Next.js (App Router)** + **React** + **TypeScript**.
- **Tailwind CSS** for styling. **shadcn/ui** as the component base (Radix under the hood).
- **TanStack Query** (`@tanstack/react-query`) for all server-state (fetching, caching, mutations).
- **Deployment target:** Vercel.
- **No color scheme / theme is defined yet.** Use Tailwind's default neutral tokens and shadcn
  defaults; all severity/compliance/provenance visual *encodings* are wired through a single tokens
  module (0.5) so the palette can be themed later without touching pages.

## 0.2 Project & route structure (create in `frontend/`)

```
frontend/
  app/
    layout.tsx                     # root layout: QueryProvider, fonts, base html
    (marketing)/
      layout.tsx                   # marketing nav shell (M0)
      page.tsx                     # A1  Landing                     → /
      products/page.tsx            # A2  Products overview           → /products
      products/[solution]/page.tsx # A3–A10 solution pages (dynamic) → /products/<slug>
      platform/page.tsx            # A11 Platform                    → /platform
      company/page.tsx             # A12 Company                     → /company
    (app)/
      layout.tsx                   # app shell: NavRail + TopBar (F2)
      home/page.tsx                # B1  Home / Command Center       → /home
      repository/page.tsx          # B2  Repository + intake         → /repository
      contracts/[id]/page.tsx      # B3  Contract Workspace          → /contracts/:id
      automations/page.tsx         # B4  Automations                 → /automations
      automations/[runId]/page.tsx # B4  Run detail                  → /automations/:runId
      playbooks/page.tsx           # B5  Playbooks & Standards        → /playbooks
      drafting/page.tsx            # B6  Drafting Studio              → /drafting
      analytics/page.tsx           # B7  Analytics & Reporting        → /analytics
      obligations/page.tsx         # B8  Obligations & Renewals       → /obligations
      counterparties/page.tsx      # B9  Counterparties directory     → /counterparties
      counterparties/[id]/page.tsx # B9  Counterparty profile         → /counterparties/:id
      settings/page.tsx            # B10 Settings & System Health      → /settings
  lib/
    api/
      client.ts                    # typed fetch wrapper (0.3)
      types.ts                     # ALL response/request types (from Appendix A)
      hooks.ts                     # TanStack Query hooks per endpoint (0.3)
      keys.ts                      # query-key factory (0.3)
    tokens.ts                      # severity/status/provenance encoding map (0.5)
  components/
    ui/                            # shadcn/ui generated components
    shell/                         # AppShell, NavRail, TopBar, CommandBar, QueueBell (F2)
    primitives/                    # design-system primitives (Part 1)
```

The Contract Workspace tabs are **client-side tabs within the single `contracts/[id]/page.tsx`**, not
nested routes — the document canvas and the current selection are shared state across tabs (see T2).

## 0.3 Data-fetching conventions (build in F1, use everywhere)

- **`lib/api/client.ts`** — one `apiFetch<T>(path, opts)` wrapper. Base URL from
  `process.env.NEXT_PUBLIC_API_BASE` (default `/api`). Sends/parses JSON; for uploads sends
  `multipart/form-data`. On non-2xx, throws a typed `ApiError` parsed from the backend error envelope
  `{ error: { code, message, detail } }`.
- **`lib/api/types.ts`** — every request/response type from Appendix A, hand-written once. Pages import
  from here; never redefine shapes inline.
- **`lib/api/keys.ts`** — query-key factory, e.g. `keys.contract(id)`, `keys.flags(id, filters)`,
  `keys.alerts(filters)`. All hooks use it so cache invalidation is consistent.
- **`lib/api/hooks.ts`** — one hook per endpoint (or endpoint family), e.g. `useContracts(filters)`,
  `useContract(id)`, `useFlags(id, filters)`, `useGenerateRedlines(id)`, `useAckAlert()`. Reads =
  `useQuery`; writes = `useMutation` with **optimistic update + rollback** and invalidation of the
  affected keys. This is where the "optimistic + undo" behavior (0.6) is implemented.
- **Loading/empty/error** are handled by wrapping content in the shared `<QueryBoundary>` primitive
  (P1) so no page hand-rolls these states.

## 0.4 Global shell behavior (built in F2, inherited by all `(app)` pages)

- Persistent **left nav rail** → the ten app workspaces (0.2). Active workspace marked (encoding via
  tokens). Collapsible to icons.
- Persistent **top bar** → breadcrumb/context label • **global command bar** (P8) • right cluster:
  **New Contract** button (opens intake slide-over, F4) • **queue bell** with unacknowledged-alert
  count (`#82`) • settings entry.
- Rail + top bar are fixed; scrolling happens inside the main region and inside independent panes.

## 0.5 Visual-encoding tokens (`lib/tokens.ts`, built in P0)

A single module mapping enumerated values → visual encoding (icon name, shape, weight, badge variant).
**Palette/colors deferred to theming** — this module returns semantic variant names, not colors.
Covers: contract `status`, redline `status`, `severity` (low|medium|high), `flag_type` (7 values),
`alert_type` (4 values), `gate_decision`, provenance (`playbook|frequency|llm|ai`). Every indicator
primitive (P2) reads from here so encodings are consistent and themeable.

## 0.6 Interaction conventions (apply everywhere)

- **Hover = preview, click = commit/select.** Selection is a first-class, single-item state on pages
  that have a canvas (T2).
- **Optimistic updates + undo** for mutations (ack alert, accept redline, apply clause) via the
  mutation hooks (0.3) + a toast with Undo (P6).
- **Provenance always shown** on LLM-produced content via `<ProvenanceTag>` (P2); deterministic data
  carries none.

---

# PART 1 — Shared primitives (build before pages)

Each primitive is one task. They live in `components/primitives/` (or `components/shell/` where noted)
and are composed by pages. Build them first; pages assume they exist.

### P0 — Setup: shadcn/ui + tokens
**Prerequisites:** F0, F1.
Install/generate the shadcn/ui base components used across the app (`button`, `badge`, `card`,
`table`, `tabs`, `dialog`, `sheet`/drawer, `popover`, `tooltip`, `command`, `input`, `select`,
`switch`, `skeleton`, `sonner` toast). Build `lib/tokens.ts` (0.5).
**DoD:** components generated under `components/ui/`; `tokens.ts` exports typed encoding maps for every
enumeration in 0.5.

### P1 — `<QueryBoundary>`
Wraps any query-driven region and renders **loading** (skeleton shaped like content), **empty**
(message + primary action slot), and **error** (envelope message + retry) states, else the children.
Used by every data region so pages never hand-roll these.

### P2 — Indicators: `<StatusBadge>`, `<SeverityIndicator>`, `<ProvenanceTag>`
Small, consistent indicators reading from `lib/tokens.ts`. `StatusBadge` handles contract/redline
status and alert type; `SeverityIndicator` handles low|medium|high; `ProvenanceTag` handles
playbook|frequency|llm|ai.

### P3 — `<DataTable>` + `<FilterRail>`
Generic dense table: sortable columns, sticky header, pagination over `{ items, total }`, row hover
revealing a trailing quick-action slot, row-click callback. `<FilterRail>` renders grouped facet
controls and emits a filter object; active facets show as removable chips above the table. Used by
Repository, Analytics tabular, Obligations, Counterparty contracts.

### P4 — `<FlagCard>`
Renders a **Flag** (Appendix A). Compact form: type icon + one-line label + `<SeverityIndicator>` +
`<ProvenanceTag>` if `source==='llm'`. Expanded (on click): `detail`, matched-rule reference, and a
**Cite** action that emits the flag's `char_start/char_end` for canvas highlighting (consumed in T2).
Missing-clause variant (no offsets): primary affordance is **Add** (emits an add-clause intent
consumed in T5). Hover emits a transient highlight-preview intent.

### P5 — `<ComplianceChip>` (value-vs-policy)
The value-vs-policy comparison primitive. Given a found value and the governing rule's allowed value
(from a `deviation` flag's `detail` + its `matched_rule_id` → rule), renders **both sides** compactly,
e.g. `Payment terms: 120d` contrasted with `Policy max: 90d`, plus a non-compliance indicator
(encoding via tokens). States: compliant / deviation / missing. Hover → rule-context hover card
(P7). Click → emits focus intent (highlight governing clause + focus its flag). **Renders the
contrast, never prose.**

### P6 — `<UndoToast>` helper
Thin wrapper over the toast lib giving optimistic mutations a "Done — Undo" affordance for a few
seconds; Undo calls the mutation's rollback.

### P7 — `<HoverCard>` preview
Rich hover surface (more than a tooltip) for previews: contract row → key metadata; counterparty →
acceptance-rate snapshot; rule reference → rule language; citation → cited text. Dismiss on mouse-out.

### P8 — `<CommandBar>` (search + palette)  *(components/shell/)*
Top-bar input that expands to a floating palette. Typing offers grouped results: contracts by keyword
(`#13`), a "search everything" action running smart search (`#15`), and navigation commands. When
smart search runs, show an **"interpreted as"** line rendering the LLM-derived `filters` as removable
chips (transparency). Select → navigate (contract → workspace; filter set → `/repository` pre-filtered).

### P9 — `<RedlineBlock>` + tracked-change diff
Renders a **Redline** (Appendix A) as an editor-style tracked change from `tracked_changes`
(insert/delete/modify spans). Shows `explanation`, an alternatives cycler (2–3), the `stance_mode`,
and a copy action for `counterparty_comment`. Controls (wired by T5): fallback toggle (`#54`), inline
refine input (`#55`), and decision actions Accept (`#56`) / Reject (`#57`) / Accept-with-edit (`#58`,
opens an editable field seeded with `replacement_text`, saves `final_text`). Selecting a block emits
its clause/offsets for canvas highlighting.

### P10 — `<SlideOver>`
Standard edge drawer over current context (no navigation). Used by intake (F4), rule editor (T14),
version-store (T8). At most one open at a time; dismiss restores prior state.

---

# FOUNDATION TASKS

### F0 — Scaffold the Next.js app
**Prerequisites:** none.
Create the Next.js (App Router) + TypeScript project in `frontend/`. Add Tailwind. Add root
`app/layout.tsx` wrapping children in the TanStack Query provider. Add `npm` scripts: `dev`, `build`,
`lint`, `typecheck`. Create the empty route files per 0.2 (placeholder exports) so routing resolves.
**DoD:** `npm run dev` serves; every route in 0.2 resolves to a placeholder; typecheck passes.

### F1 — API client, types, keys, hooks
**Prerequisites:** F0.
Build `lib/api/client.ts`, `types.ts` (transcribe **all** Appendix A response/request types), `keys.ts`,
and `hooks.ts` (one hook per endpoint family in Appendix A, reads as `useQuery`, writes as
`useMutation` with optimistic update + invalidation). Build `<QueryBoundary>` (P1) here since it
depends on query state.
**DoD:** types cover every Appendix A response; a sample `useContracts()` and `useAckAlert()` compile
and are typed end-to-end; `ApiError` parsing works against the error envelope.

### F2 — App shell
**Prerequisites:** F0, P8 (CommandBar), P2.
Build `(app)/layout.tsx` with `NavRail`, `TopBar` (breadcrumb + CommandBar + New Contract button +
QueueBell + settings), per 0.4. QueueBell shows unacknowledged count via `useAlerts({acknowledged:false})`
(`#82`).
**DoD:** shell renders around every `(app)` page; nav highlights active route; QueueBell wired.

### F3 — Contract-context primitives
**Prerequisites:** F1, P0–P2.
Build `<FlagCard>` (P4), `<ComplianceChip>` (P5), `<RedlineBlock>` (P9), `<HoverCard>` (P7). (Grouped
because they share the citation/offset-intent pattern consumed by the Workspace.)
**DoD:** each renders from a typed fixture in all its variants; emits the documented intents via props.

### F4 — New Contract intake slide-over
**Prerequisites:** F1, P10.
Build the intake `<SlideOver>` invoked from the TopBar. Step 1: PDF/DOCX drop zone + **paper-origin
toggle** (own|counterparty). Step 2: mode choice — *Process only* (`POST /api/documents`, `#1`/`#2`)
or *Process + full autonomous review* (`POST /api/review/run` multipart, `#91`). On submit: live
milestone progress bound to contract `status` (`processing → analyzed`). On completion: confirmation
from `ProcessedContract` (clause count, detected counterparty) + primary action → open
`/contracts/:id`. Dismissible while processing continues.
**DoD:** both modes wired to the correct endpoints; progress + completion states implemented;
navigates to the new workspace.

---

# PART 2 — Application page tasks

> Every T-task inherits the global **Definition of Done** and the shell (F2). Prerequisites list only
> what's beyond F0–F4 + P0–P10.

### T1 — Repository + intake  (route `/repository`, `repository/page.tsx`)  — *List-with-rail*
**Prerequisites:** P3, F4.
- `<FilterRail>` facets: contract_type, counterparty, status, effective-date range, value range;
  combinable (`#7`–`#12`). Active facets → removable chips.
- `<DataTable>` of contract rows (`#6`): title, type, counterparty, `<StatusBadge>` status,
  `<SeverityIndicator>` risk, effective/expiry, value. Row hover → quick-actions (open; run review
  `#90`; compare versions). Row click → `/contracts/:id`.
- Inline search: keyword (`#13`) and faceted (`#14`) refine the same table; **smart search** (`#15`)
  via CommandBar or in-page field renders results here + shows derived `filters` chips.
- Version lineage inline expander per row (`#17`).
- Precedent-clause results surface here when routed (`#21`).
- Empty state → New Contract (F4).
**Endpoints:** `#6`–`#15`, `#17`, `#21`, `#90`.

### T2 — Contract Workspace shell (canvas + bidirectional linking)  (route `/contracts/[id]`)  — *Canvas-with-inspector*
**Prerequisites:** T1 conceptually (a contract must exist), F3.
This is the hero task. Build the frame + the core interaction; the six tabs are T3–T8.
- **Layout:** left **document canvas** (~3/4), right **inspector rail** (~1/4, draggable/collapsible).
- **Canvas:** render `canonical_text` (`#5`) with clause boundaries and per-clause type tags from the
  clause array (`#4`). Each clause with issues shows an in-canvas **gutter marker** (severity via
  tokens). A clause-type **navigation index** (`#73`) scrolls the canvas.
- **Inspector:** client-side **tabs** — Overview, Analysis, Redlines, Intelligence, Obligations,
  Versions. Switching tabs keeps the canvas mounted.
- **Bidirectional linking (the core interaction):** a single shared selection state.
  - Inspector → canvas: selecting a `<FlagCard>`, `<RedlineBlock>`, obligation, or `<ComplianceChip>`
    highlights its `char_start/char_end` span in the canvas and scrolls to it; hover previews it.
  - Canvas → inspector: clicking an annotated span (or a gutter marker) focuses the matching inspector
    item, switching tabs if needed.
  - Single-selection model; hover never overrides an active selection.
**Endpoints:** `#4`, `#5`, `#73`.
**DoD (override addition):** selecting any offset-bearing item in a fixture highlights the correct
span, and clicking a span focuses the correct item — proven with a typed fixture, no backend needed.

### T3 — Workspace: Overview tab
**Prerequisites:** T2.
Render contract metadata (`#3`) as scannable fields (parties, dates, governing law, liability cap,
notice period, auto-renewal, payment/financial terms). **Governed fields carry `<ComplianceChip>`**
(P5) — the value-vs-policy contrast (e.g. payment terms vs policy max). Risk-aware summary (`#67`,
`<ProvenanceTag>` ai). Aggregate risk + max-severity badge (`#41`). Clicking a chip → canvas highlight
+ focus its flag (via T2 linking).
**Endpoints:** `#3`, `#41`, `#67`.

### T4 — Workspace: Analysis tab
**Prerequisites:** T2, P4.
Filter controls: flag_type (missing/prohibited/deviation/high_risk/vague/inconsistent) + severity,
combinable (`#42`–`#49`). List of `<FlagCard>` (`#41`); selecting drives canvas highlight (T2).
Contextual groupings surfaced: **Missing clauses** (`#42`, each card's primary action = **Add**,
consumed by T5) and **High-risk items** (`#45`). Run/re-run analysis by paper origin (`#39`/`#40`)
with milestone progress.
**Endpoints:** `#39`–`#49`.

### T5 — Workspace: Redlines & Negotiation tab
**Prerequisites:** T2, P9, T4 (for the missing-clause hand-off).
- Generate control + **stance selector** Light/Balanced/Firm (`#50`–`#52`).
- List of `<RedlineBlock>` (`#53`) anchored to clauses; selecting highlights in canvas (T2). Wire
  block controls: fallback toggle (`#54`), refine (`#55`), Accept/Reject/Accept-with-edit
  (`#56`–`#58`) — optimistic + undo (P6), animate the change into the canvas.
- **Click-to-apply missing-clause flow:** from a missing-clause card (T4), **Add** → generate the
  insertion from playbook preferred language at the chosen stance, render as a proposed **insertion
  redline** in the canvas, Accept to commit (`#56`) or edit-then-accept (`#58`).
  *(Composition: the Add uses the redline-generation path for that clause; treat as `#50`–`#52` +
  `#28` preferred language, surfaced as a `tracked_changes` insertion per `#53`, then `#56`/`#58`.)*
- Autonomous review from here (`#90`); show latest run's `gate_decision` + `gate_reason` banner
  (`#92`/`#93`), escalations flagged/linked.
- Negotiation history per clause type (`#16`) as a hover card / expandable subsection.
**Endpoints:** `#16`, `#50`–`#58`, `#90`, `#92`, `#93`.

### T6 — Workspace: Intelligence tab
**Prerequisites:** T2.
- Q&A (`#69`/`#70`): question input + answer thread; answers `<ProvenanceTag>` ai; **citations
  clickable** → canvas highlight (T2); repeat = instant with "from cache" hint.
- Summaries: risk-aware (`#67`) + redline-thread (`#68`).
- Easy Prompt (`#71`): show structured interpretation, then **route** to Redlines tab or Drafting
  (`/drafting`) carrying the `structured_prompt`.
- Research (`#72`): query → synthesized answer + listed web sources.
**Endpoints:** `#67`–`#72`.

### T7 — Workspace: Obligations tab
**Prerequisites:** T2.
Obligation list (`#74`/`#75`): commitment, owner, deadline, deliverable, `<StatusBadge>` (open|met|
overdue), citation → canvas highlight. Compliance check (`#77`): pass/fail + issues as
`<ComplianceChip>`. Contract-scoped alerts (`#78`–`#81`), acknowledge inline (`#83`, optimistic+undo).
**Endpoints:** `#74`, `#75`, `#77`–`#83`.

### T8 — Workspace: Versions tab + compare
**Prerequisites:** T2, P10.
Version lineage tree (`#17`). Store new / amendment / addendum via `<SlideOver>` (`#18`–`#20`).
**Compare:** select two versions → canvas switches to aligned tracked-change diff (`#95`/`#96`);
inspector shows semantic change summary (`#97`, ai). Exit → single-document canvas.
**Endpoints:** `#17`–`#20`, `#95`–`#97`.

### T9 — Home / Command Center  (route `/home`)  — *Board*
**Prerequisites:** P2.
Cards: portfolio risk (`#85`, → Analytics); **Action queue** (composite: unacked alerts `#82`+`#83`,
analyzed-not-redlined contracts `#9`, escalated runs `#93`; hover preview, click → exact action
location); upcoming renewals 30/60/90 (`#89`/`#79`); recent activity (`#6` by recency); contract value
(`#86`); open compliance-failure count (`#80`). CommandBar present (F2).
**Endpoints:** `#6`, `#9`, `#79`, `#80`, `#82`, `#83`, `#85`, `#86`, `#89`, `#93`.

### T10 — Analytics & Reporting  (route `/analytics`)  — *Board + tabular*
**Prerequisites:** P3.
Dashboard cards: contract intelligence (`#84`), portfolio risk + severity distribution (`#85`),
contract value grouped (`#86`), renewals (`#89`). Charts interactive: hover shows figure, click
cross-filters / deep-links to `/repository`. **Tabular mode** (`#87`): `<DataTable>`, one row/contract,
promoted-metadata columns; **column adder** appends an NL answer column (`#88`) populated from Q&A
cache, cells citation-backed on click. Shared filter bar (`#7`,`#8`,`#10`,`#11`).
**Endpoints:** `#7`,`#8`,`#10`,`#11`, `#84`–`#89`.

### T11 — Obligations & Renewals  (route `/obligations`)  — *List-with-rail*
**Prerequisites:** P3.
`<FilterRail>`: alert type (deadline/renewal/compliance_fail/compliance_pass) + acknowledged state
(`#78`–`#82`). Alert rows: type badge, source contract, type-specific content — deadline countdown;
renewal recommendation; compliance-fail issues as `<ComplianceChip>`. Acknowledge inline (`#83`,
optimistic+undo); row → `/contracts/:id` (Obligations tab). Run-monitor-now (`#76`).
**Endpoints:** `#76`, `#78`–`#83`.

### T12 — Counterparties  (routes `/counterparties`, `/counterparties/[id]`)  — *List-with-rail → profile*
**Prerequisites:** P3, P7.
Directory: counterparties + contract counts (`#8`). Profile: header with risk profile (`#41`/`#85`
filtered) + total value (`#86` filtered); contracts table (`#8`) with inline lineage (`#17`); renewal
alerts filtered (`#79`); **negotiation history** matrix per clause type — acceptance rate, positions,
outcomes, last-agreed text (`#16`), hover reveals detail (P7). Quick action: run review with
counterparty context (`#90`).
**Endpoints:** `#8`, `#16`, `#17`, `#41`, `#79`, `#85`, `#86`, `#90`.

### T13 — Automations / Autonomous Review  (routes `/automations`, `/automations/[runId]`)  — *List-with-rail*
**Prerequisites:** P3, F4.
Run list: review-run rows (`#90`–`#93`) — contract, trigger (manual|upload_event), status, prominent
`<StatusBadge>` gate_decision (auto_applied|escalated); filter by gate_decision. **Run detail:** render
`gate_reason` as an explicit **hard-stop checklist** (prohibited term / missing required clause /
high-severity — each pass or triggered); produced flags/redlines link into the Workspace (T5).
Trigger a run (`#90`/`#91`, via F4 or an existing-contract picker). Webhook config section (`#94`).
**Endpoints:** `#90`–`#94`.

### T14 — Playbooks & Standards  (route `/playbooks`)  — *List-with-rail (master–detail)*
**Prerequisites:** P3, P10.
Playbook list (`#22`): name, practice_area, precedence; create (`#23`), edit (`#25`), delete (`#26`).
Rules table (`#24`/`#27`): clause_type, preferred-language preview, required flag, risk_weight. **Rule
editor** in `<SlideOver>` (`#28`–`#33` create; `#34` edit; `#35` delete): preferred_language,
acceptable_variations (list), prohibited_terms (list), fallback_language, required toggle, risk_weight,
escalation_threshold. **Resolve preview** (`#36`/`#37`): merged, precedence-ordered rule set, each rule
tagged with its source playbook. **Bootstrap** (`#38`): corpus picker → milestone progress → created
count.
**Endpoints:** `#22`–`#38`.

### T15 — Drafting Studio  (route `/drafting`)  — *Split: composer + result*
**Prerequisites:** P2, P7.
Mode switch: Single clause / Full document / Precedent-matched / Memo.
- Single clause (`#59`–`#62`): clause_type + context inputs; result with **`<ProvenanceTag>`**
  (playbook|frequency|llm) prominent; NL rewrite field triggers LLM tier.
- Full document (`#63`/`#64`): template picker + variable form; output + optional **Polish** toggle.
- Precedent-matched (`#65`): output clause + the **precedents drawn from** (cards w/ similarity).
- Precedent search (`#21`): reference cards before drafting.
- Memo (`#66`): context → memo text.
- Routed Easy Prompt (`#71`): composer opens pre-filled from a workspace hand-off (T6) with a
  back-reference to the source contract.
- Every result: copy; and where a contract context exists, "insert as redline".
**Endpoints:** `#21`, `#59`–`#66`, `#71`.

### T16 — Settings & System Health  (route `/settings`)  — *Board (sections)*
**Prerequisites:** none beyond foundation.
System health tiles (`#98`): DB, embedding model, object storage — up/down, refreshable. Environment
config (read-only): model tiers, embedding model, storage backend. Webhook config (`#94`, shared with
T13). Seed status: baseline playbook templates loaded? + shortcut to `/playbooks`.
**Endpoints:** `#94`, `#98`.

---

# PART 3 — Marketing page tasks (static; build last)

Static content; **no live API calls**; illustrative (non-live) visuals only. Depend only on the
marketing shell + Tailwind. Every claim must trace to a real capability and must not imply a Non-Goal
(no e-signature, integrations, SSO/auth, multi-user collaboration, counterparty portals).

### M0 — Marketing shell  (`(marketing)/layout.tsx`)
Top nav: brand mark; links **Products / Platform / Company**; **Launch App** button → `/home`.
**Products** opens a **mega-menu** (multi-column) listing the eight solutions grouped
(review & negotiate / draft / manage & monitor / analyze), each → `/products/<slug>`.

### M1 — Landing  (`/`)
Hero (headline + subhead + CTA) → capability tile grid (one tile per solution, mirrors mega-menu) →
differentiator strip (deterministic-first, character-level citations, autonomous gate) with
illustrative snapshots → closing CTA. Tiles lift on hover, navigate on click.

### M2 — Products overview  (`/products`)
All eight solutions as alternating sections (short description + illustrative visual), each linking to
its solution page and to the app workspace via Launch App.

### M3 — Solution pages  (`/products/[solution]`, 8 slugs)
One dynamic route rendering a shared template from a per-solution content config. Slugs & framing:
`clm` (A3), `analysis` (A4), `redlining` (A5), `drafting` (A6), `autonomous-review` (A7),
`playbooks` (A8), `document-intelligence` (A9), `analytics` (A10). Template: solution hero →
3–5 feature sub-sections (value + illustrative visual) → "how it works" mini-diagram → CTA into the
matching app workspace. Content groupings per solution follow the capability groups (see Appendix A
service groupings). No live data.

### M4 — Platform  (`/platform`)
Narrative + central architecture diagram with labeled callouts: deterministic vs. LLM path;
character-offset citations; the autonomous gate. Static.

### M5 — Company  (`/company`)
Editorial vision page (what Precedent is, audience: in-house counsel / legal ops) + closing CTA.

---

# APPENDIX A — Backend API contract (the single source for `#N`)

Base path `/api`. JSON in/out. IDs are UUID strings. List endpoints paginate with `?limit=&offset=`
and return `{ items, total }`. Errors: `{ error: { code, message, detail } }`. Long operations return
a record with an id; poll the GET for status.

## A.1 Endpoints (grouped) — `#N → method path → purpose → response type`

**S1 Documents**
- `#1`/`#2` `POST /api/documents` — multipart `file` + `paper_origin=own|counterparty` → `ProcessedContract`
- `#3` `GET /api/documents/{id}` → `Contract & { metadata: ContractMetadata }`
- `#4` `GET /api/documents/{id}/clauses` → `Clause[]`
- `#5` `GET /api/documents/{id}/text` → `{ canonical_text: string }`

**S7 Repository & Search**
- `#6`–`#12` `GET /api/repository/contracts` — query: `contract_type, counterparty_id, status, effective_date_from, effective_date_to, value_min, value_max, limit, offset` → `{ items: ContractRow[], total }`
- `#13` `GET /api/repository/search?q=` → `{ items: ContractRow[], total }`
- `#14` `GET /api/repository/search?type=faceted&...` → `{ items: ContractRow[], total }`
- `#15` `POST /api/repository/smart-search` — body `{ query }` → `{ filters: object, semantic_query?: string, items: ContractRow[], total }`
- `#16` `GET /api/repository/contracts/{id}/redline-history` → `RedlineHistoryItem[]`
- `#17` `GET /api/repository/contracts/{id}/versions` → `Version[]`
- `#18`/`#19`/`#20` `POST /api/repository/contracts/{id}/versions` — multipart `file` + `relation=version|amendment|addendum` → `Version`
- `#21` `GET /api/repository/precedent-search?clause_type=&query=` → `PrecedentClause[]`

**S6 Playbooks & Rules**
- `#22` `GET /api/playbooks` → `Playbook[]`
- `#23` `POST /api/playbooks` — body `{ name, practice_area, precedence }` → `Playbook`
- `#24` `GET /api/playbooks/{id}` → `Playbook & { rules: PlaybookRule[] }`
- `#25` `PATCH /api/playbooks/{id}` — body partial `{ name?, precedence? }` → `Playbook`
- `#26` `DELETE /api/playbooks/{id}` → `204`
- `#27` `GET /api/playbooks/{id}/rules` → `PlaybookRule[]`
- `#28`–`#33` `POST /api/playbooks/{id}/rules` — body `PlaybookRule` fields → `PlaybookRule`
- `#34` `PATCH /api/playbooks/rules/{rule_id}` — partial `PlaybookRule` → `PlaybookRule`
- `#35` `DELETE /api/playbooks/rules/{rule_id}` → `204`
- `#36`/`#37` `GET /api/playbooks/resolve?contract_type=` (multi: `saas_msa+gdpr`) → `ResolvedRule[]`
- `#38` `POST /api/playbooks/bootstrap` — body `{ corpus: string[] }` → `{ created_count: number }`

**S2 Analysis**
- `#39`/`#40` `POST /api/analysis/{contract_id}` (mode from paper_origin) → `AnalysisResult`
- `#41` `GET /api/analysis/{contract_id}` → `AnalysisResult`
- `#42`–`#49` `GET /api/analysis/{contract_id}/flags?flag_type=&severity=` → `Flag[]`

**S3 Redlines**
- `#50`–`#52` `POST /api/redlines/{contract_id}` — body `{ stance_mode: light|balanced|firm }` → `Redline[]`
- `#53` `GET /api/redlines/{contract_id}` → `Redline[]`
- `#54` `POST /api/redlines/{redline_id}/toggle-fallback` → `Redline`
- `#55` `POST /api/redlines/{redline_id}/refine` — body `{ instruction }` → `Redline`
- `#56`/`#57`/`#58` `POST /api/redlines/{redline_id}/decision` — body `{ outcome: accepted|rejected, final_text? }` → `Redline`

**S4 Drafting**
- `#59`–`#62` `POST /api/drafting/clause` — body `{ clause_type, context, mode }` → `DraftResult`
- `#63`/`#64` `POST /api/drafting/document` — body `{ template, variables, polish? }` → `{ document: string }`
- `#65` `POST /api/drafting/precedent` — body `{ clause_type, context }` → `{ text: string, precedents: PrecedentClause[] }`
- `#66` `POST /api/drafting/memo` — body `{ context }` → `{ text: string }`

**S5 Intelligence**
- `#67` `POST /api/intelligence/{id}/summarize` → `{ summary: string }`
- `#68` `POST /api/intelligence/{id}/summarize-redlines` → `{ summary: string }`
- `#69`/`#70` `POST /api/intelligence/{id}/qa` — body `{ question }` → `{ answer: string, citations: Citation[] }`
- `#71` `POST /api/intelligence/{id}/easy-prompt` — body `{ instruction }` → `{ structured_prompt: string, route: 's3'|'s4' }`
- `#72` `POST /api/intelligence/{id}/research` — body `{ query }` → `{ answer: string, sources: {title,url}[] }`
- `#73` `GET /api/intelligence/{id}/navigation` → `NavIndexEntry[]`

**S8 Obligations**
- `#74` `POST /api/obligations/{id}/extract` → `Obligation[]`
- `#75` `GET /api/obligations/{id}` → `Obligation[]`
- `#76` `POST /api/obligations/monitor/run` → `{ alerts_fired: number }`
- `#77` `POST /api/obligations/{id}/compliance-check` → `{ pass: boolean, issues: object[] }`
- `#78`–`#82` `GET /api/obligations/alerts?type=&acknowledged=` → `Alert[]`
- `#83` `POST /api/obligations/alerts/{id}/ack` → `Alert`

**S9 Analytics** (read-only view payloads)
- `#84` `GET /api/analytics/intelligence` → `object` (aggregated metadata rows)
- `#85` `GET /api/analytics/portfolio-risk` → `{ score, distribution: {severity,count}[] }`
- `#86` `GET /api/analytics/contract-value` → `{ total, groups: {key,value}[] }`
- `#87` `GET /api/analytics/tabular` → `{ columns: string[], rows: object[] }`
- `#88` `GET /api/analytics/tabular?columns=q1,q2` → same, with NL answer columns
- `#89` `GET /api/analytics/renewals` → `RenewalRow[]`

**Review Pipeline**
- `#90` `POST /api/review/run` — body `{ contract_id }` → `ReviewRun`
- `#91` `POST /api/review/run` — multipart `file` + `paper_origin` → `ReviewRun`
- `#92`/`#93` `GET /api/review/runs/{run_id}` → `ReviewRun` (gate_decision auto_applied|escalated)
- `#94` `POST /api/review/webhook` — config/entry point (settings surface only)

**Version Comparison**
- `#95`/`#96` `GET /api/versions/diff?contract_id=&v_a=&v_b=` → `ChangeSet`
- `#97` `POST /api/versions/diff/summary` — body `{ contract_id, v_a, v_b }` → `{ summary: string }`

**Health**
- `#98` `GET /api/health` → `{ db: bool, embedding_model: bool, object_storage: bool }`

## A.2 Response types (define once in `lib/api/types.ts`)

Enums:
- `PaperOrigin = 'own' | 'counterparty'`
- `ContractStatus = 'processing' | 'analyzed' | 'redlined' | 'executed'`
- `Severity = 'low' | 'medium' | 'high'`
- `FlagType = 'missing' | 'prohibited' | 'non_standard' | 'high_risk' | 'vague' | 'inconsistent' | 'deviation'`
- `FlagSource = 'deterministic' | 'llm'`
- `RedlineStatus = 'proposed' | 'accepted' | 'rejected' | 'auto_applied' | 'escalated'`
- `RedlinePosition = 'preferred' | 'fallback'`
- `StanceMode = 'light' | 'balanced' | 'firm'`
- `AlertType = 'deadline' | 'renewal' | 'compliance_pass' | 'compliance_fail'`
- `GateDecision = 'auto_applied' | 'escalated'`
- `VersionRelation = 'version' | 'amendment' | 'addendum'`
- `ObligationStatus = 'open' | 'met' | 'overdue'`
- `DraftSource = 'playbook' | 'frequency' | 'llm'`

Objects (fields; `?` = nullable/optional):
- `Contract` = `{ id, title, source_format:'pdf'|'docx', paper_origin:PaperOrigin, contract_type?, counterparty_id?, current_version_id?, status:ContractStatus, created_at, updated_at }`
- `ContractMetadata` = `{ parties:{name,role}[], effective_date?, expiry_date?, governing_law?, liability_cap?:{value,currency}, notice_period_days?, auto_renewal?, payment_terms?, financial_fields?:object, milestone_dates?:string[], extracted?:object }`
- `ContractRow` = `{ id, title, contract_type?, counterparty_display_name?, paper_origin:PaperOrigin, status:ContractStatus, effective_date?, expiry_date?, value?, risk_score?, max_clause_severity?:Severity }`
- `ProcessedContract` = `{ contract_id, clauses:Clause[], metadata:ContractMetadata, paper_origin:PaperOrigin, counterparty_id? }`
- `Clause` = `{ id, contract_id, ordinal, clause_type, heading_text, text, char_start, char_end }`
- `Citation` = `{ char_start, char_end }`
- `Flag` = `{ id, contract_id, clause_id?, review_run_id?, flag_type:FlagType, severity:Severity, source:FlagSource, char_start?, char_end?, detail:object, matched_rule_id? }`
- `Risk` = `{ score:number, max_clause_severity:Severity, weights_version?, per_clause?:{clause_id,score}[] }`
- `AnalysisResult` = `{ flags:Flag[], risk:Risk }`
- `Redline` = `{ id, contract_id, clause_id, flag_id?, review_run_id?, stance_mode:StanceMode, position:RedlinePosition, replacement_text, tracked_changes:object, alternatives:object[], explanation, counterparty_comment, rationale:object, status:RedlineStatus, created_at }`
- `RedlineHistoryItem` = `{ clause_type, position_offered, recommended_stance, outcome, final_text?, created_at }`
- `Version` = `{ id, contract_id, version_number, parent_version_id?, relation:VersionRelation, created_at }`
- `PrecedentClause` = `{ clause_id, clause_type, text, contract_id, similarity:number }`
- `Playbook` = `{ id, name, practice_area:'hipaa'|'gdpr'|'saas_msa'|'nda'|'dpa', precedence:number }`
- `PlaybookRule` = `{ id, playbook_id, clause_type, preferred_language, acceptable_variations:string[], prohibited_terms:string[], fallback_language?, required:boolean, risk_weight:number, escalation_threshold? }`
- `ResolvedRule` = `PlaybookRule & { source_playbook_id, source_playbook_name }`
- `DraftResult` = `{ text:string, source:DraftSource }`
- `NavIndexEntry` = `{ clause_type, clause_id, char_start }`
- `Obligation` = `{ id, contract_id, commitment, owner, deadline?, deliverable, char_start?, char_end?, status:ObligationStatus }`
- `Alert` = `{ id, contract_id, alert_type:AlertType, payload:object, fired_at, acknowledged:boolean }`
- `ReviewRun` = `{ id, contract_id, trigger:'manual'|'upload_event', gate_decision?:GateDecision, gate_reason?:object, status:'running'|'completed'|'failed', started_at, completed_at? }`
- `ChangeSet` = `{ changes:{ type:'insert'|'delete'|'modify', clause_id?, char_start, char_end, text? }[] }`
- `RenewalRow` = `{ contract_id, title, expiry_date, days_remaining, risk_score?, recommendation? }`

---

# APPENDIX B — Coverage checklist (verify nothing was lost)

Every backend feature `#1`–`#98` lands on at least one task. Use this to confirm the plan is complete.

| Features | Task(s) |
|---|---|
| `#1`,`#2`,`#91` (intake/upload+review) | F4, T1, T13 |
| `#3` metadata | T3 |
| `#4`,`#5` clauses/text | T2 |
| `#6`–`#12` list/filter | T1 (also T9 recent, T10, T12) |
| `#13`,`#14`,`#15` search | P8, T1 (also T9) |
| `#16` redline history | T5, T12 |
| `#17` versions | T1, T8, T12 |
| `#18`–`#20` store version/amendment/addendum | T8 |
| `#21` precedent search | T1, T15 |
| `#22`–`#38` playbooks/rules/resolve/bootstrap | T14 |
| `#39`–`#49` analysis/flags | T4 |
| `#50`–`#58` redlines/decisions | T5 |
| `#59`–`#66` drafting | T15 |
| `#67` summarize | T3, T6 |
| `#68`–`#72` intel (redline-summary/qa/easy-prompt/research) | T6 |
| `#73` navigation | T2 |
| `#74`,`#75`,`#77` obligations/compliance | T7 |
| `#76` monitor run | T11 |
| `#78`–`#83` alerts/ack | T7, T9, T11 |
| `#84`–`#89` analytics | T10 (also T9, T12 filtered) |
| `#90`–`#94` review pipeline/webhook | T13 (also T1, T5, T12, T16) |
| `#95`–`#97` version diff/summary | T8 |
| `#98` health | T16 |

**Pages:** 10 app (B1–B10 → T9, T1, T2–T8, T13, T14, T15, T10, T11, T12, T16) + 12 marketing
(A1–A12 → M1, M2, M3×8, M4, M5). All accounted for.
