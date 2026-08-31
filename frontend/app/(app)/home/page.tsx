'use client';

import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import {
  usePortfolioRisk,
  useContractValue,
  useRenewals,
  useAlerts,
  useAckAlert,
  useContracts,
  useReviewRuns,
} from '@/lib/api/hooks';
import { SeverityIndicator } from '@/components/primitives/severity-indicator';
import { StatusBadge } from '@/components/primitives/status-badge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { undoToast } from '@/lib/undo-toast';
import type { Severity } from '@/lib/api/types';
import { cn } from '@/lib/utils';

function CardShell({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-lg border border-border bg-card p-4', className)}>
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
      {children}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2">
      {[70, 50, 80].map((w) => (
        <div key={w} className="h-3 animate-pulse rounded bg-muted" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

// ─── Portfolio Risk ────────────────────────────────────────────────────────────

function PortfolioRiskCard() {
  const router = useRouter();
  const { data, isLoading, error } = usePortfolioRisk();

  return (
    <CardShell title="Portfolio Risk">
      {isLoading && <Skeleton />}
      {error && <p className="text-xs text-destructive">Unable to load.</p>}
      {data && (
        <div className="space-y-3">
          <div className="flex items-end gap-1">
            <span className="text-4xl font-bold">{data.total_contracts}</span>
            <span className="mb-1 text-sm text-muted-foreground">contracts</span>
          </div>
          <div className="space-y-1">
            {(
              [
                { severity: 'high' as Severity, count: data.contracts_high_severity },
                { severity: 'medium' as Severity, count: data.contracts_medium_severity },
                { severity: 'low' as Severity, count: data.contracts_low_severity },
              ] as { severity: Severity; count: number }[]
            ).map((d) => (
              <div key={d.severity} className="flex items-center gap-2 text-xs">
                <SeverityIndicator severity={d.severity} />
                <span className="capitalize text-muted-foreground">{d.severity}:</span>
                <span className="font-medium">{d.count}</span>
              </div>
            ))}
          </div>
          <Button variant="outline" size="sm" className="w-full" onClick={() => router.push('/analytics')}>
            View Analytics →
          </Button>
        </div>
      )}
    </CardShell>
  );
}

// ─── Action Queue ─────────────────────────────────────────────────────────────

function ActionQueueCard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const alertsQuery = useAlerts({ acknowledged: false });
  const runsQuery = useReviewRuns();
  const contractsQuery = useContracts({ status: 'analyzed' });
  const ackAlert = useAckAlert();

  type QueueItem =
    | { kind: 'alert'; id: string; label: string; sub: string; href: string }
    | { kind: 'escalated'; id: string; label: string; sub: string; href: string }
    | { kind: 'redline'; id: string; label: string; sub: string; href: string };

  const items: QueueItem[] = [];

  for (const a of alertsQuery.data ?? []) {
    if (!a.acknowledged) {
      items.push({ kind: 'alert', id: a.id, label: a.alert_type.replace('_', ' '), sub: a.contract_id.slice(0, 8), href: `/contracts/${a.contract_id}?tab=obligations` });
    }
  }
  for (const r of runsQuery.data ?? []) {
    if (r.gate_decision === 'escalated') {
      items.push({ kind: 'escalated', id: r.id, label: 'Escalated run', sub: r.contract_id.slice(0, 8), href: `/automations/${r.id}` });
    }
  }
  for (const c of contractsQuery.data?.items ?? []) {
    items.push({ kind: 'redline', id: c.id, label: c.title, sub: 'Pending redlines', href: `/contracts/${c.id}?tab=redlines` });
  }

  const capped = items.slice(0, 8);

  const BADGE_LABELS: Record<QueueItem['kind'], string> = {
    alert: 'Alert',
    escalated: 'Escalated',
    redline: 'Pending',
  };

  return (
    <CardShell title="Action Queue">
      {capped.length === 0 ? (
        <p className="text-xs text-muted-foreground">All clear — no pending actions.</p>
      ) : (
        <ul className="space-y-2">
          {capped.map((item) => (
            <li key={item.kind + item.id} className="flex items-center gap-2">
              <Badge variant="secondary" className="shrink-0 text-[10px]">{BADGE_LABELS[item.kind]}</Badge>
              <button
                type="button"
                onClick={() => router.push(item.href)}
                className="min-w-0 flex-1 text-left text-xs hover:underline truncate"
              >
                <span className="font-medium capitalize">{item.label}</span>
                <span className="ml-1 text-muted-foreground">#{item.sub}</span>
              </button>
              {item.kind === 'alert' && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 shrink-0 px-2 text-xs"
                  onClick={() => {
                    ackAlert.mutate(item.id);
                    undoToast({
                      message: 'Alert acknowledged',
                      onUndo: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
                    });
                  }}
                >
                  Ack
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

// ─── Upcoming Renewals ────────────────────────────────────────────────────────

function RenewalBucket({ days }: { days: number }) {
  const cls = days <= 30 ? 'text-destructive' : days <= 60 ? 'text-amber-600' : 'text-muted-foreground';
  return <span className={cn('text-xs font-medium', cls)}>in {days}d</span>;
}

function UpcomingRenewalsCard() {
  const router = useRouter();
  const { data, isLoading, error } = useRenewals();
  const rows = (data ?? []).slice(0, 5);

  return (
    <CardShell title="Upcoming Renewals">
      {isLoading && <Skeleton />}
      {error && <p className="text-xs text-destructive">Unable to load.</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="text-xs text-muted-foreground">No upcoming renewals in 90 days.</p>
      )}
      {rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.contract_id}>
              <button
                type="button"
                onClick={() => router.push(`/contracts/${r.contract_id}`)}
                className="flex w-full items-center gap-2 text-left hover:opacity-80"
              >
                <span className="min-w-0 flex-1 truncate text-xs font-medium">{r.title}</span>
                {r.risk_score !== undefined && r.risk_score > 60 && (
                  <SeverityIndicator severity="high" />
                )}
                <RenewalBucket days={r.days_remaining} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

// ─── Recent Activity ──────────────────────────────────────────────────────────

function RecentActivityCard() {
  const router = useRouter();
  const { data, isLoading, error } = useContracts();
  const rows = (data?.items ?? []).slice(0, 5);

  return (
    <CardShell title="Recent Activity">
      {isLoading && <Skeleton />}
      {error && <p className="text-xs text-destructive">Unable to load.</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="text-xs text-muted-foreground">No contracts yet.</p>
      )}
      {rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => router.push(`/contracts/${r.id}`)}
                className="flex w-full items-center gap-2 text-left hover:opacity-80"
              >
                <span className="min-w-0 flex-1 truncate text-xs font-medium">{r.title}</span>
                <StatusBadge type="contract" value={r.status} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

// ─── Contract Value ───────────────────────────────────────────────────────────

function ContractValueCard() {
  const { data, isLoading, error } = useContractValue();

  return (
    <CardShell title="Contract Value">
      {isLoading && <Skeleton />}
      {error && <p className="text-xs text-destructive">Unable to load.</p>}
      {data && data.length === 0 && (
        <p className="text-xs text-muted-foreground">No contract value data yet.</p>
      )}
      {data && data.length > 0 && (
        <ul className="space-y-1">
          {data.slice(0, 5).map((r) => (
            <li key={r.contract_id} className="flex items-center justify-between text-xs">
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{r.title}</span>
              <span className="ml-2 font-medium">
                {r.total_value ? `${r.currency ?? '$'}${Number(r.total_value).toLocaleString()}` : '—'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

// ─── Compliance Failures ──────────────────────────────────────────────────────

function ComplianceFailuresCard() {
  const router = useRouter();
  const { data, isLoading, error } = useAlerts({ type: 'compliance_fail', acknowledged: false });
  const count = (data ?? []).length;

  return (
    <CardShell title="Open Compliance Issues">
      {isLoading && <Skeleton />}
      {error && <p className="text-xs text-destructive">Unable to load.</p>}
      {!isLoading && !error && (
        <div className="space-y-3">
          {count === 0 ? (
            <p className="text-sm font-medium text-green-600">✓ No open compliance failures</p>
          ) : (
            <>
              <p className="text-3xl font-bold text-destructive">{count}</p>
              <p className="text-xs text-muted-foreground">open compliance {count === 1 ? 'issue' : 'issues'}</p>
              <Button variant="outline" size="sm" className="w-full" onClick={() => router.push('/obligations')}>
                View Obligations →
              </Button>
            </>
          )}
        </div>
      )}
    </CardShell>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function HomePage() {
  return (
    <div className="p-6">
      <h1 className="mb-6 text-lg font-semibold">Home</h1>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PortfolioRiskCard />
        <ActionQueueCard />
        <UpcomingRenewalsCard />
        <RecentActivityCard />
        <ContractValueCard />
        <ComplianceFailuresCard />
      </div>
    </div>
  );
}
