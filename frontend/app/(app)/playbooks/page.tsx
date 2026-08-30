'use client';

import { useState } from 'react';
import { PlusIcon, Trash2Icon, PencilIcon, ChevronDownIcon, ChevronUpIcon, XIcon } from 'lucide-react';
import {
  usePlaybooks,
  usePlaybook,
  usePlaybookRules,
  useResolvedRules,
  useCreatePlaybook,
  useUpdatePlaybook,
  useDeletePlaybook,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
  useBootstrapPlaybooks,
} from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { DataTable } from '@/components/primitives/data-table';
import type { ColumnDef } from '@/components/primitives/data-table';
import { SlideOver } from '@/components/primitives/slide-over';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type {
  Playbook,
  PlaybookRule,
  PracticeArea,
  CreatePlaybookBody,
  CreateRuleBody,
} from '@/lib/api/types';

// ─── Tag input ────────────────────────────────────────────────────────────────

function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState('');

  function add() {
    const trimmed = draft.trim();
    if (trimmed && !value.includes(trimmed)) onChange([...value, trimmed]);
    setDraft('');
  }

  return (
    <div className="flex flex-wrap gap-1 rounded border border-border bg-background p-1.5">
      {value.map((tag) => (
        <span key={tag} className="flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs">
          {tag}
          <button type="button" onClick={() => onChange(value.filter((t) => t !== tag))}>
            <XIcon className="size-3" />
          </button>
        </span>
      ))}
      <input
        className="min-w-[8rem] flex-1 bg-transparent text-xs outline-none"
        placeholder={placeholder ?? 'Type + Enter'}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            add();
          }
        }}
      />
    </div>
  );
}

// ─── Rule editor SlideOver ────────────────────────────────────────────────────

interface RuleEditorProps {
  open: boolean;
  onClose: () => void;
  playbookId: string;
  rule?: PlaybookRule;
}

