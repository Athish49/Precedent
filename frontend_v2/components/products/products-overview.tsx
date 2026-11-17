'use client';

import { Reveal, SectionLabel, SerifHeading, PillButton } from '@/components/landing/primitives';
import { ProductJourney } from './product-journey';

export function ProductsOverview() {
  return (
    <>
      {/* ── Header ─────────────────────────────────────────────── */}
      <section className="relative px-4 sm:px-6 md:px-8 pt-32 md:pt-40 pb-8 md:pb-12">
        <div className="max-w-3xl mx-auto">
          <SectionLabel text="Products" />
          <Reveal>
            <SerifHeading className="text-4xl md:text-5xl lg:text-6xl mb-6">
              Contracts, minus the busywork.
            </SerifHeading>
          </Reveal>
          <Reveal delay={80}>
            <p className="text-base md:text-lg mb-8" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>
              From first draft to final renewal, Precedent drafts, reviews, and tracks every
              agreement for you — so your team moves faster and nothing slips through the cracks.
            </p>
          </Reveal>
          <Reveal delay={160} className="flex flex-wrap gap-3">
            <PillButton href="/home">Book a demo</PillButton>
            <PillButton href="/#how" outline>See how it works</PillButton>
          </Reveal>
        </div>
      </section>

      {/* ── Product journey (scroll-lit, alternating rows) ─────── */}
      <ProductJourney />
    </>
  );
}
