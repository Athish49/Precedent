'use client';

import { Reveal, SectionLabel, SerifHeading, HairlineTop, useInView, useCountUp } from './primitives';

const R = 42;
const CIRC = 2 * Math.PI * R;
const SAVED = 0.77; // 77%

function Donut() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 });
  return (
    <div ref={ref} className="relative w-full max-w-sm mx-auto aspect-square">
      <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
        {/* remaining track */}
        <circle cx="60" cy="60" r={R} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="14" />
        {/* saved arc — draws in on view */}
        <circle
          cx="60" cy="60" r={R} fill="none" stroke="url(#donutGrad)" strokeWidth="14" strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={inView ? CIRC * (1 - SAVED) : CIRC}
          data-motion
          style={{ transition: 'stroke-dashoffset 1.6s cubic-bezier(0.16,1,0.3,1)' }}
        />
        <defs>
          <linearGradient id="donutGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#9ca3af" />
          </linearGradient>
        </defs>
      </svg>
      {/* center label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl md:text-5xl" style={{ fontFamily: 'var(--font-serif)', letterSpacing: '-0.02em' }}>77%</span>
        <span className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>less review time</span>
      </div>
      {/* callouts */}
      <div className="absolute -top-1 right-2 text-right">
        <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>23%</div>
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>hands-on review</div>
      </div>
      <div className="absolute bottom-2 left-0 text-left">
        <div className="text-sm" style={{ color: 'var(--text-primary)' }}>77%</div>
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>automated away</div>
      </div>
    </div>
  );
}

function Stat({ value, suffix, prefix, label }: { value: number; suffix?: string; prefix?: string; label: string }) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.5 });
  const n = useCountUp(value, inView);
  const display = Number.isInteger(value) ? Math.round(n).toLocaleString() : n.toFixed(1);
  return (
    <div ref={ref} className="text-center sm:text-left">
      <div className="text-3xl md:text-4xl lg:text-5xl mb-1" style={{ fontFamily: 'var(--font-serif)', letterSpacing: '-0.02em' }}>
        {prefix}{display}{suffix}
      </div>
      <p className="text-xs sm:text-sm" style={{ color: 'var(--text-muted)' }}>{label}</p>
    </div>
  );
}

export function Impact() {
  return (
    <section className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28 lg:py-32 overflow-hidden">
      <HairlineTop />
      {/* drifting mesh backdrop */}
      <div
        className="absolute inset-0 -z-10 opacity-40 pointer-events-none"
        data-motion
        style={{
          background: 'radial-gradient(600px circle at 70% 30%, rgba(255,255,255,0.06), transparent 60%)',
          animation: 'mesh-drift 18s ease-in-out infinite',
        }}
      />
      <div className="max-w-6xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center mb-16 lg:mb-20">
          <div>
            <SectionLabel text="Case study" />
            <Reveal>
              <SerifHeading className="text-3xl md:text-4xl lg:text-5xl mb-5">
                77% less review time. 24-hour turnaround.
              </SerifHeading>
            </Reveal>
            <p className="text-base" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>
              A Series-C SaaS legal team replaced two outside counsel workflows with Precedent. Their
              average commercial contract turnaround dropped from 13 days to under 24 hours, and their
              per-contract legal spend fell by three quarters.
            </p>
          </div>
          <Donut />
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 pt-10" style={{ borderTop: '1px solid var(--border-color)' }}>
          <Stat prefix="$" value={4.2} suffix="B" label="Contract value handled" />
          <Stat value={4} suffix="-hr" label="Average turnaround" />
          <Stat prefix="+" value={200} label="In-house teams" />
          <Stat value={40} suffix="+" label="Countries" />
        </div>
      </div>
    </section>
  );
}
