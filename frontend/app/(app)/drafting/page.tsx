'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ProvenanceTag } from '@/components/primitives/provenance-tag';
import { HoverCard } from '@/components/primitives/hover-card';
import {
  useDraftClause,
  useDraftDocument,
  useDraftPrecedent,
  useDraftMemo,
  usePrecedentSearch,
} from '@/lib/api/hooks';
import type { DraftSource, PrecedentClause } from '@/lib/api/types';
import { cn } from '@/lib/utils';

type Mode = 'clause' | 'document' | 'precedent' | 'memo';

const MODES: { id: Mode; label: string }[] = [
  { id: 'clause', label: 'Single Clause' },
  { id: 'document', label: 'Full Document' },
  { id: 'precedent', label: 'Precedent-matched' },
  { id: 'memo', label: 'Memo' },
];

// ─── Copy button ──────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }
  return (
    <Button variant="outline" size="sm" onClick={handleCopy}>
      {copied ? 'Copied!' : 'Copy'}
    </Button>
  );
}

// ─── Result panel wrapper ─────────────────────────────────────────────────────

function ResultPanel({
  isPending,
  children,
}: {
  isPending: boolean;
  children: React.ReactNode;
}) {
  if (isPending) {
    return (
      <div className="flex h-full items-center justify-center gap-3">
        <div className="size-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <span className="text-sm text-muted-foreground">Drafting…</span>
      </div>
    );
  }
  return <>{children}</>;
}

function EmptyResult() {
  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-sm text-muted-foreground">Your drafted content will appear here.</p>
    </div>
  );
}

// ─── Mode 1: Single Clause ────────────────────────────────────────────────────

function ClauseComposer({ onPrompt }: { onPrompt?: string }) {
  const [clauseType, setClauseType] = useState('');
  const [context, setContext] = useState(onPrompt ?? '');
  const [draftMode, setDraftMode] = useState('');
  const [rewriteInstruction, setRewriteInstruction] = useState('');
  const draftClause = useDraftClause();

  useEffect(() => {
    if (onPrompt) setContext(onPrompt);
  }, [onPrompt]);

  function handleSubmit() {
    if (!clauseType || !context) return;
    draftClause.mutate({ clause_type: clauseType, context, mode: draftMode || undefined });
  }

  function handleRewrite() {
    if (!clauseType || !rewriteInstruction) return;
    draftClause.mutate({ clause_type: clauseType, context: rewriteInstruction, mode: 'llm' });
  }

  const result = draftClause.data;

  return (
    <div className="flex h-full">
      {/* Composer */}
      <div className="flex w-96 shrink-0 flex-col gap-4 border-r border-border p-4">
        {onPrompt && (
          <div className="rounded border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            From workspace — prompt pre-loaded
          </div>
        )}
        <div className="space-y-1">
          <label className="text-xs font-medium">Clause type</label>
          <input
            value={clauseType}
            onChange={(e) => setClauseType(e.target.value)}
            placeholder="e.g. payment_terms"
            className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium">Context</label>
          <textarea
            rows={3}
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Describe what this clause should cover…"
            className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium">Mode (optional)</label>
          <select
            value={draftMode}
            onChange={(e) => setDraftMode(e.target.value)}
            className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          >
            <option value="">Default</option>
            <option value="playbook">Playbook</option>
            <option value="frequency">Frequency</option>
            <option value="llm">LLM (NL rewrite)</option>
          </select>
        </div>
        <Button disabled={!clauseType || !context || draftClause.isPending} onClick={handleSubmit}>
          {draftClause.isPending ? 'Drafting…' : 'Draft Clause'}
        </Button>
      </div>

      {/* Result */}
      <div className="flex-1 p-6">
        <ResultPanel isPending={draftClause.isPending}>
          {result ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Result</span>
                <ProvenanceTag source={result.source as DraftSource} />
                <CopyButton text={result.text} />
              </div>
              <pre className="whitespace-pre-wrap rounded bg-muted p-4 text-sm">{result.text}</pre>
              <div className="space-y-2 border-t border-border pt-4">
                <label className="text-xs font-medium">Rewrite instruction</label>
                <div className="flex gap-2">
                  <input
                    value={rewriteInstruction}
                    onChange={(e) => setRewriteInstruction(e.target.value)}
                    placeholder="Rewrite this clause to…"
                    className="flex-1 rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!rewriteInstruction || draftClause.isPending}
                    onClick={handleRewrite}
                  >
                    Rewrite
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <EmptyResult />
          )}
        </ResultPanel>
      </div>
    </div>
  );
}

