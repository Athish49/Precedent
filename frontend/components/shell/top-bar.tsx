'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { PlusIcon, SettingsIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { NewContractSlideOver } from '@/components/intake/new-contract-slide-over';
import { CommandBar } from './command-bar';
import { QueueBell } from './queue-bell';

const BREADCRUMB_MAP: Record<string, string> = {
  '/home': 'Home',
  '/repository': 'Repository',
  '/automations': 'Automations',
  '/playbooks': 'Playbooks',
  '/drafting': 'Drafting',
  '/analytics': 'Analytics',
  '/obligations': 'Obligations',
  '/counterparties': 'Counterparties',
  '/settings': 'Settings',
};

function useBreadcrumb(): string {
  const pathname = usePathname();
  for (const [prefix, label] of Object.entries(BREADCRUMB_MAP)) {
    if (pathname === prefix || pathname.startsWith(prefix + '/')) return label;
  }
  return '';
}

export function TopBar() {
  const breadcrumb = useBreadcrumb();
  const router = useRouter();
  const [intakeOpen, setIntakeOpen] = useState(false);

  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-background px-4">
        {/* Breadcrumb */}
        <div className="min-w-0 flex-1">
          {breadcrumb && (
            <span className="truncate text-sm font-medium text-foreground">{breadcrumb}</span>
          )}
        </div>

        {/* Command bar */}
        <CommandBar className="w-56" />

        {/* Right cluster */}
        <div className="flex items-center gap-1">
          <Button size="sm" className="gap-1.5" onClick={() => setIntakeOpen(true)}>
            <PlusIcon className="size-3.5" />
            <span className="hidden sm:inline">New Contract</span>
          </Button>

          <QueueBell />

          <Button
            variant="ghost"
            size="icon"
            aria-label="Settings"
            onClick={() => router.push('/settings')}
          >
            <SettingsIcon className="size-4" />
          </Button>
        </div>
      </header>

      {/* Always mounted so state survives dismiss while processing */}
      <NewContractSlideOver open={intakeOpen} onClose={() => setIntakeOpen(false)} />
    </>
  );
}
