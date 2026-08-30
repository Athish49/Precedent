'use client';

import { useState } from 'react';
import { Loader2Icon } from 'lucide-react';
import { useFlags, useAnalysis, useRunAnalysis } from '@/lib/api/hooks';
import { FlagCard } from '@/components/primitives/flag-card';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/components/workspace/workspace-context';
import type { Flag, FlagType, Severity } from '@/lib/api/types';
import { cn } from '@/lib/utils';

const FLAG_TYPE_OPTIONS: { label: string; value: FlagType }[] = [
  { label: 'Missing', value: 'missing' },
  { label: 'Prohibited', value: 'prohibited' },
  { label: 'Deviation', value: 'deviation' },
  { label: 'High Risk', value: 'high_risk' },
  { label: 'Vague', value: 'vague' },
  { label: 'Inconsistent', value: 'inconsistent' },
];

const SEVERITY_OPTIONS: { label: string; value: Severity }[] = [
  { label: 'Low', value: 'low' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
];

function PillButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground'
      )}
    >
      {label}
    </button>
  );
}

function FlagGroup({ title, flags, onFlagCite, onFlagHover, onFlagHoverClear, onFlagAdd }: {
  title: string;
  flags: Flag[];
  onFlagCite: (flag: Flag) => void;
  onFlagHover: (flag: Flag) => void;
  onFlagHoverClear: () => void;
  onFlagAdd?: (flag: Flag) => void;
}) {
  if (flags.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title} <span className="font-normal">({flags.length})</span>
      </p>
      {flags.map((flag) => (
        <div key={flag.id} className="px-2">
          <FlagCard
            flag={flag}
            onCite={
              flag.char_start !== undefined && flag.char_end !== undefined
                ? (charStart, charEnd) => {
                    void charStart;
                    void charEnd;
                    onFlagCite(flag);
                  }
                : undefined
            }
            onAdd={onFlagAdd ? () => onFlagAdd(flag) : undefined}
            onHoverPreview={() => onFlagHover(flag)}
            onHoverClear={onFlagHoverClear}
          />
        </div>
      ))}
    </div>
  );
}

export function AnalysisTab({ contractId }: { contractId: string }) {
  const { setSelected, setHovered } = useWorkspace();
  const [activeFlagType, setActiveFlagType] = useState<FlagType | undefined>();
  const [activeSeverity, setActiveSeverity] = useState<Severity | undefined>();

  const flagsQuery = useFlags(contractId, {
    flag_type: activeFlagType,
    severity: activeSeverity,
  });
  const analysisQuery = useAnalysis(contractId);
  const runAnalysis = useRunAnalysis();

  function handleFlagCite(flag: Flag) {
    setSelected({
      id: flag.id,
      charStart: flag.char_start,
      charEnd: flag.char_end,
      tabHint: 'analysis',
    });
  }

  function handleFlagHover(flag: Flag) {
    setHovered(
      flag.char_start !== undefined && flag.char_end !== undefined
        ? { charStart: flag.char_start, charEnd: flag.char_end }
        : null
    );
  }

  const flags = flagsQuery.data ?? [];
  const missingFlags = flags.filter((f) => f.flag_type === 'missing');
  const highRiskFlags = flags.filter((f) => f.flag_type === 'high_risk');
  const otherFlags = flags.filter(
    (f) => f.flag_type !== 'missing' && f.flag_type !== 'high_risk'
  );

  const hasAnalysis = !!analysisQuery.data;
  const isFiltered = !!(activeFlagType || activeSeverity);
  const isEmpty = !flagsQuery.isLoading && !flagsQuery.error && flags.length === 0;

  return (
    <div className="flex h-full flex-col gap-0">
      {/* Controls */}
      <div className="shrink-0 space-y-2 border-b border-border px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-muted-foreground">Flag type</p>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-xs"
            disabled={runAnalysis.isPending}
            onClick={() => runAnalysis.mutate(contractId)}
          >
            {runAnalysis.isPending ? (
              <>
                <Loader2Icon className="mr-1 size-3 animate-spin" />
                Analyzing…
              </>
            ) : (
              'Run Analysis'
            )}
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <PillButton
            label="All"
            active={!activeFlagType}
            onClick={() => setActiveFlagType(undefined)}
          />
          {FLAG_TYPE_OPTIONS.map((opt) => (
            <PillButton
              key={opt.value}
              label={opt.label}
              active={activeFlagType === opt.value}
              onClick={() =>
                setActiveFlagType((prev) => (prev === opt.value ? undefined : opt.value))
              }
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <PillButton
            label="All"
            active={!activeSeverity}
            onClick={() => setActiveSeverity(undefined)}
          />
          {SEVERITY_OPTIONS.map((opt) => (
            <PillButton
              key={opt.value}
              label={opt.label}
              active={activeSeverity === opt.value}
              onClick={() =>
                setActiveSeverity((prev) => (prev === opt.value ? undefined : opt.value))
              }
            />
          ))}
        </div>
      </div>

      {/* Flag list */}
      <div className="min-h-0 flex-1 overflow-y-auto py-2">
        <QueryBoundary
          isLoading={flagsQuery.isLoading}
          error={flagsQuery.error ?? null}
          isEmpty={isEmpty}
          emptyMessage={
            !hasAnalysis
              ? 'Analysis not run. Click Run Analysis to start.'
              : isFiltered
                ? 'No flags match current filters.'
                : 'No flags found.'
          }
          onRetry={() => void flagsQuery.refetch()}
        >
          <div className="space-y-4">
            <FlagGroup
              title="Missing Clauses"
              flags={missingFlags}
              onFlagCite={handleFlagCite}
              onFlagHover={handleFlagHover}
              onFlagHoverClear={() => setHovered(null)}
              onFlagAdd={() => { /* T5 will handle missing-clause Add flow */ }}
            />
            <FlagGroup
              title="High Risk"
              flags={highRiskFlags}
              onFlagCite={handleFlagCite}
              onFlagHover={handleFlagHover}
              onFlagHoverClear={() => setHovered(null)}
            />
            <FlagGroup
              title="Flags"
              flags={otherFlags}
              onFlagCite={handleFlagCite}
              onFlagHover={handleFlagHover}
              onFlagHoverClear={() => setHovered(null)}
            />
          </div>
        </QueryBoundary>
      </div>
    </div>
  );
}
