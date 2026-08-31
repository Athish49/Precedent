import Link from 'next/link';
import { ShieldCheck, Link2, Zap } from 'lucide-react';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ─── Data ─────────────────────────────────────────────────────────────────────

interface Solution {
  slug: string;
  name: string;
  descriptor: string;
}

interface ProductGroup {
  heading: string;
  solutions: Solution[];
}

const PRODUCT_GROUPS: ProductGroup[] = [
  {
    heading: 'Review & Negotiate',
    solutions: [
      {
        slug: 'clm',
        name: 'Contract Lifecycle Management',
        descriptor: 'Track every contract from creation to renewal',
      },
      {
        slug: 'analysis',
        name: 'Contract Analysis',
        descriptor: 'Surface risks and obligations instantly',
      },
      {
        slug: 'redlining',
        name: 'Redlining & Negotiation',
        descriptor: 'Collaborate on edits with structured markup',
      },
    ],
  },
  {
    heading: 'Draft',
    solutions: [
      {
        slug: 'drafting',
        name: 'Drafting Studio',
        descriptor: 'Generate first drafts from templates and playbooks',
      },
    ],
  },
  {
    heading: 'Manage & Monitor',
    solutions: [
      {
        slug: 'autonomous-review',
        name: 'Autonomous Review',
        descriptor: 'AI-powered review that flags issues automatically',
      },
      {
        slug: 'playbooks',
        name: 'Playbooks & Standards',
        descriptor: 'Enforce negotiation positions at scale',
      },
    ],
  },
  {
    heading: 'Analyze',
    solutions: [
      {
        slug: 'document-intelligence',
        name: 'Document Intelligence',
        descriptor: 'Extract structured data from any contract',
      },
      {
        slug: 'analytics',
        name: 'Analytics & Reporting',
        descriptor: 'Portfolio-wide insights and trend dashboards',
      },
    ],
  },
];

// ─── Inline UI Mockups ────────────────────────────────────────────────────────

function FlagCardMockup() {
  return (
    <div className="mt-4 rounded-lg border border-border bg-muted/50 p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-medium text-foreground">Payment Terms</span>
        <span className="rounded-full bg-destructive/15 px-2 py-0.5 text-[10px] font-semibold text-destructive">
          High
        </span>
      </div>
      <p className="mt-1 text-muted-foreground">
        Net-90 payment window exceeds standard 30-day position.
      </p>
      <div className="mt-2 flex items-center gap-1 text-muted-foreground">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-destructive" />
        <span>Clause §4.2 · detected by rule engine</span>
      </div>
    </div>
  );
}

function CitationMockup() {
  return (
    <div className="mt-4 rounded-lg border border-border bg-muted/50 p-3 text-xs">
      <p className="text-muted-foreground leading-relaxed">
        <span className="text-foreground">…the Licensee shall indemnify the Licensor</span>{' '}
        <span className="rounded bg-amber-200/70 px-0.5 text-foreground dark:bg-amber-700/40">
          for any and all losses arising
        </span>{' '}
        <span className="text-muted-foreground">from use of the Software…</span>
      </p>
      <div className="mt-2 rounded border border-border bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground">
        offset 1,482–1,520 · Indemnification · §9.1
      </div>
    </div>
  );
}

function GateMockup() {
  return (
    <div className="mt-4 space-y-1.5 rounded-lg border border-border bg-muted/50 p-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
        <span className="text-foreground">Mutual NDA boilerplate — auto-applied</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
        <span className="text-foreground">Governing law aligned — auto-applied</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
        <span className="text-foreground">Liability cap deviation — escalated for review</span>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="flex flex-col">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-24 text-center sm:px-6 lg:px-8">
        <h1 className="mx-auto max-w-3xl text-5xl font-semibold tracking-tight text-foreground sm:text-6xl">
          Contract intelligence for in-house counsel
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          Precedent brings deterministic clause detection, character-level AI citations,
          and autonomous review pipelines into a single platform — so your legal team
          moves faster without sacrificing auditability.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/home"
            className={cn(
              buttonVariants({ variant: 'default' }),
              'h-11 px-6 text-base',
            )}
          >
            Launch App
          </Link>
          <Link
            href="#how-it-works"
            className={cn(
              buttonVariants({ variant: 'outline' }),
              'h-11 px-6 text-base',
            )}
          >
            See how it works
          </Link>
        </div>
      </section>

      {/* ── Capability tile grid ───────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 pb-24 sm:px-6 lg:px-8">
        <h2 className="mb-12 text-center text-2xl font-semibold tracking-tight text-foreground">
          Everything your legal ops team needs
        </h2>

        <div className="space-y-10">
          {PRODUCT_GROUPS.map((group) => (
            <div key={group.heading}>
              <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {group.heading}
              </p>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {group.solutions.map((solution) => (
                  <Link
                    key={solution.slug}
                    href={`/products/${solution.slug}`}
                    className="group block rounded-xl border border-border bg-card p-5 shadow-sm transition-transform hover:-translate-y-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                      {solution.name}
                    </h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                      {solution.descriptor}
                    </p>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Differentiator strip ──────────────────────────────────────────── */}
      <section
        id="how-it-works"
        className="border-t border-border bg-muted/30 py-24"
      >
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <h2 className="mb-2 text-center text-2xl font-semibold tracking-tight text-foreground">
            Built differently
          </h2>
          <p className="mb-12 text-center text-muted-foreground">
            Three properties that make Precedent auditable by default.
          </p>

          <div className="grid gap-8 md:grid-cols-3">
            {/* Card 1 — Deterministic-first */}
            <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <ShieldCheck className="size-5 text-primary" />
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">
                Deterministic-first
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Clause extraction, flag detection, and compliance checks run via
                deterministic rules before any LLM is invoked. Every result is
                reproducible across runs and fully auditable — no probability drift.
              </p>
              <FlagCardMockup />
            </div>

            {/* Card 2 — Character-level citations */}
            <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <Link2 className="size-5 text-primary" />
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">
                Character-level citations
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Every AI finding links back to the exact character offset in the
                source document. No summary-level references, no hallucinated
                paragraphs — each flag anchors to a precise span of text.
              </p>
              <CitationMockup />
            </div>

            {/* Card 3 — Autonomous gate */}
            <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <Zap className="size-5 text-primary" />
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">
                Autonomous gate
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                The review pipeline auto-applies changes that fall within configured
                thresholds and escalates only what needs human judgment. Safe
                throughput goes up; lawyer time stays focused on what matters.
              </p>
              <GateMockup />
            </div>
          </div>
        </div>
      </section>

      {/* ── Closing CTA ───────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-24 text-center sm:px-6 lg:px-8">
        <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          Ready to modernize your contract workflow?
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
          Precedent is purpose-built for in-house legal teams that need speed,
          traceability, and control — without the complexity of enterprise tooling.
        </p>
        <div className="mt-8">
          <Link
            href="/home"
            className={cn(
              buttonVariants({ variant: 'default' }),
              'h-11 px-6 text-base',
            )}
          >
            Launch App
          </Link>
        </div>
      </section>
    </div>
  );
}
