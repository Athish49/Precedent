'use client';

import { XIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// ─── Facet type definitions ────────────────────────────────────────────────────

export interface SelectFacetOption {
  label: string;
  value: string;
  count?: number;
}

export interface SelectFacetGroup {
  type: 'select';
  key: string;
  label: string;
  options: SelectFacetOption[];
  multiSelect?: boolean;
}

export interface RangeFacetGroup {
  type: 'range';
  key: string;
  label: string;
  min?: number;
  max?: number;
  unit?: string;
}

export type FacetGroup = SelectFacetGroup | RangeFacetGroup;

export type FilterValue = string[] | [number, number];
export type FilterState = Record<string, FilterValue | undefined>;

// ─── Chip bar ─────────────────────────────────────────────────────────────────

interface ActiveChipsProps {
  facets: FacetGroup[];
  value: FilterState;
  onChange: (state: FilterState) => void;
}

function ActiveChips({ facets, value, onChange }: ActiveChipsProps) {
  const chips: { label: string; remove: () => void }[] = [];

  for (const facet of facets) {
    const val = value[facet.key];
    if (!val) continue;

    if (facet.type === 'select' && Array.isArray(val)) {
      const selected = val as string[];
      for (const v of selected) {
        const option = facet.options.find((o) => o.value === v);
        chips.push({
          label: `${facet.label}: ${option?.label ?? v}`,
          remove: () => {
            const next = selected.filter((s) => s !== v);
            onChange({ ...value, [facet.key]: next.length ? next : undefined });
          },
        });
      }
    }

    if (facet.type === 'range' && Array.isArray(val) && val.length === 2) {
      const [lo, hi] = val as [number, number];
      chips.push({
        label: `${facet.label}: ${lo}–${hi}${facet.unit ? ` ${facet.unit}` : ''}`,
        remove: () => onChange({ ...value, [facet.key]: undefined }),
      });
    }
  }

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 border-b border-border px-3 py-2">
      {chips.map((chip) => (
        <Badge
          key={chip.label}
          variant="secondary"
          className="gap-1 pr-1 text-xs font-normal"
        >
          {chip.label}
          <button
            type="button"
            onClick={chip.remove}
            aria-label={`Remove filter: ${chip.label}`}
            className="rounded-sm opacity-60 hover:opacity-100"
          >
            <XIcon className="size-3" />
          </button>
        </Badge>
      ))}
      <button
        type="button"
        onClick={() => onChange({})}
        className="text-xs text-muted-foreground underline-offset-2 hover:underline"
      >
        Clear all
      </button>
    </div>
  );
}

// ─── Select facet ─────────────────────────────────────────────────────────────

interface SelectFacetProps {
  facet: SelectFacetGroup;
  selected: string[];
  onChange: (next: string[]) => void;
}

function SelectFacet({ facet, selected, onChange }: SelectFacetProps) {
  function toggle(val: string) {
    if (facet.multiSelect === false) {
      onChange(selected.includes(val) ? [] : [val]);
    } else {
      onChange(
        selected.includes(val) ? selected.filter((s) => s !== val) : [...selected, val]
      );
    }
  }

  return (
    <div className="space-y-1">
      {facet.options.map((opt) => {
        const active = selected.includes(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => toggle(opt.value)}
            className={cn(
              'flex w-full items-center justify-between rounded-sm px-2 py-1 text-xs transition-colors',
              active
                ? 'bg-primary/10 font-medium text-primary'
                : 'text-foreground hover:bg-muted/50'
            )}
          >
            <span>{opt.label}</span>
            {opt.count !== undefined && (
              <span className="text-muted-foreground">{opt.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ─── Range facet ──────────────────────────────────────────────────────────────

interface RangeFacetProps {
  facet: RangeFacetGroup;
  currentValue: [number, number] | undefined;
  onChange: (next: [number, number] | undefined) => void;
}

function RangeFacet({ facet, currentValue, onChange }: RangeFacetProps) {
  const loStr = currentValue ? String(currentValue[0]) : '';
  const hiStr = currentValue ? String(currentValue[1]) : '';

  function handleLo(raw: string) {
    const lo = parseFloat(raw);
    const hi = currentValue?.[1] ?? facet.max ?? lo;
    onChange(isNaN(lo) ? undefined : [lo, hi]);
  }

  function handleHi(raw: string) {
    const hi = parseFloat(raw);
    const lo = currentValue?.[0] ?? facet.min ?? 0;
    onChange(isNaN(hi) ? undefined : [lo, hi]);
  }

  const inputCls =
    'w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:ring-1 focus:ring-primary/50';

  return (
    <div className="flex items-center gap-1.5">
      <input
        type="number"
        placeholder={facet.min !== undefined ? String(facet.min) : 'Min'}
        defaultValue={loStr}
        onBlur={(e) => handleLo(e.target.value)}
        className={inputCls}
        aria-label={`${facet.label} minimum`}
      />
      <span className="text-xs text-muted-foreground">–</span>
      <input
        type="number"
        placeholder={facet.max !== undefined ? String(facet.max) : 'Max'}
        defaultValue={hiStr}
        onBlur={(e) => handleHi(e.target.value)}
        className={inputCls}
        aria-label={`${facet.label} maximum`}
      />
      {facet.unit && <span className="shrink-0 text-xs text-muted-foreground">{facet.unit}</span>}
    </div>
  );
}

// ─── FilterRail ───────────────────────────────────────────────────────────────

interface FilterRailProps {
  facets: FacetGroup[];
  value: FilterState;
  onChange: (state: FilterState) => void;
  className?: string;
}

export function FilterRail({ facets, value, onChange, className }: FilterRailProps) {
  function updateFacet(key: string, next: FilterValue | undefined) {
    onChange({ ...value, [key]: next });
  }

  return (
    <aside className={cn('flex flex-col', className)}>
      {/* Active filter chips */}
      <ActiveChips facets={facets} value={value} onChange={onChange} />

      {/* Facet groups */}
      <div className="flex flex-col divide-y divide-border overflow-y-auto">
        {facets.map((facet) => (
          <div key={facet.key} className="px-3 py-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {facet.label}
            </p>

            {facet.type === 'select' && (
              <SelectFacet
                facet={facet}
                selected={(value[facet.key] as string[] | undefined) ?? []}
                onChange={(next) => updateFacet(facet.key, next.length ? next : undefined)}
              />
            )}

            {facet.type === 'range' && (
              <RangeFacet
                facet={facet}
                currentValue={value[facet.key] as [number, number] | undefined}
                onChange={(next) => updateFacet(facet.key, next)}
              />
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
