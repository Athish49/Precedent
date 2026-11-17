import Link from 'next/link';
import { ShieldCheck, Link2, SlidersHorizontal } from 'lucide-react';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ─── Architecture Diagram ─────────────────────────────────────────────────────

function DiagramBox({
  title,
  subtitle,
  className,
}: {
  title: string;
  subtitle: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border px-4 py-3 text-center',
        className,
      )}
    >
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>
    </div>
  );
}

function DiagramArrow() {
  return (
    <div className="flex justify-center py-1 text-muted-foreground select-none" aria-hidden>
      <span className="text-lg leading-none">↓</span>
    </div>
  );
}

function ArchitectureDiagram() {
  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      {/* Two paths */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left — Deterministic path */}
        <div className="flex flex-col">
          <p className="mb-3 text-center text-[10px] font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
            Deterministic Engine
          </p>
          <DiagramBox
            title="Contract Ingestion"
            subtitle="PDF / DOCX"
            className="border-sky-500/30 bg-sky-500/5"
          />
          <DiagramArrow />
          <DiagramBox
            title="Clause Extraction"
            subtitle="character offsets"
            className="border-sky-500/30 bg-sky-500/5"
          />
          <DiagramArrow />
          <DiagramBox
            title="Rule Engine"
            subtitle="playbook rules → flags"
            className="border-sky-500/30 bg-sky-500/5"
          />
          <p className="mt-3 text-center text-[10px] text-sky-600 dark:text-sky-400">
            Deterministic · reproducible
          </p>
        </div>

        {/* Right — LLM path */}
        <div className="flex flex-col">
          <p className="mb-3 text-center text-[10px] font-semibold uppercase tracking-wider text-violet-600 dark:text-violet-400">
            LLM Layer
          </p>
          <DiagramBox
            title="LLM Analysis"
            subtitle="summaries, Q&A, redlines"
            className="border-violet-500/30 bg-violet-500/5"
          />
          <DiagramArrow />
          <DiagramBox
            title="Citation Anchoring"
            subtitle="char_start / char_end offsets"
            className="border-violet-500/30 bg-violet-500/5"
          />
          {/* spacer to align with deterministic path which has one more box */}
          <div className="flex-1" />
          <p className="mt-3 text-center text-[10px] text-violet-600 dark:text-violet-400">
            AI · always cited
          </p>
        </div>
      </div>

      {/* Merge indicator */}
      <div className="my-4 flex items-center justify-center gap-4 select-none" aria-hidden>
        <span className="flex-1 border-t border-dashed border-border" />
        <span className="text-xs text-muted-foreground">↘ merge ↙</span>
        <span className="flex-1 border-t border-dashed border-border" />
      </div>

      {/* Autonomous Gate */}
      <div className="rounded-lg border border-border bg-muted/50 px-4 py-4">
        <p className="text-center text-sm font-semibold text-foreground">Autonomous Gate</p>
        <p className="mt-0.5 text-center text-[11px] text-muted-foreground">
          hard-stop checklist → auto-apply or escalate
        </p>
        <div className="mt-3 space-y-1.5">
          {[
            { label: 'Governing law — matches jurisdiction policy', pass: true },
            { label: 'Mutual NDA boilerplate — passes threshold', pass: true },
            { label: 'Liability cap deviation — below threshold', pass: false },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-2">
              <span
                className={cn(
                  'inline-block h-1.5 w-1.5 shrink-0 rounded-full',
                  item.pass ? 'bg-emerald-500' : 'bg-amber-400',
                )}
              />
              <span className="text-[11px] text-muted-foreground">{item.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Gate outputs */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2.5 text-center">
          <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            Auto-applied
          </p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            within configured thresholds
          </p>
        </div>
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2.5 text-center">
          <p className="text-xs font-semibold text-amber-600 dark:text-amber-400">
            Escalated for review
          </p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            deviations → legal team
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Data Flow Narrative ──────────────────────────────────────────────────────

const DATA_FLOW_STEPS = [
  { n: 1, text: 'Ingest PDF or DOCX — text extracted, structure detected' },
  { n: 2, text: 'Extract clauses + metadata — typed blocks with character offsets' },
  { n: 3, text: 'Run deterministic analysis — rules fire, flags generated, reproducible' },
  { n: 4, text: 'Optionally invoke LLM layer — summaries, redlines, Q&A with citations' },
  { n: 5, text: 'Gate evaluates checklist — every item checked against configured thresholds' },
  { n: 6, text: 'Auto-apply or escalate — safe changes applied, deviations sent for review' },
];

function DataCardMockup() {
  const stages = [
    { label: 'Uploaded', badge: 'bg-muted text-muted-foreground' },
    { label: 'Processing', badge: 'bg-sky-500/15 text-sky-600 dark:text-sky-400' },
    { label: 'Analyzed', badge: 'bg-violet-500/15 text-violet-600 dark:text-violet-400' },
    { label: 'Redlined', badge: 'bg-amber-400/15 text-amber-600 dark:text-amber-400' },
    { label: 'Gate passed', badge: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' },
  ];
  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      <div className="border-b border-border bg-muted/60 px-4 py-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Contract · Vendor MSA · Acme Corp
        </p>
      </div>
      <div className="px-4 py-4 space-y-2">
        {stages.map((stage, idx) => (
          <div key={stage.label} className="flex items-center gap-3">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-[9px] font-semibold text-muted-foreground">
              {idx + 1}
            </div>
            <span
              className={cn(
                'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold',
                stage.badge,
              )}
            >
              {stage.label}
            </span>
            {idx < stages.length - 1 && (
              <span className="text-[10px] text-muted-foreground">→</span>
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-border bg-muted/30 px-4 py-2">
        <p className="font-mono text-[10px] text-muted-foreground">
          3 flags · 2 auto-applied · 1 escalated
        </p>
      </div>
    </div>
  );
}

// ─── Principles ───────────────────────────────────────────────────────────────

interface Principle {
  icon: React.ReactNode;
  title: string;
  body: string;
}

const PRINCIPLES: Principle[] = [
  {
    icon: <ShieldCheck className="size-5 text-primary" />,
    title: 'Deterministic-first',
    body: 'Rule-based clause extraction and flag detection run before any LLM. Results are typed, severity-graded, and reproducible across runs — no probability drift between identical inputs.',
  },
  {
    icon: <Link2 className="size-5 text-primary" />,
    title: 'Character-level traceability',
    body: 'Every output — flag, redline, citation, or Q&A answer — carries a char_start / char_end offset pointing to the exact source span. No summary-level references.',
  },
  {
    icon: <SlidersHorizontal className="size-5 text-primary" />,
    title: 'Configurable autonomy',
    body: 'The autonomous gate\'s thresholds are configurable. Teams set what auto-applies and what escalates. Full audit trail on every run — including which rule triggered which decision.',
  },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PlatformPage() {
  return (
    <div className="flex flex-col">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 pt-16 pb-12 sm:px-6 lg:px-8">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          The Precedent Platform
        </h1>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          An architecture built for auditability — deterministic rules first, AI second,
          every output traceable to source.
        </p>
      </section>

      {/* ── Architecture Diagram ──────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-5xl px-4 pb-16 sm:px-6 lg:px-8">
        <ArchitectureDiagram />
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Architectural Principles ──────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <h2 className="mb-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Architectural principles
        </h2>
        <p className="mb-10 max-w-xl text-muted-foreground">
          Three properties that make every Precedent output auditable by design.
        </p>
        <div className="grid gap-6 md:grid-cols-3">
          {PRINCIPLES.map((principle) => (
            <div
              key={principle.title}
              className="rounded-xl border border-border bg-card p-6 shadow-sm"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                {principle.icon}
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">
                {principle.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {principle.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Data Flow Narrative ───────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <h2 className="mb-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Data flow
        </h2>
        <p className="mb-10 max-w-xl text-muted-foreground">
          How a contract moves through the Precedent pipeline — from raw upload to a fully
          audited, gated decision.
        </p>
        <div className="grid gap-10 lg:grid-cols-2 lg:items-start">
          {/* Steps */}
          <ol className="space-y-5">
            {DATA_FLOW_STEPS.map((step) => (
              <li key={step.n} className="flex items-start gap-4">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-xs font-semibold text-foreground">
                  {step.n}
                </span>
                <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">
                  {step.text}
                </p>
              </li>
            ))}
          </ol>

          {/* Data card mockup */}
          <DataCardMockup />
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Closing CTA ───────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-24 text-center sm:px-6 lg:px-8">
        <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          Build your legal ops stack on Precedent
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
          Deterministic-first, AI-assisted, and auditable at every step — the platform
          your legal team can trust at scale.
        </p>
        <div className="mt-8">
          <Link
            href="/home"
            className={cn(buttonVariants({ variant: 'default' }), 'h-11 px-6 text-base')}
          >
            Launch App
          </Link>
        </div>
      </section>
    </div>
  );
}
