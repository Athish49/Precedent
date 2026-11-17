'use client';

import { useState } from 'react';
import Image from 'next/image';
import { Reveal, SectionLabel, SerifHeading, HairlineTop } from './primitives';
import { ContractReviewMockup, DraftingMockup, CitationMockup, MonitorMockup } from './mockups';

const STEPS = [
  {
    n: '01',
    title: 'Ingest',
    tag: 'Deterministic',
    desc: 'Upload a PDF or DOCX. We segment every clause with character offsets and extract ~50 metadata fields such as parties, dates, financials, and governing law, with zero AI guesswork.',
    mockup: <CitationMockup />,
  },
  {
    n: '02',
    title: 'Analyze',
    tag: 'Deterministic + AI',
    desc: 'Structural gates catch missing and prohibited clauses instantly. Then batched AI grades risk against your playbook for non-standard, high-risk, and vague language, with a severity-weighted score.',
    mockup: <ContractReviewMockup />,
  },
  {
    n: '03',
    title: 'Redline',
    tag: 'AI, cited',
    desc: 'Surgical tracked-change redlines with alternatives, plain-language rationale, and counterparty-ready comments, tuned to your stance and your negotiation history.',
    mockup: <DraftingMockup />,
  },
  {
    n: '04',
    title: 'Monitor',
    tag: 'Scheduled',
    desc: 'Obligations extracted at signing feed a daily monitor that fires deadline alerts and renewal recommendations, so nothing slips after the ink dries.',
    mockup: <MonitorMockup />,
  },
];

export function HowItWorks() {
  const [active, setActive] = useState(0);

  return (
    <section id="how" className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28 lg:py-32">
      <HairlineTop />
      <div className="max-w-6xl mx-auto">
        <div className="max-w-2xl mb-14">
          <SectionLabel text="How Precedent works" />
          <Reveal>
            <SerifHeading className="text-3xl md:text-4xl lg:text-5xl">
              One pipeline, from upload to renewal
            </SerifHeading>
          </Reveal>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-16 items-start">
          {/* Left: clickable steps */}
          <div className="flex flex-col">
            {STEPS.map((step, i) => {
              const isActive = i === active;
              return (
                <button
                  key={step.n}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => setActive(i)}
                  className="text-left py-5 transition-all"
                  style={{
                    borderTop: i === 0 ? 'none' : '1px solid var(--border-color)',
                    opacity: isActive ? 1 : 0.55,
                  }}
                >
                  <div className="flex items-start gap-4">
                    <span
                      className="text-sm tabular-nums mt-1 transition-colors"
                      style={{ fontFamily: 'var(--font-serif)', color: isActive ? 'var(--text-primary)' : 'var(--text-muted)' }}
                    >
                      {step.n}
                    </span>
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-1">
                        <h3
                          className="text-xl md:text-2xl"
                          style={{ fontFamily: 'var(--font-sans)', fontWeight: 500, color: 'var(--text-primary)' }}
                        >
                          {step.title}
                        </h3>
                        <span
                          className="text-[10px] px-2 py-0.5 rounded-full"
                          style={{ border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}
                        >
                          {step.tag}
                        </span>
                      </div>
                      {/* expand description only when active */}
                      <div
                        className="overflow-hidden transition-all duration-500"
                        style={{ maxHeight: isActive ? 160 : 0, opacity: isActive ? 1 : 0 }}
                      >
                        <p className="text-sm leading-relaxed pt-1" style={{ color: 'var(--text-secondary)', lineHeight: '170%' }}>
                          {step.desc}
                        </p>
                      </div>
                    </div>
                  </div>
                  {/* active progress rail */}
                  <div className="mt-4 h-px w-full relative" style={{ background: 'var(--border-color)' }}>
                    <span
                      className="absolute left-0 top-0 h-px transition-all duration-500"
                      style={{ width: isActive ? '100%' : '0%', background: 'rgba(255,255,255,0.7)' }}
                    />
                  </div>
                </button>
              );
            })}
          </div>

          {/* Right: visual for active step */}
          <div className="lg:sticky lg:top-24">
            <div className="relative rounded-xl overflow-hidden" style={{ aspectRatio: '4/3' }}>
              <Image src="/bg.png" alt="" fill className="object-cover" style={{ filter: 'brightness(0.32)' }} />
              <div className="absolute inset-0 flex items-center justify-center p-4 sm:p-6">
                <div key={active} className="w-full max-w-sm reveal is-in">
                  {STEPS[active].mockup}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
