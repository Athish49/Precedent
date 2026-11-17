'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDownIcon, ChevronUpIcon } from 'lucide-react';
import { useReviewRuns, useRunReview, useContracts, useConfigureWebhook } from '@/lib/api/hooks';
import { DataTable } from '@/components/primitives/data-table';
import { FilterRail } from '@/components/primitives/filter-rail';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { ColumnDef, SortDirection } from '@/components/primitives/data-table';
import type { FacetGroup, FilterState } from '@/components/primitives/filter-rail';
import type { ReviewRun, GateDecision, ReviewRunStatus } from '@/lib/api/types';

const FACETS: FacetGroup[] = [
  {
    type: 'select',
    key: 'gate_decision',
    label: 'Gate Decision',
    options: [
      { label: 'Auto-applied', value: 'auto_applied' },
      { label: 'Escalated', value: 'escalated' },
    ],
  },
  {
    type: 'select',
    key: 'status',
    label: 'Status',
    options: [
      { label: 'Running', value: 'running' },
      { label: 'Completed', value: 'completed' },
      { label: 'Failed', value: 'failed' },
    ],
  },
];

function GateBadge({ decision }: { decision?: GateDecision }) {
  if (!decision) return null;
  return decision === 'auto_applied' ? (
    <Badge variant="default">Auto-applied</Badge>
  ) : (
    <Badge variant="destructive">Escalated</Badge>
  );
}

function StatusBadge({ status }: { status: ReviewRunStatus }) {
  const variant =
    status === 'running' ? 'secondary' : status === 'completed' ? 'default' : 'destructive';
  const label = status === 'running' ? 'Running' : status === 'completed' ? 'Completed' : 'Failed';
  return <Badge variant={variant}>{label}</Badge>;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function AutomationsPage() {
  const router = useRouter();
  const [filterState, setFilterState] = useState<FilterState>({});
  const [sortKey, setSortKey] = useState<string | undefined>();
  const [sortDir, setSortDir] = useState<SortDirection>('desc');
  const [page, setPage] = useState(1);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [selectedContractId, setSelectedContractId] = useState('');
  const [webhookOpen, setWebhookOpen] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState('');

  const runsQuery = useReviewRuns();
  const contractsQuery = useContracts();
  const runReview = useRunReview();
  const configureWebhook = useConfigureWebhook();

  const PAGE_SIZE = 20;

  const allRuns = runsQuery.data ?? [];
  const filtered = allRuns.filter((run) => {
    const gateFilter = (filterState.gate_decision as string[] | undefined)?.[0];
    const statusFilter = (filterState.status as string[] | undefined)?.[0];
    if (gateFilter && run.gate_decision !== gateFilter) return false;
    if (statusFilter && run.status !== statusFilter) return false;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    if (!sortKey) return 0;
    const aVal = String((a as unknown as Record<string, unknown>)[sortKey] ?? '');
    const bVal = String((b as unknown as Record<string, unknown>)[sortKey] ?? '');
    return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  });

  const total = sorted.length;
  const pageItems = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const columns: ColumnDef<ReviewRun>[] = [
    {
      key: 'contract_id',
      header: 'Contract',
      sortable: true,
      cell: (run) => (
        <button
          type="button"
          className="text-primary underline-offset-2 hover:underline text-xs"
          onClick={(e) => {
            e.stopPropagation();
            router.push('/contracts/' + run.contract_id);
          }}
        >
          {run.contract_id.slice(0, 8)}…
        </button>
      ),
    },
    {
      key: 'trigger',
      header: 'Trigger',
      cell: (run) => (
        <span className="text-xs capitalize">{run.trigger === 'manual' ? 'Manual' : 'Upload event'}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      cell: (run) => <StatusBadge status={run.status} />,
    },
    {
      key: 'gate_decision',
      header: 'Gate',
      cell: (run) => <GateBadge decision={run.gate_decision} />,
    },
    {
      key: 'started_at',
      header: 'Started',
      sortable: true,
      cell: (run) => <span className="text-xs text-muted-foreground">{formatDate(run.started_at)}</span>,
    },
  ];

  function handleSort(key: string, dir: SortDirection) {
    setSortKey(key);
    setSortDir(dir);
    setPage(1);
  }

  function handleNewRun() {
    if (!selectedContractId) return;
    runReview.mutate(selectedContractId, {
      onSuccess: () => {
        setNewRunOpen(false);
        setSelectedContractId('');
      },
    });
  }

  return (
    <div className="flex h-full">
      <FilterRail
        facets={FACETS}
        value={filterState}
        onChange={(s) => { setFilterState(s); setPage(1); }}
        className="w-56 shrink-0 border-r border-border"
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2">
          <h1 className="text-sm font-semibold">Autonomous Review Runs</h1>
          <Button size="sm" onClick={() => setNewRunOpen((v) => !v)}>
            New Run
          </Button>
        </div>

        {/* Inline new run form */}
        {newRunOpen && (
          <div className="flex shrink-0 items-end gap-2 border-b border-border bg-muted/30 px-4 py-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Select contract</label>
              <select
                className="rounded border border-border bg-background px-2 py-1.5 text-xs"
                value={selectedContractId}
                onChange={(e) => setSelectedContractId(e.target.value)}
              >
                <option value="">— choose a contract —</option>
                {(contractsQuery.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.title}</option>
                ))}
              </select>
            </div>
            <Button
              size="sm"
              disabled={!selectedContractId || runReview.isPending}
              onClick={handleNewRun}
            >
              {runReview.isPending ? 'Starting…' : 'Start Review'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setNewRunOpen(false)}>Cancel</Button>
          </div>
        )}

        {/* Run table */}
        <div className="flex-1 overflow-auto p-4">
          <QueryBoundary
            isLoading={runsQuery.isLoading}
            error={runsQuery.error ?? null}
            isEmpty={filtered.length === 0}
            emptyMessage="No review runs found."
            onRetry={() => void runsQuery.refetch()}
          >
            <DataTable<ReviewRun>
              columns={columns}
              data={pageItems}
              total={total}
              page={page}
              pageSize={PAGE_SIZE}
              onPageChange={setPage}
              sortKey={sortKey}
              sortDir={sortDir}
              onSort={handleSort}
              onRowClick={(run) => router.push('/automations/' + run.id)}
              getRowKey={(run) => run.id}
            />
          </QueryBoundary>
        </div>

        {/* Webhook config */}
        <div className="shrink-0 border-t border-border">
          <button
            type="button"
            onClick={() => setWebhookOpen((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground"
          >
            Webhook Configuration
            {webhookOpen ? <ChevronUpIcon className="size-3.5" /> : <ChevronDownIcon className="size-3.5" />}
          </button>
          {webhookOpen && (
            <div className="flex items-end gap-2 px-4 pb-3">
              <div className="flex flex-col gap-1 flex-1">
                <label className="text-xs text-muted-foreground">Webhook URL</label>
                <input
                  type="url"
                  placeholder="https://…"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  className="rounded border border-border bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/50"
                />
              </div>
              <Button
                size="sm"
                disabled={!webhookUrl || configureWebhook.isPending}
                onClick={() => configureWebhook.mutate({ url: webhookUrl })}
              >
                {configureWebhook.isPending ? 'Saving…' : 'Save'}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
