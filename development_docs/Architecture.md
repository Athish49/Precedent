# Architecture Diagrams — Contract Intelligence Platform

Deterministic-first architecture: LLMs are used only where semantic understanding is genuinely required; everything structural (segmentation, typing, diffing, scoring, aggregation, monitoring) is pure code. Orange-bordered nodes are LLM calls; all others are deterministic. Node-shape conventions are in the Legend at the bottom.

## Platform-wide notes

- **One database — Neon Postgres.** Holds contract metadata, `tsvector` full-text, `pgvector` embeddings, the Negotiation Memory Store (append-only event log), the obligations store, and the analytics view layer. Object storage holds source documents as the single source of truth.
- **Clause-type normalizer (S1) is shared infrastructure.** The canonical clause `type` is consumed by S2 (rule matching + structural checks), S5 (navigation), S7 (redline history), and the Version Comparison workflow (diff alignment). Its vocabulary stays in sync with S6's clause-type taxonomy.
- **Shared diff engine (S7).** One char-level, clause-aligned diff engine is reused by S3 (redline markup) and the Version Comparison workflow. It aligns clauses by stable S1 clause id before diffing.
- **Severity-weighted risk.** Scoring weights live in S6 config, are applied by S2 per-clause, and are rolled up severity-weighted (never averaged) by S9.
- **Normalized `counterpartyId` (S1)** is the grouping key for the Negotiation Memory Store.

---

## Diagram 1 — System-Wide Overview

All 9 backend services, cross-cutting workflows, data stores, and the frontend, showing primary data flows.

```mermaid
flowchart TD
    UI([Contract Editor UI])
    DASH([Analytics Dashboard])

    S1[Service 1\nDocument Processing\ndeterministic]
    S2[Service 2\nContract Analysis]
    S3[Service 3\nRedline & Suggestion]
    S4[Service 4\nDrafting]
    S5[Service 5\nDocument Intelligence]
    S6[(Service 6\nPlaybook & Rules)]
    S7[(Service 7\nRepository + Search\nNeon PG: metadata · FTS · pgvector\n+ shared diff engine)]
    S8[Service 8\nObligation & Monitoring]
    S9[Service 9\nAnalytics — SQL views]
    NMS[(Negotiation Memory\nappend-only event log\npatterns = read-time GROUP BY)]

    UI -->|PDF/DOCX upload| S1
    S1 -->|clauses + types + metadata\ncharStart/charEnd + counterpartyId| S2
    S2 -->|flagged clauses + per-clause\n& aggregate risk + citations| S3
    S3 -->|redlines + rationale| UI

    S6 -->|type-keyed rules| S2
    S6 -->|preferred + fallback language| S3
    NMS -->|counterparty pattern view\n+ last-closed text| S3

    S1 -->|contract + metadata| S7
    S2 -->|risk scores| S9
    S8 -->|obligations + renewals| S9
    S1 -->|metadata| S9

    S7 -->|corpus vector search| S4
    S7 -->|corpus read| S6
    S1 -->|clause array| S5

    S5 -->|summaries · cited Q&A · nav| UI
    S5 -.->|Easy Prompt routed to| S3
    S5 -.->|Easy Prompt routed to| S4
    S4 -->|drafted clauses| UI
    S8 -->|alerts + obligations| UI
    S9 -->|dashboards + reports| DASH

    S3 -->|decision events| NMS
    UI -->|accept/reject + final text| NMS

    S7 -->|version pairs| VCW[Version Comparison\nshared diff engine]
    VCW -->|clause-aligned tracked changes| UI
    S3 -->|reuses| VCW
```

---

## Diagram 2 — Service 1: Document Processing

**Purpose:** Deterministic ingestion — parse the document, segment into clauses with character offsets, tag clause types, and extract ~50 structured metadata fields. Foundation every downstream citation and structural check depends on. Zero LLM.

**Integrations:** Feeds S2 (analysis), S5 (clause array for Q&A), S7 (storage), and S9 (metadata). Emits the canonical clause types, `charStart`/`charEnd` offsets, and normalized `counterpartyId` used platform-wide. Scanned/OCR PDFs are out of scope by design.

