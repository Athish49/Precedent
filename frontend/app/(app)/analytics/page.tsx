'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  usePortfolioRisk,
  useContractValue,
  useRenewals,
  useAnalyticsTabular,
  useAnalyticsIntelligence,
} from '@/lib/api/hooks';
import { DataTable } from '@/components/primitives/data-table';
import { SeverityIndicator } from '@/components/primitives/severity-indicator';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { ColumnDef, SortDirection } from '@/components/primitives/data-table';
import type { Severity } from '@/lib/api/types';

// ─── Shared card shell ────────────────────────────────────────────────────────

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="mb-3 text-sm font-semibold">{title}</p>
      {children}
    </div>
  );
}

function Bar({ pct }: { pct: number }) {
  return (
    <div className="w-full rounded bg-muted">
      <div className="h-2 rounded bg-primary transition-all" style={{ width: `${Math.max(pct, 2)}%` }} />
    </div>
  );
}

// ─── Dashboard cards ──────────────────────────────────────────────────────────

function PortfolioRiskCard() {
  const router = useRouter();
  const { data, isLoading, error } = usePortfolioRisk();

  if (isLoading) return <Card title="Portfolio Risk"><p className="text-xs text-muted-foreground">Loading…</p></Card>;
  if (error || !data) return <Card title="Portfolio Risk"><p className="text-xs text-destructive">Error loading data</p></Card>;

  const distribution: { severity: Severity; count: number }[] = [
    { severity: 'high', count: data.contracts_high_severity },
    { severity: 'medium', count: data.contracts_medium_severity },
    { severity: 'low', count: data.contracts_low_severity },
  ];
  const maxCount = Math.max(...distribution.map((d) => d.count), 1);

  return (
    <Card title="Portfolio Risk">
      <p className="mb-3 text-3xl font-bold tabular-nums">
        {data.total_contracts}
        <span className="ml-1 text-sm font-normal text-muted-foreground">contracts</span>
      </p>
      <div className="space-y-2">
        {distribution.map(({ severity: sev, count }) => (
          <button
            key={sev}
            type="button"
            onClick={() => router.push('/repository?severity=' + sev)}
            className="flex w-full items-center gap-2 text-left"
          >
            <SeverityIndicator severity={sev} />
            <div className="flex-1">
              <Bar pct={(count / maxCount) * 100} />
            </div>
            <span className="w-6 text-right text-xs tabular-nums text-muted-foreground">{count}</span>
          </button>
        ))}
      </div>
    </Card>
  );
}

