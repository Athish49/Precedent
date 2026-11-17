'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { SearchIcon, SparklesIcon, ChevronDownIcon, ExternalLinkIcon, PlayIcon, GitBranchIcon, XIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { DataTable, type ColumnDef, type SortDirection } from '@/components/primitives/data-table';
import { FilterRail, type FacetGroup, type FilterState } from '@/components/primitives/filter-rail';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { StatusBadge } from '@/components/primitives/status-badge';
import { SeverityIndicator } from '@/components/primitives/severity-indicator';
import {
  useContracts,
  useContractSearch,
  useSmartSearch,
  useContractVersions,
  useRunReview,
} from '@/lib/api/hooks';
import type { ContractRow, ContractFilters, ContractStatus, Version } from '@/lib/api/types';
import { cn } from '@/lib/utils';

const PAGE_SIZE = 20;

const FACETS: FacetGroup[] = [
  {
    type: 'select',
    key: 'contract_type',
    label: 'Type',
    options: [
      { label: 'NDA', value: 'nda' },
      { label: 'MSA', value: 'msa' },
      { label: 'SOW', value: 'sow' },
      { label: 'Employment', value: 'employment' },
    ],
  },
  {
    type: 'select',
    key: 'status',
    label: 'Status',
    options: [
      { label: 'Processing', value: 'processing' },
      { label: 'Analyzed', value: 'analyzed' },
      { label: 'Redlined', value: 'redlined' },
      { label: 'Executed', value: 'executed' },
    ],
  },
  { type: 'range', key: 'effective_date', label: 'Effective Date', unit: 'year' },
  { type: 'range', key: 'value', label: 'Value ($)', unit: 'USD' },
];

function formatDate(d?: string) {
  if (!d) return '—';
  return d.slice(0, 10);
}

function formatValue(v?: number) {
  if (v === undefined || v === null) return '—';
  return `$${v.toLocaleString()}`;
}

// ─── Version expander panel ───────────────────────────────────────────────────