```mermaid
flowchart TD
    A([Document Upload\nPDF or DOCX]) --> FMT{Format?}
    FMT -->|DOCX| DX[DOCX Parser\nDeterministic\ntext + explicit heading styles + numbering]
    FMT -->|PDF| B[PDF Parser\nDeterministic\nraw text + font sizes · bold · whitespace · coords]

    DX --> C[Canonical Text + Structure Signal\nsingle source for charStart/charEnd]
    B --> C

    C --> D[Heading & Structure Detector\nDeterministic\ndecimal · alpha · roman · ALL CAPS · bold\nfallback: blank-line paragraphs]
    D --> E[Clause Boundary Segmentation\nDeterministic]
    E --> TN[Clause-Type Normalizer\nDeterministic\nsynonym/fuzzy dictionary: heading text → canonical type]
    TN --> F[Clause Array\nid · type · text · charStart · charEnd]

    C --> G[NER + Pattern Matching Engine\nDeterministic]
    G --> G1[Party & Org Extraction\n+ normalized counterpartyId]
    G --> G2[Date Extraction]
    G --> G3[Financial Field Extraction]
    G --> G4[Governing Law Detection]
    G --> G5[Notice & Address Extraction]

    G1 --> H[Metadata Object\n~50 fields]
    G2 --> H
    G3 --> H
    G4 --> H
    G5 --> H

    UPL([Upload Context]) --> PO[Paper Origin Flag\nDeterministic\nown · counterparty]

    F --> OUT([Output Contract\nclauses[] + metadata + paperOrigin + canonical text\nto Service 2 / Service 7])
    H --> OUT
    PO --> OUT
```

---

## Diagram 3 — Service 2: Contract Analysis Decision Cycle

**Purpose:** Analyzes segmented clauses to flag issues (missing, prohibited, non-standard, high-risk, vague, inconsistent) and produce per-clause + per-contract risk scores, switching analysis mode by `paperOrigin`. Layer 1 is deterministic (clause-type list only); Layer 2 uses batched LLM calls on clause bodies.

**Integrations:** Consumes S1 clauses/types and S6 type-keyed rules (matched per-clause to shrink prompts). Emits flagged clauses + risk scores to S3 and S9. Scoring weights come from S6 config.

```mermaid
flowchart TD
    IN([Input from Service 1\nclauses[] · types · metadata · paperOrigin])
    PB[(Playbook\nService 6)]

    subgraph L1 [Layer 1 — Heading-Level Structural Checks — Deterministic]
        HL[Extract Clause Type List\nheadings only]
        MC[Missing Clause Detection\ntypes vs required list]
        PC[Prohibited Clause Detection\ntypes vs prohibited list]
        HL --> MC
        HL --> PC
    end

    RM[Clause↔Rule Matcher\nDeterministic\nattach matching playbook rule\nper clause by type]

    subgraph L2 [Layer 2 — Content Analysis — Full Clause Text]
        CPO{paperOrigin?}
        RE[Regex Pre-filter\nInconsistent Term Candidates]
        OWN[LLM Batch Call — Own Paper\nNon-standard · High-risk · Vague\n+ confirm inconsistent terms]
        CPY[LLM Batch Call — Counterparty Paper\nDeviation vs Preferred\n+ High-risk · Vague\n+ confirm inconsistent terms]
        CPO -->|own paper| RE
        RE --> OWN
        CPO -->|counterparty paper| CPY
    end

    IN --> HL
    IN --> RM
    PB --> HL
    PB --> RM
    RM --> CPO
    RM --> OWN
    RM --> CPY

    MC --> AGG[Deterministic Aggregation + Risk Scoring\nseverity flags → numeric score\nweights from playbook config]
    PC --> AGG
    OWN --> AGG
    CPY --> AGG

    AGG --> OUT([Flagged Clauses + Risk Scores\n+ charStart/charEnd citations\n+ deviation flags\nto Service 3])

    style OWN fill:#fff3ee,stroke:#eb6c36
    style CPY fill:#fff3ee,stroke:#eb6c36
```

---

## Diagram 4 — Service 3: Redline & Suggestion Pipeline

**Purpose:** Turns flagged clauses from S2 into surgical tracked-change redlines with alternatives, plain-language rationale, and counterparty-ready comments, governed by stance mode, playbook language, and negotiation memory. One bundled LLM call per clause; the LLM emits replacement text, and the deterministic diff engine renders the tracked changes.

**Integrations:** Consumes S2 flags, S6 preferred/fallback language, and NMS counterparty patterns. Reuses the shared diff engine (also used by the Version Comparison workflow). Writes decision events to NMS.