function ContractValueCard() {
  const router = useRouter();
  const { data, isLoading, error } = useContractValue();

  if (isLoading) return <Card title="Contract Value"><p className="text-xs text-muted-foreground">Loading…</p></Card>;
  if (error || !data) return <Card title="Contract Value"><p className="text-xs text-destructive">Error loading data</p></Card>;

  return (
    <Card title="Contract Value">
      {data.length === 0 ? (
        <p className="text-xs text-muted-foreground">No contract value data yet.</p>
      ) : (
        <div className="space-y-2">
          {data.slice(0, 8).map((r) => (
            <button
              key={r.contract_id}
              type="button"
              onClick={() => router.push('/contracts/' + r.contract_id)}
              className="flex w-full items-center gap-2 text-left"
            >
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{r.title}</span>
              <span className="w-20 text-right text-xs tabular-nums text-muted-foreground">
                {r.total_value ? `${r.currency ?? '$'}${Number(r.total_value).toLocaleString()}` : '—'}
              </span>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}

function RenewalsBadge({ days }: { days: number }) {
  if (days <= 30) return <Badge variant="destructive">{days}d</Badge>;
  if (days <= 60) return <Badge variant="secondary">{days}d</Badge>;
  return <Badge variant="outline">{days}d</Badge>;
}

function RenewalsCard() {
  const router = useRouter();
  const { data, isLoading, error } = useRenewals();

  if (isLoading) return <Card title="Upcoming Renewals"><p className="text-xs text-muted-foreground">Loading…</p></Card>;
  if (error || !data) return <Card title="Upcoming Renewals"><p className="text-xs text-destructive">Error loading data</p></Card>;
  if (data.length === 0) return <Card title="Upcoming Renewals"><p className="text-xs text-muted-foreground">No upcoming renewals in 90 days.</p></Card>;

  return (
    <Card title="Upcoming Renewals">
      <div className="space-y-1.5">
        {data.slice(0, 8).map((row) => (
          <button
            key={row.contract_id}
            type="button"
            onClick={() => router.push('/contracts/' + row.contract_id)}
            className="flex w-full items-center justify-between gap-2 rounded px-1 py-0.5 text-left hover:bg-muted/50"
          >
            <span className="min-w-0 flex-1 truncate text-xs">{row.title}</span>
            <RenewalsBadge days={row.days_remaining} />
          </button>
        ))}
      </div>
    </Card>
  );
}

function IntelligenceCard() {
  const { data, isLoading, error } = useAnalyticsIntelligence();

  if (isLoading) return <Card title="Intelligence Overview"><p className="text-xs text-muted-foreground">Loading…</p></Card>;
  if (error || !data) return <Card title="Intelligence Overview"><p className="text-xs text-destructive">Error loading data</p></Card>;

  const entries = Object.entries(data).filter(([, v]) => typeof v !== 'object' || v === null);

  return (
    <Card title="Intelligence Overview">
      <dl className="space-y-1.5">
        {entries.map(([key, val]) => (
          <div key={key} className="flex items-start justify-between gap-2">
            <dt className="text-xs capitalize text-muted-foreground">{key.replace(/_/g, ' ')}</dt>
            <dd className="text-right text-xs font-medium">{String(val)}</dd>
          </div>
        ))}
        {entries.length === 0 && <p className="text-xs text-muted-foreground">No intelligence data available.</p>}
      </dl>
    </Card>
  );
}

// ─── Tabular mode ─────────────────────────────────────────────────────────────

function TabularView() {
  const router = useRouter();
  const [extraColumns, setExtraColumns] = useState<string[]>([]);
  const [nlInput, setNlInput] = useState('');
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<string | undefined>();
  const [sortDir, setSortDir] = useState<SortDirection>('asc');
  const PAGE_SIZE = 20;

  const { data, isLoading, error } = useAnalyticsTabular(
    extraColumns.length > 0 ? extraColumns : undefined,
  );

  function handleAddColumn(e: React.FormEvent) {
    e.preventDefault();
    const col = nlInput.trim();
    if (col && !extraColumns.includes(col)) {
      setExtraColumns((prev) => [...prev, col]);
    }
    setNlInput('');
  }

  function handleSort(key: string, dir: SortDirection) {
    setSortKey(key);
    setSortDir(dir);
    setPage(1);
  }

  if (isLoading) return <p className="p-6 text-sm text-muted-foreground">Loading…</p>;
  if (error || !data) return <p className="p-6 text-sm text-destructive">Error loading data</p>;

  const columns: ColumnDef<Record<string, unknown>>[] = data.columns.map((col) => ({
    key: col,
    header: col.replace(/_/g, ' '),
    cell: (row) => <span className="text-xs">{String(row[col] ?? '—')}</span>,
    sortable: true,
  }));

  const sorted = [...data.rows].sort((a, b) => {
    if (!sortKey) return 0;
    const av = String(a[sortKey] ?? '');
    const bv = String(b[sortKey] ?? '');
    return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
  });

  const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="flex flex-col gap-3 p-6">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold">All Contracts</p>
        <form onSubmit={handleAddColumn} className="flex items-center gap-2">
          <input
            type="text"
            value={nlInput}
            onChange={(e) => setNlInput(e.target.value)}
            placeholder="Add NL column (e.g. 'payment terms')"
            className="rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:ring-1 focus:ring-primary/50 w-56"
          />
          <Button type="submit" size="sm" variant="outline" disabled={!nlInput.trim()}>Add</Button>
        </form>
      </div>
      {extraColumns.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {extraColumns.map((col) => (
            <button
              key={col}
              type="button"
              onClick={() => setExtraColumns((prev) => prev.filter((c) => c !== col))}
              className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-xs hover:bg-muted/50"
            >
              {col} ×
            </button>
          ))}
        </div>
      )}
      <DataTable
        columns={columns}
        data={paged}
        total={data.rows.length}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
        onRowClick={(row) => {
          const id = row['id'];
          if (typeof id === 'string') router.push('/contracts/' + id);
        }}
        getRowKey={(_, i) => String(i)}
      />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type Mode = 'dashboard' | 'tabular';

export default function AnalyticsPage() {
  const [mode, setMode] = useState<Mode>('dashboard');

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Mode toggle */}
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-6 py-3">
        <h1 className="flex-1 text-base font-semibold">Analytics & Reporting</h1>
        {(['dashboard', 'tabular'] as const).map((m) => (
          <Button
            key={m}
            size="sm"
            variant={mode === m ? 'default' : 'outline'}
            onClick={() => setMode(m)}
            className="capitalize"
          >
            {m}
          </Button>
        ))}
      </div>

      {mode === 'dashboard' ? (
        <div className="grid grid-cols-1 gap-4 p-6 md:grid-cols-2">
          <PortfolioRiskCard />
          <ContractValueCard />
          <RenewalsCard />
          <IntelligenceCard />
        </div>
      ) : (
        <TabularView />
      )}
    </div>
  );
}
