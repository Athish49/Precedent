'use client';

import { Reveal, SectionLabel, SerifHeading, HairlineTop, useInView, useCountUp } from './primitives';

const PAINS = [
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <polyline points="12 7 12 12 15 14" />
      </svg>
    ),
    title: 'Weeks of backlog',
    desc: 'Every contract waits behind a human queue. Deals slip while reviewers dig through the same clauses again and again.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16v4H4zM4 10h10v4H4zM4 16h13v4H4z" />
      </svg>
    ),
    title: 'Inconsistent positions',
    desc: 'The same clause negotiated three different ways. Standards live in people’s heads and stale Word docs, not in one enforceable place.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9.5 2a5.5 5.5 0 0 0-5 7.8L3 14l3-1 .5.2A5.5 5.5 0 1 0 9.5 2z" />
        <line x1="9" y1="9" x2="9" y2="9.01" />
        <line x1="13" y1="12" x2="13" y2="12.01" />
      </svg>
    ),
    title: 'Zero institutional memory',
    desc: 'Nobody remembers how you closed the last deal with this counterparty, or which fallback they accepted six months ago.',
  },
];

function BacklogCounter() {
  const { ref, inView } = useInView<HTMLDivElement>();
  const count = useCountUp(1284, inView, 1800);
  return (
    <div ref={ref} className="text-right">
      <div
        className="text-2xl md:text-3xl tabular-nums"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}
      >
        {Math.round(count).toLocaleString()}
      </div>
      <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>contracts in queue right now</p>
    </div>
  );
}

export function Problem() {
  return (
    <section className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28">
      <HairlineTop />
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6 mb-14">
          <div className="max-w-2xl">
            <SectionLabel text="The old way is broken" />
            <Reveal>
              <SerifHeading className="text-3xl md:text-4xl lg:text-5xl">
                Contract review hasn&rsquo;t changed in 50 years. Your business has.
              </SerifHeading>
            </Reveal>
          </div>
          <BacklogCounter />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {PAINS.map((p, i) => (
            <Reveal key={p.title} delay={i * 100}>
              <div
                className="h-full rounded-2xl p-6 transition-colors"
                style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}
              >
                <div className="mb-5" style={{ color: 'var(--text-secondary)' }}>{p.icon}</div>
                <h3 className="text-lg mb-2" style={{ fontFamily: 'var(--font-sans)', fontWeight: 500, color: 'var(--text-primary)' }}>
                  {p.title}
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)', lineHeight: '165%' }}>
                  {p.desc}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
