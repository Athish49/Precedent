import Image from 'next/image';
import Link from 'next/link';
import { PillButton, SerifHeading } from './primitives';

const FOOTER_COLS = [
  {
    heading: 'Products',
    links: [
      { label: 'Drafting Studio', href: '/products/drafting' },
      { label: 'Playbooks & Standards', href: '/products/playbooks' },
      { label: 'Contract Analysis', href: '/products/contract-analysis' },
      { label: 'Redlining & Negotiation', href: '/products/redlining' },
      { label: 'Autonomous Review', href: '/products/autonomous-review' },
      { label: 'Document Intelligence', href: '/products/document-intelligence' },
      { label: 'Repository & Search', href: '/products/repository' },
      { label: 'Obligations & Monitoring', href: '/products/obligations' },
      { label: 'Analytics & Reporting', href: '/products/analytics' },
    ],
  },
  {
    heading: 'Solutions',
    links: [
      { label: 'In-house Legal', href: '/solutions' },
      { label: 'Legal Operations', href: '/solutions/legal-ops' },
      { label: 'Procurement & Sourcing', href: '/solutions/procurement' },
      { label: 'Sales / Deal Desk', href: '/solutions/sales' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About', href: '#' },
      { label: 'Security', href: '#' },
      { label: 'Careers', href: '#' },
      { label: 'Contact', href: '#' },
    ],
  },
  {
    heading: 'Resources',
    links: [
      { label: 'Blog', href: '#' },
      { label: 'Guides', href: '#' },
      { label: 'Glossary', href: '#' },
      { label: 'Changelog', href: '#' },
    ],
  },
];

export function CtaFooter() {
  return (
    <>
      {/* ── Final CTA ── */}
      <section className="relative px-4 sm:px-6 md:px-8 py-24 md:py-36 text-center overflow-hidden">
        <Image src="/bg.png" alt="" fill className="object-cover" style={{ filter: 'brightness(0.28)' }} />
        <div className="absolute inset-0" style={{ background: 'linear-gradient(to bottom, #0a0a0a 0%, rgba(10,10,10,0.4) 50%, #0a0a0a 100%)' }} />
        <div className="relative z-10 max-w-3xl mx-auto">
          <SerifHeading className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl mb-6">
            Give your legal team superpowers.
          </SerifHeading>
          <p className="text-base md:text-lg mb-10" style={{ color: 'var(--text-secondary)', lineHeight: '170%' }}>
            See Precedent on your own contracts in a 20-minute demo. Setup in a day, cancel anytime.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <PillButton href="#">Book a Demo</PillButton>
            <PillButton href="/home" outline>Launch App</PillButton>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="px-4 sm:px-6 md:px-8 pt-16 pb-10" style={{ borderTop: '1px solid var(--border-color)' }}>
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-10 mb-14">
            <div className="col-span-2 md:col-span-1">
              <Link href="/" className="flex items-center gap-2 mb-3">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="white" aria-hidden="true">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
                </svg>
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Precedent</span>
              </Link>
              <p className="text-xs max-w-[200px]" style={{ color: 'var(--text-muted)' }}>
                Contract intelligence for in-house counsel.
              </p>
            </div>
            {FOOTER_COLS.map((col) => (
              <div key={col.heading}>
                <p className="text-[11px] font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--text-muted)' }}>{col.heading}</p>
                <ul className="space-y-2.5">
                  {col.links.map((l) => (
                    <li key={l.label}>
                      <Link href={l.href} className="text-sm transition-colors hover:text-white" style={{ color: 'var(--text-secondary)' }}>{l.label}</Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-8" style={{ borderTop: '1px solid var(--border-color)' }}>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              © {new Date().getFullYear()} Precedent. All rights reserved.
            </p>
            <div className="flex items-center gap-6">
              {['Privacy', 'Terms', 'Security'].map((link) => (
                <Link key={link} href="#" className="text-xs transition-colors hover:text-white" style={{ color: 'var(--text-muted)' }}>{link}</Link>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
