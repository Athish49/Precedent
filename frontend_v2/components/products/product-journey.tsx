'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { SerifHeading } from '@/components/landing/primitives';

type Product = {
  stage: string;
  name: string;
  desc: string;
  href: string;
  gradient: string; // placeholder art — swap for a real mockup image later
};

// The 9 products, in lifecycle order (Create → Negotiate → Manage → Renew).
const PRODUCTS: Product[] = [
  {
    stage: 'Create',
    name: 'Drafting Studio',
    desc: 'Generate a polished first draft in seconds — built from your own templates and playbook, never a blank page.',
    href: '/products/drafting',
    gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6, #d946ef)',
  },
  {
    stage: 'Create',
    name: 'Playbooks & Standards',
    desc: 'Encode your negotiation positions once, and have them enforced automatically on every deal that comes in.',
    href: '/products/playbooks',
    gradient: 'linear-gradient(135deg, #0ea5e9, #6366f1)',
  },
  {
    stage: 'Negotiate',
    name: 'Contract Analysis',
    desc: 'Drop in any contract and see every risk, obligation, and red flag surfaced and scored in seconds.',
    href: '/products/contract-analysis',
    gradient: 'linear-gradient(135deg, #f59e0b, #ef4444)',
  },
  {
    stage: 'Negotiate',
    name: 'Redlining & Negotiation',
    desc: 'Get clean, tracked-change redlines with plain-language rationale — shaped by how your team has negotiated before.',
    href: '/products/redlining',
    gradient: 'linear-gradient(135deg, #10b981, #0ea5e9)',
  },
  {
    stage: 'Negotiate',
    name: 'Autonomous Review',
    desc: 'Let AI handle routine review end to end, and escalate only the handful of issues that truly need a human.',
    href: '/products/autonomous-review',
    gradient: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
  },
  {
    stage: 'Manage',
    name: 'Repository & Search',
    desc: 'Every signed contract in one place, searchable all the way down to the individual clause.',
    href: '/products/repository',
    gradient: 'linear-gradient(135deg, #14b8a6, #22c55e)',
  },
  {
    stage: 'Manage',
    name: 'Document Intelligence',
    desc: 'Ask any contract a question in plain English and get an answer, cited to the exact line it came from.',
    href: '/products/document-intelligence',
    gradient: 'linear-gradient(135deg, #3b82f6, #06b6d4)',
  },
  {
    stage: 'Manage',
    name: 'Obligations & Monitoring',
    desc: 'Never miss a deadline or renewal again — obligations are extracted, tracked, and surfaced to you automatically.',
    href: '/products/obligations',
    gradient: 'linear-gradient(135deg, #f43f5e, #f59e0b)',
  },
  {
    stage: 'Renew',
    name: 'Analytics & Reporting',
    desc: 'See portfolio-wide risk, value, and upcoming renewals at a glance — and act before anything hits.',
    href: '/products/analytics',
    gradient: 'linear-gradient(135deg, #a855f7, #6366f1)',
  },
];

// Active when the element overlaps the center band of the viewport, so exactly
// the section you've scrolled to lights up while the rest stay dimmed.
function useActiveOnCenter<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setActive(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => setActive(entry.isIntersecting),
      { rootMargin: '-45% 0px -45% 0px', threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, active };
}

function ProductRow({ product, index }: { product: Product; index: number }) {
  const { ref, active } = useActiveOnCenter<HTMLElement>();
  const imageFirst = index % 2 === 0;

  return (
    <section
      ref={ref}
      className="relative grid grid-cols-1 lg:grid-cols-2 lg:min-h-[85vh]"
    >
      {/* Media — full-bleed to the screen edge */}
      <div className={imageFirst ? 'lg:order-1' : 'lg:order-2'}>
        <div
          className="relative w-full h-72 sm:h-96 lg:h-full overflow-hidden"
          style={{
            filter: active ? 'grayscale(0) brightness(1)' : 'grayscale(1) brightness(0.4)',
            opacity: active ? 1 : 0.5,
            transition: 'filter 0.7s cubic-bezier(0.16,1,0.3,1), opacity 0.7s cubic-bezier(0.16,1,0.3,1)',
          }}
        >
          <div className="absolute inset-0" style={{ background: product.gradient }} />
          <span
            className="absolute inset-0 flex items-center justify-center text-xs tracking-widest uppercase"
            style={{ color: 'rgba(255,255,255,0.75)', fontFamily: 'var(--font-sans)' }}
          >
            {product.name} — mockup
          </span>
        </div>
      </div>

      {/* Copy */}
      <div
        className={`flex items-center px-6 sm:px-10 lg:px-16 py-12 lg:py-0 ${imageFirst ? 'lg:order-2' : 'lg:order-1'}`}
        style={{ transition: 'opacity 0.7s', opacity: active ? 1 : 0.55 }}
      >
        <div className="max-w-md">
          <span
            className="text-xs font-medium tracking-widest uppercase"
            style={{
              color: active ? 'var(--text-secondary)' : 'var(--text-muted)',
              transition: 'color 0.7s',
            }}
          >
            {product.stage}
          </span>
          <SerifHeading className="text-3xl md:text-4xl lg:text-5xl mt-3 mb-5">
            <span
              style={{
                color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                transition: 'color 0.7s',
              }}
            >
              {product.name}
            </span>
          </SerifHeading>
          <p
            className="text-base md:text-lg mb-8"
            style={{
              color: active ? 'var(--text-secondary)' : 'rgba(255,255,255,0.25)',
              transition: 'color 0.7s',
              lineHeight: '175%',
            }}
          >
            {product.desc}
          </p>
          <Link
            href={product.href}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all hover:gap-3 hover:-translate-y-0.5"
            style={{
              border: '1px solid rgba(255,255,255,0.25)',
              color: active ? 'var(--text-primary)' : 'var(--text-muted)',
              background: 'transparent',
            }}
          >
            Learn more
            <span aria-hidden>→</span>
          </Link>
        </div>
      </div>
    </section>
  );
}

export function ProductJourney() {
  return (
    <div>
      {PRODUCTS.map((product, i) => (
        <ProductRow key={product.name} product={product} index={i} />
      ))}
    </div>
  );
}
