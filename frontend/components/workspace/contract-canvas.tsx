'use client';

import { useMemo, useState } from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import {
  useContractText,
  useContractClauses,
  useNavigation,
  useVersionDiff,
  useDiffSummary,
} from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { Button } from '@/components/ui/button';
import { useWorkspace, type CompareMode } from './workspace-context';
import type { Clause, NavIndexEntry, ChangeSet } from '@/lib/api/types';
import { cn } from '@/lib/utils';

// ─── Text segmentation ────────────────────────────────────────────────────────

type TextSegment =
  | { type: 'plain'; text: string; key: string }
  | { type: 'clause'; clause: Clause; text: string; key: string };

export function buildSegments(canonicalText: string, clauses: Clause[]): TextSegment[] {
  const sorted = [...clauses].sort((a, b) => a.char_start - b.char_start);
  const segments: TextSegment[] = [];
  let cursor = 0;

  for (const clause of sorted) {
    const start = Math.max(clause.char_start, cursor);
    const end = Math.min(clause.char_end, canonicalText.length);
    if (start > cursor) {
      segments.push({ type: 'plain', text: canonicalText.slice(cursor, start), key: `plain-${cursor}` });
    }
    if (start < end) {
      segments.push({ type: 'clause', clause, text: canonicalText.slice(start, end), key: `clause-${clause.id}` });
    }
    cursor = Math.max(cursor, end);
  }

  if (cursor < canonicalText.length) {
    segments.push({ type: 'plain', text: canonicalText.slice(cursor), key: `plain-${cursor}` });
  }

  return segments;
}

// ─── Clause border ────────────────────────────────────────────────────────────

const CLAUSE_BORDER = 'border-l-2 border-border pl-3';

// ─── Highlight helpers ────────────────────────────────────────────────────────

function isInRange(clause: Clause, charStart?: number, charEnd?: number): boolean {
  if (charStart === undefined || charEnd === undefined) return false;
  return clause.char_start < charEnd && clause.char_end > charStart;
}

// ─── Diff highlight segments ──────────────────────────────────────────────────

type DiffSegment =
  | { type: 'plain'; text: string; key: string }
  | { type: 'diff'; diffType: ChangeSet['changes'][number]['type']; text: string; key: string };

function applyDiffHighlights(
  text: string,
  changes: ChangeSet['changes'],
): DiffSegment[] {
  const sorted = [...changes].sort((a, b) => a.char_start - b.char_start);
  const segments: DiffSegment[] = [];
  let cursor = 0;

  for (const change of sorted) {
    const start = Math.max(change.char_start, cursor);
    const end = Math.min(change.char_end, text.length);
    if (start > cursor) {
      segments.push({ type: 'plain', text: text.slice(cursor, start), key: `plain-${cursor}` });
    }
    if (start < end) {
      segments.push({
        type: 'diff',
        diffType: change.type,
        text: text.slice(start, end),
        key: `diff-${start}`,
      });
    }
    cursor = Math.max(cursor, end);
  }

  if (cursor < text.length) {
    segments.push({ type: 'plain', text: text.slice(cursor), key: `plain-${cursor}` });
  }

  return segments;
}

const DIFF_CLASSES: Record<ChangeSet['changes'][number]['type'], string> = {
  delete: 'bg-red-100 line-through text-red-800 dark:bg-red-950/40 dark:text-red-300',
  insert: 'bg-green-100 underline text-green-800 dark:bg-green-950/40 dark:text-green-300',
  modify: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950/40 dark:text-yellow-300',
};

// ─── Diff canvas ──────────────────────────────────────────────────────────────

interface DiffCanvasProps {
  contractId: string;
  compareMode: CompareMode;
}

