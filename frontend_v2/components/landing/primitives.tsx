'use client';

import Link from 'next/link';
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

// ─── useInView ─────────────────────────────────────────────────────────────────
// Returns a ref + whether the element has entered the viewport (fires once).
export function useInView<T extends HTMLElement = HTMLDivElement>(
  options: IntersectionObserverInit = { threshold: 0.15 },
  once = true,
) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (once) observer.unobserve(entry.target);
        } else if (!once) {
          setInView(false);
        }
      });
    }, options);
    observer.observe(el);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [once]);

  return { ref, inView };
}

// ─── Reveal ────────────────────────────────────────────────────────────────────
// Wraps children in a scroll-reveal fade-up. `delay` staggers grouped items.
export function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={`reveal ${inView ? 'is-in' : ''} ${className}`}
      style={{ ['--reveal-delay' as string]: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

// ─── useCountUp ────────────────────────────────────────────────────────────────
// Animates a number from 0 → target once `active` becomes true.
export function useCountUp(target: number, active: boolean, durationMs = 1400) {
  const [value, setValue] = useState(0);
  const startedRef = useRef(false);

  useEffect(() => {
    if (!active || startedRef.current) return;
    startedRef.current = true;

    if (
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      setValue(target);
      return;
    }

    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / durationMs, 1);
      // easeOutExpo
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      setValue(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, target, durationMs]);

  return value;
}

// ─── SectionLabel ──────────────────────────────────────────────────────────────
export function SectionLabel({ text }: { text: string }) {
  return (
    <div className="mb-4">
      <span
        className="text-xs font-medium tracking-widest uppercase"
        style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-sans)' }}
      >
        {text}
      </span>
    </div>
  );
}

// ─── PillButton ────────────────────────────────────────────────────────────────
export function PillButton({
  href,
  children,
  outline = false,
}: {
  href: string;
  children: ReactNode;
  outline?: boolean;
}) {
  return (
    <Link
      href={href}
      className="px-5 py-2.5 sm:px-6 sm:py-3 rounded-lg text-xs sm:text-sm font-medium cursor-pointer transition-all hover:-translate-y-0.5 active:scale-[0.98] inline-block"
      style={
        outline
          ? { border: '1px solid rgba(255,255,255,0.25)', color: 'var(--text-primary)', background: 'transparent' }
          : { background: 'var(--button-primary-bg)', color: 'var(--button-primary-text)' }
      }
    >
      {children}
    </Link>
  );
}

// ─── SerifHeading ──────────────────────────────────────────────────────────────
// Consistent serif display heading used across sections.
export function SerifHeading({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2
      className={className}
      style={{
        fontFamily: 'var(--font-serif)',
        fontWeight: 400,
        lineHeight: '115%',
        letterSpacing: '-0.02em',
        color: 'var(--text-primary)',
      }}
    >
      {children}
    </h2>
  );
}

// ─── HairlineTop ───────────────────────────────────────────────────────────────
// The subtle fading top border used between sections.
export function HairlineTop() {
  return (
    <div
      className="absolute top-0 left-8 right-8"
      style={{
        height: '1px',
        background: 'linear-gradient(to right, transparent, var(--border-color), transparent)',
      }}
    />
  );
}
