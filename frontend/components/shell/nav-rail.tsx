'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import {
  HomeIcon,
  FolderIcon,
  ZapIcon,
  BookOpenIcon,
  PenToolIcon,
  BarChart2Icon,
  ClipboardListIcon,
  BuildingIcon,
  SettingsIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ScaleIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { label: 'Home', href: '/home', icon: HomeIcon },
  { label: 'Repository', href: '/repository', icon: FolderIcon },
  { label: 'Automations', href: '/automations', icon: ZapIcon },
  { label: 'Playbooks', href: '/playbooks', icon: BookOpenIcon },
  { label: 'Drafting', href: '/drafting', icon: PenToolIcon },
  { label: 'Analytics', href: '/analytics', icon: BarChart2Icon },
  { label: 'Obligations', href: '/obligations', icon: ClipboardListIcon },
  { label: 'Counterparties', href: '/counterparties', icon: BuildingIcon },
  { label: 'Settings', href: '/settings', icon: SettingsIcon },
];

export function NavRail() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <nav
      className={cn(
        'group relative flex h-full flex-col border-r border-border bg-sidebar transition-all duration-200',
        collapsed ? 'w-14' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className={cn('flex h-14 items-center border-b border-border px-3', collapsed ? 'justify-center' : 'gap-2')}>
        <ScaleIcon className="size-5 shrink-0 text-primary" />
        {!collapsed && (
          <span className="text-sm font-semibold text-foreground">Precedent</span>
        )}
      </div>

      {/* Nav items */}
      <div className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
          const isActive = pathname === href || (href !== '/home' && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex h-9 items-center rounded-lg px-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                collapsed ? 'justify-center' : 'gap-3'
              )}
              title={collapsed ? label : undefined}
            >
              <Icon className="size-4 shrink-0" />
              {!collapsed && <span>{label}</span>}
            </Link>
          );
        })}
      </div>

      {/* Collapse toggle */}
      <div className="border-t border-border p-2">
        <Button
          variant="ghost"
          size="icon"
          className="w-full"
          onClick={() => setCollapsed((v) => !v)}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {collapsed ? (
            <ChevronRightIcon className="size-4" />
          ) : (
            <ChevronLeftIcon className="size-4" />
          )}
        </Button>
      </div>
    </nav>
  );
}
