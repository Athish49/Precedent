'use client';

import { useState } from 'react';
import { Loader2Icon } from 'lucide-react';
import { useContract, useAnalysis, useSummarize } from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { ComplianceChip } from '@/components/primitives/compliance-chip';
import { SeverityIndicator } from '@/components/primitives/severity-indicator';
import { ProvenanceTag } from '@/components/primitives/provenance-tag';
import { HoverCard } from '@/components/primitives/hover-card';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/components/workspace/workspace-context';
import type { ContractDetail, ContractField, Risk } from '@/lib/api/types';

function fmt(date?: string | null): string {
  if (!date) return '—';
  return new Date(date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function fieldByKey(fields: ContractField[], key: string): ContractField | undefined {
  return fields.find((f) => f.field_key === key);
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

// Wraps a metadata value with its extraction evidence quote (`fields[]`),
// when there is one, as a hover card — reuses the existing `citation`
// variant rather than adding new UI.
function EvidenceValue({ display, field }: { display: React.ReactNode; field?: ContractField }) {
  if (!field?.quote) return <>{display}</>;
  return (
    <HoverCard
      trigger={<span className="cursor-help underline decoration-dotted decoration-muted-foreground/50">{display}</span>}
      content={{
        variant: 'citation',
        char_start: field.char_start ?? 0,
        char_end: field.char_end ?? 0,
        text: field.quote,
      }}
    />
  );
}

interface ContentProps {
  contractId: string;
  contract: ContractDetail;
  risk: Risk | undefined;
}

function OverviewContent({ contractId, contract, risk }: ContentProps) {
  const { setSelected } = useWorkspace();
  const summarize = useSummarize();
  const [summary, setSummary] = useState<string | null>(null);
  const metadata = contract.metadata;
  const fields = contract.fields;

  function handleSummarize() {
    summarize.mutate(contractId, {
      onSuccess: (data) => setSummary(data.summary),
    });
  }

  const liabilityCapStr =
    metadata.liability_cap_amount != null
      ? [
          metadata.currency ?? '',
          metadata.liability_cap_amount.toLocaleString(),
          metadata.liability_cap_basis ? `(${metadata.liability_cap_basis})` : '',
        ]
          .filter(Boolean)
          .join(' ')
      : undefined;

  const paymentTermsStr =
    metadata.payment_terms_days != null ? `${metadata.payment_terms_days} days` : undefined;

  // `auto_renewal` is a Tier 1 registry field but is not one of the
  // `contract_metadata` projection columns the backend currently surfaces
  // under `metadata` (see `_METADATA_FIELDS` in
  // `backend/app/api/routes/documents.py`) — read it from `fields[]`
  // instead, same as any other in-force field value.
  const autoRenewalField = fieldByKey(fields, 'auto_renewal');
  const autoRenewalValue =
    typeof autoRenewalField?.value === 'boolean' ? autoRenewalField.value : undefined;

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
      {contract.parties.length > 0 && (
        <section>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Parties</p>
          <ul className="space-y-0.5">
            {contract.parties.map((p) => (
              <li key={p.party_id} className="flex gap-1.5 text-xs">
                <span className="font-medium">{p.name}</span>
                <span className="text-muted-foreground">({p.role_label ?? p.role})</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Metadata grid */}
      <section>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Details</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
          <MetaField label="Effective date">
            <EvidenceValue display={fmt(metadata.effective_date)} field={fieldByKey(fields, 'effective_date')} />
          </MetaField>
          <MetaField label="Expiry date">
            <EvidenceValue display={fmt(metadata.expiry_date)} field={fieldByKey(fields, 'expiry_date')} />
            {metadata.expiry_is_derived && (
              <span className="ml-1 text-[10px] font-normal text-muted-foreground">(derived)</span>
            )}
          </MetaField>
          <MetaField label="Governing law">
            <EvidenceValue
              display={metadata.governing_law ?? '—'}
              field={fieldByKey(fields, 'governing_law')}
            />
          </MetaField>
          <MetaField label="Auto-renewal">
            {autoRenewalValue === undefined ? '—' : (
              <EvidenceValue
                display={
                  <span className={autoRenewalValue ? 'text-amber-600' : 'text-muted-foreground'}>
                    {autoRenewalValue ? 'Yes' : 'No'}
                  </span>
                }
                field={autoRenewalField}
              />
            )}
          </MetaField>
          <MetaField label="Termination notice">
            {metadata.termination_notice_days != null ? `${metadata.termination_notice_days} days` : '—'}
          </MetaField>
        </dl>
      </section>

      {/* Governed fields with ComplianceChip */}
      <section>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Governed Fields</p>
        <div className="flex flex-col gap-2">
          <ComplianceChip
            label="Payment terms"
            foundValue={paymentTermsStr ?? '—'}
            policyValue="Policy max"
            state={paymentTermsStr ? 'deviation' : 'missing'}
            onFocus={() => setSelected({ id: 'payment_terms_days', tabHint: 'analysis' })}
          />
          <ComplianceChip
            label="Liability cap"
            foundValue={liabilityCapStr ?? '—'}
            policyValue="Policy max"
            state={liabilityCapStr ? 'deviation' : 'missing'}
            onFocus={() => setSelected({ id: 'liability_cap_amount', tabHint: 'analysis' })}
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
            contract={contractQuery.data}
            risk={analysisQuery.data?.risk}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