function DiffCanvas({ contractId, compareMode }: DiffCanvasProps) {
  const workspace = useWorkspace();
  const textQuery = useContractText(contractId);
  const diffQuery = useVersionDiff(contractId, compareMode.vA, compareMode.vB);
  const diffSummary = useDiffSummary();
  const [summary, setSummary] = useState<string | null>(null);

  const isLoading = textQuery.isLoading || diffQuery.isLoading;
  const error = textQuery.error ?? diffQuery.error;
  const isEmpty = !isLoading && !error && (!textQuery.data || !diffQuery.data);

  return (
    <div className="flex h-full flex-col overflow-hidden border-r border-border">
      {/* Compare banner */}
      <div className="flex shrink-0 items-center justify-between border-b border-border bg-muted/40 px-4 py-2">
        <p className="text-xs font-medium text-muted-foreground">
          Comparing <span className="font-semibold text-foreground">{compareMode.vA.slice(0, 8)}</span>
          {' ↔ '}
          <span className="font-semibold text-foreground">{compareMode.vB.slice(0, 8)}</span>
        </p>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-6 text-xs"
            disabled={diffSummary.isPending}
            onClick={() =>
              diffSummary.mutate(
                { contractId, vA: compareMode.vA, vB: compareMode.vB },
                { onSuccess: (d) => setSummary(d.summary) },
              )
            }
          >
            {diffSummary.isPending ? 'Summarizing…' : 'Summarize changes'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 text-xs"
            onClick={() => workspace.setCompareMode(null)}
          >
            Exit compare
          </Button>
        </div>
      </div>

      {summary && (
        <div className="shrink-0 border-b border-border bg-muted/20 px-4 py-2">
          <p className="text-xs text-foreground/80">{summary}</p>
        </div>
      )}

      <QueryBoundary
        isLoading={isLoading}
        error={error}
        isEmpty={isEmpty}
        emptyMessage="Diff not available."
        onRetry={() => {
          void textQuery.refetch();
          void diffQuery.refetch();
        }}
      >
        {textQuery.data && diffQuery.data && (
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl px-6 py-6 font-mono text-sm leading-relaxed">
              {applyDiffHighlights(textQuery.data.canonical_text, diffQuery.data.changes).map((seg) => {
                if (seg.type === 'plain') {
                  return (
                    <span key={seg.key} className="whitespace-pre-wrap text-foreground/80">
                      {seg.text}
                    </span>
                  );
                }
                return (
                  <span
                    key={seg.key}
                    className={cn('whitespace-pre-wrap rounded px-0.5', DIFF_CLASSES[seg.diffType])}
                  >
                    {seg.text}
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}

// ─── Canvas content (rendered once text + clauses loaded) ─────────────────────

interface CanvasContentProps {
  canonicalText: string;
  clauses: Clause[];
  navEntries: NavIndexEntry[];
  navOpen: boolean;
  onNavToggle: () => void;
}

function CanvasContent({ canonicalText, clauses, navEntries, navOpen, onNavToggle }: CanvasContentProps) {
  const workspace = useWorkspace();
  const segments = useMemo(() => buildSegments(canonicalText, clauses), [canonicalText, clauses]);

  const selectedRange = workspace.selected;
  const hoveredRange = workspace.hovered;

  function isClauseSelected(clause: Clause): boolean {
    if (!selectedRange?.charStart && !selectedRange?.charEnd) {
      return selectedRange?.id === clause.id;
    }
    return isInRange(clause, selectedRange?.charStart, selectedRange?.charEnd);
  }

  function isClauseHovered(clause: Clause): boolean {
    if (!hoveredRange) return false;
    return isInRange(clause, hoveredRange.charStart, hoveredRange.charEnd);
  }

  function handleClauseClick(clause: Clause) {
    workspace.setSelected({
      id: clause.id,
      charStart: clause.char_start,
      charEnd: clause.char_end,
    });
  }

  function handleNavClick(entry: NavIndexEntry) {
    workspace.setSelected({ id: entry.clause_id, charStart: entry.char_start });
    const el = document.querySelector(`[data-clause-id="${entry.clause_id}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* Navigation TOC */}
      {navOpen && navEntries.length > 0 && (
        <aside className="w-48 shrink-0 overflow-y-auto border-r border-border bg-muted/30 py-2">
          <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Contents
          </p>
          {navEntries.map((entry) => (
            <button
              key={entry.clause_id}
              type="button"
              onClick={() => handleNavClick(entry)}
              className={cn(
                'w-full px-3 py-1.5 text-left text-xs text-foreground/70 transition-colors hover:bg-muted hover:text-foreground',
                workspace.selected?.id === entry.clause_id && 'bg-primary/10 font-medium text-primary'
              )}
            >
              {entry.clause_type}
            </button>
          ))}
        </aside>
      )}

      {/* Document text */}
      <div className="relative flex-1 overflow-y-auto">
        {/* Nav toggle */}
        <button
          type="button"
          onClick={onNavToggle}
          aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
          className="absolute left-2 top-3 z-10 flex size-6 items-center justify-center rounded border border-border bg-background text-muted-foreground shadow-sm hover:text-foreground"
        >
          {navOpen ? <ChevronLeftIcon className="size-3" /> : <ChevronRightIcon className="size-3" />}
        </button>

        <div className="max-w-3xl mx-auto px-6 py-6 pl-12 font-mono text-sm leading-relaxed">
          {segments.map((seg) => {
            if (seg.type === 'plain') {
              return (
                <span key={seg.key} className="whitespace-pre-wrap text-foreground/80">
                  {seg.text}
                </span>
              );
            }

            const selected = isClauseSelected(seg.clause);
            const hovered = !selected && isClauseHovered(seg.clause);

            return (
              <span
                key={seg.key}
                data-clause-id={seg.clause.id}
                data-selected={selected ? 'true' : undefined}
                onClick={() => handleClauseClick(seg.clause)}
                className={cn(
                  'inline cursor-pointer',
                  CLAUSE_BORDER,
                  selected && 'bg-primary/15 ring-1 ring-primary/40 rounded',
                  hovered && 'bg-muted/50 rounded',
                  !selected && !hovered && 'hover:bg-muted/30'
                )}
              >
                <span className="mr-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
                  {seg.clause.clause_type}
                </span>
                <span className="whitespace-pre-wrap text-foreground">{seg.text}</span>
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── ContractCanvas (public) ──────────────────────────────────────────────────

interface ContractCanvasProps {
  contractId: string;
}

export function ContractCanvas({ contractId }: ContractCanvasProps) {
  const workspace = useWorkspace();
  const textQuery = useContractText(contractId);
  const clausesQuery = useContractClauses(contractId);
  const navQuery = useNavigation(contractId);
  const [navOpen, setNavOpen] = useState(true);

  // Switch to diff view when compare mode is active
  if (workspace.compareMode) {
    return <DiffCanvas contractId={contractId} compareMode={workspace.compareMode} />;
  }

  const textData = textQuery.data;
  const clausesData = clausesQuery.data;
  const navData = navQuery.data ?? [];

  const isLoading = textQuery.isLoading || clausesQuery.isLoading;
  const error = textQuery.error ?? clausesQuery.error;
  const isEmpty = !isLoading && !error && (!textData || !clausesData);

  return (
    <div className="flex h-full flex-col overflow-hidden border-r border-border">
      <QueryBoundary
        isLoading={isLoading}
        error={error}
        isEmpty={isEmpty}
        emptyMessage="Contract text not available."
        onRetry={() => {
          void textQuery.refetch();
          void clausesQuery.refetch();
        }}
      >
        {textData && clausesData && (
          <CanvasContent
            canonicalText={textData.canonical_text}
            clauses={clausesData}
            navEntries={navData}
            navOpen={navOpen}
            onNavToggle={() => setNavOpen((v) => !v)}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
