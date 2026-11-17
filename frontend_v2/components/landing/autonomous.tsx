'use client';

import { useEffect, useRef, useState } from 'react';
import { SectionLabel, SerifHeading } from './primitives';

// Incoming "requests" that get gathered, worked, and written up.
const CARDS = [
  { who: 'Sophia Grant', when: '3:00 PM', subj: 'Northstar MSA: new redline', body: 'Deal Desk wants the 3 PM call held. They’re pushing uncapped indemnity on AI outputs, and I do not want Sales improvising here.', x: 6, y: 10, r: -5 },
  { who: 'Priya Natarajan', when: '11:00 AM', subj: 'Atlas DPA renewal', body: 'Atlas flagged a breach notice, so the DPA renewal is no longer routine. Subprocessor list needs a proper review before Friday.', x: 58, y: 6, r: 4 },
  { who: 'Iris Coleman', when: 'Yesterday', subj: 'Vendor webhook incident', body: 'A vendor webhook exposed customer IDs in logs. Do we need to treat this as notifiable under any customer contracts?', x: 20, y: 52, r: -3 },
  { who: 'Finance Operations', when: 'Yesterday', subj: 'Aperture order form', body: 'Order form came back asking for net-90 and audit rights. Can someone review the audit clause before we send a counter?', x: 60, y: 54, r: 6 },
  { who: 'Marcus Lee', when: '2:00 PM', subj: 'Board deck wording', body: 'Need a read on the Henderson litigation reserves language before this goes out.', x: 38, y: 30, r: -2 },
  { who: 'Nina Park', when: '2:00 AM', subj: 'Consent basis: beta', body: 'What consent basis covers the Canadian beta transcript summaries?', x: 4, y: 78, r: 3 },
];

const MATTERS = [
  'Northstar expansion: authorize the final MSA fallback',
  'UK subsidiary: create board written consent',
  'Atlas DPA renewal: breach notice and subprocessors',
  'Aperture order form: net-90 and audit rights',
  'Vendor webhook incident: notifiability review',
  'Consent basis: Canadian beta transcripts',
];

function lerpClamp(p: number, a: number, b: number) {
  return Math.max(0, Math.min(1, (p - a) / (b - a)));
}