```mermaid
flowchart TD
    IN([Flagged Clauses\nfrom Service 2]) --> SM[Stance Mode Filter\nDeterministic\nLight / Balanced / Firm]
    SM -->|controls which flags\nget redlines| QUEUE[Clause Queue\nfor Redline Generation]

    NMS[(Negotiation\nMemory Store)] --> SC[Stance Context\nDeterministic\naccept/reject stats + patterns\nx stance mode]
    PB[(Playbook\nPreferred Language)] --> MAIN

    SC --> MAIN
    QUEUE --> MAIN

    MAIN[LLM Call — per Clause or Batched\nBundled Structured Output\nstance baked in]
    MAIN --> T1[Replacement Clause Text]
    MAIN --> R2[Alternative Language\n2–3 proposals]
    MAIN --> R3[Plain-Language Explanation]
    MAIN --> R4[Counterparty Negotiation Comment]

    T1 --> DIFF[Char-Level Tracked-Change Diff\nDeterministic — reuse Version Comparison engine]
    DIFF --> R1[Preferred Position Redline\nsurgical tracked changes]

    R1 --> NIC[Non-Interference Check\nDeterministic\nchanged spans ⊆ flagged set]

    FT[Fallback Toggle\nDeterministic\nswap preferred → fallback\n→ re-diff] -.->|overrides| R1

    NIC --> RAT[Deterministic Rationale Field\nplaybook position + LLM output\nno extra LLM call]
    R2 --> RAT
    R3 --> RAT
    R4 --> RAT

    RAT --> OUT([Redline Output\n+ Rationale to UI])

    UIR([User Refinement Instruction]) --> MPR[Multi-Pass Refinement\nLLM Call\ninstruction + clause + prior redline]
    R1 --> MPR
    MPR --> DIFF2[Char-Level Diff\nDeterministic] --> ROUT([Refined Redline Output])

    style MAIN fill:#fff3ee,stroke:#eb6c36
    style MPR fill:#fff3ee,stroke:#eb6c36
```

---

## Diagram 5 — Service 4: Drafting Paths

**Purpose:** Generates contract language (single clauses, first-draft documents, memos, precedent-matched clauses) via a cost-tiered cascade — playbook lookup → frequency reuse → LLM only as last resort. Requests branch on mode first; only single-clause requests enter the cascade.

**Integrations:** Reads S6 playbook and S7 (context-scoped last-N frequency query + precedent vector search).

```mermaid
flowchart TD
    REQ([User Drafting Request\nmode + clause type + context]) --> MODE{Request Mode?}

    MODE -->|Single clause / rewrite| CHK1{Playbook has\npreferred clause\nfor this type?}
    MODE -->|First-draft document| TE[Template Engine\nVariable Fill — Deterministic]
    MODE -->|Precedent-matched| VS[Vector Search\nService 7 corpus — Deterministic]
    MODE -->|Memo / action letter| MD[LLM Call\nMemo & Letter Drafting]

    CHK1 -->|Yes| PBC[Return Playbook Clause\nDeterministic — Service 6 lookup]
    CHK1 -->|No| CHK2{Frequency Tracker\ncontext-scoped by metadata:\nclause above threshold\nin last N contracts?}

    CHK2 -->|Yes| FTC[Return Most Common Version\nDeterministic\nService 7: scoped last-N query · aggregate · rank]
    CHK2 -->|No| GEN{Rewrite or\nnovel clause?}

    GEN -->|NL rewrite prompt| NL[LLM Call\nClause Rewrite on NL Prompt]
    GEN -->|Novel clause type| DC[LLM Call\nClause Generation]

    TE --> OUT([Drafted Output\nto Contract Editor UI])
    TE -.->|optional on-demand| TEP[LLM Call — Optional\nPolish Conditional Clauses]
    VS --> VSP[LLM Call\nStyle-Matched Clause Generation]

    S6[(Service 6\nPlaybook)] --> CHK1
    S7[(Service 7\nRepository)] --> FTC
    S7 --> VS

    PBC --> OUT
    FTC --> OUT
    NL --> OUT
    DC --> OUT
    TEP --> OUT
    VSP --> OUT
    MD --> OUT

    style NL fill:#fff3ee,stroke:#eb6c36
    style TEP fill:#fff3ee,stroke:#eb6c36
    style VSP fill:#fff3ee,stroke:#eb6c36
    style MD fill:#fff3ee,stroke:#eb6c36
    style DC fill:#fff3ee,stroke:#eb6c36
```

