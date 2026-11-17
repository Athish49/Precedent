'use client';

import Link from 'next/link';
import { Reveal, SectionLabel, SerifHeading, PillButton, useInView } from '@/components/landing/primitives';

// The three "by team" solution pages we actually build. In-house Legal is folded
// in as the primary persona narrative (below), not a separate page.
const TEAMS = [
  {
    name: 'Legal Operations',
    href: '/solutions/legal-ops',
    blurb: 'Run the whole contract lifecycle from one system — set the standards, enforce them on every deal, see the entire portfolio.',
    gradient: 'linear-gradient(135deg, #6366f1, #7c3aed, #0ea5e9)',
  },
  {
    name: 'Procurement & Sourcing',
    href: '/solutions/procurement',
    blurb: 'Review vendor paper you didn’t write, at intake volume — risks surfaced and redlined before it reaches your desk.',
    gradient: 'linear-gradient(135deg, #f59e0b, #f97316, #ef4444)',
  },
  {
    name: 'Sales / Deal Desk',
    href: '/solutions/sales',
    blurb: 'Close deals without the legal bottleneck — self-serve review with guardrails that escalate only what truly needs a lawyer.',
    gradient: 'linear-gradient(135deg, #10b981, #14b8a6, #0ea5e9)',
  },
];

// The "works across your paper" band — this is how the contract-type axis is
// represented (no standalone regulatory pages). Links to the real routing story.
const PAPER = ['SaaS / MSA', 'NDAs', 'Data Processing (DPA / GDPR)', 'Healthcare (HIPAA BAA)'];

function TeamCard({ team }: { team: (typeof TEAMS)[number] }) {
  const { ref, inView } = useInView<HTMLAnchorElement>({ threshold: 0.2 });
  return (
    <Link
      href={team.href}
      ref={ref}
      className="group block rounded-2xl overflow-hidden transition-all hover:-translate-y-1"
      style={{
        border: '1px solid var(--border-color)',
        opacity: inView ? 1 : 0,
        transform: inView ? 'translateY(0)' : 'translateY(32px)',
        transition: 'opacity 0.7s cubic-bezier(0.16,1,0.3,1), transform 0.7s cubic-bezier(0.16,1,0.3,1)',
      }}
    >
      <div className="relative w-full aspect-[16/10] overflow-hidden" style={{ background: team.gradient }}>
        <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.15)' }} />
      </div>
      <div className="p-6 md:p-7">
        <h3 className="tx-body mb-2" style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{team.name}</h3>
        <p className="tx-body mb-5" style={{ color: 'var(--text-secondary)' }}>{team.blurb}</p>
        <span className="inline-flex items-center gap-1.5 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Explore
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </span>
      </div>
    </Link>
  );
}

export function SolutionsOverview() {
  return (
    <>
      {/* ── Header ───────────────────────────────────────────────── */}
      <section className="relative px-4 sm:px-6 md:px-8 pt-32 md:pt-40 pb-8 md:pb-12">
        <div className="max-w-3xl mx-auto">
          <SectionLabel text="Solutions" />
          <Reveal>
            <SerifHeading className="text-4xl md:text-5xl lg:text-6xl mb-6">
              Built for the way your team actually works.
            </SerifHeading>
          </Reveal>
          <Reveal delay={80}>
            <p className="text-base md:text-lg mb-8" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>
              Precedent’s capabilities recombine around the people who use them — legal ops running the
              lifecycle, procurement reviewing vendor paper, sales closing without the bottleneck.
            </p>
          </Reveal>
          <Reveal delay={160} className="flex flex-wrap gap-3">
            <PillButton href="/home">Book a demo</PillButton>
            <PillButton href="/products" outline>Explore products</PillButton>
          </Reveal>
        </div>
      </section>

      {/* ── Primary persona: In-house Legal (folded in, no separate page) ── */}
      <section className="px-4 sm:px-6 md:px-8 py-12 md:py-16">
        <div className="page-container">
          <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
            <Reveal className="lg:col-start-2 lg:col-end-12">
              <div
                className="rounded-3xl p-8 md:p-14"
                style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}
              >
                <p className="text-xs font-medium tracking-widest uppercase mb-4" style={{ color: 'var(--text-muted)' }}>
                  For in-house legal
                </p>
                <h2 className="tx-h3 mb-5 max-w-3xl" style={{ color: 'var(--text-primary)' }}>
                  A lean legal team, moving at the speed of the business — without adding risk.
                </h2>
                <p className="tx-lead max-w-2xl" style={{ color: 'var(--text-secondary)' }}>
                  In-house counsel is Precedent’s home ground. Draft from your own playbook, catch risk the
                  moment a contract lands, redline in your own voice, and keep every obligation in view —
                  the whole platform is built to make a small team review like a large one.
                </p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <PillButton href="/products">See what it does</PillButton>
                  <PillButton href="/products/contract-analysis" outline>Start with analysis</PillButton>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ── By team ──────────────────────────────────────────────── */}
      <section className="px-4 sm:px-6 md:px-8 py-12 md:py-20">
        <div className="page-container">
          <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
            <div className="lg:col-start-2 lg:col-end-12">
              <Reveal className="mb-10 md:mb-14">
                <h2 className="tx-h4 mb-3" style={{ color: 'var(--text-primary)' }}>By team</h2>
                <p className="tx-lead md:w-2/3" style={{ color: 'var(--text-secondary)' }}>
                  Same platform, framed around the pain each team actually feels — and the workflow it replaces.
                </p>
              </Reveal>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 md:gap-6">
                {TEAMS.map((team) => (
                  <TeamCard key={team.name} team={team} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Works across your paper (contract-type axis, represented as a band) ── */}
      <section className="px-4 sm:px-6 md:px-8 py-16 md:py-24" style={{ borderTop: '1px solid var(--border-color)' }}>
        <div className="page-container">
          <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px] gap-y-8">
            <Reveal className="lg:col-start-2 lg:col-span-4">
              <h2 className="tx-h4 mb-4" style={{ color: 'var(--text-primary)' }}>Works across your paper</h2>
              <p className="tx-body" style={{ color: 'var(--text-secondary)' }}>
                Precedent recognizes which rule-sets apply to a deal — HIPAA, GDPR, SaaS MSA, NDA, DPA — and
                merges them in a fixed order, all seeded from the contracts you’ve already signed. Not a
                generic legal library; your standards, on your agreements.
              </p>
              <div className="mt-6">
                <Link
                  href="/products/playbooks"
                  className="inline-flex items-center gap-1.5 text-sm font-medium transition-colors hover:text-white"
                  style={{ color: 'var(--text-primary)' }}
                >
                  See practice-area routing
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M5 12h14M13 6l6 6-6 6" />
                  </svg>
                </Link>
              </div>
            </Reveal>
            <Reveal delay={120} className="lg:col-start-7 lg:col-span-5 self-center">
              <div className="grid grid-cols-2 gap-3 md:gap-4">
                {PAPER.map((label) => (
                  <div
                    key={label}
                    className="rounded-xl px-5 py-6 text-sm"
                    style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)', color: 'var(--text-primary)' }}
                  >
                    {label}
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>
    </>
  );
}
