'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Reveal, useInView, useCountUp } from '@/components/landing/primitives';
import type { IconName, Pillar, SolutionPageData, Stat, UseCase } from './types';

// Placeholder mockup surface — mirrors the products engine. Swap for <Image /> later.
function Mockup({ label, gradient, className = '' }: { label: string; gradient: string; className?: string }) {
  void label;
  return (
    <div className={`relative overflow-hidden ${className}`} style={{ background: gradient }}>
      <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.15)' }} />
    </div>
  );
}

const DEMO_HREF = '/home';

function DemoButton({ children = 'Request a Demo' }: { children?: string }) {
  return (
    <Link
      href={DEMO_HREF}
      className="inline-flex h-12 items-center justify-center px-5 rounded-lg text-sm font-medium whitespace-nowrap transition-all hover:-translate-y-0.5 active:scale-[0.98]"
      style={{ background: 'var(--button-primary-bg)', color: 'var(--button-primary-text)' }}
    >
      {children}
    </Link>
  );
}

// ─── Icon vocabulary (line icons, 24×24, stroke=currentColor) ────────────────
const ICON_PATHS: Record<IconName, string> = {
  clock: 'M12 7v5l3 2M12 21a9 9 0 100-18 9 9 0 000 18z',
  shield: 'M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6l7-3z',
  layers: 'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17l9 5 9-5',
  bolt: 'M13 2L4 14h6l-1 8 9-12h-6l1-8z',
  target: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 16a4 4 0 100-8 4 4 0 000 8zM12 12h.01',
  chart: 'M4 20V10M10 20V4M16 20v-6M22 20H2',
  lock: 'M6 11V8a6 6 0 1112 0v3M5 11h14v10H5V11z',
  search: 'M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3',
  bell: 'M6 8a6 6 0 1112 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 003.4 0',
  scale: 'M12 3v18M5 21h14M3 8l4-4 4 4-4 6-4-6zM13 8l4-4 4 4-4 6-4-6z',
  route: 'M6 3v12a4 4 0 004 4h4M6 3a2 2 0 100 4 2 2 0 000-4zM18 17a2 2 0 100 4 2 2 0 000-4z',
  check: 'M20 6L9 17l-5-5',
};

