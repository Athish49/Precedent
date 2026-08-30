'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowUpRightIcon } from 'lucide-react';
import {
  useObligations,
  useExtractObligations,
  useComplianceCheck,
  useAlerts,
  useAckAlert,
} from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { StatusBadge } from '@/components/primitives/status-badge';
import { ComplianceChip } from '@/components/primitives/compliance-chip';
import { undoToast } from '@/lib/undo-toast';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useWorkspace } from '@/components/workspace/workspace-context';
import type { ObligationStatus } from '@/lib/api/types';
import { cn } from '@/lib/utils';

function formatRelative(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const OBLIGATION_VARIANT: Record<ObligationStatus, 'destructive' | 'default' | 'secondary'> = {
  overdue: 'destructive',
  met: 'default',
  open: 'secondary',
};

export function ObligationsTab({ contractId }: { contractId: string }) {
  const { setSelected } = useWorkspace();
  const queryClient = useQueryClient();

  const obligationsQuery = useObligations(contractId);
  const alertsQuery = useAlerts({ acknowledged: false });
  const extractMutation = useExtractObligations();
  const complianceMutation = useComplianceCheck();
  const ackAlert = useAckAlert();

  const [complianceResult, setComplianceResult] = useState<{
    pass: boolean;
    issues: Record<string, unknown>[];
  } | null>(null);

  const contractAlerts = (alertsQuery.data ?? []).filter(
    (a) => a.contract_id === contractId && !a.acknowledged,
  );

  return (
    <div className="flex flex-col gap-0 px-3 py-3">
      {/* ── Section 1: Obligations ── */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Obligations
          </p>
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-xs"
            disabled={extractMutation.isPending}
            onClick={() => extractMutation.mutate(contractId)}
          >
            {extractMutation.isPending ? 'Extracting…' : 'Extract'}
          </Button>
        </div>

        <QueryBoundary
          isLoading={obligationsQuery.isLoading}
          error={obligationsQuery.error ?? null}
          isEmpty={!obligationsQuery.data?.length}
          emptyMessage="No obligations extracted. Click Extract to analyze."
          onRetry={() => void obligationsQuery.refetch()}
        >
          <div className="flex flex-col gap-2">
            {obligationsQuery.data?.map((ob) => (
              <div
                key={ob.id}
                className="rounded-md border border-border bg-muted/20 px-3 py-2 text-xs"
              >
                <div className="mb-1 flex items-start justify-between gap-2">
                  <Badge variant={OBLIGATION_VARIANT[ob.status]} className="shrink-0 capitalize">
                    {ob.status}
                  </Badge>
                  {ob.char_start !== undefined && ob.char_end !== undefined && (
                    <button
                      type="button"
                      aria-label="Jump to clause"
                      onClick={() =>
                        setSelected({
                          id: ob.id,
                          charStart: ob.char_start,
                          charEnd: ob.char_end,
                          tabHint: 'obligations',
                        })
                      }
                      className="text-muted-foreground hover:text-primary"
                    >
                      <ArrowUpRightIcon className="size-3.5" />
                    </button>
                  )}
                </div>
                <p className="line-clamp-2 font-medium text-foreground">{ob.commitment}</p>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-muted-foreground">
                  <span>Owner: {ob.owner}</span>
                  {ob.deadline && <span>Due: {ob.deadline}</span>}
                  <span>Deliverable: {ob.deliverable}</span>
                </div>
              </div>
            ))}
          </div>
        </QueryBoundary>
      </div>

      {/* ── Section 2: Compliance check ── */}
      <div className="mt-4 border-t border-border pt-4">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Compliance
          </p>
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-xs"
            disabled={complianceMutation.isPending}
            onClick={() =>
              complianceMutation.mutate(contractId, {
                onSuccess: (data) => setComplianceResult(data),
              })
            }
          >
            {complianceMutation.isPending ? 'Checking…' : 'Run Check'}
          </Button>
        </div>

        {complianceResult && (
          <div className="flex flex-col gap-2">
            <div
              className={cn(
                'rounded-md px-3 py-2 text-xs font-medium',
                complianceResult.pass
                  ? 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300'
                  : 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
              )}
            >
              {complianceResult.pass ? '✓ Compliance check passed' : '⚠ Issues found'}
            </div>
            {!complianceResult.pass &&
              complianceResult.issues.map((issue, i) => (
                <ComplianceChip
                  key={i}
                  label={String(issue.field ?? issue.type ?? 'Issue')}
                  foundValue={String(issue.found_value ?? '—')}
                  policyValue={String(issue.policy_value ?? '—')}
                  state="deviation"
                />
              ))}
          </div>
        )}
      </div>

      {/* ── Section 3: Alerts ── */}
      <div className="mt-4 border-t border-border pt-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Alerts
        </p>

        {contractAlerts.length === 0 ? (
          <p className="text-xs text-muted-foreground">No active alerts.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {contractAlerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
              >
                <div className="flex min-w-0 flex-col gap-0.5">
                  <StatusBadge type="alert" value={alert.alert_type} />
                  <span className="text-xs text-muted-foreground">
                    {formatRelative(alert.fired_at)}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 shrink-0 px-2 text-xs"
                  disabled={ackAlert.isPending}
                  onClick={() => {
                    ackAlert.mutate(alert.id);
                    undoToast({
                      message: 'Alert acknowledged',
                      onUndo: () =>
                        queryClient.invalidateQueries({ queryKey: ['alerts'] }),
                    });
                  }}
                >
                  Ack
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
