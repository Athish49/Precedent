'use client';

import { provenanceTokens } from '@/lib/tokens';
import type { ProvenanceSource } from '@/lib/api/types';
import { cn } from '@/lib/utils';

interface ProvenanceTagProps {
  source: ProvenanceSource;
  className?: string;
}

export function ProvenanceTag({ source, className }: ProvenanceTagProps) {
  const token = provenanceTokens[source];
  if (!token) return null;

  const isAi = source === 'llm' || source === 'ai';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium',
        isAi
          ? 'bg-accent text-accent-foreground'
          : 'bg-muted text-muted-foreground',
        className
      )}
    >
      {token.label}
    </span>
  );
}
