import Link from 'next/link';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ─── Stat / Value Cards ───────────────────────────────────────────────────────

interface StatCard {
  value: string;
  label: string;
  detail: string;
}

const STAT_CARDS: StatCard[] = [
  {
    value: '7 flag types',
    label: 'Typed flags',
    detail: 'Missing, prohibited, deviation, non-standard, vague, inconsistent, high-risk',
  },
  {
    value: '3 stances',
    label: 'Negotiation stances',
    detail: 'Light, Balanced, Firm — playbook-aligned redlines for every position',
  },
  {
    value: 'Char-level',
    label: 'Character-level citations',
    detail: 'Every finding linked to exact char_start / char_end offsets in the source',
  },
];

// ─── Audience Cards ───────────────────────────────────────────────────────────

interface AudienceCard {
  title: string;
  body: string;
}

const AUDIENCE_CARDS: AudienceCard[] = [
  {
    title: 'In-house counsel',
    body: 'You review contracts under time pressure. Precedent surfaces the issues that matter, generates playbook-aligned redlines, and keeps the document canvas and analysis in sync — so you spend less time hunting and more time deciding.',
  },
  {
    title: 'Legal ops teams',
    body: 'You manage the contract lifecycle, enforce standards, and report on portfolio risk. Precedent gives you a searchable repository, configurable playbooks, autonomous review pipelines, and analytics — all in one place.',
  },
];

// ─── Core Values ──────────────────────────────────────────────────────────────

interface CoreValue {
  title: string;
  body: string;
}

const CORE_VALUES: CoreValue[] = [
  {
    title: 'Auditability over magic',
    body: 'Every AI output is traceable. No black-box summaries, no hallucinated references. If Precedent says something, it can show you exactly where in the document it came from.',
  },
  {
    title: 'Deterministic-first',
    body: 'Rule-based detection runs before any LLM. The results are reproducible, typed, and severity-graded — independent of model updates or prompt drift.',
  },
  {
    title: 'Legal judgment stays with lawyers',
    body: 'Precedent automates the mechanical work and escalates the judgment calls. The autonomous gate is configurable — your team decides what auto-applies and what needs a human.',
  },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CompanyPage() {
  return (
    <div className="flex flex-col">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 pt-16 pb-12 sm:px-6 lg:px-8">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          Built for in-house legal teams
        </h1>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          Precedent is a contract intelligence platform designed for in-house counsel and
          legal operations teams who need speed, traceability, and control — without
          enterprise complexity.
        </p>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Vision / Mission ──────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-start">
          {/* Left — Editorial narrative */}
          <div className="space-y-5">
            <p className="text-sm leading-relaxed text-muted-foreground">
              Most contract review tools treat AI as a black box. Findings appear without
              citations, redlines lack rationale, and &ldquo;AI-assisted&rdquo; is a label that
              replaces rather than augments legal judgment.
            </p>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Precedent is built on a different premise: deterministic rules run first, AI runs
              second, and every output is anchored to the exact characters in the source document.
              Your team sees where every flag came from.
            </p>
            <p className="text-sm leading-relaxed text-muted-foreground">
              We built Precedent for in-house counsel and legal ops teams managing recurring
              contract workflows — MSAs, NDAs, vendor agreements, licensing deals. Teams that
              need throughput without sacrificing auditability.
            </p>
            <p className="text-sm leading-relaxed text-muted-foreground">
              The result is a platform where legal teams can move faster, enforce negotiation
              positions at scale, and hand off clean contracts — with a full audit trail at
              every step.
            </p>
          </div>

          {/* Right — Stat / value card cluster */}
          <div className="flex flex-col gap-4">
            {STAT_CARDS.map((card) => (
              <div
                key={card.value}
                className="rounded-xl border border-border bg-card p-5 shadow-sm"
              >
                <p className="text-2xl font-semibold tracking-tight text-foreground">
                  {card.value}
                </p>
                <p className="mt-0.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {card.label}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {card.detail}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Who it's for ──────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <h2 className="mb-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Who it&rsquo;s for
        </h2>
        <p className="mb-10 max-w-xl text-muted-foreground">
          Two roles, one platform — built to reduce friction for everyone in the contract
          workflow.
        </p>
        <div className="grid gap-6 md:grid-cols-2">
          {AUDIENCE_CARDS.map((card) => (
            <div
              key={card.title}
              className="rounded-xl border border-border bg-card p-6 shadow-sm"
            >
              <h3 className="text-base font-semibold text-foreground">{card.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{card.body}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Core values / principles ──────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <h2 className="mb-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Our principles
        </h2>
        <p className="mb-10 max-w-xl text-muted-foreground">
          The values that shape every product decision at Precedent.
        </p>
        <div className="grid gap-6 md:grid-cols-3">
          {CORE_VALUES.map((value) => (
            <div
              key={value.title}
              className="rounded-xl border border-border bg-card p-6 shadow-sm"
            >
              <h3 className="text-base font-semibold text-foreground">{value.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{value.body}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <hr className="border-border" />
      </div>

      {/* ── Closing CTA ───────────────────────────────────────────────────── */}
      <section className="mx-auto w-full max-w-7xl px-4 py-24 text-center sm:px-6 lg:px-8">
        <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          Ready to see Precedent in action?
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
          Launch the app and explore with your own contracts.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/home"
            className={cn(buttonVariants({ variant: 'default' }), 'h-11 px-6 text-base')}
          >
            Launch App
          </Link>
          <Link
            href="/platform"
            className={cn(
              buttonVariants({ variant: 'ghost' }),
              'h-11 px-6 text-base text-muted-foreground hover:text-foreground',
            )}
          >
            Explore the platform →
          </Link>
        </div>
      </section>
    </div>
  );
}
