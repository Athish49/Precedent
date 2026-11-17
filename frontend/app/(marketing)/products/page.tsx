import Link from 'next/link';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Solution {
  slug: string;
  name: string;
  tagline: string;
  description: string;
  appLink: string;
  visual: React.ReactNode;
}

// ─── Illustrative Visuals ─────────────────────────────────────────────────────

function ClmVisual() {
  const rows = [
    { title: 'Master Services Agreement', counterparty: 'Acme Corp', status: 'Active', expiry: '2025-03-31', statusColor: 'bg-emerald-500' },
    { title: 'Software License Agreement', counterparty: 'Beta LLC', status: 'Renewing', expiry: '2024-12-15', statusColor: 'bg-amber-400' },
    { title: 'NDA — Vendor Onboarding', counterparty: 'Gamma Inc', status: 'Expired', expiry: '2023-11-01', statusColor: 'bg-destructive' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="grid grid-cols-4 border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <span>Title</span>
        <span>Counterparty</span>
        <span>Status</span>
        <span>Expiry</span>
      </div>
      {rows.map((row) => (
        <div
          key={row.title}
          className="grid grid-cols-4 items-center border-b border-border px-3 py-2.5 text-xs last:border-b-0"
        >
          <span className="truncate font-medium text-foreground">{row.title}</span>
          <span className="text-muted-foreground">{row.counterparty}</span>
          <span className="flex items-center gap-1.5">
            <span className={cn('inline-block h-1.5 w-1.5 rounded-full', row.statusColor)} />
            <span className="text-foreground">{row.status}</span>
          </span>
          <span className="font-mono text-muted-foreground">{row.expiry}</span>
        </div>
      ))}
    </div>
  );
}

function AnalysisVisual() {
  const flags = [
    { label: 'Missing limitation of liability clause', type: 'Missing Clause', severity: 'High', dot: 'bg-destructive', badge: 'bg-destructive/15 text-destructive' },
    { label: 'Indemnification is unilateral — no reciprocity', type: 'Deviation', severity: 'Medium', dot: 'bg-amber-400', badge: 'bg-amber-400/15 text-amber-600 dark:text-amber-400' },
    { label: 'Auto-renewal with 90-day notice window', type: 'High-Risk', severity: 'Low', dot: 'bg-sky-500', badge: 'bg-sky-500/15 text-sky-600 dark:text-sky-400' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Analysis Flags · 3 issues
      </div>
      <ul className="divide-y divide-border">
        {flags.map((flag) => (
          <li key={flag.label} className="flex items-start gap-2.5 px-3 py-2.5">
            <span className={cn('mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full', flag.dot)} />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-foreground leading-snug">{flag.label}</p>
              <p className="mt-0.5 text-[10px] text-muted-foreground">{flag.type}</p>
            </div>
            <span className={cn('mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold', flag.badge)}>
              {flag.severity}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RedliningVisual() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Redline — §8.1 Liability Cap · Firm stance
      </div>
      <div className="px-3 py-3 text-xs leading-relaxed">
        <p className="font-mono text-muted-foreground">
          <span className="line-through text-destructive/80">
            In no event shall either party&apos;s liability exceed the fees paid in the thirty (30) days prior to the claim.
          </span>
        </p>
        <p className="mt-1 font-mono text-emerald-600 dark:text-emerald-400">
          + In no event shall either party&apos;s liability exceed the total fees paid in the twelve (12) months prior to the claim.
        </p>
        <div className="mt-2.5 rounded-md border border-border bg-background px-2.5 py-2">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Explanation</p>
          <p className="text-[11px] text-muted-foreground">
            30-day cap is below our standard position. Firm playbook requires a 12-month reference period.
          </p>
        </div>
      </div>
    </div>
  );
}

function DraftingVisual() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Generated output · Confidentiality clause
      </div>
      <div className="px-3 py-3 text-xs leading-relaxed text-muted-foreground">
        <p>
          Each party agrees to hold the other&apos;s Confidential Information in strict confidence and
          not to disclose such information to any third party without prior written consent, except
          as required by applicable law.
        </p>
        <div className="mt-2.5 flex items-center gap-1.5">
          <span className="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
            Playbook
          </span>
          <span className="text-[10px] text-muted-foreground">Standard NDA template · Preferred language</span>
        </div>
        <div className="mt-1.5 flex items-center gap-1.5">
          <span className="inline-flex items-center rounded-full border border-muted-foreground/20 bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
            Frequency
          </span>
          <span className="text-[10px] text-muted-foreground">Used in 84% of similar contracts</span>
        </div>
      </div>
    </div>
  );
}

function AutonomousReviewVisual() {
  const gates = [
    { label: 'Governing law — matches jurisdiction policy', pass: true },
    { label: 'Mutual NDA boilerplate — auto-applied', pass: true },
    { label: 'Payment terms within 45-day window', pass: true },
    { label: 'Liability cap below 12-month threshold — escalated', pass: false },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Autonomous Review · Gate checklist
      </div>
      <ul className="divide-y divide-border">
        {gates.map((gate) => (
          <li key={gate.label} className="flex items-center gap-2.5 px-3 py-2.5">
            <span
              className={cn(
                'inline-block h-2 w-2 shrink-0 rounded-full',
                gate.pass ? 'bg-emerald-500' : 'bg-amber-400',
              )}
            />
            <span
              className={cn(
                'text-xs',
                gate.pass ? 'text-foreground' : 'font-medium text-amber-600 dark:text-amber-400',
              )}
            >
              {gate.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PlaybooksVisual() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Playbook rule · Limitation of Liability
      </div>
      <div className="px-3 py-3 space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Clause type</span>
          <span className="font-medium text-foreground">Limitation of Liability</span>
        </div>
        <div className="rounded-md border border-border bg-background px-2.5 py-2">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">Preferred language</p>
          <p className="text-[11px] text-muted-foreground font-mono leading-relaxed">
            …liability shall not exceed total fees paid in the preceding twelve (12) months…
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-full border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold text-destructive">
            Required
          </span>
          <span className="text-[10px] text-muted-foreground">Precedence: Enterprise · overrides Standard</span>
        </div>
      </div>
    </div>
  );
}

function DocumentIntelligenceVisual() {
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Q&A · Contract research
      </div>
      <div className="divide-y divide-border text-xs">
        <div className="px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Question</p>
          <p className="text-foreground font-medium">What is the notice period for termination for convenience?</p>
        </div>
        <div className="px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Answer</p>
          <p className="text-muted-foreground">
            Either party may terminate for convenience with{' '}
            <span className="rounded bg-amber-200/70 px-0.5 text-foreground dark:bg-amber-700/40 font-medium">
              60 days&apos; written notice
            </span>
            {' '}to the other party.
          </p>
          <div className="mt-2 rounded border border-border bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground">
            offset 3,210–3,248 · Termination · §12.2
          </div>
        </div>
      </div>
    </div>
  );
}

function AnalyticsVisual() {
  const stats = [
    { label: 'Total contracts', value: '42' },
    { label: 'High risk', value: '8', accent: true },
    { label: 'Portfolio value', value: '$2.4M' },
  ];
  return (
    <div className="rounded-xl border border-border bg-muted/40 overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Portfolio overview · Q4 2024
      </div>
      <div className="grid grid-cols-3 divide-x divide-border p-0">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col items-center justify-center px-3 py-4">
            <span
              className={cn(
                'text-xl font-semibold tabular-nums',
                stat.accent ? 'text-destructive' : 'text-foreground',
              )}
            >
              {stat.value}
            </span>
            <span className="mt-0.5 text-center text-[10px] text-muted-foreground">{stat.label}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-border px-3 py-2.5">
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground mb-1.5">
          <span>Risk distribution</span>
        </div>
        <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full w-[19%] bg-destructive" title="High risk" />
          <div className="h-full w-[33%] bg-amber-400" title="Medium risk" />
          <div className="h-full w-[48%] bg-emerald-500" title="Low risk" />
        </div>
        <div className="mt-1.5 flex gap-3">
          {[
            { label: 'High', color: 'bg-destructive' },
            { label: 'Medium', color: 'bg-amber-400' },
            { label: 'Low', color: 'bg-emerald-500' },
          ].map((item) => (
            <span key={item.label} className="flex items-center gap-1">
              <span className={cn('h-1.5 w-1.5 rounded-full', item.color)} />
              <span className="text-[10px] text-muted-foreground">{item.label}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Solutions Data ───────────────────────────────────────────────────────────

const SOLUTIONS: Solution[] = [
  {
    slug: 'clm',
    name: 'Contract Lifecycle Management',
    tagline: 'Track every contract from creation to renewal',
    description:
      'Ingest PDFs and DOCX files, extract structured metadata automatically, and maintain a searchable repository with full version lineage. Filter by counterparty, status, value, or date range — and surface renewal risks before they become missed deadlines.',
    appLink: '/repository',
    visual: <ClmVisual />,
  },
  {
    slug: 'analysis',
    name: 'Contract Analysis',
    tagline: 'Surface risks and obligations instantly',
    description:
      'Run deterministic rule-based analysis before any LLM is invoked. Flags are typed (missing clause, prohibited term, deviation, high-risk) and severity-graded. Every flag links back to the exact character offset in the source document.',
    appLink: '/home',
    visual: <AnalysisVisual />,
  },
  {
    slug: 'redlining',
    name: 'Redlining & Negotiation',
    tagline: 'AI-generated redlines anchored to your playbooks',
    description:
      'Generate tracked changes at Light, Balanced, or Firm stance. Each redline includes explanation, counterparty comment, and 2–3 alternative positions. Accept, reject, or edit inline — changes animate into the document canvas.',
    appLink: '/home',
    visual: <RedliningVisual />,
  },
  {
    slug: 'drafting',
    name: 'Drafting Studio',
    tagline: 'Generate first drafts from templates and playbooks',
    description:
      'Draft single clauses, full documents, or precedent-matched text from your clause library. Every output is tagged with its source — playbook language, frequency-based, or LLM-generated — so provenance is always visible.',
    appLink: '/drafting',
    visual: <DraftingVisual />,
  },
  {
    slug: 'autonomous-review',
    name: 'Autonomous Review',
    tagline: 'AI-powered review that flags issues automatically',
    description:
      'Upload a contract and trigger a full autonomous review. The pipeline checks prohibited terms, missing required clauses, and high-severity flags against a hard-stop checklist. Safe changes are auto-applied; deviations are escalated for human review.',
    appLink: '/automations',
    visual: <AutonomousReviewVisual />,
  },
  {
    slug: 'playbooks',
    name: 'Playbooks & Standards',
    tagline: 'Enforce negotiation positions at scale',
    description:
      'Define preferred language, acceptable variations, prohibited terms, and fallback positions per clause type. Layer multiple playbooks with explicit precedence — Precedent resolves the merged rule set automatically for any contract type.',
    appLink: '/playbooks',
    visual: <PlaybooksVisual />,
  },
  {
    slug: 'document-intelligence',
    name: 'Document Intelligence',
    tagline: 'Extract structured data from any contract',
    description:
      'Q&A, summarization, and research grounded in the contract text. Citations are character-level — click any finding to highlight the exact source span. Run portfolio-wide NL queries that populate tabular columns on demand.',
    appLink: '/home',
    visual: <DocumentIntelligenceVisual />,
  },
  {
    slug: 'analytics',
    name: 'Analytics & Reporting',
    tagline: 'Portfolio-wide insights and trend dashboards',
    description:
      'Track portfolio risk distribution, contract value by counterparty, and upcoming renewals. Add NL answer columns to the tabular view — each cell backed by a citation. Cross-filter between dashboard charts and the contract repository.',
    appLink: '/analytics',
    visual: <AnalyticsVisual />,
  },
];

// ─── Section ──────────────────────────────────────────────────────────────────

function SolutionSection({ solution, index }: { solution: Solution; index: number }) {
  const isEven = index % 2 === 0; // 0-indexed: even = content left, odd = content right
  return (
    <>
      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div
          className={cn(
            'flex flex-col gap-10 lg:grid lg:grid-cols-2 lg:items-center lg:gap-16',
            !isEven && 'lg:grid-flow-col-dense',
          )}
        >
          {/* Content block */}
          <div className={cn('flex flex-col gap-5', !isEven && 'lg:col-start-2')}>
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                {solution.name}
              </h2>
              <p className="mt-1.5 text-base text-muted-foreground">{solution.tagline}</p>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">{solution.description}</p>
            <div className="flex flex-wrap items-center gap-3">
              <Link
                href={`/products/${solution.slug}`}
                className={cn(buttonVariants({ variant: 'default', size: 'sm' }), 'h-8 px-4')}
              >
                Learn more
              </Link>
              <Link
                href={solution.appLink}
                className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'h-8 px-4')}
              >
                Open in app
              </Link>
            </div>
          </div>

          {/* Visual block */}
          <div className={cn(!isEven && 'lg:col-start-1 lg:row-start-1')}>
            {solution.visual}
          </div>
        </div>
      </section>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>
    </>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ProductsPage() {
  return (
    <div className="flex flex-col">
      {/* Page header */}
      <section className="mx-auto w-full max-w-7xl px-4 pb-4 pt-16 sm:px-6 lg:px-8">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          Products
        </h1>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          Eight purpose-built solutions that cover every stage of the contract lifecycle — from
          first draft to final execution and ongoing portfolio management.
        </p>
      </section>

      <div className="mx-auto mt-12 w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* Alternating solution sections */}
      {SOLUTIONS.map((solution, index) => (
        <SolutionSection key={solution.slug} solution={solution} index={index} />
      ))}
    </div>
  );
}
