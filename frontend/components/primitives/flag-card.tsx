'use client';

import { useState } from 'react';
import {
  FileMinus,
  Ban,
  ShieldAlert,
  Shield,
  HelpCircle,
  AlertTriangle,
  GitBranch,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SeverityIndicator } from './severity-indicator';
import { ProvenanceTag } from './provenance-tag';
import type { Flag, PlaybookRule } from '@/lib/api/types';
import { flagTypeTokens } from '@/lib/tokens';
import { cn } from '@/lib/utils';

const FLAG_ICONS: Record<string, LucideIcon> = {
  FileMinus,
  Ban,
  ShieldAlert,
  Shield,
  HelpCircle,
  AlertTriangle,
  GitBranch,
};

interface FlagCardProps {
  flag: Flag;
  rule?: PlaybookRule;
  onCite?: (charStart: number, charEnd: number) => void;
  onAdd?: () => void;
  onHoverPreview?: () => void;
  onHoverClear?: () => void;
  className?: string;
}

export function FlagCard({
  flag,
  rule,
  onCite,
  onAdd,
  onHoverPreview,
  onHoverClear,
  className,
}: FlagCardProps) {
  const [expanded, setExpanded] = useState(false);
  const token = flagTypeTokens[flag.flag_type];
  const Icon: LucideIcon = FLAG_ICONS[token.icon] ?? Shield;
  const isMissing = flag.flag_type === 'missing';
  const hasOffsets = flag.char_start !== undefined && flag.char_end !== undefined;

  const detailEntries = Object.entries(flag.detail).filter(
    ([, v]) => typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
  );

  return (
    <div
      className={cn('group rounded-md border border-border bg-card text-card-foreground', className)}
      onMouseEnter={onHoverPreview}
      onMouseLeave={onHoverClear}
    >
      {/* Compact header */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left transition-colors hover:bg-muted/40"
      >
        <Icon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate text-sm font-medium">{token.label}</span>
        <SeverityIndicator severity={flag.severity} />
        {flag.source === 'llm' && <ProvenanceTag source="llm" />}
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="space-y-2 border-t border-border px-3 py-2">
          {detailEntries.length > 0 && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              {detailEntries.map(([k, v]) => (
                <span key={k} className="contents">
                  <dt className="capitalize text-muted-foreground">{k.replace(/_/g, ' ')}</dt>
                  <dd className="text-foreground">{String(v)}</dd>
                </span>
              ))}
            </dl>
          )}

          {rule && (
            <div className="text-xs text-muted-foreground">
              Rule:{' '}
              <span className="font-medium text-foreground">{rule.clause_type}</span>
            </div>
          )}

          <div className="flex gap-2 pt-1">
            {isMissing ? (
              <Button
                size="sm"
                variant="outline"
                onClick={onAdd}
                className="h-6 px-2 text-xs"
              >
                Add
              </Button>
            ) : hasOffsets ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onCite?.(flag.char_start!, flag.char_end!)}
                className="h-6 px-2 text-xs"
              >
                Cite
              </Button>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
