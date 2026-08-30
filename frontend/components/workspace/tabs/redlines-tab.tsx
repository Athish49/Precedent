'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronDownIcon, ChevronUpIcon, Loader2Icon } from 'lucide-react';
import {
  useRedlines,
  useGenerateRedlines,
  useToggleFallback,
  useRefineRedline,
  useDecideRedline,
  useRedlineHistory,
  useRunReview,
  useReviewRun,
} from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { RedlineBlock } from '@/components/primitives/redline-block';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/components/workspace/workspace-context';
import { undoToast } from '@/lib/undo-toast';
import type { StanceMode, Redline } from '@/lib/api/types';
import { cn } from '@/lib/utils';

const STANCE_OPTIONS: { value: StanceMode; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'firm', label: 'Firm' },
];

interface RedlinesTabProps {
  contractId: string;
}

export function RedlinesTab({ contractId }: RedlinesTabProps) {
  const { setSelected } = useWorkspace();
  const queryClient = useQueryClient();

  const [stance, setStance] = useState<StanceMode>('balanced');
  const [runId, setRunId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const redlinesQuery = useRedlines(contractId);
  const historyQuery = useRedlineHistory(contractId);
  const reviewRunQuery = useReviewRun(runId ?? '');

  const generateRedlines = useGenerateRedlines();
  const toggleFallback = useToggleFallback();
  const refine = useRefineRedline();
  const decide = useDecideRedline();
  const runReview = useRunReview();

  const gateDecision = reviewRunQuery.data?.gate_decision;

  function handleGenerate() {
    generateRedlines.mutate({ contractId, stance_mode: stance });
  }

  function handleRunReview() {
    runReview.mutate(contractId, {
      onSuccess: (data) => setRunId(data.id),
    });
  }

  function handleAccept(r: Redline) {
    decide.mutate({ redlineId: r.id, contractId, body: { outcome: 'accepted' } });
    undoToast({
      message: 'Redline accepted',
      onUndo: () => queryClient.invalidateQueries({ queryKey: ['redlines', contractId] }),
    });
  }

  function handleReject(r: Redline) {
    decide.mutate({ redlineId: r.id, contractId, body: { outcome: 'rejected' } });
    undoToast({
      message: 'Redline rejected',
      onUndo: () => queryClient.invalidateQueries({ queryKey: ['redlines', contractId] }),
    });
  }

  const redlines = redlinesQuery.data ?? [];
  const history = historyQuery.data ?? [];

  return (
    <div className="flex flex-col gap-0">
      {/* Controls */}
      <div className="space-y-2 border-b border-border px-3 py-3">
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-border">
            {STANCE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setStance(opt.value)}
                className={cn(
                  'px-3 py-1 text-xs font-medium transition-colors first:rounded-l-[calc(0.375rem-1px)] last:rounded-r-[calc(0.375rem-1px)]',
                  stance === opt.value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-foreground hover:bg-muted/50'
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <Button
            size="sm"
            className="ml-auto gap-1.5"
            disabled={generateRedlines.isPending}
            onClick={handleGenerate}
          >
            {generateRedlines.isPending && <Loader2Icon className="size-3 animate-spin" />}
            {generateRedlines.isPending ? 'Generating…' : 'Generate Redlines'}
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={runReview.isPending || reviewRunQuery.data?.status === 'running'}
            onClick={handleRunReview}
          >
            {(runReview.isPending || reviewRunQuery.data?.status === 'running') && (
              <Loader2Icon className="size-3 animate-spin" />
            )}
            Run Autonomous Review
          </Button>
        </div>

        {/* Gate decision banner */}
        {gateDecision && (
          <div
            className={cn(
              'rounded-md px-3 py-2 text-xs font-medium',
              gateDecision === 'auto_applied'
                ? 'bg-green-50 text-green-800'
                : 'bg-amber-50 text-amber-800'
            )}
          >
            {gateDecision === 'auto_applied'
              ? 'Gate: Auto-applied'
              : 'Gate: Escalated — review required'}
          </div>
        )}
      </div>

      {/* Redline list */}
      <div className="px-3 py-3">
        <QueryBoundary
          isLoading={redlinesQuery.isLoading}
          error={redlinesQuery.error ?? null}
          isEmpty={!redlinesQuery.isLoading && redlines.length === 0}
          emptyMessage="No redlines yet. Generate redlines to start negotiation."
          emptyAction={
            <Button size="sm" onClick={handleGenerate} disabled={generateRedlines.isPending}>
              Generate Redlines
            </Button>
          }
          onRetry={() => void redlinesQuery.refetch()}
        >
          <div className="space-y-3">
            {redlines.map((r) => (
              <RedlineBlock
                key={r.id}
                redline={r}
                onSelect={() => setSelected({ id: r.id, tabHint: 'redlines' })}
                onToggleFallback={() => toggleFallback.mutate({ redlineId: r.id, contractId })}
                onRefine={(instruction) => refine.mutate({ redlineId: r.id, contractId, instruction })}
                onAccept={() => handleAccept(r)}
                onReject={() => handleReject(r)}
                onAcceptWithEdit={(text) =>
                  decide.mutate({ redlineId: r.id, contractId, body: { outcome: 'accepted', final_text: text } })
                }
              />
            ))}
          </div>
        </QueryBoundary>
      </div>

      {/* Negotiation history */}
      <div className="border-t border-border px-3 py-2">
        <button
          type="button"
          onClick={() => setHistoryOpen((v) => !v)}
          className="flex w-full items-center justify-between text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          Negotiation History
          {historyOpen ? <ChevronUpIcon className="size-3.5" /> : <ChevronDownIcon className="size-3.5" />}
        </button>

        {historyOpen && (
          <div className="mt-2">
            {history.length === 0 ? (
              <p className="text-xs text-muted-foreground">No history yet.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    <th className="pb-1 text-left font-medium text-muted-foreground">Clause</th>
                    <th className="pb-1 text-left font-medium text-muted-foreground">Position</th>
                    <th className="pb-1 text-left font-medium text-muted-foreground">Stance</th>
                    <th className="pb-1 text-left font-medium text-muted-foreground">Outcome</th>
                    <th className="pb-1 text-left font-medium text-muted-foreground">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h, i) => (
                    <tr key={i} className="border-b border-border/50">
                      <td className="py-1 pr-2">{h.clause_type}</td>
                      <td className="py-1 pr-2 capitalize">{h.position_offered}</td>
                      <td className="py-1 pr-2 capitalize">{h.recommended_stance}</td>
                      <td className="py-1 pr-2">{h.outcome}</td>
                      <td className="py-1">{new Date(h.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
