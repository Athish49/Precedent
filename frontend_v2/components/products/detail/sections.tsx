'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Reveal, useInView, useCountUp } from '@/components/landing/primitives';
import type {
  CapabilityCard,
  ProductPageData,
  Stat,
  Testimonial,
} from './types';

// A reusable placeholder mockup surface. Swap for a real <Image /> later.
function Mockup({
  label,
  gradient,
  className = '',
}: {
  label: string;
  gradient: string;
  className?: string;
}) {
  // `label` retained in the type for future alt text; no on-image text for now.
  void label;
  return (
    <div className={`relative overflow-hidden ${className}`} style={{ background: gradient }}>
      <div className="absolute inset-0" style={{ background: 'rgba(0,0,0,0.15)' }} />
    </div>
  );
}

const DEMO_HREF = '/home';

// The primary CTA button (Harvey: h-12, px-5, medium). Boxy to match the site.
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

// ─── §1 Hero ─────────────────────────────────────────────────────────────────
// 12-col grid, content inset to cols 2–11. Headline cols 2–6, pitch+CTA cols
// 8–11 bottom-aligned (self-end), like Harvey's HeadlineHeroSection.
export function ProductHero({ name, hero }: Pick<ProductPageData, 'name' | 'hero'>) {
  return (
    <section className="relative pt-24 md:pt-28 pb-4 md:pb-6" style={{ background: 'var(--bg-primary)' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-y-8 lg:gap-x-[18px]">
          {/* Breadcrumb — full content width */}
          <Reveal className="lg:col-start-2 lg:col-end-12">
            <p className="text-sm mb-2" style={{ color: 'var(--text-muted)' }}>
              <Link href="/products" className="transition-colors hover:text-white">
                Products
              </Link>
              <span className="mx-2">/</span>
              <span style={{ color: 'var(--text-secondary)' }}>{name}</span>
            </p>
          </Reveal>

          {/* Headline — cols 2–6 */}
          <Reveal className="lg:col-start-2 lg:col-span-5">
            <h1 className="tx-h1" style={{ color: 'var(--text-primary)' }}>
              {hero.headline}
            </h1>
          </Reveal>

          {/* Pitch + CTA — cols 8–11, bottom-aligned */}
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

// ─── §2 Hero image (inset to cols 2–11, mt-lg gap) ───────────────────────────
export function ProductHeroImage({ heroImage }: Pick<ProductPageData, 'heroImage'>) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.1 });
  return (
    <section className="pt-4 md:pt-6 pb-24 md:pb-32" style={{ background: 'var(--bg-primary)' }}>
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

// ─── §4 Capability deep-dive blocks (sticky-stacking) ────────────────────────
// Each block pins at the same offset; the next block slides up and covers the
// previous one (which stays fixed underneath). Header left, content below,
// mockup + sub-points side by side — matching Harvey's ValueProps blocks.
function CapabilityBlock({ card }: { card: CapabilityCard }) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 });
  return (
    <div className="cap-stack-item flex flex-col" style={{ zIndex: 1 }}>
      {/* Header row: heading left, blurb right — hairline on top */}
      <div
        className="flex-none flex flex-col md:flex-row md:justify-between gap-3 md:gap-8 py-6 md:py-7"
        style={{ borderTop: '1px solid var(--border-color)' }}
      >
        <h3 className="tx-h4 w-full md:w-1/2" style={{ color: 'var(--text-primary)' }}>{card.title}</h3>
        <p className="tx-lead w-full md:w-[40%]" style={{ color: 'var(--text-secondary)' }}>{card.blurb}</p>
      </div>

      {/* Content row: mockup left (rises in), sub-points right */}
      <div className="flex flex-col md:flex-row md:justify-between gap-8 md:gap-12 flex-1 min-h-0 pt-2 pb-8 md:pb-0">
        <div
          ref={ref}
          className="w-full md:w-1/2 min-h-0"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(48px)',
            transition: 'opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1)',
          }}
        >
          <Mockup
            label={card.mockupLabel}
            gradient={card.gradient}
            className="w-full h-full min-h-[260px] md:min-h-[340px] rounded-2xl"
          />
        </div>

        <div className="w-full md:w-[40%] md:self-center">
          {card.points.map((p, i) => (
            <div
              key={p.title}
              className="py-5"
              style={i > 0 ? { borderTop: '1px solid var(--border-color)' } : undefined}
            >
              <h4 className="tx-body mb-1.5" style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                {p.title}
              </h4>
              <p className="tx-body" style={{ color: 'var(--text-secondary)' }}>{p.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CapabilityCards({ capabilities }: Pick<ProductPageData, 'capabilities'>) {
  return (
    <section className="pt-20 md:pt-28 pb-16 md:pb-24" style={{ background: 'var(--bg-primary)' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
          <div className="lg:col-start-2 lg:col-end-12">
            {/* section lead */}
            <Reveal className="mb-16 md:mb-24 md:w-1/2">
              <h2 className="tx-h4 mb-4" style={{ color: 'var(--text-primary)' }}>{capabilities.sectionTitle}</h2>
              <p className="tx-lead" style={{ color: 'var(--text-secondary)' }}>{capabilities.sectionIntro}</p>
            </Reveal>

            {/* stacking blocks */}
            <div className="flex flex-col gap-[6rem] lg:gap-[9rem]">
              {capabilities.cards.map((card) => (
                <CapabilityBlock key={card.title} card={card} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── §4.5 Feature spotlight ("Introducing …") ────────────────────────────────
export function Spotlight({ spotlight }: { spotlight: NonNullable<ProductPageData['spotlight']> }) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.25 });
  return (
    <section className="py-16 md:py-24" style={{ background: 'var(--bg-primary)' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px]">
          <div
            ref={ref}
            className="lg:col-start-2 lg:col-end-12 rounded-3xl overflow-hidden"
            style={{
              border: '1px solid var(--border-color)',
              background: 'rgba(255,255,255,0.02)',
              opacity: inView ? 1 : 0,
              transform: inView ? 'translateY(0)' : 'translateY(40px)',
              transition: 'opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1)',
            }}
          >
            <div className="grid grid-cols-1 lg:grid-cols-2 items-stretch">
              <Mockup
                label={spotlight.mockupLabel}
                gradient={spotlight.gradient}
                className="w-full min-h-[300px] lg:min-h-[460px]"
              />
              <div className="flex flex-col items-center justify-center text-center px-8 py-16 lg:py-24">
                <span className="text-xs font-medium tracking-widest uppercase mb-5" style={{ color: 'var(--text-muted)' }}>
                  {spotlight.kicker}
                </span>
                <h2 className="tx-h2 mb-5" style={{ color: 'var(--text-primary)' }}>{spotlight.title}</h2>
                <p className="tx-lead max-w-md" style={{ color: 'var(--text-secondary)' }}>{spotlight.tagline}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── §5a Impact metrics ──────────────────────────────────────────────────────
function StatRow({ stat, isFirst }: { stat: Stat; isFirst: boolean }) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 });
  const n = useCountUp(stat.value, inView);
  const display = Number.isInteger(stat.value) ? Math.round(n) : n.toFixed(1);
  return (
    <div
      ref={ref}
      className={isFirst ? 'pb-5 md:pb-6' : 'py-5 md:py-6'}
      style={!isFirst ? { borderTop: '1px solid var(--border-color)' } : undefined}
    >
      <div className="tx-h1" style={{ color: 'var(--text-primary)' }}>
        {stat.prefix}
        {display}
        {stat.suffix}
      </div>
      <p className="tx-body mt-1" style={{ color: 'var(--text-muted)' }}>{stat.label}</p>
    </div>
  );
}

function TestimonialCarousel({ testimonials }: { testimonials: Testimonial[] }) {
  const [index, setIndex] = useState(0);
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.3 }, false);

  useEffect(() => {
    if (!inView || testimonials.length <= 1) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = setTimeout(() => setIndex((i) => (i + 1) % testimonials.length), 6000);
    return () => clearTimeout(id);
  }, [index, inView, testimonials.length]);

  return (
    <div ref={ref} className="relative overflow-hidden">
      <div
        className="flex"
        style={{ transform: `translateX(-${index * 100}%)`, transition: 'transform 0.7s cubic-bezier(0.16,1,0.3,1)' }}
      >
        {testimonials.map((t) => (
          <div key={t.name + t.quote.slice(0, 12)} className="w-full flex-shrink-0">
            <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-6 lg:gap-12">
              <div>
                <p className="tx-body" style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{t.name}</p>
                <p className="tx-body mb-4" style={{ color: 'var(--text-muted)' }}>{t.role}</p>
                <p className="text-xs tracking-widest uppercase" style={{ color: 'var(--text-secondary)' }}>{t.firm}</p>
              </div>
              <blockquote className="tx-h3" style={{ color: 'var(--text-primary)' }}>
                &ldquo;{t.quote}&rdquo;
              </blockquote>
            </div>
          </div>
        ))}
      </div>

      {testimonials.length > 1 && (
        <div className="flex gap-2 mt-10 lg:ml-[288px]">
          {testimonials.map((t, i) => (
            <button
              key={i}
              aria-label={`Show testimonial ${i + 1}`}
              onClick={() => setIndex(i)}
              className="h-1 rounded-full transition-all"
              style={{ width: i === index ? 28 : 12, background: i === index ? 'var(--text-primary)' : 'rgba(255,255,255,0.25)' }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function ImpactMetrics({ impact }: { impact: NonNullable<ProductPageData['impact']> }) {
  return (
    <section
      className="py-14 md:py-16"
      style={{ background: 'rgba(255,255,255,0.02)', borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)' }}
    >
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px] gap-y-8">
          <div className="lg:col-start-2 lg:col-span-4">
            <h2 className="tx-h4" style={{ color: 'var(--text-primary)' }}>{impact.heading}</h2>
          </div>
          <div className="lg:col-start-7 lg:col-span-5">
            {impact.stats.map((s, i) => (
              <StatRow key={s.label} stat={s} isFirst={i === 0} />
            ))}
          </div>
        </div>

        {impact.testimonials.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px] mt-6 md:mt-8">
            <div className="lg:col-start-2 lg:col-end-12 pt-8" style={{ borderTop: '1px solid var(--border-color)' }}>
              <TestimonialCarousel testimonials={impact.testimonials} />
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

// ─── §6 "In action" catalog (dark, list ↔ mockup) ────────────────────────────
export function InActionCatalog({ catalog }: { catalog: NonNullable<ProductPageData['catalog']> }) {
  const [active, setActive] = useState(0);
  const current = catalog.items[active];

  return (
    <section className="py-20 md:py-28" style={{ background: '#000000' }}>
      <div className="page-container">
        <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-x-[18px] gap-y-10 items-start">
          {/* Left: selectable list — cols 2–6 */}
          <div className="order-2 lg:order-1 lg:col-start-2 lg:col-span-5">
            {catalog.items.map((item, i) => {
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
                  <div className="overflow-hidden transition-all" style={{ maxHeight: isActive ? 140 : 0, opacity: isActive ? 1 : 0 }}>
                    <p className="tx-body mt-2 max-w-md" style={{ color: 'var(--text-secondary)' }}>{item.desc}</p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Right: swapping mockup — cols 8–11 (gap col 7), top-aligned with the list */}
          <div className="order-1 lg:order-2 lg:col-start-8 lg:col-span-4">
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