---

## Diagram 6 — Service 5: Document Intelligence Flows

**Purpose:** In-editor intelligence: risk-aware contract summarization, redline-thread summarization, cited Q&A, Easy Prompt (NL→structured legal prompt), Chat2 web research, and deterministic clause navigation. Single-document Q&A reads the S1 clause array directly (no vector RAG).

**Integrations:** Reads S1 clause array and S2 risk flags (for risk-aware summaries). Easy Prompt routes its structured output into S3/S4. Ad-hoc Q&A answers are cached for S9 tabular review.

```mermaid
flowchart TD
    ACT([User Action in Editor]) --> TYPE{Request Type?}

    TYPE -->|Summarize contract| CS[LLM Call\nRisk-Aware Contract Summarization\ngrounded on S1 metadata + S2 risk flags]
    TYPE -->|Summarize redline thread| RT[LLM Call\nRedline Thread Summarization]
    TYPE -->|Contract Q&A| QL[Load S1 Clause Array\nDeterministic\nfull-context + charStart/charEnd]
    TYPE -->|Easy Prompt| EP[LLM Call\nNL → Structured Legal Prompt]
    TYPE -->|Chat2 Research| WS[Web Search\nfrom within editor]
    TYPE -->|Navigate clauses| NI[Clause Navigation Index\nDeterministic\nfrom Service 1 clause type tags]

    QL --> QA[LLM Call\nAnswer + Character-Level Citation]
    WS --> CR[LLM Call\nSynthesize Web Result\nwith Contract Context\nInline cited answer]

    CS --> UI([Output to\nContract Editor UI])
    RT --> UI
    QA --> UI
    CR --> UI
    NI --> UI
    EP -->|structured prompt routed to| DS([Service 3 / Service 4\nexecutes the real action])

    style CS fill:#fff3ee,stroke:#eb6c36
    style RT fill:#fff3ee,stroke:#eb6c36
    style QA fill:#fff3ee,stroke:#eb6c36
    style EP fill:#fff3ee,stroke:#eb6c36
    style CR fill:#fff3ee,stroke:#eb6c36
```

---

## Diagram 7 — Service 6: Playbook Routing + One-Time Bootstrap

**Purpose:** Selects the applicable standards for an incoming contract (all matching practice areas, merged by fixed precedence) and serves preferred/acceptable/prohibited language + fallbacks from a unified store. A one-time LLM bootstrap seeds preferred language + acceptable variations from the existing corpus; humans own all edits thereafter via CRUD. No versioning/audit (out of scope).

**Integrations:** Serves S2 and S3. Bootstrap reads the S7 corpus. Prohibited terms are seeded from template defaults + human CRUD (not mined from executed agreements).

```mermaid
flowchart TD
    REQ([Contract Type Signal\nupload context OR Service 1 metadata]) --> RT{Practice Area Routing\nselect ALL applicable}

    RT --> APP[Applicable Rule-Sets — Deterministic\nHIPAA · GDPR · SaaS MSA · NDA · DPA\nmerged by fixed precedence]

    APP --> PB[(Unified Playbook Store\nper clause type:\npreferred · acceptable variations\nprohibited · fallback language)]

    PB --> OUT([Playbook Output\nto Service 2 and Service 3])

    subgraph BOOT [One-Time Bootstrap — runs once per org]
        S7C[(Service 7\nExecuted Agreements Corpus)] --> BL[Batch LLM Call\nExtract preferred language\n+ common acceptable variations ONLY]
        BL --> SEED[Seed Playbook\nvia Service 6 CRUD]
        TMPL([Pre-built template defaults\nprohibited terms + base rules]) --> SEED
    end

    LT([Legal Team]) -->|Self-Service CRUD\nprohibited terms + ongoing edits| SEED
    SEED --> PB

    style BL fill:#fff3ee,stroke:#eb6c36
```

---

## Diagram 8 — Service 7: Contract Repository & Search Flow

**Purpose:** Single source of truth for all contracts — stores documents + metadata, exposes keyword/faceted/NL search, amendment linking, redline-history lookup, and version-pair fetch. Smart Search is the only LLM call (NL → constrained structured filters + optional semantic query). Consolidated on Neon Postgres + pgvector with embedding-on-write.

