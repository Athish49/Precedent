'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDownIcon, ChevronUpIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProvenanceTag } from '@/components/primitives/provenance-tag';
import { useQA, useSummarize, useSummarizeRedlines, useEasyPrompt, useResearch } from '@/lib/api/hooks';
import { useWorkspace } from '@/components/workspace/workspace-context';
import type { Citation } from '@/lib/api/types';

// ─── Shared section shell ─────────────────────────────────────────────────────

interface SectionProps {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function Section({ title, open, onToggle, children }: SectionProps) {
  return (
    <div className="border-b border-border">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        {title}
        {open ? <ChevronUpIcon className="size-3.5" /> : <ChevronDownIcon className="size-3.5" />}
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

// ─── Q&A thread ──────────────────────────────────────────────────────────────

interface ThreadEntry {
  question: string;
  answer: string;
  citations: Citation[];
}

function QASection({ contractId }: { contractId: string }) {
  const { setSelected } = useWorkspace();
  const qa = useQA();
  const [input, setInput] = useState('');
  const [thread, setThread] = useState<ThreadEntry[]>([]);

  function handleAsk() {
    const q = input.trim();
    if (!q) return;
    const isRepeat = thread.some((e) => e.question === q);
    qa.mutate(
      { contractId, body: { question: q } },
      {
        onSuccess: (data) => {
          setThread((prev) => [{ question: q, answer: data.answer, citations: data.citations }, ...prev]);
          setInput('');
        },
      }
    );
    if (isRepeat) {
      // from cache hint will show via isPending being very brief
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-1.5">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleAsk(); }}
          placeholder="Ask a question about this contract."
          disabled={qa.isPending}
          className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/50 disabled:opacity-50"
        />
        <Button size="sm" onClick={handleAsk} disabled={qa.isPending || !input.trim()}>
          {qa.isPending ? (
            <span className="flex items-center gap-1">
              <span className="size-3 animate-spin rounded-full border border-current border-t-transparent" />
              Asking
            </span>
          ) : (
            'Ask'
          )}
        </Button>
      </div>

      {thread.length === 0 && (
        <p className="text-xs text-muted-foreground">Ask a question about this contract.</p>
      )}

      {thread.map((entry, i) => (
        <div key={i} className="space-y-1 rounded bg-muted/30 p-2">
          <p className="text-xs font-semibold">{entry.question}</p>
          <div className="flex items-start gap-1">
            <p className="flex-1 text-xs text-foreground/80">{entry.answer}</p>
            <ProvenanceTag source="llm" />
          </div>
          {entry.citations.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {entry.citations.map((cit, ci) => (
                <button
                  key={ci}
                  type="button"
                  onClick={() =>
                    setSelected({
                      id: `citation-${cit.char_start}`,
                      charStart: cit.char_start,
                      charEnd: cit.char_end,
                      tabHint: 'intelligence',
                    })
                  }
                  className="text-[10px] font-medium text-primary underline-offset-2 hover:underline"
                >
                  [{ci + 1}]
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Summaries ────────────────────────────────────────────────────────────────

function SummariesSection({ contractId }: { contractId: string }) {
  const summarize = useSummarize();
  const summarizeRedlines = useSummarizeRedlines();
  const [contractSummary, setContractSummary] = useState<string | null>(null);
  const [redlineSummary, setRedlineSummary] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="outline"
          className="flex-1 text-xs"
          disabled={summarize.isPending}
          onClick={() =>
            summarize.mutate(contractId, { onSuccess: (d) => setContractSummary(d.summary) })
          }
        >
          {summarize.isPending ? (
            <span className="flex items-center gap-1">
              <span className="size-3 animate-spin rounded-full border border-current border-t-transparent" />
              Loading
            </span>
          ) : (
            'Contract Summary'
          )}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="flex-1 text-xs"
          disabled={summarizeRedlines.isPending}
          onClick={() =>
            summarizeRedlines.mutate(contractId, {
              onSuccess: (d) => setRedlineSummary(d.summary),
            })
          }
        >
          {summarizeRedlines.isPending ? (
            <span className="flex items-center gap-1">
              <span className="size-3 animate-spin rounded-full border border-current border-t-transparent" />
              Loading
            </span>
          ) : (
            'Redline Thread'
          )}
        </Button>
      </div>

      {contractSummary && (
        <div className="rounded bg-muted/30 p-2">
          <div className="mb-1 flex items-center gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Contract</span>
            <ProvenanceTag source="llm" />
          </div>
          <p className="text-xs text-foreground/80">{contractSummary}</p>
        </div>
      )}

      {redlineSummary && (
        <div className="rounded bg-muted/30 p-2">
          <div className="mb-1 flex items-center gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Redlines</span>
            <ProvenanceTag source="llm" />
          </div>
          <p className="text-xs text-foreground/80">{redlineSummary}</p>
        </div>
      )}
    </div>
  );
}

// ─── Easy Prompt ──────────────────────────────────────────────────────────────

function EasyPromptSection({ contractId }: { contractId: string }) {
  const router = useRouter();
  const { setActiveTab } = useWorkspace();
  const easyPrompt = useEasyPrompt();
  const [instruction, setInstruction] = useState('');

  function handleSubmit() {
    const val = instruction.trim();
    if (!val) return;
    easyPrompt.mutate({ contractId, body: { instruction: val } });
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">
        <input
          type="text"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
          placeholder="Describe what you want to do…"
          disabled={easyPrompt.isPending}
          className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/50 disabled:opacity-50"
        />
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={easyPrompt.isPending || !instruction.trim()}
        >
          {easyPrompt.isPending ? (
            <span className="size-3 animate-spin rounded-full border border-current border-t-transparent" />
          ) : (
            'Go'
          )}
        </Button>
      </div>

      {easyPrompt.data && (
        <div className="space-y-2">
          <pre className="whitespace-pre-wrap rounded bg-muted p-2 text-xs">
            {easyPrompt.data.structured_prompt}
          </pre>
          {easyPrompt.data.route === 's3' ? (
            <Button size="sm" variant="outline" className="w-full text-xs" onClick={() => setActiveTab('redlines')}>
              Go to Redlines →
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="w-full text-xs"
              onClick={() =>
                router.push(`/drafting?prompt=${encodeURIComponent(easyPrompt.data!.structured_prompt)}`)
              }
            >
              Go to Drafting →
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Research ─────────────────────────────────────────────────────────────────

function ResearchSection({ contractId }: { contractId: string }) {
  const research = useResearch();
  const [query, setQuery] = useState('');

  function handleResearch() {
    const q = query.trim();
    if (!q) return;
    research.mutate({ contractId, body: { query: q } });
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleResearch(); }}
          placeholder="Enter a research query."
          disabled={research.isPending}
          className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/50 disabled:opacity-50"
        />
        <Button
          size="sm"
          onClick={handleResearch}
          disabled={research.isPending || !query.trim()}
        >
          {research.isPending ? (
            <span className="size-3 animate-spin rounded-full border border-current border-t-transparent" />
          ) : (
            'Research'
          )}
        </Button>
      </div>

      {!research.data && !research.isPending && (
        <p className="text-xs text-muted-foreground">Enter a research query.</p>
      )}

      {research.data && (
        <div className="space-y-2">
          <div className="flex items-start gap-1">
            <p className="flex-1 text-xs text-foreground/80">{research.data.answer}</p>
            <ProvenanceTag source="llm" />
          </div>
          {research.data.sources.length > 0 && (
            <ul className="space-y-1">
              {research.data.sources.map((src, i) => (
                <li key={i}>
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-primary underline underline-offset-2"
                  >
                    {src.title}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ─── IntelligenceTab (public) ─────────────────────────────────────────────────

type SectionId = 'qa' | 'summaries' | 'easyprompt' | 'research';

export function IntelligenceTab({ contractId }: { contractId: string }) {
  const [openSection, setOpenSection] = useState<SectionId>('qa');

  function toggle(id: SectionId) {
    setOpenSection((prev) => (prev === id ? ('' as SectionId) : id));
  }

  return (
    <div className="flex flex-col divide-y divide-border">
      <Section title="Q&A" open={openSection === 'qa'} onToggle={() => toggle('qa')}>
        <QASection contractId={contractId} />
      </Section>

      <Section title="Summaries" open={openSection === 'summaries'} onToggle={() => toggle('summaries')}>
        <SummariesSection contractId={contractId} />
      </Section>

      <Section title="Easy Prompt" open={openSection === 'easyprompt'} onToggle={() => toggle('easyprompt')}>
        <EasyPromptSection contractId={contractId} />
      </Section>

      <Section title="Research" open={openSection === 'research'} onToggle={() => toggle('research')}>
        <ResearchSection contractId={contractId} />
      </Section>
    </div>
  );
}
