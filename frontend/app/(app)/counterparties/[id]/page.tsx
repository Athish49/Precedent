'use client';

import { use, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useContracts, useRedlineHistory, useRenewals, useRunReview } from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { DataTable } from '@/components/primitives/data-table';
import { StatusBadge } from '@/components/primitives/status-badge';
import { SeverityIndicator } from '@/components/primitives/severity-indicator';
import { HoverCard } from '@/components/primitives/hover-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { ColumnDef } from '@/components/primitives/data-table';
import type { ContractRow, RedlineHistoryItem, Severity } from '@/lib/api/types';

function riskToSeverity(score: number): Severity {
  if (score >= 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

// Sub-component: fetches + renders redline history for one contract
function ContractHistorySection({ contractId, counterpartyName }: { contractId: string; counterpartyName: string }) {
  const historyQuery = useRedlineHistory(contractId);

  if (historyQuery.isLoading) return <p className="text-xs text-muted-foreground">Loading history…</p>;
  if (!historyQuery.data?.length) return <p className="text-xs text-muted-foreground">No history.</p>;

  const grouped = new Map<string, RedlineHistoryItem[]>();
  for (const item of historyQuery.data) {
    const existing = grouped.get(item.clause_type) ?? [];
    existing.push(item);
    grouped.set(item.clause_type, existing);
  }

  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-border text-left text-muted-foreground">
          <th className="pb-1 pr-3 font-medium">Clause Type</th>
          <th className="pb-1 pr-3 font-medium">Outcomes</th>
          <th className="pb-1 pr-3 font-medium">Last Outcome</th>
          <th className="pb-1 font-medium">Stance</th>
        </tr>
      </thead>
      <tbody>
        {[...grouped.entries()].map(([clauseType, items]) => {
          const accepted = items.filter((i) => i.outcome === 'accepted').length;
          const total = items.length;
          const last = items[items.length - 1];
          const acceptanceRate = total > 0 ? accepted / total : 0;

          return (
            <HoverCard
              key={clauseType}
              trigger={
                <tr className="cursor-pointer border-b border-border/50 hover:bg-muted/30">
                  <td className="py-1.5 pr-3">{clauseType}</td>
                  <td className="py-1.5 pr-3">
                    {accepted}/{total} accepted
                  </td>
                  <td className="py-1.5 pr-3 capitalize">{last.outcome}</td>
                  <td className="py-1.5 capitalize">{last.recommended_stance}</td>
                </tr>
              }
              content={{ variant: 'counterparty', name: counterpartyName, acceptanceRate }}
            />
          );
        })}
      </tbody>
    </table>
  );
}

export default function CounterpartyProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const contractsQuery = useContracts({ counterparty_id: id });
  const renewalsQuery = useRenewals();
  const runReview = useRunReview();

  const contracts = useMemo(
    () => contractsQuery.data?.items ?? [],
    [contractsQuery.data],
  );

  const counterpartyName = contracts[0]?.counterparty_display_name ?? decodeURIComponent(id);
  const totalValue = useMemo(
    () => contracts.reduce((sum, c) => sum + (c.value ?? 0), 0),
    [contracts],
  );
  const avgRisk = useMemo(() => {
    const scores = contracts.map((c) => c.risk_score).filter((s): s is number => s !== undefined);
    return scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : undefined;
  }, [contracts]);

  const counterpartyContractIds = new Set(contracts.map((c) => c.id));
  const relevantRenewals = (renewalsQuery.data ?? []).filter((r) =>
    counterpartyContractIds.has(r.contract_id),
  );

  const contractColumns: ColumnDef<ContractRow>[] = [
    { key: 'title', header: 'Title', sortable: true, cell: (r) => r.title },
    {
      key: 'contract_type',
      header: 'Type',
      cell: (r) => r.contract_type ?? <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'status',
      header: 'Status',
      cell: (r) => <StatusBadge type="contract" value={r.status} />,
    },
    {
      key: 'effective_date',
      header: 'Effective',
      cell: (r) => r.effective_date ?? <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'value',
      header: 'Value',
      align: 'right',
      cell: (r) =>
        r.value !== undefined ? (
          `$${r.value.toLocaleString()}`
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: 'max_clause_severity',
      header: 'Risk',
      cell: (r) =>
        r.max_clause_severity ? (
          <SeverityIndicator severity={r.max_clause_severity} />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  const historyContracts = contracts.slice(0, 3);

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            type="button"
            onClick={() => router.push('/counterparties')}
            className="mb-1 text-xs text-muted-foreground hover:underline"
          >
            ← Counterparties
          </button>
          <h1 className="text-xl font-semibold">{counterpartyName}</h1>
          <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
            <span>{contracts.length} contracts</span>
            {totalValue > 0 && <span>${totalValue.toLocaleString()} total value</span>}
            {avgRisk !== undefined && (
              <span className="flex items-center gap-1">
                Avg risk: <SeverityIndicator severity={riskToSeverity(avgRisk)} />
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Contracts table */}
      <section>
        <h2 className="mb-2 text-sm font-semibold">Contracts</h2>
        <QueryBoundary
          isLoading={contractsQuery.isLoading}
          error={contractsQuery.error ?? null}
          isEmpty={!contractsQuery.isLoading && contracts.length === 0}
          emptyMessage="No contracts found for this counterparty."
        >
          <DataTable
            columns={contractColumns}
            data={contracts}
            total={contracts.length}
            page={1}
            pageSize={contracts.length || 1}
            onPageChange={() => undefined}
            onRowClick={(row) => router.push(`/contracts/${row.id}`)}
            getRowKey={(row) => row.id}
            quickActions={(row) => (
              <>
                <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); router.push(`/contracts/${row.id}`); }}>
                  Open
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={runReview.isPending}
                  onClick={(e) => { e.stopPropagation(); runReview.mutate(row.id); }}
                >
                  Run Review
                </Button>
              </>
            )}
          />
        </QueryBoundary>
      </section>

      {/* Negotiation history */}
      {historyContracts.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">Negotiation History</h2>
          <div className="space-y-4">
            {historyContracts.map((c) => (
              <div key={c.id} className="rounded-md border border-border p-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">{c.title}</p>
                <ContractHistorySection contractId={c.id} counterpartyName={counterpartyName} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Upcoming renewals */}
      {relevantRenewals.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">Upcoming Renewals</h2>
          <div className="space-y-2">
            {relevantRenewals.map((r) => (
              <div
                key={r.contract_id}
                className="flex cursor-pointer items-center justify-between rounded-md border border-border px-3 py-2 hover:bg-muted/30"
                onClick={() => router.push(`/contracts/${r.contract_id}`)}
              >
                <span className="text-sm">{r.title}</span>
                <Badge
                  variant={
                    r.days_remaining <= 30
                      ? 'destructive'
                      : r.days_remaining <= 60
                        ? 'secondary'
                        : 'outline'
                  }
                  className="text-xs"
                >
                  {r.days_remaining}d
                </Badge>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