**Integrations:** Stores contracts from S1. Serves S4 (precedent vector search) and S6 (corpus read). Hosts the shared diff engine reused by S3 and the Version Comparison workflow. Redline History Index is fed by S3 decision logs / NMS.

```mermaid
flowchart TD
    INC([Incoming Contract\nfrom Service 1 or Direct Upload]) --> OBJ[Object Storage\nsingle source of truth]
    OBJ --> MDB[(Metadata DB\nNeon Postgres)]
    OBJ --> EMB[Embedding on Write\nDeterministic model call]
    EMB --> VEC[(Vector Index\npgvector on Neon\n— or Qdrant if scale demands)]

    MDB --> FTI[Full-Text Index\npg tsvector / Typesense]
    MDB --> PCL[Parent-Child Links\nAmendment / Addendum / Version]

    S3N([Service 3 / Negotiation\nMemory Store]) -->|prior positions per clause| RHI[Redline History Index]

    USR([User Search Query]) --> QT{Query Type?}
    QT -->|Keyword / structured| FTS[Full-Text Search\nDeterministic]
    QT -->|Faceted metadata filters| FF[Faceted Filtering\nDeterministic]
    QT -->|Natural language| SS[LLM Call — single\nNL to structured filters\n+ optional semantic query string\nconstrained to metadata schema]

    SS -->|structured filters| FF
    SS -->|semantic query| VS[Vector Search\nDeterministic]
    VS --> VEC
    FTI --> FTS
    MDB --> FF

    FTS --> MRG[Merge Results\nDeterministic]
    FF --> MRG
    VS --> MRG
    MRG --> RES([Search Results\nto Caller])

    S4([Service 4 Drafting]) -->|precedent retrieval| VEC
    S6([Service 6 Playbook\nBootstrap]) -->|corpus read| OBJ

    style SS fill:#fff3ee,stroke:#eb6c36
```

---

## Diagram 9 — Service 8: Obligation & Monitoring Decision Cycle

**Purpose:** Extracts every commitment/deadline/deliverable once at ingest (LLM, grounded on S1 metadata), then runs a single daily deterministic monitor pass that fires deadline alerts and renewal recommendations. On the renewal path, recommendation + compliance are one bundled LLM call; compliance can also be triggered on upload/on-demand.

**Integrations:** Consumes S1 metadata and S6 playbook. Reuses S2's counterparty-deviation rubric for compliance consistency. Feeds S9.

```mermaid
flowchart TD
    S1([Contract Processed by Service 1\n+ extracted dates/parties/financials]) --> EXT[LLM Call\nObligation Extraction\ngrounded with S1 metadata\ncommitment · owner · deadline · deliverable]
    EXT --> ODB[(Obligations Store)]

    CRON((Cron\nDaily — single pass)) --> MON[Monitor\nDeterministic\ndeadline check + renewal-window check]
    ODB --> MON

    MON --> DG{Days to\nDeadline?}
    DG -->|within threshold| DA[Fire Deadline Alert]
    DG -->|outside| SKIP([No Action])

    MON --> RG{Days to\nExpiry?}
    RG -->|30–90 days| RRCV[LLM Call — Bundled\nRenewal Rec + Compliance\nextend/renegotiate/close · pass/fail + issues\nreuses S2 deviation rubric]
    RG -->|outside window| SKIP

    EVT((Upload Event\nor On-Demand Request)) --> ET[Deterministic Trigger]
    ET --> CV[LLM Call\nCompliance Verification only\nreuses S2 deviation rubric]

    PB[(Playbook — Service 6)] --> RRCV
    PB --> CV

    RRCV --> CVG{Compliance\nResult?}
    CV --> CVG
    CVG -->|Pass| PA[Proceed Alert + recommendation]
    CVG -->|Fail| FA[Flag Issues Alert + recommendation]

    DA --> NOTIF([Alerts + Recommendations\nto UI / Notification System])
    PA --> NOTIF
    FA --> NOTIF

    style EXT fill:#fff3ee,stroke:#eb6c36
    style RRCV fill:#fff3ee,stroke:#eb6c36
    style CV fill:#fff3ee,stroke:#eb6c36
```

---

## Diagram 10 — Service 9: Analytics Aggregation

**Purpose:** Turns upstream data (S1 metadata, S2 risk scores, S8 obligations/renewals) into dashboards and reports via deterministic SQL views over the shared Neon Postgres. Zero LLM. Portfolio risk is severity-weighted, not averaged.

