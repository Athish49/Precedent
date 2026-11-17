import Link from 'next/link';
import { Reveal, SectionLabel, SerifHeading, HairlineTop } from './primitives';

const POINTS = [
  { t: 'SOC 2 Type II', d: 'Independently audited controls.' },
  { t: 'No training on your data', d: 'Your contracts never train a model.' },
  { t: 'Encrypted end to end', d: 'At rest and in transit.' },
  { t: 'Every AI action logged', d: 'Deterministic, auditable by design.' },
];

export function Security() {
  return (
    <section className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28">
      <HairlineTop />
      <div className="max-w-6xl mx-auto">
        <div className="max-w-2xl mb-12">
          <SectionLabel text="Security & trust" />
          <Reveal>
            <SerifHeading className="text-3xl md:text-4xl lg:text-5xl mb-4">
              Enterprise-grade, auditable by design
            </SerifHeading>
          </Reveal>
          <p className="text-base" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>
            Because everything structural is deterministic code, most of the platform is reproducible and
            explainable without a model in the loop, and where AI runs, it&rsquo;s always cited and logged.
          </p>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-px rounded-2xl overflow-hidden mb-8" style={{ background: 'var(--border-color)' }}>
          {POINTS.map((p, i) => (
            <Reveal key={p.t} delay={i * 70}>
              <div className="h-full p-6" style={{ background: '#0a0a0a' }}>
                <div className="mb-3" style={{ color: 'var(--text-secondary)' }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                </div>
                <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>{p.t}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{p.d}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          Built for in-house legal, ops, procurement, sales &amp; compliance, across SaaS, NDA, DPA &amp; HIPAA.{' '}
          <Link href="/solutions" className="underline transition-colors hover:text-white" style={{ color: 'var(--text-secondary)' }}>
            See solutions →
          </Link>
        </p>
      </div>
    </section>
  );
}
