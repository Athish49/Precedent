'use client';

import { useState } from 'react';
import { UploadCloudIcon, FileTextIcon, GitBranchIcon } from 'lucide-react';
import { useContractVersions, useStoreVersion } from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { SlideOver } from '@/components/primitives/slide-over';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/components/workspace/workspace-context';
import type { VersionRelation, Version } from '@/lib/api/types';
import { cn } from '@/lib/utils';

// ─── Store version SlideOver ──────────────────────────────────────────────────

interface StoreVersionSlideOverProps {
  contractId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function StoreVersionSlideOver({ contractId, open, onOpenChange }: StoreVersionSlideOverProps) {
  const storeVersion = useStoreVersion();
  const [file, setFile] = useState<File | null>(null);
  const [relation, setRelation] = useState<VersionRelation>('amendment');

  const RELATIONS: VersionRelation[] = ['amendment', 'addendum', 'version'];

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && (f.name.endsWith('.pdf') || f.name.endsWith('.docx'))) setFile(f);
  }

  function handleSubmit() {
    if (!file) return;
    storeVersion.mutate(
      { contractId, file, relation },
      {
        onSuccess: () => {
          onOpenChange(false);
          setFile(null);
          setRelation('amendment');
          storeVersion.reset();
        },
      },
    );
  }

  return (
    <SlideOver open={open} onOpenChange={onOpenChange} title="Store version" description="Upload a new version of this contract.">
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
        {/* File drop zone */}
        <div
          role="button"
          tabIndex={0}
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => document.getElementById('version-file-input')?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ')
              document.getElementById('version-file-input')?.click();
          }}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-border p-8 text-center transition-colors hover:border-primary/50 hover:bg-muted/20',
            file && 'border-primary/40 bg-primary/5',
          )}
        >
          <input
            id="version-file-input"
            type="file"
            accept=".pdf,.docx"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) setFile(f);
            }}
          />
          {file ? (
            <>
              <FileTextIcon className="size-8 text-primary" />
              <p className="text-sm font-medium">{file.name}</p>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setFile(null); }}
                className="text-xs text-muted-foreground underline hover:text-foreground"
              >
                Remove
              </button>
            </>
          ) : (
            <>
              <UploadCloudIcon className="size-8 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Drop PDF or DOCX here</p>
                <p className="text-xs text-muted-foreground">or click to browse</p>
              </div>
            </>
          )}
        </div>

        {/* Relation selector */}
        <div className="space-y-1.5">
          <p className="text-sm font-medium">Relation</p>
          <div className="flex gap-2">
            {RELATIONS.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRelation(r)}
                className={cn(
                  'flex-1 rounded-md border px-3 py-2 text-sm font-medium capitalize transition-colors',
                  relation === r
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border hover:bg-muted/40',
                )}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-auto">
          <Button
            className="w-full"
            disabled={!file || storeVersion.isPending}
            onClick={handleSubmit}
          >
            {storeVersion.isPending ? 'Uploading…' : 'Store version'}
          </Button>
        </div>
      </div>
    </SlideOver>
  );
}

// ─── Version node ─────────────────────────────────────────────────────────────

interface VersionNodeProps {
  version: Version;
  parent?: Version;
  selected: boolean;
  onToggle: () => void;
}

function VersionNode({ version, parent, selected, onToggle }: VersionNodeProps) {
  const date = new Date(version.created_at).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  });

  return (
    <div className="flex items-start gap-2 rounded-md px-2 py-2 hover:bg-muted/30">
      <GitBranchIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold">v{version.version_number}</span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] capitalize text-muted-foreground">
            {version.relation}
          </span>
          <span className="text-[10px] text-muted-foreground">{date}</span>
        </div>
        {parent && (
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            ↳ from v{parent.version_number}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          'shrink-0 rounded px-2 py-0.5 text-[10px] font-medium transition-colors',
          selected
            ? 'bg-primary text-primary-foreground'
            : 'border border-border text-muted-foreground hover:border-primary hover:text-primary',
        )}
      >
        {selected ? 'Selected' : 'Select'}
      </button>
    </div>
  );
}

// ─── VersionsTab ──────────────────────────────────────────────────────────────

interface VersionsTabProps {
  contractId: string;
}

export function VersionsTab({ contractId }: VersionsTabProps) {
  const workspace = useWorkspace();
  const versionsQuery = useContractVersions(contractId);
  const [storeOpen, setStoreOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const versions = versionsQuery.data ?? [];

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((s) => s !== id);
      if (prev.length >= 2) return [...prev.slice(1), id]; // drop oldest, add new
      return [...prev, id];
    });
  }

  function handleCompare() {
    if (selectedIds.length !== 2) return;
    workspace.setCompareMode({ vA: selectedIds[0], vB: selectedIds[1] });
  }

  const versionMap = new Map(versions.map((v) => [v.id, v]));

  return (
    <div className="flex h-full flex-col">
      {/* Compare mode banner */}
      {workspace.compareMode && (
        <div className="flex shrink-0 items-center justify-between border-b border-border bg-amber-50 px-3 py-2 dark:bg-amber-950/20">
          <p className="text-xs font-medium text-amber-800 dark:text-amber-300">
            Comparing {workspace.compareMode.vA.slice(0, 8)} ↔ {workspace.compareMode.vB.slice(0, 8)}
          </p>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 text-xs"
            onClick={() => workspace.setCompareMode(null)}
          >
            Exit
          </Button>
        </div>
      )}

      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Version lineage
        </p>
        <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => setStoreOpen(true)}>
          Store version
        </Button>
      </div>

      {/* Version list */}
      <div className="min-h-0 flex-1 overflow-y-auto px-1 py-1">
        <QueryBoundary
          isLoading={versionsQuery.isLoading}
          error={versionsQuery.error ?? null}
          isEmpty={!versionsQuery.isLoading && versions.length === 0}
          emptyMessage="No versions stored yet. Upload a version to track changes."
        >
          <div className="space-y-0.5">
            {versions.map((v) => (
              <VersionNode
                key={v.id}
                version={v}
                parent={v.parent_version_id ? versionMap.get(v.parent_version_id) : undefined}
                selected={selectedIds.includes(v.id)}
                onToggle={() => toggleSelect(v.id)}
              />
            ))}
          </div>
        </QueryBoundary>
      </div>

      {/* Compare action */}
      {selectedIds.length === 2 && !workspace.compareMode && (
        <div className="shrink-0 border-t border-border p-3">
          <Button className="w-full" size="sm" onClick={handleCompare}>
            Compare selected versions
          </Button>
        </div>
      )}

      <StoreVersionSlideOver
        contractId={contractId}
        open={storeOpen}
        onOpenChange={setStoreOpen}
      />
    </div>
  );
}