**Integrations:** Pure consumer of S1/S2/S8 schemas (frozen as a read contract via DB views). Ad-hoc tabular columns read an S5-written cached-answers table — no LLM in S9.

```mermaid
flowchart TD
    PG[(Shared Postgres — Neon\nS1 metadata · S2 risk scores\nS8 obligations + renewal text)]

    PG --> VW[Deterministic View Layer\nSQL views / roll-up queries\nno separate store, no LLM]

    CACHE[(Cached Q&A Answers\nwritten by Service 5\none row per contract×question)] -.->|optional ad-hoc columns| TAB

    VW --> CID[Contract Intelligence Dashboard\naggregation over extracted fields]
    VW --> PRR[Portfolio Risk Report\nseverity-weighted roll-up\nNOT naive average]
    VW --> CVT[Contract Value Tracking\nsum + group financial fields]
    VW --> TAB[Tabular Review\nrow = contract · column = field\n+ optional S5-cached NL columns]
    VW --> REN[Renewal Dashboard\nrenewal dates + risk\n+ S8 recommendation text]

    CID --> UI([Analytics Dashboard UI])
    PRR --> UI
    CVT --> UI
    TAB --> UI
    REN --> UI
```

---

## Diagram 11 — Review Pipeline & Autonomous Review Trigger

**Purpose:** Event-triggered, code-orchestrated pipeline that runs S1→S6→S2→S3 on upload (S1 parse and S6 playbook fetch run concurrently), then a deterministic threshold gate either auto-applies redlines or escalates to a human. "Autonomous" means event-triggered, not LLM-directed — code owns all flow. The gate applies hard-stops (any prohibited/missing clause, quality failure, or single high-risk clause forces escalation), not just an aggregate score.

**Integrations:** Orchestrates S1, S6, S2, S3. S3 reads NMS itself for counterparty context; human accept/reject decisions are logged to NMS.

```mermaid
sequenceDiagram
    participant U as User / Upload Event
    participant ART as Autonomous Review Trigger
    participant NMS as Negotiation Memory Store
    participant S6 as Service 6 — Playbook & Rules
    participant S1 as Service 1 — Document Processing
    participant S2 as Service 2 — Contract Analysis
    participant S3 as Service 3 — Redline & Suggestion
    participant GATE as Threshold Gate (Deterministic)
    participant UI as Contract Editor UI

    U->>ART: Upload event (webhook / queue)

    par Parse and playbook fetch run concurrently
        ART->>S1: Process PDF/DOCX
        Note over S1: Deterministic parse → NER/regex/layout<br/>→ clauses[] + metadata + charStart/charEnd
        S1-->>ART: clauses[] + metadata + paperOrigin
    and
        ART->>S6: Fetch playbook for contract type<br/>(from upload context)
        S6-->>ART: Preferred language, rules, prohibited terms
    end

    ART->>S2: Analyze clauses (+ playbook)
    Note over S2: Deterministic structural gates first,<br/>then batched LLM content analysis
    S2-->>ART: Flagged clauses + per-clause & aggregate<br/>risk + prohibited/missing flags + citations

    ART->>S3: Generate redlines
    Note over S3: S3 reads NMS itself for counterparty context,<br/>then LLM: redlines, explanations, comments
    S3->>NMS: Read counterparty pattern view (deterministic)
    NMS-->>S3: Counterparty context
    S3-->>ART: Redlines + rationale + quality result

    ART->>GATE: Apply deterministic rules

    alt Hard-stop (prohibited/missing clause,<br/>quality fail, or max per-clause risk high)
        GATE->>UI: Escalate to human + attach rationale
        Note over UI: Human accepts / rejects;<br/>decisions logged to NMS
    else Aggregate AND max per-clause risk below threshold
        GATE->>UI: Auto-apply redlines (semi-autonomous)
        Note over UI: Rationale attached to every change
    end

    UI-->>U: Review results displayed in editor
```

---

## Diagram 12 — Negotiation Memory Store

**Purpose:** A deterministic, append-only decision log giving the platform negotiation memory. Counterparty patterns are derived at read time (GROUP BY over the event log), not maintained as a separate entity. Zero LLM.

**Integrations:** Written by S3 (decision events) and the editor (accept/reject + final agreed text). Read only by S3, before its LLM call. Requires a normalized `counterpartyId` from S1 as the grouping key.