// ─── Mode 2: Full Document ────────────────────────────────────────────────────

type VarRow = { key: string; value: string };

function DocumentComposer() {
  const [template, setTemplate] = useState('');
  const [varRows, setVarRows] = useState<VarRow[]>([
    { key: '', value: '' },
    { key: '', value: '' },
  ]);
  const [polish, setPolish] = useState(false);
  const draftDoc = useDraftDocument();

  function addRow() {
    setVarRows((r) => [...r, { key: '', value: '' }]);
  }
  function removeRow(i: number) {
    setVarRows((r) => r.filter((_, idx) => idx !== i));
  }
  function updateRow(i: number, field: 'key' | 'value', val: string) {
    setVarRows((r) => r.map((row, idx) => (idx === i ? { ...row, [field]: val } : row)));
  }

  function handleSubmit() {
    const variables = Object.fromEntries(
      varRows.filter((r) => r.key).map((r) => [r.key, r.value])
    );
    draftDoc.mutate({ template, variables, polish });
  }

  const result = draftDoc.data;

  return (
    <div className="flex h-full">
      <div className="flex w-96 shrink-0 flex-col gap-4 border-r border-border p-4">
        <div className="space-y-1">
          <label className="text-xs font-medium">Template</label>
          <input
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            placeholder="e.g. nda_standard"
            className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium">Variables</label>
            <Button variant="ghost" size="sm" onClick={addRow}>+ Add</Button>
          </div>
          {varRows.map((row, i) => (
            <div key={i} className="flex gap-2">
              <input
                value={row.key}
                onChange={(e) => updateRow(i, 'key', e.target.value)}
                placeholder="Key"
                className="w-1/3 rounded border border-border bg-background px-2 py-1 text-xs outline-none"
              />
              <input
                value={row.value}
                onChange={(e) => updateRow(i, 'value', e.target.value)}
                placeholder="Value"
                className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs outline-none"
              />
              <button
                type="button"
                onClick={() => removeRow(i)}
                className="text-xs text-muted-foreground hover:text-destructive"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={polish} onChange={(e) => setPolish(e.target.checked)} />
          Polish output
        </label>
        <Button disabled={!template || draftDoc.isPending} onClick={handleSubmit}>
          {draftDoc.isPending ? 'Drafting…' : 'Draft Document'}
        </Button>
      </div>
      <div className="flex-1 p-6">
        <ResultPanel isPending={draftDoc.isPending}>
          {result ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Document</span>
                <CopyButton text={result.document} />
              </div>
              <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded bg-muted p-4 text-sm">
                {result.document}
              </pre>
            </div>
          ) : (
            <EmptyResult />
          )}
        </ResultPanel>
      </div>
    </div>
  );
}

// ─── Mode 3: Precedent-matched ────────────────────────────────────────────────

function PrecedentComposer() {
  const [clauseType, setClauseType] = useState('');
  const [context, setContext] = useState('');
  const [searchEnabled, setSearchEnabled] = useState(false);
  const draftPrecedent = useDraftPrecedent();
  const precedentQuery = usePrecedentSearch(
    searchEnabled ? clauseType : '',
    searchEnabled ? context : ''
  );

  function handleSearch() {
    if (clauseType && context) setSearchEnabled(true);
  }

  function handleDraft() {
    draftPrecedent.mutate({ clause_type: clauseType, context });
  }

  const result = draftPrecedent.data;

  return (
    <div className="flex h-full">
      <div className="flex w-96 shrink-0 flex-col gap-4 border-r border-border p-4">
        <div className="space-y-1">
          <label className="text-xs font-medium">Clause type</label>
          <input
            value={clauseType}
            onChange={(e) => { setClauseType(e.target.value); setSearchEnabled(false); }}
            placeholder="e.g. limitation_of_liability"
            className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium">Context</label>
          <textarea
            rows={3}
            value={context}
            onChange={(e) => { setContext(e.target.value); setSearchEnabled(false); }}
            placeholder="Describe what you need…"
            className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
        <Button variant="outline" disabled={!clauseType || !context} onClick={handleSearch}>
          Search Precedents
        </Button>
        {searchEnabled && precedentQuery.data && precedentQuery.data.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              {precedentQuery.data.length} precedents found
            </p>
            {precedentQuery.data.slice(0, 4).map((c: PrecedentClause) => (
              <HoverCard
                key={c.clause_id}
                trigger={
                  <div className="cursor-pointer rounded border border-border p-2 text-xs hover:bg-muted/40">
                    <span className="font-medium">{c.clause_type}</span>
                    {c.similarity !== undefined && (
                      <Badge variant="secondary" className="ml-2 text-[10px]">
                        {Math.round(c.similarity * 100)}%
                      </Badge>
                    )}
                    <p className="mt-1 line-clamp-2 text-muted-foreground">{c.text}</p>
                  </div>
                }
                content={{ variant: 'citation', char_start: 0, char_end: 0, text: c.text }}
              />
            ))}
          </div>
        )}
        <Button disabled={!clauseType || !context || draftPrecedent.isPending} onClick={handleDraft}>
          {draftPrecedent.isPending ? 'Drafting…' : 'Draft from Precedents'}
        </Button>
      </div>
      <div className="flex-1 p-6">
        <ResultPanel isPending={draftPrecedent.isPending}>
          {result ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Result</span>
                <ProvenanceTag source="frequency" />
                <CopyButton text={result.text} />
              </div>
              <pre className="whitespace-pre-wrap rounded bg-muted p-4 text-sm">{result.text}</pre>
              {result.precedents.length > 0 && (
                <div className="space-y-2 border-t border-border pt-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Precedents drawn from
                  </p>
                  {result.precedents.map((p: PrecedentClause) => (
                    <div key={p.clause_id} className="rounded border border-border p-3 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{p.clause_type}</span>
                        <span className="text-muted-foreground">contract: {p.contract_id}</span>
                        {p.similarity !== undefined && (
                          <Badge variant="secondary" className="text-[10px]">
                            {Math.round(p.similarity * 100)}%
                          </Badge>
                        )}
                      </div>
                      <p className="mt-1 line-clamp-3 text-muted-foreground">{p.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <EmptyResult />
          )}
        </ResultPanel>
      </div>
    </div>
  );
}

// ─── Mode 4: Memo ─────────────────────────────────────────────────────────────

function MemoComposer() {
  const [context, setContext] = useState('');
  const draftMemo = useDraftMemo();

  const result = draftMemo.data;

  return (
    <div className="flex h-full">
      <div className="flex w-96 shrink-0 flex-col gap-4 border-r border-border p-4">
        <div className="space-y-1">
          <label className="text-xs font-medium">Context</label>
          <textarea
            rows={5}
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Describe what the memo should cover…"
            className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
        <Button
          disabled={!context || draftMemo.isPending}
          onClick={() => draftMemo.mutate({ context })}
        >
          {draftMemo.isPending ? 'Drafting…' : 'Draft Memo'}
        </Button>
      </div>
      <div className="flex-1 p-6">
        <ResultPanel isPending={draftMemo.isPending}>
          {result ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Memo</span>
                <ProvenanceTag source="llm" />
                <CopyButton text={result.text} />
              </div>
              <pre className="whitespace-pre-wrap rounded bg-muted p-4 text-sm">{result.text}</pre>
            </div>
          ) : (
            <EmptyResult />
          )}
        </ResultPanel>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DraftingPage() {
  const searchParams = useSearchParams();
  const routedPrompt = searchParams.get('prompt') ?? undefined;
  const [mode, setMode] = useState<Mode>('clause');

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Mode selector */}
      <div className="flex shrink-0 items-center gap-1 border-b border-border px-4 py-2">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={cn(
              'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
              mode === m.id
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Active composer */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {mode === 'clause' && <ClauseComposer onPrompt={routedPrompt} />}
        {mode === 'document' && <DocumentComposer />}
        {mode === 'precedent' && <PrecedentComposer />}
        {mode === 'memo' && <MemoComposer />}
      </div>
    </div>
  );
}
