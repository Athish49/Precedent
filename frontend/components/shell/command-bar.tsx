'use client';

import { useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SearchIcon, XIcon, FileTextIcon, NavigationIcon, SparklesIcon } from 'lucide-react';
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
} from '@/components/ui/command';
import { Badge } from '@/components/ui/badge';
import { useContractSearch, useSmartSearch } from '@/lib/api/hooks';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { label: 'Home', href: '/home' },
  { label: 'Repository', href: '/repository' },
  { label: 'Automations', href: '/automations' },
  { label: 'Playbooks', href: '/playbooks' },
  { label: 'Drafting Studio', href: '/drafting' },
  { label: 'Analytics', href: '/analytics' },
  { label: 'Obligations', href: '/obligations' },
  { label: 'Counterparties', href: '/counterparties' },
  { label: 'Settings', href: '/settings' },
];

interface CommandBarProps {
  className?: string;
}

export function CommandBar({ className }: CommandBarProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [interpreted, setInterpreted] = useState<Record<string, unknown> | null>(null);

  const { data: contractResults } = useContractSearch(query.length >= 2 ? query : '');
  const smartSearch = useSmartSearch();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleSelect = useCallback(
    (href: string) => {
      setOpen(false);
      setQuery('');
      router.push(href);
    },
    [router]
  );

  const handleSmartSearch = useCallback(async () => {
    if (!query.trim()) return;
    try {
      const result = await smartSearch.mutateAsync(query);
      if (result.filters) {
        setInterpreted(result.filters);
        setOpen(false);
        const params = new URLSearchParams();
        for (const [k, v] of Object.entries(result.filters)) {
          if (v != null) params.set(k, String(v));
        }
        router.push(`/repository?${params.toString()}`);
      }
    } catch {
      // silently fall through — keyword results remain visible
    }
  }, [query, smartSearch, router]);

  const removeFilter = useCallback((key: string) => {
    setInterpreted((prev) => {
      if (!prev) return null;
      const next = { ...prev };
      delete next[key];
      return Object.keys(next).length ? next : null;
    });
  }, []);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={cn(
          'flex h-8 items-center gap-2 rounded-lg border border-input bg-muted/50 px-3 text-sm text-muted-foreground transition-colors hover:bg-muted',
          className
        )}
      >
        <SearchIcon className="size-3.5 shrink-0" />
        <span className="hidden sm:inline">Search contracts…</span>
        <kbd className="ml-auto hidden rounded border border-border px-1.5 py-0.5 text-[10px] font-mono sm:inline">
          ⌘K
        </kbd>
      </button>

      {interpreted && (
        <div className="flex flex-wrap items-center gap-1">
          {Object.entries(interpreted).map(([key, val]) =>
            val != null ? (
              <Badge key={key} variant="secondary" className="gap-1">
                {key}: {String(val)}
                <button
                  onClick={() => removeFilter(key)}
                  className="ml-0.5 rounded hover:text-foreground"
                  aria-label={`Remove ${key} filter`}
                >
                  <XIcon className="size-2.5" />
                </button>
              </Badge>
            ) : null
          )}
        </div>
      )}

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder="Search contracts, pages…"
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>

          {contractResults && contractResults.items.length > 0 && (
            <CommandGroup heading="Contracts">
              {contractResults.items.slice(0, 6).map((contract) => (
                <CommandItem
                  key={contract.id}
                  value={`contract-${contract.id}`}
                  onSelect={() => handleSelect(`/contracts/${contract.id}`)}
                >
                  <FileTextIcon className="size-4 text-muted-foreground" />
                  <span>{contract.title}</span>
                  {contract.counterparty_display_name && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      {contract.counterparty_display_name}
                    </span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {query.length >= 2 && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Smart Search">
                <CommandItem
                  value={`smart-search-${query}`}
                  onSelect={handleSmartSearch}
                  disabled={smartSearch.isPending}
                >
                  <SparklesIcon className="size-4 text-muted-foreground" />
                  <span>Search everything for &ldquo;{query}&rdquo;</span>
                  {smartSearch.isPending && (
                    <span className="ml-auto text-xs text-muted-foreground">Searching…</span>
                  )}
                </CommandItem>
              </CommandGroup>
            </>
          )}

          <CommandSeparator />
          <CommandGroup heading="Navigation">
            {NAV_ITEMS.filter(
              (item) => !query || item.label.toLowerCase().includes(query.toLowerCase())
            ).map((item) => (
              <CommandItem
                key={item.href}
                value={`nav-${item.href}`}
                onSelect={() => handleSelect(item.href)}
              >
                <NavigationIcon className="size-4 text-muted-foreground" />
                {item.label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