function RuleEditor({ open, onClose, playbookId, rule }: RuleEditorProps) {
  const isEdit = !!rule;
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();

  const [clauseType, setClauseType] = useState(rule?.clause_type ?? '');
  const [preferredLanguage, setPreferredLanguage] = useState(rule?.preferred_language ?? '');
  const [acceptableVariations, setAcceptableVariations] = useState<string[]>(rule?.acceptable_variations ?? []);
  const [prohibitedTerms, setProhibitedTerms] = useState<string[]>(rule?.prohibited_terms ?? []);
  const [fallbackLanguage, setFallbackLanguage] = useState(rule?.fallback_language ?? '');
  const [required, setRequired] = useState(rule?.required ?? false);
  const [riskWeight, setRiskWeight] = useState(rule?.risk_weight ?? 0.5);
  const [escalationThreshold, setEscalationThreshold] = useState<string>(
    rule?.escalation_threshold !== undefined ? String(rule.escalation_threshold) : ''
  );

  const isPending = createRule.isPending || updateRule.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: CreateRuleBody = {
      clause_type: clauseType,
      preferred_language: preferredLanguage,
      acceptable_variations: acceptableVariations,
      prohibited_terms: prohibitedTerms,
      fallback_language: fallbackLanguage || undefined,
      required,
      risk_weight: riskWeight,
      escalation_threshold: escalationThreshold ? parseFloat(escalationThreshold) : undefined,
    };
    if (isEdit && rule) {
      updateRule.mutate({ ruleId: rule.id, playbookId, ...body }, { onSuccess: onClose });
    } else {
      createRule.mutate({ playbookId, ...body }, { onSuccess: onClose });
    }
  }

  const inputCls = 'w-full rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50';
  const labelCls = 'block text-xs font-medium text-muted-foreground mb-1';

  return (
    <SlideOver
      open={open}
      onOpenChange={(o) => { if (!o) onClose(); }}
      title={isEdit ? 'Edit Rule' : 'Add Rule'}
      description="Define how this clause type should be governed."
    >
      <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
        <div>
          <label className={labelCls}>Clause type *</label>
          <input required value={clauseType} onChange={(e) => setClauseType(e.target.value)} className={inputCls} placeholder="e.g. indemnification" />
        </div>
        <div>
          <label className={labelCls}>Preferred language *</label>
          <textarea required rows={4} value={preferredLanguage} onChange={(e) => setPreferredLanguage(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Acceptable variations</label>
          <TagInput value={acceptableVariations} onChange={setAcceptableVariations} placeholder="Type + Enter to add" />
        </div>
        <div>
          <label className={labelCls}>Prohibited terms</label>
          <TagInput value={prohibitedTerms} onChange={setProhibitedTerms} placeholder="Type + Enter to add" />
        </div>
        <div>
          <label className={labelCls}>Fallback language</label>
          <textarea rows={2} value={fallbackLanguage} onChange={(e) => setFallbackLanguage(e.target.value)} className={inputCls} placeholder="Optional" />
        </div>
        <div className="flex items-center gap-2">
          <input type="checkbox" id="rule-required" checked={required} onChange={(e) => setRequired(e.target.checked)} className="size-4" />
          <label htmlFor="rule-required" className="text-sm">Required clause</label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Risk weight (0–1)</label>
            <input type="number" min={0} max={1} step={0.1} value={riskWeight} onChange={(e) => setRiskWeight(parseFloat(e.target.value))} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Escalation threshold</label>
            <input type="number" min={0} max={1} step={0.1} value={escalationThreshold} onChange={(e) => setEscalationThreshold(e.target.value)} className={inputCls} placeholder="Optional" />
          </div>
        </div>
        <div className="mt-auto">
          <Button type="submit" className="w-full" disabled={isPending}>
            {isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add rule'}
          </Button>
        </div>
      </form>
    </SlideOver>
  );
}

// ─── Create playbook SlideOver ────────────────────────────────────────────────

const PRACTICE_AREAS: PracticeArea[] = ['hipaa', 'gdpr', 'saas_msa', 'nda', 'dpa'];

function CreatePlaybookSlideOver({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createPlaybook = useCreatePlaybook();
  const [name, setName] = useState('');
  const [practiceArea, setPracticeArea] = useState<PracticeArea>('nda');
  const [precedence, setPrecedence] = useState(10);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: CreatePlaybookBody = { name, practice_area: practiceArea, precedence };
    createPlaybook.mutate(body, { onSuccess: onClose });
  }

  const inputCls = 'w-full rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50';
  const labelCls = 'block text-xs font-medium text-muted-foreground mb-1';

  return (
    <SlideOver open={open} onOpenChange={(o) => { if (!o) onClose(); }} title="New Playbook">
      <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-4 px-4 py-4">
        <div>
          <label className={labelCls}>Name *</label>
          <input required value={name} onChange={(e) => setName(e.target.value)} className={inputCls} placeholder="e.g. GDPR Data Processing" />
        </div>
        <div>
          <label className={labelCls}>Practice area</label>
          <select value={practiceArea} onChange={(e) => setPracticeArea(e.target.value as PracticeArea)} className={inputCls}>
            {PRACTICE_AREAS.map((a) => <option key={a} value={a}>{a.toUpperCase()}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Precedence</label>
          <input type="number" value={precedence} onChange={(e) => setPrecedence(parseInt(e.target.value))} className={inputCls} min={1} />
        </div>
        <div className="mt-auto">
          <Button type="submit" className="w-full" disabled={createPlaybook.isPending}>
            {createPlaybook.isPending ? 'Creating…' : 'Create playbook'}
          </Button>
        </div>
      </form>
    </SlideOver>
  );
}

// ─── Detail panel ─────────────────────────────────────────────────────────────

function PlaybookDetail({ playbookId }: { playbookId: string }) {
  const playbookQuery = usePlaybook(playbookId);
  const rulesQuery = usePlaybookRules(playbookId);
  const updatePlaybook = useUpdatePlaybook();
  const deleteRule = useDeleteRule();
  const bootstrap = useBootstrapPlaybooks();

  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [ruleEditorOpen, setRuleEditorOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<PlaybookRule | undefined>();
  const [resolveOpen, setResolveOpen] = useState(false);
  const [contractType, setContractType] = useState('');
  const [bootstrapOpen, setBootstrapOpen] = useState(false);
  const [selectedCorpus, setSelectedCorpus] = useState<string[]>([]);
  const [bootstrapMessage, setBootstrapMessage] = useState('');

  const resolvedQuery = useResolvedRules(contractType);
  const CORPUS_OPTIONS = ['nda', 'msa', 'sow', 'employment', 'gdpr_dpa'];

  const ruleColumns: ColumnDef<PlaybookRule>[] = [
    { key: 'clause_type', header: 'Clause type', cell: (r) => r.clause_type, sortable: true },
    {
      key: 'preferred_language',
      header: 'Preferred language',
      cell: (r) => (
        <span className="block max-w-[200px] truncate text-xs text-muted-foreground">
          {r.preferred_language}
        </span>
      ),
    },
    {
      key: 'required',
      header: 'Required',
      cell: (r) => r.required ? <Badge variant="default">Required</Badge> : <span className="text-muted-foreground">—</span>,
    },
    { key: 'risk_weight', header: 'Risk weight', cell: (r) => r.risk_weight.toFixed(1) },
    {
      key: 'row_actions',
      header: '',
      width: '80px',
      cell: (r) => (
        <div className="flex gap-1">
          <button type="button" onClick={(e) => { e.stopPropagation(); setEditingRule(r); setRuleEditorOpen(true); }} className="rounded p-1 hover:bg-muted" aria-label="Edit">
            <PencilIcon className="size-3" />
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); if (window.confirm('Delete this rule?')) deleteRule.mutate({ ruleId: r.id, playbookId }); }}
            className="rounded p-1 text-destructive hover:bg-destructive/10"
            aria-label="Delete"
          >
            <Trash2Icon className="size-3" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <QueryBoundary isLoading={playbookQuery.isLoading} error={playbookQuery.error ?? null} isEmpty={!playbookQuery.data} emptyMessage="Playbook not found.">
      {playbookQuery.data && (
        <div className="flex flex-col gap-6 p-6">
          {/* Header */}
          <div>
            {editingName ? (
              <div className="flex items-center gap-2">
                <input autoFocus value={nameInput} onChange={(e) => setNameInput(e.target.value)} className="rounded border border-border px-2 py-1 text-lg font-semibold outline-none focus:ring-1 focus:ring-primary/50" />
                <Button size="sm" onClick={() => { updatePlaybook.mutate({ id: playbookId, name: nameInput }); setEditingName(false); }}>Save</Button>
                <Button size="sm" variant="ghost" onClick={() => setEditingName(false)}>Cancel</Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">{playbookQuery.data.name}</h2>
                <button type="button" onClick={() => { setNameInput(playbookQuery.data.name); setEditingName(true); }} className="rounded p-1 text-muted-foreground hover:bg-muted">
                  <PencilIcon className="size-3.5" />
                </button>
              </div>
            )}
            <div className="mt-1 flex items-center gap-2">
              <Badge variant="secondary">{playbookQuery.data.practice_area.toUpperCase()}</Badge>
              <span className="text-xs text-muted-foreground">Precedence: {playbookQuery.data.precedence}</span>
            </div>
          </div>

          {/* Rules */}
          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold">Rules</p>
              <Button size="sm" onClick={() => { setEditingRule(undefined); setRuleEditorOpen(true); }}>
                <PlusIcon className="mr-1 size-3.5" /> Add Rule
              </Button>
            </div>
            <QueryBoundary
              isLoading={rulesQuery.isLoading}
              error={rulesQuery.error ?? null}
              isEmpty={rulesQuery.data?.length === 0}
              emptyMessage="No rules yet."
              emptyAction={<Button size="sm" onClick={() => { setEditingRule(undefined); setRuleEditorOpen(true); }}>Add first rule</Button>}
            >
              <DataTable<PlaybookRule>
                columns={ruleColumns}
                data={rulesQuery.data ?? []}
                total={rulesQuery.data?.length ?? 0}
                page={1}
                pageSize={rulesQuery.data?.length ?? 50}
                onPageChange={() => {}}
                getRowKey={(r) => r.id}
              />
            </QueryBoundary>
          </div>

          {/* Resolve preview */}
          <div className="rounded-lg border border-border">
            <button type="button" onClick={() => setResolveOpen((v) => !v)} className="flex w-full items-center justify-between px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:bg-muted/30">
              Resolve preview
              {resolveOpen ? <ChevronUpIcon className="size-4" /> : <ChevronDownIcon className="size-4" />}
            </button>
            {resolveOpen && (
              <div className="border-t border-border p-4">
                <input value={contractType} onChange={(e) => setContractType(e.target.value)} placeholder="Contract type (e.g. nda)" className="mb-3 w-full rounded border border-border px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50" />
                {contractType && (
                  <QueryBoundary isLoading={resolvedQuery.isLoading} error={resolvedQuery.error ?? null} isEmpty={resolvedQuery.data?.length === 0} emptyMessage="No resolved rules.">
                    <table className="w-full text-xs">
                      <thead><tr className="border-b border-border text-left text-muted-foreground"><th className="py-1 pr-3">Clause type</th><th className="py-1 pr-3">Source playbook</th><th className="py-1 pr-3">Required</th><th className="py-1">Risk weight</th></tr></thead>
                      <tbody>
                        {resolvedQuery.data?.map((r) => (
                          <tr key={r.id} className="border-b border-border/50">
                            <td className="py-1.5 pr-3 font-medium">{r.clause_type}</td>
                            <td className="py-1.5 pr-3"><Badge variant="outline" className="text-[10px]">{r.source_playbook_name}</Badge></td>
                            <td className="py-1.5 pr-3">{r.required ? 'Yes' : '—'}</td>
                            <td className="py-1.5">{r.risk_weight.toFixed(1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </QueryBoundary>
                )}
              </div>
            )}
          </div>

          {/* Bootstrap */}
          <div className="rounded-lg border border-border">
            <button type="button" onClick={() => setBootstrapOpen((v) => !v)} className="flex w-full items-center justify-between px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:bg-muted/30">
              Bootstrap playbooks
              {bootstrapOpen ? <ChevronUpIcon className="size-4" /> : <ChevronDownIcon className="size-4" />}
            </button>
            {bootstrapOpen && (
              <div className="border-t border-border p-4">
                <div className="mb-4 flex flex-wrap gap-3">
                  {CORPUS_OPTIONS.map((c) => (
                    <label key={c} className="flex items-center gap-1.5 text-sm">
                      <input type="checkbox" checked={selectedCorpus.includes(c)} onChange={(e) => setSelectedCorpus((prev) => e.target.checked ? [...prev, c] : prev.filter((x) => x !== c))} />
                      {c}
                    </label>
                  ))}
                </div>
                {bootstrapMessage && <p className="mb-2 text-xs text-green-600">{bootstrapMessage}</p>}
                <Button size="sm" disabled={bootstrap.isPending || selectedCorpus.length === 0} onClick={() => { bootstrap.mutate(selectedCorpus, { onSuccess: (data) => { setBootstrapMessage(`Created ${data.created_count} playbooks.`); setSelectedCorpus([]); } }); }}>
                  {bootstrap.isPending ? 'Bootstrapping…' : 'Bootstrap Playbooks'}
                </Button>
              </div>
            )}
          </div>

          <RuleEditor open={ruleEditorOpen} onClose={() => setRuleEditorOpen(false)} playbookId={playbookId} rule={editingRule} />
        </div>
      )}
    </QueryBoundary>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PlaybooksPage() {
  const playbooksQuery = usePlaybooks();
  const deletePlaybook = useDeletePlaybook();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  // Suppress unused import warnings — types are used in sub-components
  void (null as unknown as Playbook);

  return (
    <div className="flex h-full">
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-background">
        <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
          <span className="text-sm font-semibold">Playbooks</span>
          <Button size="sm" variant="ghost" onClick={() => setCreateOpen(true)} aria-label="New playbook">
            <PlusIcon className="size-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <QueryBoundary isLoading={playbooksQuery.isLoading} error={playbooksQuery.error ?? null} isEmpty={playbooksQuery.data?.length === 0} emptyMessage="No playbooks yet. Create one or use Bootstrap.">
            {playbooksQuery.data?.map((pb) => (
              <div
                key={pb.id}
                onClick={() => setSelectedId(pb.id)}
                className={`group flex cursor-pointer items-start justify-between gap-2 border-b border-border/50 px-3 py-2.5 hover:bg-muted/40 ${selectedId === pb.id ? 'bg-primary/10' : ''}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{pb.name}</p>
                  <div className="mt-0.5 flex items-center gap-1.5">
                    <Badge variant="outline" className="text-[10px]">{pb.practice_area.toUpperCase()}</Badge>
                    <span className="text-[10px] text-muted-foreground">p{pb.precedence}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); if (window.confirm(`Delete "${pb.name}"?`)) { deletePlaybook.mutate(pb.id); if (selectedId === pb.id) setSelectedId(null); } }}
                  className="shrink-0 rounded p-1 text-destructive opacity-0 hover:bg-destructive/10 group-hover:opacity-100"
                  aria-label="Delete playbook"
                >
                  <Trash2Icon className="size-3.5" />
                </button>
              </div>
            ))}
          </QueryBoundary>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        {selectedId ? (
          <PlaybookDetail playbookId={selectedId} />
        ) : (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">Select a playbook to view its rules.</p>
          </div>
        )}
      </main>

      <CreatePlaybookSlideOver open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
