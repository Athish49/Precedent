'use client';

import { useState } from 'react';
import { Loader2Icon } from 'lucide-react';
import { useContract, useAnalysis, useSummarize } from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { ComplianceChip } from '@/components/primitives/compliance-chip';
import { SeverityIndicator } from '@/components/primitives/severity-indicator';
import { ProvenanceTag } from '@/components/primitives/provenance-tag';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/components/workspace/workspace-context';
import type { ContractMetadata, Risk } from '@/lib/api/types';

function fmt(date?: string): string {
  if (!date) return '—';
  return new Date(date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

interface MetaFieldProps { label: string; children: React.ReactNode }
function MetaField({ label, children }: MetaFieldProps) {
  return (
    <>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xs font-medium">{children}</dd>
    </>
  );
}

interface ContentProps {
  contractId: string;
  metadata: ContractMetadata;
  risk: Risk | undefined;
}

function OverviewContent({ contractId, metadata, risk }: ContentProps) {
  const { setSelected } = useWorkspace();
  const summarize = useSummarize();
  const [summary, setSummary] = useState<string | null>(null);

  function handleSummarize() {
    summarize.mutate(contractId, {
      onSuccess: (data) => setSummary(data.summary),
    });
  }

  const liabilityCapStr = metadata.liability_cap
    ? `${metadata.liability_cap.currency} ${metadata.liability_cap.value.toLocaleString()}`
    : undefined;

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Risk header */}
      {risk && (
        <div className="flex items-center gap-2">
          <SeverityIndicator severity={risk.max_clause_severity} />
          <span className="text-xs text-muted-foreground">Risk: {risk.score}/100</span>
        </div>
      )}

      {/* Summary */}
      <section>
        <div className="mb-1.5 flex items-center gap-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Summary</p>
          {summary && <ProvenanceTag source="llm" />}
        </div>
        {summary ? (
          <p className="text-xs leading-relaxed text-foreground">{summary}</p>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={summarize.isPending}
            onClick={handleSummarize}
          >
            {summarize.isPending && <Loader2Icon className="mr-1.5 size-3 animate-spin" />}
            Generate
          </Button>
        )}
      </section>

      {/* Parties */}
      {metadata.parties.length > 0 && (
        <section>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Parties</p>
          <ul className="space-y-0.5">
            {metadata.parties.map((p, i) => (
              <li key={i} className="flex gap-1.5 text-xs">
                <span className="font-medium">{p.name}</span>
                <span className="text-muted-foreground">({p.role})</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Metadata grid */}
      <section>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Details</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
          <MetaField label="Effective date">{fmt(metadata.effective_date)}</MetaField>
          <MetaField label="Expiry date">{fmt(metadata.expiry_date)}</MetaField>
          <MetaField label="Governing law">{metadata.governing_law ?? '—'}</MetaField>
          <MetaField label="Auto-renewal">
            {metadata.auto_renewal === undefined ? '—' : (
              <span className={metadata.auto_renewal ? 'text-amber-600' : 'text-muted-foreground'}>
                {metadata.auto_renewal ? 'Yes' : 'No'}
              </span>
            )}
          </MetaField>
          <MetaField label="Notice period">
            {metadata.notice_period_days !== undefined ? `${metadata.notice_period_days} days` : '—'}
          </MetaField>
        </dl>
      </section>

      {/* Governed fields with ComplianceChip */}
      <section>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Governed Fields</p>
        <div className="flex flex-col gap-2">
          <ComplianceChip
            label="Payment terms"
            foundValue={metadata.payment_terms ?? '—'}
            policyValue="Policy max"
            state={metadata.payment_terms ? 'deviation' : 'missing'}
            onFocus={() => setSelected({ id: 'payment_terms', tabHint: 'analysis' })}
          />
          <ComplianceChip
            label="Liability cap"
            foundValue={liabilityCapStr ?? '—'}
            policyValue="Policy max"
            state={metadata.liability_cap ? 'deviation' : 'missing'}
            onFocus={() => setSelected({ id: 'liability_cap', tabHint: 'analysis' })}
          />
        </div>
      </section>
    </div>
  );
}

export function OverviewTab({ contractId }: { contractId: string }) {
  const contractQuery = useContract(contractId);
  const analysisQuery = useAnalysis(contractId);

  return (
    <div className="h-full overflow-y-auto">
      <QueryBoundary
        isLoading={contractQuery.isLoading}
        error={contractQuery.error ?? null}
        isEmpty={!contractQuery.data}
        emptyMessage="Contract not found."
        onRetry={() => void contractQuery.refetch()}
      >
        {contractQuery.data && (
          <OverviewContent
            contractId={contractId}
            metadata={contractQuery.data.metadata}
            risk={analysisQuery.data?.risk}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
