'use client';

import { Badge } from '@/components/ui/badge';
import {
  contractStatusTokens,
  redlineStatusTokens,
  alertTypeTokens,
} from '@/lib/tokens';
import type { ContractStatus, RedlineStatus, AlertType } from '@/lib/api/types';
import { cn } from '@/lib/utils';

type StatusValue = ContractStatus | RedlineStatus | AlertType;

interface StatusBadgeProps {
  type: 'contract' | 'redline' | 'alert';
  value: StatusValue;
  className?: string;
}

export function StatusBadge({ type, value, className }: StatusBadgeProps) {
  let token: { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' | 'ghost' };

  if (type === 'contract') {
    token = contractStatusTokens[value as ContractStatus];
  } else if (type === 'redline') {
    token = redlineStatusTokens[value as RedlineStatus];
  } else {
    token = alertTypeTokens[value as AlertType];
  }

  if (!token) return null;

  return (
    <Badge variant={token.variant} className={cn(className)}>
      {token.label}
    </Badge>
  );
}
