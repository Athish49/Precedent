'use client';

import { useState } from 'react';
import { SerifHeading, HairlineTop, PillButton } from './primitives';

const FAQS = [
  {
    q: 'How is Precedent different from a general-purpose AI assistant?',
    a: 'Everything structural, from clause segmentation and typing to diffing, scoring, and monitoring, is deterministic code, not a model. AI is invoked only where language genuinely needs understanding, and every output is anchored to a character-level citation. That means it’s faster, cheaper, and auditable.',
  },
  {
    q: 'Does my contract data train your models?',
    a: 'No. Your contracts are never used to train any model. They stay yours, encrypted at rest and in transit, and every AI action against them is logged.',
  },
  {
    q: 'What does "autonomous review" actually mean?',
    a: 'It’s event-triggered, not model-directed. On upload, code orchestrates parsing, playbook lookup, analysis, and redlining, then a deterministic gate either auto-applies low-risk changes or escalates anything that hits a hard stop, such as a prohibited clause, a missing required clause, or a high-severity risk.',
  },
  {
    q: 'How fast is a review?',
    a: 'Most contracts are parsed, analyzed, and redlined in minutes. Deterministic structural checks return instantly; the AI content pass runs in batched calls so even long agreements clear quickly.',
  },
  {
    q: 'Which contract types and practice areas are supported?',
    a: 'Playbooks route by practice area, covering SaaS MSA, NDA, DPA/GDPR, and HIPAA BAA out of the box, merged by precedence, with full self-service control for your legal team.',
  },
];

function Item({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ borderBottom: '1px solid var(--border-color)' }}>
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between gap-4 py-5 text-left">
        <span className="text-base md:text-lg" style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-sans)', fontWeight: 400 }}>{q}</span>
        <span
          className="flex-shrink-0 transition-transform duration-300"
          style={{ transform: open ? 'rotate(45deg)' : 'rotate(0deg)', color: 'var(--text-secondary)' }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
        </span>
      </button>
      <div className="overflow-hidden transition-all duration-400" style={{ maxHeight: open ? 240 : 0, opacity: open ? 1 : 0 }}>
        <p className="text-sm pb-5 pr-8" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>{a}</p>
      </div>
    </div>
  );
}

export function FAQ() {
  return (
    <section className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28">
      <HairlineTop />
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-[0.8fr_1.2fr] gap-10 lg:gap-16">
        <div>
          <SerifHeading className="text-3xl md:text-4xl lg:text-5xl mb-5">Questions</SerifHeading>
          <p className="text-sm mb-8" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>
            Everything you need to know about how Precedent reviews, redlines, and protects your contracts.
          </p>
          <PillButton href="#">Book a Demo</PillButton>
        </div>
        <div>
          {FAQS.map((f) => (
            <Item key={f.q} {...f} />
          ))}
        </div>
      </div>
    </section>
  );
}
