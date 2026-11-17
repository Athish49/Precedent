'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useContracts } from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { DataTable } from '@/components/primitives/data-table';
import { SeverityIndicator } from '@/components/primitives/severity-indicator';
import { Button } from '@/components/ui/button';
import type { ColumnDef, SortDirection } from '@/components/primitives/data-table';
import type { Severity } from '@/lib/api/types';

type CounterpartyEntry = {
  id: string;
  name: string;
  contractCount: number;
  avgRisk?: number;
};

function riskToSeverity(score: number): Severity {
  if (score >= 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

const PAGE_SIZE = 20;

export default function CounterpartiesPage() {
  const router = useRouter();
  const contractsQuery = useContracts();
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<string>('name');
  const [sortDir, setSortDir] = useState<SortDirection>('asc');

  const entries = useMemo<CounterpartyEntry[]>(() => {
    const items = contractsQuery.data?.items ?? [];
    const map = new Map<string, typeof items>();
    for (const row of items) {
      const key = row.counterparty_display_name ?? 'Unknown';
      const existing = map.get(key) ?? [];
      existing.push(row);
      map.set(key, existing);
    }
    const result: CounterpartyEntry[] = [];
    for (const [name, rows] of map) {
      const riskScores = rows
        .map((r) => r.risk_score)
        .filter((s): s is number => s !== undefined);
      const avgRisk =
        riskScores.length > 0
          ? riskScores.reduce((a, b) => a + b, 0) / riskScores.length
          : undefined;
      result.push({
        id: encodeURIComponent(name),
        name,
        contractCount: rows.length,
        avgRisk,
      });
    }

    result.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'name') cmp = a.name.localeCompare(b.name);
      else if (sortKey === 'contractCount') cmp = a.contractCount - b.contractCount;
      else if (sortKey === 'avgRisk') cmp = (a.avgRisk ?? 0) - (b.avgRisk ?? 0);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return result;
  }, [contractsQuery.data, sortKey, sortDir]);

  const paginated = entries.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const columns: ColumnDef<CounterpartyEntry>[] = [
    { key: 'name', header: 'Name', sortable: true, cell: (r) => r.name },
    {
      key: 'contractCount',
      header: 'Contracts',
      sortable: true,
      cell: (r) => `${r.contractCount} contract${r.contractCount !== 1 ? 's' : ''}`,
    },
    {
      key: 'avgRisk',
      header: 'Avg Risk',
      sortable: true,
      cell: (r) =>
        r.avgRisk !== undefined ? (
          <SeverityIndicator severity={riskToSeverity(r.avgRisk)} />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  return (
    <div className="flex h-full flex-col p-6">
      <h1 className="mb-4 text-lg font-semibold">Counterparties</h1>
      <QueryBoundary
        isLoading={contractsQuery.isLoading}
        error={contractsQuery.error ?? null}
        isEmpty={!contractsQuery.isLoading && entries.length === 0}
        emptyMessage="No counterparties found."
      >
        <DataTable
          columns={columns}
          data={paginated}
          total={entries.length}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={(key, dir) => {
            setSortKey(key);
            setSortDir(dir);
            setPage(1);
          }}
          onRowClick={(entry) => router.push(`/counterparties/${entry.id}`)}
          getRowKey={(entry) => entry.id}
          quickActions={(entry) => (
            <Button
              size="sm"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                router.push(`/counterparties/${entry.id}`);
              }}
            >
              View Profile
            </Button>
          )}
        />
      </QueryBoundary>
    </div>
  );
}
