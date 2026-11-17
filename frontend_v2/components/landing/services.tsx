'use client';

import Link from 'next/link';
import { Reveal, SectionLabel, SerifHeading, HairlineTop } from './primitives';

const SERVICES = [
  { name: 'Contract Analysis', href: '/products/contract-analysis', desc: 'Surface every risk in seconds.' },
  { name: 'Redlining & Negotiation', href: '/products/redlining', desc: 'Tracked changes with a memory.' },
  { name: 'Autonomous Review', href: '/products/autonomous-review', desc: 'AI reviews, escalates only what matters.' },
  { name: 'Drafting Studio', href: '/products/drafting', desc: 'First drafts from your own playbook.' },
  { name: 'Playbooks & Standards', href: '/products/playbooks', desc: 'Your standards, enforced at scale.' },
  { name: 'Document Intelligence', href: '/products/document-intelligence', desc: 'Ask any contract anything.' },
  { name: 'Repository & Search', href: '/products/repository', desc: 'Find any clause, instantly.' },
  { name: 'Obligations & Monitoring', href: '/products/obligations', desc: 'Never miss a renewal again.' },
  { name: 'Analytics & Reporting', href: '/products/analytics', desc: 'Portfolio-wide risk at a glance.' },
];

export function Services() {
  return (
    <section className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28 lg:py-32">
      <HairlineTop />
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6 mb-12">
          <div className="max-w-2xl">
            <SectionLabel text="One platform, nine services" />
            <Reveal>
              <SerifHeading className="text-3xl md:text-4xl lg:text-5xl">
                Everything your contract lifecycle needs
              </SerifHeading>
            </Reveal>
          </div>
          <Link
            href="/products"
            className="text-sm whitespace-nowrap transition-colors hover:text-white"
            style={{ color: 'var(--text-secondary)' }}
          >
            Explore all products →
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px rounded-2xl overflow-hidden" style={{ background: 'var(--border-color)' }}>
          {SERVICES.map((s, i) => (
            <Reveal key={s.name} delay={(i % 3) * 80}>
              <Link
                href={s.href}
                className="group block h-full p-6 transition-colors"
                style={{ background: '#0a0a0a' }}
              >
                <div
                  className="flex items-start justify-between gap-3 h-full transition-transform duration-300 group-hover:-translate-y-0.5"
                >
                  <div>
                    <h3
                      className="text-base mb-1.5 transition-colors"
                      style={{ fontFamily: 'var(--font-sans)', fontWeight: 500, color: 'var(--text-primary)' }}
                    >
                      {s.name}
                    </h3>
                    <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{s.desc}</p>
                  </div>
                  <span
                    className="mt-1 opacity-0 -translate-x-1 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    →
                  </span>
                </div>
              </Link>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
