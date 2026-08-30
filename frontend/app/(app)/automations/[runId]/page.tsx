'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import { CheckIcon, XIcon } from 'lucide-react';
import { useReviewRun } from '@/lib/api/hooks';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { GateDecision, ReviewRunStatus } from '@/lib/api/types';

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function StatusBadge({ status }: { status: ReviewRunStatus }) {
  const variant =
    status === 'running' ? 'secondary' : status === 'completed' ? 'default' : 'destructive';
  return <Badge variant={variant} className="capitalize">{status}</Badge>;
}

function GateBanner({ decision }: { decision?: GateDecision }) {
  if (!decision) return null;
  if (decision === 'auto_applied') {
    return (
      <div className="rounded-md bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
        ✓ Gate: Auto-applied — all checks passed
      </div>
    );
  }
  return (
    <div className="rounded-md bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
      ⚠ Gate: Escalated — manual review required
    </div>
  );
}

export default function RunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const router = useRouter();
  const { data: run, isLoading, error } = useReviewRun(runId);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading run…</p>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-destructive">Failed to load run.</p>
      </div>
    );
  }

  const gateEntries = Object.entries(run.gate_reason ?? {});

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-base font-semibold">Run {runId.slice(0, 8)}…</h1>
          <StatusBadge status={run.status} />
          <Badge variant="outline" className="capitalize">{run.trigger === 'manual' ? 'Manual' : 'Upload event'}</Badge>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>Contract:
            <button
              type="button"
              onClick={() => router.push('/contracts/' + run.contract_id)}
              className="ml-1 text-primary underline-offset-2 hover:underline"
            >
              {run.contract_id.slice(0, 8)}…
            </button>
          </span>
          <span>Started: {formatDate(run.started_at)}</span>
          {run.completed_at && <span>Completed: {formatDate(run.completed_at)}</span>}
        </div>
      </div>

      {/* Running spinner */}
      {run.status === 'running' && (
        <div className="flex items-center gap-3 rounded-md bg-muted/50 px-4 py-3">
          <div className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm">Analysis in progress…</span>
        </div>
      )}

      {/* Failed banner */}
      {run.status === 'failed' && (
        <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          ✗ Run failed
        </div>
      )}

      {/* Gate decision banner */}
      <GateBanner decision={run.gate_decision} />

      {/* Hard-stop checklist */}
      <div className="rounded-lg border border-border p-4 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Gate Checklist</p>
        {gateEntries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No gate details available.</p>
        ) : (
          gateEntries.map(([check, result]) => (
            <div key={check} className="flex items-center gap-2">
              {result ? (
                <CheckIcon className="size-4 text-green-600 shrink-0" />
              ) : (
                <XIcon className="size-4 text-destructive shrink-0" />
              )}
              <span className="text-sm capitalize">{check.replace(/_/g, ' ')}</span>
              <span className={cn('text-xs', result ? 'text-green-600' : 'text-destructive')}>
                {result ? 'Pass' : 'Triggered'}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Workspace links */}
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push('/contracts/' + run.contract_id + '?tab=analysis')}
        >
          View Flags →
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push('/contracts/' + run.contract_id + '?tab=redlines')}
        >
          View Redlines →
        </Button>
      </div>
    </div>
  );
}
