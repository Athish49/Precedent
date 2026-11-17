'use client';

import { HoverCard } from './hover-card';
import type { PlaybookRule } from '@/lib/api/types';
import { cn } from '@/lib/utils';

type ComplianceState = 'compliant' | 'deviation' | 'missing';

interface ComplianceChipProps {
  label: string;
  foundValue: string;
  policyValue: string;
  state: ComplianceState;
  rule?: PlaybookRule;
  onFocus?: () => void;
  className?: string;
}

const STATE_STYLES: Record<ComplianceState, string> = {
  compliant: 'border-transparent bg-muted',
  deviation: 'border-destructive/40 bg-destructive/5',
  missing: 'border-muted-foreground/30 bg-muted text-muted-foreground',
};

const INDICATOR_STYLES: Record<ComplianceState, string> = {
  compliant: 'bg-green-500',
  deviation: 'bg-destructive',
  missing: 'bg-muted-foreground/50',
};

type ChipInnerProps = Omit<ComplianceChipProps, 'rule'>;

function ChipInner({ label, foundValue, policyValue, state, onFocus, className }: ChipInnerProps) {
  return (
    <button
      type="button"
      onClick={onFocus}
      className={cn(
        'inline-flex items-center gap-2 rounded border px-2 py-1 text-xs font-medium transition-opacity hover:opacity-80',
        STATE_STYLES[state],
        className
      )}
    >
      <span className={cn('size-1.5 shrink-0 rounded-full', INDICATOR_STYLES[state])} />
      <span className="text-muted-foreground">{label}:</span>
      {state === 'missing' ? (
        <span className="italic">missing</span>
      ) : (
        <>
          <span>{foundValue}</span>
          {state === 'deviation' && (
            <>
              <span className="text-muted-foreground/50">vs</span>
              <span className="text-muted-foreground line-through">{policyValue}</span>
            </>
          )}
        </>
      )}
    </button>
  );
}

export function ComplianceChip({
  label,
  foundValue,
  policyValue,
  state,
  rule,
  onFocus,
  className,
}: ComplianceChipProps) {
  const chip = (
    <ChipInner
      label={label}
      foundValue={foundValue}
      policyValue={policyValue}
      state={state}
      onFocus={onFocus}
      className={className}
    />
  );

  if (!rule) return chip;

  return (
    <HoverCard trigger={chip} content={{ variant: 'rule', rule }} side="top" />
  );
}