```mermaid
flowchart TD
    S3W[Service 3\nRedline Generation] -->|create event:\nrecommended stance + position offered\noutcome = pending| NMS

    UIR([User Accept / Reject\nRedline in Editor]) -->|append outcome:\naccepted/rejected + final agreed text| NMS

    S1[(Service 1\nnormalized counterpartyId)] -.->|grouping key| NMS

    NMS[(Negotiation Memory Store\nappend-only decision_event log\ncounterpartyId · clauseType\npositionOffered · outcome · finalText)]

    NMS --> AGG[Deterministic Pattern Aggregation\nGROUP BY counterpartyId + clauseType\nacceptance rate per position\nlast-closed clause text]

    AGG -->|counterparty pattern + last-closed text\ninjected into S3 LLM prompt| S3R[Service 3\nRedline Generation\nreads before LLM call]
```

**Data shape — `decision_event`:** `id`, `contractId`, `counterpartyId` (normalized), `clauseType`, `positionOffered` (preferred/fallback-N), `recommendedStance`, `outcome` (accepted/rejected/countered, nullable until user acts), `finalText`, `timestamp`. Patterns are a view: `GROUP BY counterpartyId, clauseType → acceptance rate per position, most-recent finalText`.

---

## Diagram 13 — Version Comparison Workflow

**Purpose:** Diff any two stored contract versions into tracked changes for the editor, with an optional on-demand LLM semantic-change summary. Clauses are aligned by stable S1 clause id before the character diff (robust to insertion/deletion/reorder). Diff and version-write are deterministic and live in Service 7 — this is the shared diff engine reused by S3.

**Integrations:** Reads version pairs from S7's version-aware repository. Depends on stable S1 clause ids. Diff engine is reused by S3 for redline markup.

```mermaid
flowchart TD
    UI([User selects two versions\ne.g. v2 and v3\nin Contract Editor])

    S7[(Service 7\nVersion-Aware Repository\nv1 · v2 · v3 · ...\nparent-child version links)]

    UI --> FV[Fetch Both Versions\nfrom Service 7 — Deterministic]
    S7 --> FV

    FV --> ALIGN[Align Clauses by Stable Clause ID\nDeterministic\nrobust to insertion / deletion / reorder]
    ALIGN --> DIFF[Character-Level Text Diff\nDeterministic\nper aligned clause · compute deltas]

    DIFF --> CS[Change Set\ninserted · deleted · modified text\nper clause · with charStart/charEnd]

    CS --> DISP([Tracked-Change View\nin Contract Editor UI\naccept · reject · comment per change])

    CS --> SEM[LLM Call — Optional\nSemantic Change Summary\ne.g. 'Section 4.2 shifts liability cap\nfrom fixed amount to uncapped']
    SEM --> DISP

    SAVE([User saves edited version]) --> WV[Write New Version\nto Service 7 — Deterministic\nincrement version · link to parent]
    WV --> S7

    style SEM fill:#fff3ee,stroke:#eb6c36
```

---

## Legend

| Symbol | Meaning |
|---|---|
| `[ ]` | Service, processing step, or deterministic component |
| `{ }` | Decision point / branch |
| `[( )]` / `(( ))` | Database or event trigger |
| `([ ])` | Terminal: system input or output |
| Orange node border | LLM Call (non-deterministic content generation) |
| Plain node border | Deterministic (pure code, no LLM) |
| Dashed arrow `-.->` | Optional / override path |

## Service Type Summary

| Service | Type | LLM Calls |
|---|---|---|
| S1 — Document Processing | Deterministic | 0 |
| S2 — Contract Analysis | Fixed Workflow | 1 (batched) |
| S3 — Redline & Suggestion | LLM Calls | 1 per clause |
| S4 — Drafting | Cascade | 0–1 per request |
| S5 — Document Intelligence | LLM + Fixed Workflows | 1 per request |
| S6 — Playbook & Rules | Deterministic | 0 ongoing; 1 batch bootstrap |
| S7 — Repository & Search | Deterministic + versioning | 1 (Smart Search) |
| S8 — Obligation & Monitoring | LLM + Scheduled Jobs | 1–2 per event |
| S9 — Analytics | Deterministic | 0 |
| Review Pipeline (Diagram 11) | Orchestration | 0 (own layer) |
| Negotiation Memory Store (Diagram 12) | Deterministic | 0 |
| Version Comparison (Diagram 13) | Fixed Workflow | 0–1 (optional) |
