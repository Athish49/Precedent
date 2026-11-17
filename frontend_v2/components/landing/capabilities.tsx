'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { SectionLabel, SerifHeading, HairlineTop, useInView } from './primitives';
import { DraftingMockup, TabularMockup, ContractReviewMockup } from './mockups';

const DURATION = 5200; // ms per tab

const TABS = [
  {
    id: 'drafting',
    label: 'Drafting',
    blurb: 'Polished drafts in minutes',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </svg>
    ),
    heading: 'Drafting Studio',
    description:
      'Generate first drafts, clauses, and memos in minutes. A cost-tiered cascade pulls from your playbook and your most-used language before it ever calls the model, so output already meets your positions.',
    cta: 'Explore Drafting',
    mockup: <DraftingMockup />,
  },
  {
    id: 'tabular',
    label: 'Tabular Review',
    blurb: 'Answers from hundreds of docs',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" />
        <rect x="14" y="3" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" />
        <rect x="3" y="14" width="7" height="7" />
      </svg>
    ),
    heading: 'Tabular Review',
    description:
      'Turn a whole portfolio into a spreadsheet you can query. One row per contract, one column per field. Add a natural-language column and every answer stays anchored to a character-level citation.',
    cta: 'Explore Analytics',
    mockup: <TabularMockup />,
  },
  {
    id: 'review',
    label: 'Contract Review',
    blurb: 'Spot risks before they bite',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
    ),
    heading: 'Contract Review',
    description:
      'Review contracts against your playbooks instantly. Deterministic rules flag missing and prohibited clauses before any AI runs; then risk is graded, scored, and cited, issue by issue.',
    cta: 'Explore Contract Analysis',
    mockup: <ContractReviewMockup />,
  },
];

export function Capabilities() {
  const [active, setActive] = useState(0);
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.35 }, false);

  // Auto-advance while the section is on screen.
  useEffect(() => {
    if (!inView) return;
    if (
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      return;
    }
    const id = setTimeout(() => setActive((a) => (a + 1) % TABS.length), DURATION);
    return () => clearTimeout(id);
  }, [active, inView]);

  const current = TABS[active];

  return (
    <section ref={ref} className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28 lg:py-32">
      <HairlineTop />
      <div className="max-w-6xl mx-auto">
        {/* Header row: title left, three summary items right */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-16 items-start mb-12 lg:mb-16">
          <div>
            <SectionLabel text="Drafting & review" />
            <SerifHeading className="text-3xl md:text-4xl lg:text-5xl">
              What Precedent drafts and reviews
            </SerifHeading>
          </div>
          <div className="flex flex-col sm:flex-row gap-6 sm:gap-8 pt-2">
            {TABS.map((t, i) => (
              <button
                key={t.id}
                onClick={() => setActive(i)}
                className="flex-1 text-left transition-opacity"
                style={{ opacity: i === active ? 1 : 0.5 }}
              >
                <div className="mb-2" style={{ color: i === active ? 'var(--text-primary)' : 'var(--text-muted)' }}>{t.icon}</div>
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{t.label}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{t.blurb}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Main card */}
        <div
          className="rounded-2xl overflow-hidden"
          style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2">
            {/* Left: active detail + tab list w/ progress line */}
            <div className="p-6 sm:p-8 lg:p-10 flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <div
                    className="flex items-center justify-center w-8 h-8 rounded-full"
                    style={{ border: '1px solid rgba(255,255,255,0.15)', color: 'var(--text-primary)' }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="9 12 12 15 15 9" />
                    </svg>
                  </div>
                  <h3 className="text-xl md:text-2xl" style={{ fontFamily: 'var(--font-sans)', fontWeight: 400, color: 'var(--text-primary)' }}>
                    {current.heading}
                  </h3>
                </div>
                <p key={active} className="reveal is-in text-sm md:text-base leading-relaxed mb-8" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>
                  {current.description}
                </p>
              </div>

              <div>
                <ul className="space-y-3 mb-8">
                  {TABS.map((t, i) => {
                    const isActive = i === active;
                    return (
                      <li key={t.id}>
                        <button onClick={() => setActive(i)} className="w-full text-left group">
                          <div className="flex items-center text-sm" style={{ color: isActive ? '#fff' : 'rgba(255,255,255,0.35)' }}>
                            <span style={{ fontWeight: isActive ? 500 : 400 }}>{t.label}</span>
                          </div>
                          {/* progress rail under the active item */}
                          <div className="mt-2 h-px w-full relative overflow-hidden" style={{ background: 'rgba(255,255,255,0.1)' }}>
                            {isActive && (
                              <span
                                key={active}
                                className="absolute left-0 top-0 h-px w-full origin-left"
                                data-motion
                                style={{
                                  background: 'rgba(255,255,255,0.85)',
                                  animation: `tab-progress ${DURATION}ms linear forwards`,
                                  animationPlayState: inView ? 'running' : 'paused',
                                }}
                              />
                            )}
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>

                <Link
                  href="#"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium transition-all hover:-translate-y-0.5 active:scale-[0.98]"
                  style={{ border: '1px solid rgba(255,255,255,0.2)', color: 'var(--text-primary)' }}
                >
                  {current.cta} →
                </Link>
              </div>
            </div>

            {/* Right: mockup */}
            <div className="relative min-h-[360px] lg:min-h-0">
              <Image src="/bg.png" alt="" fill className="object-cover" style={{ filter: 'brightness(0.3)' }} />
              <div className="absolute inset-0 flex items-center justify-center p-6 sm:p-8">
                <div key={active} className="w-full max-w-sm reveal is-in">
                  {current.mockup}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
