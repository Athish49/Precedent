'use client';

import { useEffect, useState } from 'react';
import { SectionLabel, SerifHeading, HairlineTop, useInView } from './primitives';

const QUOTES = [
  {
    quote: 'We cut contract review from two weeks to an afternoon. My team spends its time on judgment calls now, not clause hunting.',
    name: 'Dana Whitfield', title: 'General Counsel', company: 'Series-C SaaS', metric: '−85% review time',
  },
  {
    quote: 'The character-level citations sold our security team instantly. Every AI suggestion points to the exact clause, with nothing to take on faith.',
    name: 'Marcus Reyes', title: 'Head of Legal Ops', company: 'Fintech scale-up', metric: '0 hallucinated cites',
  },
  {
    quote: 'Autonomous review clears our routine NDAs before I get to my desk. It only escalates the ones that actually need me.',
    name: 'Priya Anand', title: 'Deputy GC', company: 'Healthcare platform', metric: '68% auto-cleared',
  },
];

export function Testimonials() {
  const [i, setI] = useState(0);
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.3 }, false);

  useEffect(() => {
    if (!inView) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = setInterval(() => setI((x) => (x + 1) % QUOTES.length), 6000);
    return () => clearInterval(id);
  }, [inView]);

  const q = QUOTES[i];

  return (
    <section ref={ref} className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28">
      <HairlineTop />
      <div className="max-w-4xl mx-auto text-center">
        <div className="flex justify-center">
          <SectionLabel text="What legal teams say" />
        </div>
        <div key={i} className="reveal is-in">
          <SerifHeading className="text-2xl md:text-3xl lg:text-4xl mb-8" >
            &ldquo;{q.quote}&rdquo;
          </SerifHeading>
          <div className="flex flex-col items-center gap-1">
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{q.name}</span>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{q.title} · {q.company}</span>
            <span className="mt-3 text-xs px-3 py-1 rounded-full" style={{ border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>{q.metric}</span>
          </div>
        </div>

        <div className="flex justify-center gap-2 mt-10">
          {QUOTES.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setI(idx)}
              aria-label={`Testimonial ${idx + 1}`}
              className="h-px transition-all"
              style={{ width: idx === i ? 28 : 14, background: idx === i ? 'rgba(255,255,255,0.8)' : 'rgba(255,255,255,0.2)' }}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