export function Autonomous() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const [p, setP] = useState(0);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    setReduced(window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }, []);

  useEffect(() => {
    if (reduced) return;
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = sectionRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const total = el.offsetHeight - window.innerHeight;
        const scrolled = Math.min(Math.max(-rect.top, 0), total);
        setP(total > 0 ? scrolled / total : 0);
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener('scroll', onScroll);
      cancelAnimationFrame(raf);
    };
  }, [reduced]);

  // Stage opacities
  const f1 = reduced ? 0 : 1 - lerpClamp(p, 0.24, 0.36);
  const f2 = reduced ? 0 : lerpClamp(p, 0.30, 0.40) * (1 - lerpClamp(p, 0.60, 0.70));
  const f3 = reduced ? 1 : lerpClamp(p, 0.64, 0.74);
  const stage = p < 0.34 ? 0 : p < 0.66 ? 1 : 2;
  const STAGE_LABELS = [
    { n: '01', t: 'It gathers context', d: 'Every request, thread, and prior decision, pulled into one place.' },
    { n: '02', t: 'It does the work', d: 'Parsed, analyzed, and redlined against your playbook and history.' },
    { n: '03', t: 'You approve', d: 'The finished work arrives written up, cited, with the source attached.' },
  ];

  return (
    <section ref={sectionRef} className="relative" style={{ height: reduced ? 'auto' : '320vh' }}>
      <div className={`${reduced ? '' : 'sticky top-0 h-screen'} overflow-hidden flex flex-col`}>
        {/* header */}
        <div className="px-4 sm:px-6 md:px-8 pt-14 md:pt-16 flex-shrink-0">
          <div className="max-w-6xl mx-auto text-center">
            <div className="flex justify-center">
              <SectionLabel text="Autonomous review" />
            </div>
            <SerifHeading className="text-2xl md:text-3xl lg:text-4xl max-w-3xl mx-auto">
              Upload a contract. Walk away. Come back to a redlined draft.
            </SerifHeading>
          </div>
        </div>

        {/* stage viewport */}
        <div className="relative flex-1 min-h-0 overflow-hidden max-w-5xl w-full mx-auto px-4">
          {/* Frame 1 — scattered cards */}
          <div className="absolute inset-0" style={{ opacity: f1, pointerEvents: 'none', transition: reduced ? undefined : 'opacity 0.2s linear' }}>
            {CARDS.map((c) => (
              <div
                key={c.subj}
                className="absolute w-56 rounded-xl p-3.5 text-left"
                style={{
                  left: `${c.x}%`, top: `${8 + c.y * 0.7}%`,
                  transform: `rotate(${c.r}deg) translateY(${(1 - f1) * 20}px)`,
                  border: '1px solid var(--border-color)',
                  background: 'rgba(20,20,20,0.9)',
                  backdropFilter: 'blur(4px)',
                  boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
                }}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{c.who}</span>
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{c.when}</span>
                </div>
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>{c.subj}</p>
                <p className="text-[10px] leading-snug" style={{ color: 'var(--text-muted)' }}>{c.body}</p>
              </div>
            ))}
          </div>

          {/* Frame 2 — organized matters list */}
          <div className="absolute inset-0 flex items-center justify-center" style={{ opacity: f2, pointerEvents: 'none', transition: reduced ? undefined : 'opacity 0.2s linear' }}>
            <div className="w-full max-w-md rounded-xl overflow-hidden" style={{ border: '1px solid var(--border-color)', background: 'rgba(20,20,20,0.95)' }}>
              <div className="px-4 py-2.5 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border-color)' }}>
                <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Matters</span>
                <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{MATTERS.length} active</span>
              </div>
              {MATTERS.map((m, i) => (
                <div key={m} className="px-4 py-3 flex items-center justify-between gap-3" style={{ borderBottom: i < MATTERS.length - 1 ? '1px solid var(--border-color)' : 'none' }}>
                  <span className="text-xs truncate" style={{ color: 'var(--text-secondary)' }}>{m}</span>
                  <span className="text-[10px] flex-shrink-0" style={{ color: 'var(--text-muted)' }}>done</span>
                </div>
              ))}
            </div>
          </div>

          {/* Frame 3 — the writeup */}
          <div className="absolute inset-0 flex items-center justify-center" style={{ opacity: f3, pointerEvents: 'none', transition: reduced ? undefined : 'opacity 0.2s linear' }}>
            <div className="w-full max-w-2xl rounded-xl p-5 sm:p-6 text-left" style={{ border: '1px solid var(--border-color)', background: 'rgba(20,20,20,0.97)', maxHeight: '100%', overflow: 'hidden' }}>
              <div className="flex items-center gap-2 mb-2.5">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Worked for 6m 18s · gate decision: escalated</span>
              </div>
              <h4 className="text-base sm:text-lg mb-2.5" style={{ fontFamily: 'var(--font-serif)', color: 'var(--text-primary)' }}>
                Northstar expansion: authorize the final MSA fallback
              </h4>
              <p className="text-[13px] sm:text-sm mb-3.5" style={{ color: 'var(--text-secondary)', lineHeight: '165%' }}>
                Northstar is asking for a $10M liability cap, uncapped AI-output indemnity, and a blanket
                data-use restriction. The defensible package keeps the fees-paid cap and offers a $2.4M
                aggregate super-cap for defined high-risk claims.
              </p>
              <div className="space-y-1.5">
                {['Liability structure: hold at fees paid + $2.4M super-cap', 'AI-output indemnity: limit to third-party IP claims', 'Data use: permit de-identified evaluation only'].map((pt) => (
                  <p key={pt} className="text-xs" style={{ color: 'var(--text-muted)' }}>{pt}</p>
                ))}
              </div>
              <div className="mt-4 pt-3.5 flex items-center gap-3" style={{ borderTop: '1px solid var(--border-color)' }}>
                <button className="px-3 py-1.5 rounded-full text-[11px] font-medium" style={{ background: 'var(--button-primary-bg)', color: 'var(--button-primary-text)' }}>Approve &amp; apply</button>
                <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Source thread attached · 5 citations</span>
              </div>
            </div>
          </div>
        </div>

        {/* stage caption */}
        <div className="px-4 pb-12 md:pb-14 flex-shrink-0">
          <div className="max-w-6xl mx-auto text-center">
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>{STAGE_LABELS[stage].n}</div>
            <div className="text-lg mb-1" style={{ fontFamily: 'var(--font-sans)', fontWeight: 500, color: 'var(--text-primary)' }}>{STAGE_LABELS[stage].t}</div>
            <p className="text-sm max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>{STAGE_LABELS[stage].d}</p>
            {!reduced && (
              <div className="mt-5 mx-auto h-px max-w-xs" style={{ background: 'var(--border-color)' }}>
                <div className="h-px" style={{ width: `${p * 100}%`, background: 'rgba(255,255,255,0.7)', transition: 'width 0.1s linear' }} />
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
