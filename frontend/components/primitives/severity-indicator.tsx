'use client';

import { Badge } from '@/components/ui/badge';
import { severityTokens } from '@/lib/tokens';
import type { Severity } from '@/lib/api/types';
import { cn } from '@/lib/utils';

interface SeverityIndicatorProps {
  severity: Severity;
  className?: string;
}

export function SeverityIndicator({ severity, className }: SeverityIndicatorProps) {
  const token = severityTokens[severity];
  if (!token) return null;

  return (
    <Badge variant={token.variant} className={cn(className)}>
      {token.label}
    </Badge>
  );
}
