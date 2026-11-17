'use client';

import { use, useState } from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import { useContract } from '@/lib/api/hooks';
import { StatusBadge } from '@/components/primitives/status-badge';
import { WorkspaceProvider } from '@/components/workspace/workspace-context';
import { ContractCanvas } from '@/components/workspace/contract-canvas';
import { InspectorShell } from '@/components/workspace/inspector-shell';
import { cn } from '@/lib/utils';

interface ContractHeaderProps {
  contractId: string;
}

function ContractHeader({ contractId }: ContractHeaderProps) {
  const { data: contract } = useContract(contractId);
  return (
    <div className="flex shrink-0 items-center gap-3 border-b border-border bg-background px-4 py-2">
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
        {contract?.title ?? 'Loading…'}
      </h1>
      {contract && (
        <StatusBadge type="contract" value={contract.status} />
      )}
      {contract?.contract_type && (
        <span className="shrink-0 text-xs text-muted-foreground">{contract.contract_type}</span>
      )}
    </div>
  );
}

interface WorkspaceLayoutProps {
  contractId: string;
}

function WorkspaceLayout({ contractId }: WorkspaceLayoutProps) {
  const [inspectorOpen, setInspectorOpen] = useState(true);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ContractHeader contractId={contractId} />

      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {/* Canvas — takes remaining width */}
        <div className={cn('flex-1 min-w-0 overflow-hidden transition-all duration-200')}>
          <ContractCanvas contractId={contractId} />
        </div>

        {/* Inspector toggle button — sits on the boundary */}
        <button
          type="button"
          onClick={() => setInspectorOpen((v) => !v)}
          aria-label={inspectorOpen ? 'Collapse inspector' : 'Expand inspector'}
          className="absolute right-0 top-1/2 z-20 flex -translate-y-1/2 translate-x-1/2 items-center justify-center size-5 rounded-full border border-border bg-background shadow-sm hover:bg-muted"
          style={{ right: inspectorOpen ? '20rem' : 0 }}
        >
          {inspectorOpen ? (
            <ChevronRightIcon className="size-3" />
          ) : (
            <ChevronLeftIcon className="size-3" />
          )}
        </button>

        {/* Inspector rail */}
        <div
          className={cn(
            'shrink-0 overflow-hidden border-l border-border transition-all duration-200',
            inspectorOpen ? 'w-80' : 'w-0'
          )}
        >
          <div className="h-full w-80">
            <InspectorShell contractId={contractId} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ContractPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <WorkspaceProvider>
      <WorkspaceLayout contractId={id} />
    </WorkspaceProvider>
  );
}
