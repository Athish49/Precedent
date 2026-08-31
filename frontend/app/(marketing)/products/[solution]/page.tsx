import Link from 'next/link';
import { notFound } from 'next/navigation';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Feature {
  name: string;
  description: string;
  mockup?: React.ReactNode;
}

interface SolutionConfig {
  name: string;
  tagline: string;
  intro: string;
  appLink: string;
  features: Feature[];
  howItWorks: [string, string, string];
}

// ─── Inline Mockups ───────────────────────────────────────────────────────────

function MetadataMockup() {
  const fields = [
    { label: 'Parties', value: 'Acme Corp · Beta LLC' },
    { label: 'Governing law', value: 'New York' },
    { label: 'Liability cap', value: '$500,000' },
    { label: 'Effective date', value: '2024-01-15' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Extracted metadata
      </div>
      <div className="divide-y divide-border">
        {fields.map((f) => (
          <div key={f.label} className="flex items-center justify-between px-3 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{f.label}</span>
            <span className="text-xs font-medium text-foreground">{f.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FacetedFilterMockup() {
  const filters = ['Counterparty: Acme Corp', 'Status: Active', 'Type: MSA'];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Active filters
      </div>
      <div className="flex flex-wrap gap-2 px-3 py-3">
        {filters.map((f) => (
          <span
            key={f}
            className="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 text-[11px] font-medium text-primary"
          >
            {f}
          </span>
        ))}
        <span className="inline-flex items-center rounded-full border border-muted-foreground/20 bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          + Add filter
        </span>
      </div>
      <div className="border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
        12 contracts match
      </div>
    </div>
  );
}

function FlagTypesMockup() {
  const flags = [
    { type: 'Missing', severity: 'High', color: 'bg-destructive', badge: 'bg-destructive/15 text-destructive' },
    { type: 'Prohibited', severity: 'High', color: 'bg-destructive', badge: 'bg-destructive/15 text-destructive' },
    { type: 'Deviation', severity: 'Medium', color: 'bg-amber-400', badge: 'bg-amber-400/15 text-amber-600 dark:text-amber-400' },
    { type: 'Non-standard', severity: 'Low', color: 'bg-sky-500', badge: 'bg-sky-500/15 text-sky-600 dark:text-sky-400' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Flag types
      </div>
      <ul className="divide-y divide-border">
        {flags.map((f) => (
          <li key={f.type} className="flex items-center justify-between px-3 py-2">
            <span className="flex items-center gap-2">
              <span className={cn('inline-block h-1.5 w-1.5 rounded-full shrink-0', f.color)} />
              <span className="text-xs font-medium text-foreground">{f.type}</span>
            </span>
            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', f.badge)}>
              {f.severity}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CitationMockup() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Flag citation
      </div>
      <div className="px-3 py-3 space-y-2 text-xs">
        <p className="text-foreground font-medium">Missing limitation of liability clause</p>
        <p className="text-muted-foreground leading-relaxed">
          …shall be liable for any indirect, incidental or consequential damages{' '}
          <span className="rounded bg-destructive/20 px-0.5 text-destructive font-medium">
            [missing cap]
          </span>{' '}
          arising out of this agreement…
        </p>
        <div className="rounded border border-border bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground">
          offset 4,102–4,189 · §9.3 Limitation
        </div>
      </div>
    </div>
  );
}

function StancesMockup() {
  const stances = [
    { label: 'Light', desc: 'Minimal change', active: false },
    { label: 'Balanced', desc: 'Standard position', active: true },
    { label: 'Firm', desc: 'Full playbook', active: false },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Negotiation stance
      </div>
      <div className="flex divide-x divide-border">
        {stances.map((s) => (
          <div
            key={s.label}
            className={cn(
              'flex flex-1 flex-col items-center px-3 py-3',
              s.active && 'bg-primary/10',
            )}
          >
            <span className={cn('text-xs font-semibold', s.active ? 'text-primary' : 'text-foreground')}>
              {s.label}
            </span>
            <span className="mt-0.5 text-[10px] text-muted-foreground text-center">{s.desc}</span>
            {s.active && (
              <span className="mt-1.5 rounded-full bg-primary/20 px-2 py-0.5 text-[9px] font-semibold text-primary">
                Selected
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function InlineDecisionMockup() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Redline decision · §8.1
      </div>
      <div className="px-3 py-3 text-xs space-y-1.5">
        <p className="font-mono text-muted-foreground line-through text-destructive/80">
          …fees paid in the thirty (30) days prior…
        </p>
        <p className="font-mono text-emerald-600 dark:text-emerald-400">
          + …fees paid in the twelve (12) months prior…
        </p>
        <div className="mt-2 flex items-center gap-2">
          <span className="rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
            Accept
          </span>
          <span className="rounded border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold text-destructive">
            Reject
          </span>
          <span className="rounded border border-border bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
            Edit
          </span>
        </div>
      </div>
    </div>
  );
}

function ProvenanceMockup() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Draft output · Indemnification clause
      </div>
      <div className="px-3 py-3 text-xs leading-relaxed text-muted-foreground space-y-2">
        <p>
          Each party shall indemnify, defend, and hold harmless the other from any third-party
          claims arising from its own breach of this Agreement.
        </p>
        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
            Playbook
          </span>
          <span className="text-[10px] text-muted-foreground self-center">Mutual indemnity · preferred language</span>
        </div>
      </div>
    </div>
  );
}

function PrecedentSearchMockup() {
  const results = [
    { clause: 'Mutual indemnification', score: '94%' },
    { clause: 'Limited liability scope', score: '81%' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Precedent search · Indemnity
      </div>
      <ul className="divide-y divide-border">
        {results.map((r) => (
          <li key={r.clause} className="flex items-center justify-between px-3 py-2.5">
            <span className="text-xs font-medium text-foreground">{r.clause}</span>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
              {r.score}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GateChecklistMockup() {
  const gates = [
    { label: 'No prohibited terms detected', pass: true },
    { label: 'All required clauses present', pass: true },
    { label: 'Liability cap below threshold — escalated', pass: false },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Hard-stop checklist
      </div>
      <ul className="divide-y divide-border">
        {gates.map((g) => (
          <li key={g.label} className="flex items-center gap-2.5 px-3 py-2.5">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', g.pass ? 'bg-emerald-500' : 'bg-amber-400')} />
            <span className={cn('text-xs', g.pass ? 'text-foreground' : 'font-medium text-amber-600 dark:text-amber-400')}>
              {g.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AuditTrailMockup() {
  const events = [
    { time: '09:14', label: 'Pipeline triggered on upload' },
    { time: '09:14', label: 'Gate checklist evaluated — 2/3 pass' },
    { time: '09:15', label: 'Safe changes auto-applied' },
    { time: '09:15', label: 'Deviation escalated for review' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Audit trail
      </div>
      <ul className="divide-y divide-border">
        {events.map((e, i) => (
          <li key={i} className="flex items-center gap-2.5 px-3 py-2">
            <span className="font-mono text-[10px] text-muted-foreground w-8 shrink-0">{e.time}</span>
            <span className="text-xs text-foreground">{e.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PlaybookRuleMockup() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Rule · Limitation of Liability
      </div>
      <div className="px-3 py-3 space-y-2 text-xs">
        <div className="rounded-md border border-border bg-background px-2.5 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Preferred language</p>
          <p className="text-[11px] text-muted-foreground font-mono leading-relaxed">
            …liability shall not exceed total fees paid in the preceding twelve (12) months…
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex items-center rounded-full border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold text-destructive">
            Required
          </span>
          <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
            High risk weight
          </span>
        </div>
      </div>
    </div>
  );
}

function PlaybookLayersMockup() {
  const books = [
    { name: 'Enterprise SaaS MSA', precedence: 1, active: true },
    { name: 'HIPAA DPA', precedence: 2, active: true },
    { name: 'Standard NDA', precedence: 3, active: false },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Playbook stack · Precedence order
      </div>
      <ul className="divide-y divide-border">
        {books.map((b) => (
          <li key={b.name} className="flex items-center gap-2.5 px-3 py-2.5">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-muted-foreground">
              {b.precedence}
            </span>
            <span className={cn('flex-1 text-xs', b.active ? 'font-medium text-foreground' : 'text-muted-foreground')}>
              {b.name}
            </span>
            {b.active && (
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
                Active
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function QAMockup() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Contract Q&A
      </div>
      <div className="divide-y divide-border text-xs">
        <div className="px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Question</p>
          <p className="text-foreground font-medium">What is the notice period for termination for convenience?</p>
        </div>
        <div className="px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Answer</p>
          <p className="text-muted-foreground">
            Either party may terminate with{' '}
            <span className="rounded bg-amber-200/70 px-0.5 text-foreground dark:bg-amber-700/40 font-medium">
              60 days&apos; written notice
            </span>
            .
          </p>
          <div className="mt-2 rounded border border-border bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground">
            offset 3,210–3,248 · §12.2
          </div>
        </div>
      </div>
    </div>
  );
}

function PortfolioQAMockup() {
  const rows = [
    { contract: 'MSA — Acme Corp', answer: '60 days' },
    { contract: 'NDA — Beta LLC', answer: '30 days' },
    { contract: 'SaaS — Gamma Inc', answer: '90 days' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="grid grid-cols-2 border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <span>Contract</span>
        <span>Notice period</span>
      </div>
      {rows.map((r) => (
        <div key={r.contract} className="grid grid-cols-2 border-b border-border px-3 py-2 text-xs last:border-b-0">
          <span className="truncate text-foreground">{r.contract}</span>
          <span className="text-muted-foreground">{r.answer}</span>
        </div>
      ))}
    </div>
  );
}

function RiskDashboardMockup() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Risk distribution · Portfolio
      </div>
      <div className="px-3 py-3 space-y-2">
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full w-[19%] bg-destructive" />
          <div className="h-full w-[33%] bg-amber-400" />
          <div className="h-full w-[48%] bg-emerald-500" />
        </div>
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-destructive" />High 19%
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400" />Medium 33%
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />Low 48%
          </span>
        </div>
      </div>
    </div>
  );
}

function RenewalCalendarMockup() {
  const items = [
    { contract: 'MSA — Acme Corp', days: '28d', risk: 'High', badge: 'bg-destructive/15 text-destructive' },
    { contract: 'SaaS — Gamma Inc', days: '55d', risk: 'Med', badge: 'bg-amber-400/15 text-amber-600 dark:text-amber-400' },
    { contract: 'DPA — Beta LLC', days: '82d', risk: 'Low', badge: 'bg-sky-500/15 text-sky-600 dark:text-sky-400' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Upcoming renewals
      </div>
      <ul className="divide-y divide-border">
        {items.map((i) => (
          <li key={i.contract} className="flex items-center justify-between px-3 py-2.5">
            <span className="text-xs font-medium text-foreground">{i.contract}</span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[10px] text-muted-foreground">{i.days}</span>
              <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', i.badge)}>{i.risk}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Solutions Config ─────────────────────────────────────────────────────────

const SOLUTIONS: Record<string, SolutionConfig> = {
  clm: {
    name: 'Contract Lifecycle Management',
    tagline: 'Track every contract from creation to renewal',
    intro:
      'Precedent gives in-house teams a searchable, filterable repository with automatic metadata extraction, version lineage, and renewal alerting — all from PDF or DOCX ingestion.',
    appLink: '/repository',
    features: [
      {
        name: 'Automatic metadata extraction',
        description:
          'Parties, dates, governing law, liability caps, and financial terms extracted at ingestion. No manual data entry.',
        mockup: <MetadataMockup />,
      },
      {
        name: 'Faceted filtering',
        description:
          'Filter by counterparty, status, contract type, effective date range, or value. Combine filters freely. Smart search derives filter sets from plain-English queries.',
        mockup: <FacetedFilterMockup />,
      },
      {
        name: 'Version lineage',
        description:
          'Amendments and addenda are linked to their parent contracts. Compare any two versions as a tracked-change diff.',
      },
      {
        name: 'Renewal alerting',
        description:
          'Deadlines fire at 30, 60, and 90 days. Recommendations surface in the Obligations dashboard.',
      },
    ],
    howItWorks: ['Ingest PDF/DOCX', 'Extract metadata + clauses', 'Repository with filters & alerts'],
  },
  analysis: {
    name: 'Contract Analysis',
    tagline: 'Surface risks and obligations instantly',
    intro:
      "Precedent's analysis engine runs deterministic rules first — before any LLM — so every flag is typed, severity-graded, and character-level cited back to the source.",
    appLink: '/home',
    features: [
      {
        name: 'Deterministic-first detection',
        description:
          'Missing clauses, prohibited terms, and compliance deviations are detected by rule engine. Results are reproducible across runs.',
      },
      {
        name: 'Seven flag types',
        description:
          'Missing, prohibited, non-standard, high-risk, vague, inconsistent, deviation. Each flag is typed and carries a severity (low / medium / high).',
        mockup: <FlagTypesMockup />,
      },
      {
        name: 'Character-level citations',
        description:
          'Every flag links to an exact char_start / char_end offset. Click a flag and the document scrolls to the precise span.',
        mockup: <CitationMockup />,
      },
      {
        name: 'Playbook-driven compliance',
        description:
          'Flags are evaluated against your active playbooks. Deviations show the found value vs. the policy max side by side.',
      },
    ],
    howItWorks: ['Upload contract', 'Run rule analysis', 'Review typed, cited flags'],
  },
  redlining: {
    name: 'Redlining & Negotiation',
    tagline: 'AI-generated redlines anchored to your playbooks',
    intro:
      'Generate tracked changes at three negotiation stances. Each redline is explained, cited, and comes with 2–3 alternatives — accept, reject, or edit inline.',
    appLink: '/home',
    features: [
      {
        name: 'Three negotiation stances',
        description:
          'Light (minimal change), Balanced (standard position), Firm (full playbook enforcement). Select per run or per clause.',
        mockup: <StancesMockup />,
      },
      {
        name: 'Tracked changes with alternatives',
        description:
          'Each redline shows the original, the proposed replacement, an explanation, and a counterparty comment. Cycle through 2–3 alternative positions.',
      },
      {
        name: 'Inline decisions',
        description:
          'Accept, reject, or accept-with-edit directly in the inspector. Accepted changes animate into the document canvas. Undo available for every action.',
        mockup: <InlineDecisionMockup />,
      },
      {
        name: 'Missing-clause insertion',
        description:
          "Analysis flags missing clauses; one click generates the insertion from your playbook's preferred language and presents it as a proposed redline.",
      },
    ],
    howItWorks: ['Select stance', 'Generate redlines', 'Accept / reject / edit inline'],
  },
  drafting: {
    name: 'Drafting Studio',
    tagline: 'Generate first drafts from templates and playbooks',
    intro:
      'Draft single clauses, full documents, or precedent-matched text. Every output carries a provenance tag — playbook language, frequency-based, or LLM-generated — so sourcing is always visible.',
    appLink: '/drafting',
    features: [
      {
        name: 'Four drafting modes',
        description:
          'Single clause, full document, precedent-matched, and legal memo. Each mode is purpose-built with the right inputs.',
      },
      {
        name: 'Provenance tagging',
        description:
          'Every draft output is tagged: Playbook (from preferred language), Frequency (drawn from corpus patterns), or LLM (generated). No opaque outputs.',
        mockup: <ProvenanceMockup />,
      },
      {
        name: 'Precedent search',
        description:
          'Before drafting, search your corpus for similar clauses by type and context. Similarity score shown for each match.',
        mockup: <PrecedentSearchMockup />,
      },
      {
        name: 'Easy Prompt routing',
        description:
          "Plain-English instructions ('make this indemnity mutual') are interpreted into a structured prompt and routed to the right drafting mode automatically.",
      },
    ],
    howItWorks: ['Choose mode + inputs', 'Generate draft', 'Copy or insert as redline'],
  },
  'autonomous-review': {
    name: 'Autonomous Review',
    tagline: 'AI-powered review that flags issues automatically',
    intro:
      'Upload a contract and trigger a full pipeline review. A hard-stop checklist evaluates prohibited terms, missing required clauses, and high-severity flags — safe changes auto-applied, deviations escalated.',
    appLink: '/automations',
    features: [
      {
        name: 'Hard-stop checklist',
        description:
          'Every run evaluates three gate conditions: prohibited terms present, required clauses missing, high-severity flags. Each condition is pass/fail with a reason.',
        mockup: <GateChecklistMockup />,
      },
      {
        name: 'Auto-apply and escalate',
        description:
          'Changes within configured thresholds are applied automatically. Deviations requiring judgment are escalated with a gate reason.',
      },
      {
        name: 'Trigger on upload',
        description:
          'Configure a webhook to trigger a review run automatically on every new contract upload. No manual step required.',
      },
      {
        name: 'Full audit trail',
        description:
          'Every run records its trigger, gate decision, gate reason, flags, and redlines. Full history accessible per contract and in the Automations list.',
        mockup: <AuditTrailMockup />,
      },
    ],
    howItWorks: ['Upload contract', 'Pipeline evaluates checklist', 'Auto-apply or escalate'],
  },
  playbooks: {
    name: 'Playbooks & Standards',
    tagline: 'Enforce negotiation positions at scale',
    intro:
      'Define preferred language, acceptable variations, prohibited terms, and fallback positions per clause type. Layer multiple playbooks with explicit precedence.',
    appLink: '/playbooks',
    features: [
      {
        name: 'Per-clause rules',
        description:
          'Each rule defines preferred language, a list of acceptable variations, prohibited terms, fallback language, and a risk weight. Required clauses are flagged when absent.',
        mockup: <PlaybookRuleMockup />,
      },
      {
        name: 'Precedence-ordered layering',
        description:
          'Multiple playbooks (HIPAA, GDPR, SaaS MSA, NDA, DPA) stack with explicit numeric precedence. Conflicts resolve automatically.',
        mockup: <PlaybookLayersMockup />,
      },
      {
        name: 'Resolved rule preview',
        description:
          'Before running analysis or redlines, preview the merged, precedence-ordered rule set for any contract type. Each rule is tagged with its source playbook.',
      },
      {
        name: 'Bootstrap from corpus',
        description:
          'Seed an initial playbook from your existing contract corpus. Precedent extracts patterns and creates a starting rule set automatically.',
      },
    ],
    howItWorks: ['Define rules', 'Layer playbooks', 'Rules drive analysis and redlines'],
  },
  'document-intelligence': {
    name: 'Document Intelligence',
    tagline: 'Extract structured data from any contract',
    intro:
      'Ask questions, get summaries, and run research — all grounded in character-level citations back to the source document. No hallucinated references.',
    appLink: '/home',
    features: [
      {
        name: 'Contract Q&A',
        description:
          'Ask any question about a contract in plain English. Answers cite exact character offsets — click a citation to highlight the source span in the document canvas.',
        mockup: <QAMockup />,
      },
      {
        name: 'Risk-aware summarization',
        description:
          'Summaries highlight the highest-risk items, not just the longest clauses. Redline threads are summarized separately.',
      },
      {
        name: 'Easy Prompt',
        description:
          'Plain-English instructions are interpreted into structured prompts and routed to the right action (redlines or drafting) automatically.',
      },
      {
        name: 'Portfolio Q&A columns',
        description:
          'Add NL question columns to the Analytics tabular view. Each cell is populated from Q&A cache and backed by a citation.',
        mockup: <PortfolioQAMockup />,
      },
    ],
    howItWorks: ['Ask a question', 'Cited answer grounded in document', 'Click citation to highlight'],
  },
  analytics: {
    name: 'Analytics & Reporting',
    tagline: 'Portfolio-wide insights and trend dashboards',
    intro:
      'Track risk distribution, contract value, and renewal exposure across your entire portfolio. Cross-filter between dashboard charts and the contract repository.',
    appLink: '/analytics',
    features: [
      {
        name: 'Portfolio risk dashboard',
        description:
          'Risk score distribution by severity across all contracts. Drill down by counterparty or contract type.',
        mockup: <RiskDashboardMockup />,
      },
      {
        name: 'Contract value tracking',
        description: 'Total portfolio value grouped by counterparty, type, or time period.',
      },
      {
        name: 'Renewal calendar',
        description:
          'Upcoming expirations at 30/60/90-day horizons with risk scores and recommendations.',
        mockup: <RenewalCalendarMockup />,
      },
      {
        name: 'Tabular mode with NL columns',
        description:
          'Export a structured table of every contract with metadata columns. Add plain-English query columns — each cell backed by a citation from Q&A cache.',
      },
    ],
    howItWorks: ['View dashboard', 'Drill down by dimension', 'Cross-filter to repository'],
  },
};

// ─── Components ───────────────────────────────────────────────────────────────

function HowItWorks({ steps }: { steps: [string, string, string] }) {
  return (
    <section id="how-it-works" className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl mb-10">
        How it works
      </h2>
      <div className="flex flex-col items-start gap-6 sm:flex-row sm:items-center sm:gap-0">
        {steps.map((step, i) => (
          <div key={step} className="flex sm:flex-1 items-center gap-0 w-full sm:w-auto">
            {/* Step */}
            <div className="flex flex-col items-center gap-3 flex-1">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 border-primary bg-primary/10 text-sm font-bold text-primary">
                {i + 1}
              </div>
              <p className="text-center text-sm font-medium text-foreground max-w-[120px]">{step}</p>
            </div>
            {/* Arrow (between steps) */}
            {i < 2 && (
              <div className="hidden sm:flex items-center px-2 shrink-0 self-start pt-5">
                <svg
                  className="h-4 w-4 text-muted-foreground"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export async function generateStaticParams() {
  return Object.keys(SOLUTIONS).map((slug) => ({ solution: slug }));
}

export default async function SolutionPage({
  params,
}: {
  params: Promise<{ solution: string }>;
}) {
  const { solution: slug } = await params;
  const config = SOLUTIONS[slug];
  if (!config) notFound();

  return (
    <div className="flex flex-col">
      {/* ── Hero ── */}
      <section className="mx-auto w-full max-w-7xl px-4 pb-12 pt-16 sm:px-6 lg:px-8">
        <p className="mb-4 text-sm font-medium text-muted-foreground">
          <Link href="/products" className="hover:text-foreground transition-colors">
            ← All Products
          </Link>
        </p>
        <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          {config.name}
        </h1>
        <p className="mt-3 text-xl text-muted-foreground">{config.tagline}</p>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted-foreground">
          {config.intro}
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            href={config.appLink}
            className={cn(buttonVariants({ variant: 'default', size: 'lg' }))}
          >
            Open in App
          </Link>
          <Link
            href="/products"
            className={cn(buttonVariants({ variant: 'outline', size: 'lg' }))}
          >
            ← All Products
          </Link>
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Features ── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl mb-10">
          Features
        </h2>
        <div className="grid gap-6 sm:grid-cols-2">
          {config.features.map((feature) => (
            <div
              key={feature.name}
              className="flex flex-col gap-4 rounded-2xl border border-border bg-muted/20 p-6"
            >
              <div>
                <h3 className="text-base font-semibold text-foreground">{feature.name}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {feature.description}
                </p>
              </div>
              {feature.mockup && (
                <div className="mt-auto">{feature.mockup}</div>
              )}
            </div>
          ))}
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── How it works ── */}
      <HowItWorks steps={config.howItWorks} />

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── CTA ── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          Ready to try {config.name}?
        </h2>
        <p className="mt-4 text-base text-muted-foreground max-w-xl mx-auto">
          Open the app and start working with your contracts.
        </p>
        <div className="mt-8">
          <Link
            href={config.appLink}
            className={cn(buttonVariants({ variant: 'default', size: 'lg' }))}
          >
            Open in App
          </Link>
        </div>
      </section>
    </div>
  );
}
