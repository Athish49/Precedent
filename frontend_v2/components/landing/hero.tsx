import Image from 'next/image';
import { PillButton } from './primitives';

const METRICS = [
  { value: '$4.2B', label: 'contract value analyzed' },
  { value: '1.2M', label: 'clauses reviewed' },
  { value: '92%', label: 'faster first-pass review' },
  { value: '200+', label: 'legal teams' },
];

export function Hero() {
  return (
    <section className="min-h-screen relative overflow-hidden" style={{ background: 'var(--bg-primary)' }}>
      <Image
        src="/bg.png"
        alt="Background"
        fill
        className="object-cover"
        sizes="100vw"
        priority
        quality={45}
      />
      <div
        className="absolute inset-0"
        style={{ background: 'linear-gradient(rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.5) 50%, rgba(0,0,0,0.82) 100%)' }}
      />
      <div
        className="absolute bottom-0 left-0 right-0 h-32 z-10 pointer-events-none"
        style={{ background: 'linear-gradient(to bottom, transparent 0%, #0a0a0a 100%)' }}
      />

      <div className="flex flex-col min-h-screen relative z-10">
        <div className="grow flex items-center justify-center">
          <div className="max-w-5xl mx-auto px-6 sm:px-10 md:px-12 lg:px-16 pt-28 sm:pt-32 md:pt-36 pb-6 relative z-10">
            {/* Eyebrow */}
            <div className="flex justify-center mb-5">
              <span
                className="text-[11px] font-medium tracking-[0.2em] uppercase"
                style={{ color: 'rgba(255,255,255,0.55)' }}
              >
                Contract Intelligence Platform
              </span>
            </div>

            <h1
              className="text-center mb-4 md:mb-5 text-4xl sm:text-5xl md:text-6xl lg:text-7xl"
              style={{
                fontFamily: 'var(--font-serif)',
                fontWeight: 400,
                lineHeight: '110%',
                letterSpacing: '-0.02em',
                color: 'var(--text-primary)',
              }}
            >
              The AI legal team<br className="hidden sm:block" /> that never sleeps.
            </h1>
            <p
              className="text-center max-w-2xl mx-auto mb-8 md:mb-10 text-sm sm:text-base md:text-lg px-4"
              style={{
                fontFamily: 'var(--font-sans)',
                fontWeight: 400,
                lineHeight: '160%',
                letterSpacing: '-0.01em',
                color: 'rgba(255,255,255,0.9)',
              }}
            >
              From upload to renewal, every contract is analyzed, redlined, and monitored in
              minutes, not weeks. Deterministic where it matters, AI where it counts, auditable everywhere.
            </p>
            <div className="flex flex-wrap justify-center gap-3 mb-12">
              <PillButton href="#">Book a Demo</PillButton>
              <PillButton href="#how" outline>
                See it in action ▸
              </PillButton>
            </div>

            {/* Metric ticker */}
            <div className="max-w-3xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-y-4">
              {METRICS.map(({ value, label }, i) => (
                <div
                  key={label}
                  className={`text-center px-2 ${i > 0 ? 'sm:border-l' : ''}`}
                  style={{ borderColor: 'rgba(255,255,255,0.1)' }}
                >
                  <div
                    className="text-2xl md:text-3xl"
                    style={{ fontFamily: 'var(--font-serif)', fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}
                  >
                    {value}
                  </div>
                  <p className="text-[10px] sm:text-xs mt-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    {label}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
