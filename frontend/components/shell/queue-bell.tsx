'use client';

import { BellIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAlerts } from '@/lib/api/hooks';
import { cn } from '@/lib/utils';

export function QueueBell() {
  const { data: alerts } = useAlerts({ acknowledged: false });

  const count = alerts?.length ?? 0;

  return (
    <Button variant="ghost" size="icon" aria-label={`Alerts${count > 0 ? ` — ${count} unacknowledged` : ''}`}>
      <span className="relative inline-flex">
        <BellIcon className="size-4" />
        {count > 0 && (
          <span
            className={cn(
              'absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground'
            )}
          >
            {count > 99 ? '99+' : count}
          </span>
        )}
      </span>
    </Button>
  );
}
