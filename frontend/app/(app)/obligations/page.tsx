'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useAlerts, useAckAlert, useMonitorRun } from '@/lib/api/hooks';
import { FilterRail } from '@/components/primitives/filter-rail';
import { StatusBadge } from '@/components/primitives/status-badge';
import { ComplianceChip } from '@/components/primitives/compliance-chip';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { undoToast } from '@/lib/undo-toast';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { AlertType, AlertFilters } from '@/lib/api/types';
import type { FacetGroup, FilterState } from '@/components/primitives/filter-rail';

const FACETS: FacetGroup[] = [
  {
    type: 'select',
    key: 'alert_type',
    label: 'Type',
    options: [
      { label: 'Deadline', value: 'deadline' },
      { label: 'Renewal', value: 'renewal' },
      { label: 'Compliance Pass', value: 'compliance_pass' },
      { label: 'Compliance Fail', value: 'compliance_fail' },
    ],
  },
  {
    type: 'select',
    key: 'acknowledged',
    label: 'Status',
    multiSelect: false,
    options: [
      { label: 'Unacknowledged', value: 'false' },
      { label: 'Acknowledged', value: 'true' },
    ],
  },
];

function filterStateToAlertFilters(fs: FilterState): AlertFilters {
  return {
    type: (fs.alert_type as string[] | undefined)?.[0] as AlertType | undefined,
    acknowledged: fs.acknowledged
      ? (fs.acknowledged as string[])[0] === 'true'
      : undefined,
  };
}

export default function ObligationsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [filterState, setFilterState] = useState<FilterState>({});
  const [monitorMsg, setMonitorMsg] = useState<string | null>(null);

  const alertFilters = filterStateToAlertFilters(filterState);
  const alertsQuery = useAlerts(alertFilters);
  const ackAlert = useAckAlert();
  const monitorRun = useMonitorRun();

  const alerts = alertsQuery.data ?? [];
  const unackedCount = alerts.filter((a) => !a.acknowledged).length;

  function handleMonitorRun() {
    monitorRun.mutate(undefined, {
      onSuccess: (data) => {
        setMonitorMsg(`Monitor run complete — ${data.alerts_fired} alerts fired`);
        setTimeout(() => setMonitorMsg(null), 3000);
      },
    });
  }

  function handleAck(alertId: string) {
    ackAlert.mutate(alertId);
    undoToast({
      message: 'Alert acknowledged',
      onUndo: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
    });
  }

  return (
    <div className="flex h-full">
      <FilterRail
        facets={FACETS}
        value={filterState}
        onChange={setFilterState}
        className="w-56 shrink-0 border-r border-border"
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-2">
          <span className="text-sm font-medium">Obligations & Renewals</span>
          {unackedCount > 0 && (
            <span className="rounded-full bg-destructive px-2 py-0.5 text-xs font-medium text-destructive-foreground">
              {unackedCount} unacked
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            {monitorMsg && (
              <span className="text-xs text-muted-foreground">{monitorMsg}</span>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={handleMonitorRun}
              disabled={monitorRun.isPending}
            >
              {monitorRun.isPending ? 'Running…' : 'Run Monitor'}
            </Button>
          </div>
        </div>

        {/* Alert list */}
        <div className="flex-1 overflow-y-auto p-4">
          <QueryBoundary
            isLoading={alertsQuery.isLoading}
            error={alertsQuery.error ?? null}
            isEmpty={alerts.length === 0}
            emptyMessage="No alerts match current filters."
            onRetry={() => void alertsQuery.refetch()}
          >
            <div className="space-y-3">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="cursor-pointer rounded-lg border border-border bg-card p-3 transition-colors hover:bg-muted/30"
                  onClick={() => {
                    if (alert.alert_type === 'renewal') {
                      router.push('/contracts/' + alert.contract_id);
                    } else {
                      router.push('/contracts/' + alert.contract_id + '?tab=obligations');
                    }
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge type="alert" value={alert.alert_type} />

                      {/* Type-specific content */}
                      {alert.alert_type === 'deadline' && (
                        <span
                          className={cn(
                            'text-xs font-medium',
                            typeof alert.payload.days_remaining === 'number' &&
                              alert.payload.days_remaining <= 7
                              ? 'text-destructive'
                              : typeof alert.payload.days_remaining === 'number' &&
                                  alert.payload.days_remaining <= 30
                                ? 'text-amber-600'
                                : 'text-muted-foreground'
                          )}
                        >
                          {typeof alert.payload.days_remaining === 'number'
                            ? `${alert.payload.days_remaining} days remaining`
                            : 'Deadline alert'}
                        </span>
                      )}

                      {alert.alert_type === 'renewal' && typeof alert.payload.title === 'string' && (
                        <span className="text-xs text-muted-foreground">
                          {alert.payload.title}
                        </span>
                      )}

                      {alert.alert_type === 'compliance_pass' && (
                        <span className="text-xs text-green-600">Compliance check passed</span>
                      )}
                    </div>

                    {!alert.acknowledged && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0 text-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleAck(alert.id);
                        }}
                      >
                        Ack
                      </Button>
                    )}
                  </div>

                  {/* Renewal recommendation */}
                  {alert.alert_type === 'renewal' &&
                    typeof alert.payload.recommendation === 'string' && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {alert.payload.recommendation}
                      </p>
                    )}

                  {/* Compliance fail issues */}
                  {alert.alert_type === 'compliance_fail' &&
                    Array.isArray(alert.payload.issues) && (
                      <div
                        className="mt-2 flex flex-wrap gap-1.5"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {(alert.payload.issues as Record<string, unknown>[]).map((issue, i) => (
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

                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Contract: {alert.contract_id} ·{' '}
                    {new Date(alert.fired_at).toLocaleDateString()}
                    {alert.acknowledged && ' · Acknowledged'}
                  </p>
                </div>
              ))}
            </div>
          </QueryBoundary>
        </div>
      </div>
    </div>
  );
}
