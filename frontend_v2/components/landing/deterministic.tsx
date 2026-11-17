'use client';

import { useState } from 'react';
import { Reveal, SectionLabel, SerifHeading, HairlineTop } from './primitives';

const BLUE = '#60a5fa';
const AMBER = '#eb6c36';

type NodeKind = 'code' | 'ai';
type Node = { id: string; label: string; kind: NodeKind; x: number; y: number };

const NODES: Node[] = [
  { id: 'seg', label: 'Segment', kind: 'code', x: 8, y: 20 },
  { id: 'type', label: 'Clause typing', kind: 'code', x: 8, y: 55 },
  { id: 'extract', label: 'Extract fields', kind: 'code', x: 8, y: 88 },
  { id: 'gate', label: 'Structural gates', kind: 'code', x: 40, y: 38 },
  { id: 'risk', label: 'Risk analysis', kind: 'ai', x: 72, y: 20 },
  { id: 'redline', label: 'Redline drafting', kind: 'ai', x: 72, y: 55 },
  { id: 'qa', label: 'Cited Q&A', kind: 'ai', x: 72, y: 88 },
  { id: 'score', label: 'Severity score', kind: 'code', x: 40, y: 72 },
];

const EDGES: [string, string][] = [
  ['seg', 'gate'], ['type', 'gate'], ['extract', 'score'],
  ['gate', 'risk'], ['gate', 'redline'], ['score', 'qa'], ['gate', 'score'],
];

function pos(id: string) {
  const n = NODES.find((x) => x.id === id)!;
  return { x: n.x, y: n.y };
}

export function Deterministic() {
  const [mode, setMode] = useState<NodeKind>('code');

  return (
    <section className="relative px-4 sm:px-6 md:px-8 py-20 md:py-28 lg:py-32">
      <HairlineTop />
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
        {/* Left: copy */}
        <div>
          <SectionLabel text="Why we're different" />
          <Reveal>
            <SerifHeading className="text-3xl md:text-4xl lg:text-5xl mb-6">
              Not another black box. AI you can actually trust.
            </SerifHeading>
          </Reveal>
          <p className="text-base mb-8" style={{ color: 'var(--text-secondary)', lineHeight: '175%' }}>
            Most contract AI hands the whole document to a model and hopes. We don&rsquo;t. Everything
            structural is pure code: fast, cheap, and auditable. The model is called only where
            language genuinely needs understanding, and every output is cited.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
            <div className="rounded-xl p-5" style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
              <p className="text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>Pure code</p>
              <p className="text-sm" style={{ color: 'var(--text-muted)', lineHeight: '160%' }}>
                Segmentation · clause typing · diffing · scoring · monitoring, all deterministic and reproducible.
              </p>
            </div>
            <div className="rounded-xl p-5" style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
              <p className="text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>AI, only where it counts</p>
              <p className="text-sm" style={{ color: 'var(--text-muted)', lineHeight: '160%' }}>
                Risk analysis · redline drafting · Q&amp;A, always grounded, always cited.
              </p>
            </div>
          </div>

          <p className="text-sm" style={{ color: 'var(--text-primary)' }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: '1.25rem' }}>The result:</span>{' '}
            <span style={{ color: 'var(--text-secondary)' }}>70% lower cost per contract · zero hallucinated citations.</span>
          </p>
        </div>

        {/* Right: interactive node map */}
        <div className="rounded-2xl p-6 sm:p-8" style={{ border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
          {/* toggle */}
          <div className="flex items-center gap-1 p-1 rounded-full w-max mb-6" style={{ border: '1px solid var(--border-color)' }}>
            {(['code', 'ai'] as NodeKind[]).map((k) => (
              <button
                key={k}
                onClick={() => setMode(k)}
                className="px-4 py-1.5 rounded-full text-xs font-medium transition-all"
                style={{
                  background: mode === k ? (k === 'code' ? BLUE : AMBER) : 'transparent',
                  color: mode === k ? '#0a0a0a' : 'var(--text-secondary)',
                }}
              >
                {k === 'code' ? 'Deterministic' : 'AI'}
              </button>
            ))}
          </div>

          <div className="relative w-full" style={{ aspectRatio: '3/2' }}>
            <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
              {EDGES.map(([a, b]) => {
                const pa = pos(a);
                const pb = pos(b);
                const kindA = NODES.find((n) => n.id === a)!.kind;
                const on = kindA === mode || NODES.find((n) => n.id === b)!.kind === mode;
                return (
                  <line
                    key={`${a}-${b}`}
                    x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
                    stroke={on ? (mode === 'code' ? BLUE : AMBER) : 'rgba(255,255,255,0.12)'}
                    strokeWidth={0.5}
                    style={{ transition: 'stroke 0.4s ease' }}
                  />
                );
              })}
            </svg>
            {NODES.map((n) => {
              const on = n.kind === mode;
              const color = n.kind === 'code' ? BLUE : AMBER;
              return (
                <div
                  key={n.id}
                  className="absolute -translate-x-1/2 -translate-y-1/2 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] whitespace-nowrap transition-all duration-400"
                  style={{
                    left: `${n.x}%`,
                    top: `${n.y}%`,
                    border: `1px solid ${on ? color : 'rgba(255,255,255,0.12)'}`,
                    background: on ? `${color}1a` : 'rgba(255,255,255,0.03)',
                    color: on ? '#fff' : 'var(--text-muted)',
                    opacity: on ? 1 : 0.5,
                    boxShadow: on ? `0 0 20px ${color}33` : 'none',
                  }}
                >
                  {n.label}
                </div>
              );
            })}
          </div>
          <p className="text-[11px] mt-4 text-center" style={{ color: 'var(--text-muted)' }}>
            Toggle to see which parts of the pipeline are code vs. model.
          </p>
        </div>
      </div>
    </section>
  );
}