function VersionsPanel({ contractId, onClose }: { contractId: string; onClose: () => void }) {
  const { data, isLoading, error } = useContractVersions(contractId);
  return (
    <div className="border-t border-border bg-muted/30 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold text-muted-foreground">Version lineage</p>
        <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <XIcon className="size-3.5" />
        </button>
      </div>
      {isLoading && (
        <div className="space-y-1.5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-4 w-3/4 animate-pulse rounded bg-muted" />
          ))}
        </div>
      )}
      {error && <p className="text-xs text-destructive">Failed to load versions.</p>}
      {data && data.length === 0 && (
        <p className="text-xs text-muted-foreground">No versions stored.</p>
      )}
      {data && data.length > 0 && (
        <ol className="space-y-1">
          {data.map((v: Version) => (
            <li key={v.id} className="flex items-center gap-2 text-xs">
              <GitBranchIcon className="size-3 shrink-0 text-muted-foreground" />
              <span className="font-medium">v{v.version_number}</span>
              <Badge variant="outline" className="px-1 py-0 text-[10px]">
                {v.relation}
              </Badge>
              <span className="text-muted-foreground">{formatDate(v.created_at)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function RepositoryPage() {
  const router = useRouter();

  const [filters, setFilters] = useState<FilterState>({});
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState('');
  const [sortDir, setSortDir] = useState<SortDirection>('asc');
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [isSmartMode, setIsSmartMode] = useState(false);
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  const runReview = useRunReview();

  // 300ms debounce for keyword search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset to page 1 when filters or search change
  const prevFiltersRef = useRef(filters);
  useEffect(() => {
    if (prevFiltersRef.current !== filters) {
      setPage(1);
      prevFiltersRef.current = filters;
    }
  }, [filters]);

  // Map FilterState → ContractFilters
  const mappedFilters: ContractFilters = (() => {
    const out: ContractFilters = { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE };
    const ct = filters['contract_type'] as string[] | undefined;
    if (ct?.length) out.contract_type = ct[0];
    const st = filters['status'] as string[] | undefined;
    if (st?.length) out.status = st[0] as ContractStatus;
    const dateRange = filters['effective_date'] as [number, number] | undefined;
    if (dateRange) {
      out.effective_date_from = `${dateRange[0]}-01-01`;
      out.effective_date_to = `${dateRange[1]}-12-31`;
    }
    const valueRange = filters['value'] as [number, number] | undefined;
    if (valueRange) {
      out.value_min = valueRange[0];
      out.value_max = valueRange[1];
    }
    return out;
  })();

  const isKeywordSearch = !isSmartMode && debouncedSearch.length >= 2;

  // Always call all three hooks; conditionally use results
  const contractsQuery = useContracts(!isSmartMode && !isKeywordSearch ? mappedFilters : undefined);
  const searchQuery = useContractSearch(isKeywordSearch ? debouncedSearch : '');
  const smartSearch = useSmartSearch();

  // Active data source
  const activeIsLoading = isSmartMode
    ? smartSearch.isPending
    : isKeywordSearch
      ? searchQuery.isLoading
      : contractsQuery.isLoading;

  const activeError: Error | null = isSmartMode
    ? (smartSearch.error as Error | null)
    : isKeywordSearch
      ? (searchQuery.error as Error | null)
      : (contractsQuery.error as Error | null);

  const activeData = isSmartMode
    ? smartSearch.data
    : isKeywordSearch
      ? searchQuery.data
      : contractsQuery.data;

  function handleSort(key: string, dir: SortDirection) {
    setSortKey(key);
    setSortDir(dir);
    setPage(1);
  }

  function handleSmartSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (searchInput.trim()) smartSearch.mutate(searchInput.trim());
  }

  function toggleExpand(rowId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setExpandedRowId((prev) => (prev === rowId ? null : rowId));
  }

  const COLUMNS: ColumnDef<ContractRow>[] = [
    {
      key: 'title',
      header: 'Title',
      sortable: true,
      cell: (row) => <span className="font-medium">{row.title}</span>,
    },
    {
      key: 'contract_type',
      header: 'Type',
      sortable: true,
      cell: (row) => row.contract_type ? (
        <span className="capitalize">{row.contract_type}</span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    },
    {
      key: 'counterparty_display_name',
      header: 'Counterparty',
      cell: (row) => row.counterparty_display_name ?? <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'status',
      header: 'Status',
      cell: (row) => <StatusBadge type="contract" value={row.status} />,
    },
    {
      key: 'max_clause_severity',
      header: 'Risk',
      cell: (row) =>
        row.max_clause_severity ? (
          <SeverityIndicator severity={row.max_clause_severity} />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: 'effective_date',
      header: 'Effective',
      cell: (row) => <span className="text-muted-foreground">{formatDate(row.effective_date)}</span>,
    },
    {
      key: 'value',
      header: 'Value',
      align: 'right',
      cell: (row) => <span className="text-muted-foreground">{formatValue(row.value)}</span>,
    },
  ];

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* ── FilterRail ── */}
      <div
        className={cn(
          'w-[220px] shrink-0 border-r border-border bg-background',
          isSmartMode && 'pointer-events-none opacity-40'
        )}
      >
        <div className="border-b border-border px-3 py-2.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Filters
          </p>
        </div>
        <FilterRail facets={FACETS} value={filters} onChange={setFilters} />
      </div>

      {/* ── Main content ── */}
      <div className="flex min-w-0 flex-1 flex-col gap-0 overflow-hidden">
        {/* Search bar */}
        <div className="border-b border-border bg-background px-4 py-3">
          <form
            className="flex items-center gap-2"
            onSubmit={isSmartMode ? handleSmartSubmit : (e) => e.preventDefault()}
          >
            <div className="relative flex-1">
              <SearchIcon className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-8 text-sm"
                placeholder={isSmartMode ? 'Ask anything about your contracts…' : 'Search contracts…'}
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </div>

            {isSmartMode ? (
              <>
                <Button type="submit" size="sm" disabled={smartSearch.isPending}>
                  <SparklesIcon className="mr-1.5 size-3.5" />
                  Search
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setIsSmartMode(false);
                    setSearchInput('');
                  }}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsSmartMode(true)}
                className="gap-1.5 text-xs"
              >
                <SparklesIcon className="size-3.5" />
                Smart search
              </Button>
            )}
          </form>

          {/* Smart search inferred filter chips */}
          {isSmartMode && smartSearch.data?.filters && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <p className="text-xs text-muted-foreground">AI inferred:</p>
              {Object.entries(smartSearch.data.filters).map(([k, v]) => (
                <Badge key={k} variant="secondary" className="text-xs">
                  {k}: {String(v)}
                </Badge>
              ))}
            </div>
          )}
          {isSmartMode && smartSearch.data?.semantic_query && (
            <p className="mt-1 text-xs text-muted-foreground">
              Query: <em>{smartSearch.data.semantic_query}</em>
            </p>
          )}
        </div>

        {/* Table area */}
        <div className="flex min-h-0 flex-1 flex-col overflow-auto p-4">
          <QueryBoundary
            isLoading={activeIsLoading}
            isEmpty={!activeIsLoading && !activeError && (activeData?.items.length ?? 0) === 0}
            error={activeError}
            emptyMessage="No contracts yet."
            emptyAction={
              <Button variant="outline" size="sm" onClick={() => router.push('/repository')}>
                Upload your first contract using the New Contract button above
              </Button>
            }
            onRetry={() => contractsQuery.refetch()}
          >
            {activeData && (
              <div className="flex flex-col gap-2">
                <DataTable<ContractRow>
                  columns={COLUMNS}
                  data={activeData.items}
                  total={activeData.total}
                  page={page}
                  pageSize={PAGE_SIZE}
                  onPageChange={setPage}
                  sortKey={sortKey || undefined}
                  sortDir={sortDir}
                  onSort={handleSort}
                  onRowClick={(row) => router.push(`/contracts/${row.id}`)}
                  getRowKey={(row) => row.id}
                  quickActions={(row) => (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 gap-1 px-2 text-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          router.push(`/contracts/${row.id}`);
                        }}
                      >
                        <ExternalLinkIcon className="size-3" />
                        Open
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 gap-1 px-2 text-xs"
                        disabled={runReview.isPending}
                        onClick={(e) => {
                          e.stopPropagation();
                          runReview.mutate(row.id);
                        }}
                      >
                        <PlayIcon className="size-3" />
                        Review
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 gap-1 px-2 text-xs"
                        onClick={(e) => toggleExpand(row.id, e)}
                      >
                        <ChevronDownIcon
                          className={cn(
                            'size-3 transition-transform',
                            expandedRowId === row.id && 'rotate-180'
                          )}
                        />
                        Versions
                      </Button>
                    </>
                  )}
                />

                {/* Version lineage expander */}
                {expandedRowId && activeData.items.some((r) => r.id === expandedRowId) && (
                  <VersionsPanel
                    contractId={expandedRowId}
                    onClose={() => setExpandedRowId(null)}
                  />
                )}
              </div>
            )}
          </QueryBoundary>
        </div>
      </div>
    </div>
  );
}
