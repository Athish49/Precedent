'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import Link from 'next/link';

type MenuItem = { name: string; desc: string; href: string };
type MenuGroup = { heading: string; items: MenuItem[] };

// Products = what the platform does (one entry per capability, by lifecycle stage)
const PRODUCTS: MenuGroup[] = [
  {
    heading: 'Review & Negotiate',
    items: [
      { name: 'Contract Analysis', desc: 'Surface risks and obligations instantly', href: '/products/contract-analysis' },
      { name: 'Redlining & Negotiation', desc: 'Tracked changes with a memory', href: '/products/redlining' },
      { name: 'Autonomous Review', desc: 'AI reviews, escalates only what matters', href: '/products/autonomous-review' },
    ],
  },
  {
    heading: 'Draft & Standardize',
    items: [
      { name: 'Drafting Studio', desc: 'First drafts from your own playbook', href: '/products/drafting' },
      { name: 'Playbooks & Standards', desc: 'Your standards, enforced at scale', href: '/products/playbooks' },
    ],
  },
  {
    heading: 'Manage & Analyze',
    items: [
      { name: 'Document Intelligence', desc: 'Ask any contract anything', href: '/products/document-intelligence' },
      { name: 'Repository & Search', desc: 'Find any clause, instantly', href: '/products/repository' },
      { name: 'Obligations & Monitoring', desc: 'Never miss a renewal again', href: '/products/obligations' },
      { name: 'Analytics & Reporting', desc: 'Portfolio-wide risk at a glance', href: '/products/analytics' },
    ],
  },
];

// Solutions = who it's for. Curated to the pages we actually build; In-house
// Legal is the primary persona of the Solutions overview (no separate page),
// and the by-contract-type axis lives as a band on that overview.
const SOLUTIONS: MenuGroup[] = [
  {
    heading: 'By team',
    items: [
      { name: 'In-house Legal', desc: 'The whole platform, end to end', href: '/solutions' },
      { name: 'Legal Operations', desc: 'Run the contract lifecycle end to end', href: '/solutions/legal-ops' },
      { name: 'Procurement & Sourcing', desc: 'Review vendor paper at speed', href: '/solutions/procurement' },
      { name: 'Sales / Deal Desk', desc: 'Close deals without legal bottlenecks', href: '/solutions/sales' },
    ],
  },
];

function MegaMenu({ groups, width, onClose }: { groups: MenuGroup[]; width: number; onClose: () => void }) {
  return (
    <div
      className="absolute left-1/2 top-full mt-2 -translate-x-1/2 max-w-[calc(100vw-2rem)] rounded-2xl border border-white/10 bg-[#111111] p-6 shadow-2xl"
      style={{ width }}
      onMouseLeave={onClose}
    >
      <div className="grid gap-6" style={{ gridTemplateColumns: `repeat(${groups.length}, minmax(0, 1fr))` }}>
        {groups.map((group) => (
          <div key={group.heading}>
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-white/40">
              {group.heading}
            </p>
            <ul className="space-y-1">
              {group.items.map((item) => (
                <li key={item.name}>
                  <Link
                    href={item.href}
                    onClick={onClose}
                    className="group block rounded-lg p-2 -mx-2 transition-colors hover:bg-white/5"
                  >
                    <span className="block text-sm font-medium text-white/90 group-hover:text-white">
                      {item.name}
                    </span>
                    <span className="block text-xs text-white/40 mt-0.5 leading-snug">
                      {item.desc}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Nav() {
  const [openMenuId, setOpenMenuId] = useState<'products' | 'solutions' | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const openMenu = useCallback((id: 'products' | 'solutions') => {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    setOpenMenuId(id);
  }, []);

  const scheduleClose = useCallback(() => {
    closeTimerRef.current = setTimeout(() => setOpenMenuId(null), 120);
  }, []);

  const closeMenu = useCallback(() => {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    setOpenMenuId(null);
  }, []);

  return (
    <nav className="fixed top-4 left-4 right-4 z-50 flex items-center justify-between gap-3">
      {/* Left pill: logo + nav links */}
      <div
        className="flex items-center px-3 py-2 sm:px-4 sm:py-2.5 rounded-xl transition-all duration-300"
        style={{
          background: scrolled ? 'rgba(10,10,10,0.85)' : 'transparent',
          backdropFilter: scrolled ? 'blur(12px)' : 'none',
          boxShadow: scrolled ? '0 1px 0 rgba(255,255,255,0.06)' : 'none',
        }}
      >
        {/* Logo */}
        <Link
          href="/"
          className="flex items-center gap-2 mr-8 flex-shrink-0"
        >
          {/* Star/asterisk mark matching Lexi's snowflake icon style */}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="white" aria-hidden="true">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
          </svg>
          <span className="text-sm font-medium text-white">Precedent</span>
        </Link>

        {/* Nav links — desktop only */}
        <div className="hidden lg:flex items-center gap-1">
          <div
            className="relative"
            onMouseEnter={() => openMenu('products')}
            onMouseLeave={scheduleClose}
          >
            <button
              type="button"
              aria-expanded={openMenuId === 'products'}
              aria-haspopup="true"
              onClick={() => (openMenuId === 'products' ? closeMenu() : openMenu('products'))}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors cursor-pointer text-white/70 hover:text-white"
            >
              Products
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                style={{ transform: openMenuId === 'products' ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>

            {openMenuId === 'products' && <MegaMenu groups={PRODUCTS} width={780} onClose={closeMenu} />}
          </div>

          <div
            className="relative"
            onMouseEnter={() => openMenu('solutions')}
            onMouseLeave={scheduleClose}
          >
            <button
              type="button"
              aria-expanded={openMenuId === 'solutions'}
              aria-haspopup="true"
              onClick={() => (openMenuId === 'solutions' ? closeMenu() : openMenu('solutions'))}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors cursor-pointer text-white/70 hover:text-white"
            >
              Solutions
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                style={{ transform: openMenuId === 'solutions' ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>

            {openMenuId === 'solutions' && <MegaMenu groups={SOLUTIONS} width={340} onClose={closeMenu} />}
          </div>

          <Link
            href="/company"
            className="px-3 py-1.5 rounded-full text-sm transition-colors text-white/70 hover:text-white"
          >
            Company
          </Link>
        </div>
      </div>

      {/* Right: CTA button */}
      <div
        className="p-1.5 rounded-xl lg:p-0 bg-white/5 backdrop-blur-xl lg:bg-transparent lg:backdrop-blur-0"
      >
        <Link
          href="/home"
          className="rounded-lg text-xs sm:text-sm font-medium whitespace-nowrap cursor-pointer transition-all hover:-translate-y-0.5 active:scale-[0.98] px-4 py-2 sm:px-5 sm:py-2.5 inline-block"
          style={{ background: 'var(--button-primary-bg)', color: 'var(--button-primary-text)' }}
        >
          <span className="hidden sm:inline">Schedule a Call</span>
          <span className="sm:hidden">Book Demo</span>
        </Link>
      </div>
    </nav>
  );
}
