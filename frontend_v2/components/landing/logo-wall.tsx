const LOGOS = ['Y Combinator', 'Plug and Play', 'Google for Startups', 'Sequoia Scout', 'Lovable', 'a16z speedrun'];

export function LogoWall() {
  return (
    <section className="relative py-10 md:py-12 overflow-hidden" style={{ borderBottom: '1px solid var(--border-color)' }}>
      <p className="text-center text-xs mb-6" style={{ color: 'var(--text-muted)' }}>
        Trusted by legal teams at high-growth companies and Am&nbsp;Law firms
      </p>
      <div className="relative">
        {/* edge fades */}
        <div className="absolute left-0 top-0 bottom-0 w-24 z-10 pointer-events-none" style={{ background: 'linear-gradient(to right, #0a0a0a, transparent)' }} />
        <div className="absolute right-0 top-0 bottom-0 w-24 z-10 pointer-events-none" style={{ background: 'linear-gradient(to left, #0a0a0a, transparent)' }} />
        <div className="flex overflow-hidden">
          <div className="flex animate-marquee whitespace-nowrap gap-16 pr-16" data-motion>
            {[...LOGOS, ...LOGOS].map((name, i) => (
              <span
                key={`${name}-${i}`}
                className="text-sm font-medium flex-shrink-0 transition-opacity opacity-40 hover:opacity-90"
                style={{ color: 'var(--text-primary)' }}
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
