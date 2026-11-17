'use client';

import React, { useRef, useState, useCallback } from 'react';
import Link from 'next/link';
import { ChevronDownIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

// ─── Data ────────────────────────────────────────────────────────────────────

interface Solution {
  slug: string;
  name: string;
  descriptor: string;
}

interface ProductGroup {
  heading: string;
  solutions: Solution[];
}

const PRODUCT_GROUPS: ProductGroup[] = [
  {
    heading: 'Review & Negotiate',
    solutions: [
      {
        slug: 'clm',
        name: 'Contract Lifecycle Management',
        descriptor: 'Track every contract from creation to renewal',
      },
      {
        slug: 'analysis',
        name: 'Contract Analysis',
        descriptor: 'Surface risks and obligations instantly',
      },
      {
        slug: 'redlining',
        name: 'Redlining & Negotiation',
        descriptor: 'Collaborate on edits with structured markup',
      },
    ],
  },
  {
    heading: 'Draft',
    solutions: [
      {
        slug: 'drafting',
        name: 'Drafting Studio',
        descriptor: 'Generate first drafts from templates and playbooks',
      },
    ],
  },
  {
    heading: 'Manage & Monitor',
    solutions: [
      {
        slug: 'autonomous-review',
        name: 'Autonomous Review',
        descriptor: 'AI-powered review that flags issues automatically',
      },
      {
        slug: 'playbooks',
        name: 'Playbooks & Standards',
        descriptor: 'Enforce negotiation positions at scale',
      },
    ],
  },
  {
    heading: 'Analyze',
    solutions: [
      {
        slug: 'document-intelligence',
        name: 'Document Intelligence',
        descriptor: 'Extract structured data from any contract',
      },
      {
        slug: 'analytics',
        name: 'Analytics & Reporting',
        descriptor: 'Portfolio-wide insights and trend dashboards',
      },
    ],
  },
];

// ─── Mega-menu ────────────────────────────────────────────────────────────────

function ProductsMegaMenu({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="absolute left-1/2 top-full mt-2 -translate-x-1/2 w-[880px] max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-popover p-6 shadow-lg ring-1 ring-foreground/10"
      onMouseLeave={onClose}
    >
      <div className="grid grid-cols-4 gap-6">
        {PRODUCT_GROUPS.map((group) => (
          <div key={group.heading}>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.heading}
            </p>
            <ul className="space-y-3">
              {group.solutions.map((solution) => (
                <li key={solution.slug}>
                  <Link
                    href={`/products/${solution.slug}`}
                    onClick={onClose}
                    className="group block rounded-md p-2 -mx-2 transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                  >
                    <span className="block text-sm font-medium text-foreground group-hover:text-primary">
                      {solution.name}
                    </span>
                    <span className="block text-xs text-muted-foreground mt-0.5 leading-snug">
                      {solution.descriptor}
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

// ─── Nav ─────────────────────────────────────────────────────────────────────

export function MarketingNav() {
  const [megaMenuOpen, setMegaMenuOpen] = useState(false);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const openMenu = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setMegaMenuOpen(true);
  }, []);

  const scheduleClose = useCallback(() => {
    closeTimerRef.current = setTimeout(() => {
      setMegaMenuOpen(false);
    }, 100);
  }, []);

  const closeMenu = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setMegaMenuOpen(false);
  }, []);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6 lg:px-8">
        {/* Brand mark */}
        <Link
          href="/"
          className="flex-shrink-0 text-base font-semibold tracking-tight text-foreground hover:text-primary transition-colors"
        >
          Precedent
        </Link>

        {/* Nav links */}
        <nav className="flex flex-1 items-center gap-1">
          {/* Products — with mega-menu */}
          <div
            className="relative"
            onMouseEnter={openMenu}
            onMouseLeave={scheduleClose}
          >
            <button
              type="button"
              aria-haspopup="true"
              aria-expanded={megaMenuOpen}
              onClick={() => (megaMenuOpen ? closeMenu() : openMenu())}
              onFocus={openMenu}
              onBlur={scheduleClose}
              className={cn(
                'inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                'text-muted-foreground hover:text-foreground hover:bg-muted',
                megaMenuOpen && 'text-foreground bg-muted',
              )}
            >
              Products
              <ChevronDownIcon
                className={cn(
                  'size-3.5 transition-transform duration-200',
                  megaMenuOpen && 'rotate-180',
                )}
              />
            </button>

            {megaMenuOpen && (
              <ProductsMegaMenu onClose={closeMenu} />
            )}
          </div>

          <Link
            href="/platform"
            className="inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground hover:bg-muted"
          >
            Platform
          </Link>

          <Link
            href="/company"
            className="inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground hover:bg-muted"
          >
            Company
          </Link>
        </nav>

        {/* Launch App CTA */}
        <div className="flex-shrink-0">
          <Link
            href="/home"
            className="inline-flex h-7 items-center justify-center gap-1 rounded-lg bg-primary px-2.5 text-[0.8rem] font-medium text-primary-foreground transition-colors hover:bg-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Launch App
          </Link>
        </div>
      </div>
    </header>
  );
}