function Icon({ name }: { name: IconName }) {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

// ─── §1 Hero ─────────────────────────────────────────────────────────────────
// "For <team>" eyebrow + serif headline (cols 2–6), pitch + CTA bottom-aligned
// (cols 8–11) — Harvey's HeadlineHeroSection.
export function SolutionHero({ hero }: Pick<SolutionPageData, 'hero'>) {
  return (
    <section className="relative pt-24 md:pt-28 pb-4 md:pb-6" style={{ background: 'var(--bg-primary)' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-y-8 lg:gap-x-[18px]">
          <Reveal className="lg:col-start-2 lg:col-end-12">
            <p className="text-xs font-medium tracking-widest uppercase mb-4" style={{ color: 'var(--text-muted)' }}>
              {hero.eyebrow}
            </p>
          </Reveal>

          <Reveal className="lg:col-start-2 lg:col-span-5">
            <h1 className="tx-h1" style={{ color: 'var(--text-primary)' }}>
              {hero.headline}
            </h1>
          </Reveal>

          <Reveal delay={120} className="lg:col-start-8 lg:col-span-4 lg:self-end lg:mb-2">
            <div className="flex flex-col gap-5 md:gap-6">
              <p className="tx-lead" style={{ color: 'var(--text-secondary)' }}>
                {hero.pitch}
              </p>
              <div>
                <DemoButton />
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ─── §1.5 Hero image ─────────────────────────────────────────────────────────
export function SolutionHeroImage({ heroImage }: Pick<SolutionPageData, 'heroImage'>) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.1 });
  return (
    <section className="pt-4 md:pt-6 pb-16 md:pb-20" style={{ background: 'var(--bg-primary)' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
          <div
            ref={ref}
            className="lg:col-start-2 lg:col-end-12 rounded-2xl overflow-hidden"
            style={{
              border: '1px solid var(--border-color)',
              opacity: inView ? 1 : 0,
              transform: inView ? 'scale(1)' : 'scale(0.98)',
              transition: 'opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1)',
            }}
          >
            <Mockup label={heroImage.label} gradient={heroImage.gradient} className="w-full aspect-[16/9]" />
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── §2 Proof band — fictional, self-consistent wordmarks ────────────────────
export function ProofBand({ proof }: Pick<SolutionPageData, 'proof'>) {
  return (
    <section className="py-14 md:py-16" style={{ background: 'var(--bg-primary)' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
          <div className="lg:col-start-2 lg:col-end-12">
            <Reveal>
              <p className="text-center text-sm mb-8" style={{ color: 'var(--text-muted)' }}>{proof.caption}</p>
            </Reveal>
            <Reveal delay={80}>
              <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-6 md:gap-x-14">
                {proof.logos.map((logo) => (
                  <span
                    key={logo}
                    className="text-lg md:text-xl font-medium tracking-tight"
                    style={{ color: 'var(--text-secondary)', opacity: 0.7, fontFamily: 'var(--font-serif)' }}
                  >
                    {logo}
                  </span>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── §3 Pillars — "Built for <team>" (three icon columns) ────────────────────
function PillarCol({ pillar }: { pillar: Pillar }) {
  return (
    <Reveal className="flex flex-col">
      <div style={{ color: 'var(--text-primary)' }}>
        <Icon name={pillar.icon} />
      </div>
      <h3 className="tx-h4 mt-5 mb-3" style={{ color: 'var(--text-primary)' }}>{pillar.title}</h3>
      <p className="tx-body" style={{ color: 'var(--text-secondary)' }}>{pillar.desc}</p>
    </Reveal>
  );
}

export function PillarsSection({ pillars }: Pick<SolutionPageData, 'pillars'>) {
  return (
    <section className="py-20 md:py-28" style={{ background: 'var(--bg-primary)', borderTop: '1px solid var(--border-color)' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
          <div className="lg:col-start-2 lg:col-end-12">
            <Reveal className="mb-12 md:mb-16 md:w-2/3">
              <h2 className="tx-h2" style={{ color: 'var(--text-primary)' }}>{pillars.sectionTitle}</h2>
              {pillars.sectionIntro && (
                <p className="tx-lead mt-4" style={{ color: 'var(--text-secondary)' }}>{pillars.sectionIntro}</p>
              )}
            </Reveal>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-12">
              {pillars.items.map((p) => (
                <PillarCol key={p.title} pillar={p} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── §4 Use cases — dark interactive list ↔ swapping mockup ──────────────────
// Harvey's "How Law Firms Use Harvey": a selectable list on the left that swaps
// the mockup on the right. Each item is a DISTINCT day-in-the-life scenario.
export function UseCasesSection({ useCases }: Pick<SolutionPageData, 'useCases'>) {
  const [active, setActive] = useState(0);
  const current: UseCase = useCases.items[active];

  return (
    <section className="py-20 md:py-28" style={{ background: '#000000' }}>
      <div className="page-container">
        <Reveal className="mb-12 md:mb-16">
          <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
            <div className="lg:col-start-2 lg:col-end-11">
              <h2 className="tx-h2" style={{ color: 'var(--text-primary)' }}>{useCases.sectionTitle}</h2>
              {useCases.sectionIntro && (
                <p className="tx-lead mt-4 md:w-3/4" style={{ color: 'var(--text-secondary)' }}>{useCases.sectionIntro}</p>
              )}
            </div>
          </div>
        </Reveal>

        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px] gap-y-10 items-start">
          {/* Left: selectable list — cols 2–6 */}
          <div className="order-2 lg:order-1 lg:col-start-2 lg:col-span-5">
            {useCases.items.map((item, i) => {
              const isActive = i === active;
              return (
                <button
                  key={item.name}
                  onClick={() => setActive(i)}
                  className="w-full text-left py-6"
                  style={i > 0 ? { borderTop: '1px solid rgba(255,255,255,0.1)' } : undefined}
                >
                  <h3
                    className="text-2xl font-medium transition-colors"
                    style={{ color: isActive ? 'var(--text-primary)' : 'rgba(255,255,255,0.4)' }}
                  >
                    {item.name}
                  </h3>
                  <div className="overflow-hidden transition-all" style={{ maxHeight: isActive ? 200 : 0, opacity: isActive ? 1 : 0 }}>
                    <p className="tx-body mt-2 max-w-md" style={{ color: 'var(--text-secondary)' }}>{item.desc}</p>
                    {item.href && item.linkLabel && (
                      <Link
                        href={item.href}
                        className="group mt-4 inline-flex items-center gap-1.5 text-sm font-medium transition-colors hover:text-white"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {item.linkLabel}
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
                          <path d="M5 12h14M13 6l6 6-6 6" />
                        </svg>
                      </Link>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Right: swapping mockup — cols 7–11, top-aligned */}
          <div className="order-1 lg:order-2 lg:col-start-7 lg:col-span-5">
            <Mockup
              key={active}
              label={current.mockupLabel}
              gradient={current.gradient}
              className="reveal is-in w-full aspect-[4/3] rounded-2xl"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── §5 Featured testimonial — full-bleed portrait + big serif quote ─────────
export function FeaturedTestimonial({ featured }: Pick<SolutionPageData, 'featured'>) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 });
  return (
    <section className="py-20 md:py-28" style={{ background: 'var(--bg-primary)' }}>
      <div className="page-container">
        <div
          ref={ref}
          className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px] items-center gap-y-8"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(32px)',
            transition: 'opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1)',
          }}
        >
          <div className="lg:col-start-2 lg:col-span-4">
            <Mockup
              label={`${featured.name} — portrait`}
              gradient={featured.portraitGradient}
              className="w-full aspect-square rounded-2xl"
            />
          </div>
          <div className="lg:col-start-7 lg:col-span-5">
            <blockquote className="tx-h3" style={{ color: 'var(--text-primary)' }}>
              &ldquo;{featured.quote}&rdquo;
            </blockquote>
            <div className="mt-8">
              <p className="tx-body" style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{featured.name}</p>
              <p className="tx-body" style={{ color: 'var(--text-muted)' }}>{featured.role}</p>
              <p className="text-xs tracking-widest uppercase mt-2" style={{ color: 'var(--text-secondary)' }}>{featured.firm}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── §6 Impact — count-up metrics band ───────────────────────────────────────
function StatBlock({ stat }: { stat: Stat }) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 });
  const n = useCountUp(stat.value, inView);
  const display = Number.isInteger(stat.value) ? Math.round(n) : n.toFixed(1);
  return (
    <div ref={ref}>
      <div className="tx-h1" style={{ color: 'var(--text-primary)' }}>
        {stat.prefix}
        {display}
        {stat.suffix}
      </div>
      <p className="tx-body mt-2" style={{ color: 'var(--text-muted)' }}>{stat.label}</p>
    </div>
  );
}

export function ImpactStats({ impact }: Pick<SolutionPageData, 'impact'>) {
  return (
    <section
      className="py-16 md:py-20"
      style={{ background: 'rgba(255,255,255,0.02)', borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)' }}
    >
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px] gap-y-10">
          <Reveal className="lg:col-start-2 lg:col-span-3">
            <h2 className="tx-h4" style={{ color: 'var(--text-primary)' }}>{impact.heading}</h2>
          </Reveal>
          <div className="lg:col-start-6 lg:col-end-12 grid grid-cols-1 sm:grid-cols-3 gap-8 md:gap-10">
            {impact.stats.map((s) => (
              <StatBlock key={s.label} stat={s} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
