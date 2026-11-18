'use client';

import { useState } from 'react';
import { PlusIcon, Trash2Icon, PencilIcon, ChevronDownIcon, ChevronUpIcon, ArrowUpIcon, ArrowDownIcon } from 'lucide-react';
import {
  usePlaybooks,
  usePlaybook,
  usePlaybookRules,
  usePlaybookVersions,
  useCreateDraftVersion,
  usePublishVersion,
  useResolvedRules,
  useCreatePlaybook,
  useUpdatePlaybook,
  useDeletePlaybook,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
  useBootstrapPlaybooks,
  useRuleParameters,
  useCreateRuleParameter,
  useDeleteRuleParameter,
  useRuleObjections,
  useCreateRuleObjection,
  useDeleteRuleObjection,
  useRuleTestCases,
  useCreateRuleTestCase,
  useDeleteRuleTestCase,
} from '@/lib/api/hooks';
import { QueryBoundary } from '@/components/primitives/query-boundary';
import { DataTable } from '@/components/primitives/data-table';
import type { ColumnDef } from '@/components/primitives/data-table';
import { SlideOver } from '@/components/primitives/slide-over';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { ApiError } from '@/lib/api/client';
import type {
  Playbook,
  PlaybookRule,
  PracticeArea,
  CreatePlaybookBody,
  CreateRuleBody,
  UpdateRuleBody,
  RulePosition,
  RulePositionInput,
  RedLine,
  RuleRedLineInput,
  Zone,
  ParameterValueType,
  ParameterDirection,
  RedLineAction,
  TestCaseExpectedOutcome,
} from '@/lib/api/types';

// ─── Rule display helpers (preferred/fallback language now live in
// `positions`, not flat fields; see lib/api/types.ts PlaybookRule) ───────────

function getPreferredPosition(rule: PlaybookRule): RulePosition | undefined {
  const positions = rule.positions ?? [];
  return positions.find((p) => p.kind === 'preferred') ?? positions.find((p) => p.rung === 0);
}

function getFallbackPositions(rule: PlaybookRule): RulePosition[] {
  return (rule.positions ?? [])
    .filter((p) => p.kind === 'fallback')
    .sort((a, b) => (a.rung ?? 0) - (b.rung ?? 0));
}

// ─── Shared form bits ─────────────────────────────────────────────────────────

const inputCls =
  'w-full rounded border border-border bg-background px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50';
const labelCls = 'block text-xs font-medium text-muted-foreground mb-1';

// ─── Rule child tabs: parameters, objections, test cases. Positions and
// rule-scoped red lines are now edited inline in the rule Details form
// (preferred/variants/fallbacks/red lines map to `positions`/`red_lines`
// child rows — see RuleEditor below), so standalone add/delete tabs for them
// were removed: editing both places risked the Details form's full id-sync
// save clobbering a row just added here. ─────────────────────────────────────

function ParametersTab({ ruleId }: { ruleId: string }) {
  const parametersQuery = useRuleParameters(ruleId);
  const createParameter = useCreateRuleParameter();
  const deleteParameter = useDeleteRuleParameter();

  const [key, setKey] = useState('');
  const [label, setLabel] = useState('');
  const [valueType, setValueType] = useState<ParameterValueType>('number');
  const [direction, setDirection] = useState<ParameterDirection>('higher_is_better');
  const [unit, setUnit] = useState('');

  function handleAdd() {
    if (!key || !label) return;
    createParameter.mutate(
      { ruleId, key, label, value_type: valueType, direction, unit: unit || undefined },
      {
        onSuccess: () => {
          setKey('');
          setLabel('');
          setUnit('');
        },
      }
    );
  }

  return (
    <div className="space-y-4 p-4">
      <QueryBoundary
        isLoading={parametersQuery.isLoading}
        error={parametersQuery.error ?? null}
        isEmpty={parametersQuery.data?.length === 0}
        emptyMessage="No parameters yet."
      >
        <div className="space-y-2">
          {parametersQuery.data?.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded border border-border p-2.5 text-xs">
              <div>
                <p className="font-medium">
                  {p.label} <span className="text-muted-foreground">({p.key})</span>
                </p>
                <p className="text-muted-foreground">
                  {p.value_type} · {p.direction}
                  {p.unit ? ` · ${p.unit}` : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={() => deleteParameter.mutate({ parameterId: p.id, ruleId })}
                className="rounded p-1 text-destructive hover:bg-destructive/10"
                aria-label="Delete parameter"
              >
                <Trash2Icon className="size-3" />
              </button>
            </div>
          ))}
        </div>
      </QueryBoundary>

      <div className="space-y-2 rounded border border-dashed border-border p-3">
        <p className="text-xs font-semibold">Add parameter</p>
        <div className="grid grid-cols-2 gap-2">
          <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="Key" className={inputCls} />
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label" className={inputCls} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <select value={valueType} onChange={(e) => setValueType(e.target.value as ParameterValueType)} className={inputCls}>
            <option value="number">number</option>
            <option value="duration_days">duration_days</option>
            <option value="percent">percent</option>
            <option value="currency_usd">currency_usd</option>
            <option value="enum">enum</option>
            <option value="boolean">boolean</option>
          </select>
          <select value={direction} onChange={(e) => setDirection(e.target.value as ParameterDirection)} className={inputCls}>
            <option value="higher_is_better">higher_is_better</option>
            <option value="lower_is_better">lower_is_better</option>
            <option value="exact">exact</option>
            <option value="set_membership">set_membership</option>
          </select>
        </div>
        <input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="Unit (optional)" className={inputCls} />
        <Button size="sm" disabled={!key || !label || createParameter.isPending} onClick={handleAdd}>
          {createParameter.isPending ? 'Adding…' : 'Add parameter'}
        </Button>
      </div>
    </div>
  );
}

function ObjectionsTab({ ruleId }: { ruleId: string }) {
  const objectionsQuery = useRuleObjections(ruleId);
  const createObjection = useCreateRuleObjection();
  const deleteObjection = useDeleteRuleObjection();

  const [objection, setObjection] = useState('');
  const [response, setResponse] = useState('');

  function handleAdd() {
    if (!objection || !response) return;
    createObjection.mutate(
      { ruleId, objection, response },
      {
        onSuccess: () => {
          setObjection('');
          setResponse('');
        },
      }
    );
  }

  return (
    <div className="space-y-4 p-4">
      <QueryBoundary
        isLoading={objectionsQuery.isLoading}
        error={objectionsQuery.error ?? null}
        isEmpty={objectionsQuery.data?.length === 0}
        emptyMessage="No objections yet."
      >
        <div className="space-y-2">
          {objectionsQuery.data?.map((o) => (
            <div key={o.id} className="rounded border border-border p-2.5 text-xs">
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="font-medium">&ldquo;{o.objection}&rdquo;</p>
                <button
                  type="button"
                  onClick={() => deleteObjection.mutate({ objectionId: o.id, ruleId })}
                  className="rounded p-1 text-destructive hover:bg-destructive/10"
                  aria-label="Delete objection"
                >
                  <Trash2Icon className="size-3" />
                </button>
              </div>
              <p className="text-muted-foreground">{o.response}</p>
            </div>
          ))}
        </div>
      </QueryBoundary>

      <div className="space-y-2 rounded border border-dashed border-border p-3">
        <p className="text-xs font-semibold">Add objection</p>
        <textarea
          value={objection}
          onChange={(e) => setObjection(e.target.value)}
          placeholder="What the counterparty says"
          rows={2}
          className={inputCls}
        />
        <textarea
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          placeholder="How we respond"
          rows={2}
          className={inputCls}
        />
        <Button size="sm" disabled={!objection || !response || createObjection.isPending} onClick={handleAdd}>
          {createObjection.isPending ? 'Adding…' : 'Add objection'}
        </Button>
      </div>
    </div>
  );
}

function TestCasesTab({ ruleId }: { ruleId: string }) {
  const testCasesQuery = useRuleTestCases(ruleId);
  const createTestCase = useCreateRuleTestCase();
  const deleteTestCase = useDeleteRuleTestCase();

  const [name, setName] = useState('');
  const [expectedOutcome, setExpectedOutcome] = useState<TestCaseExpectedOutcome>('compliant');
  const [sampleText, setSampleText] = useState('');
  const [expectedZone, setExpectedZone] = useState<Zone | ''>('');
  const [isTrap, setIsTrap] = useState(false);

  function handleAdd() {
    if (!name) return;
    createTestCase.mutate(
      {
        ruleId,
        name,
        expected_outcome: expectedOutcome,
        sample_text: sampleText || undefined,
        expected_zone: expectedZone || undefined,
        is_trap: isTrap,
      },
      {
        onSuccess: () => {
          setName('');
          setSampleText('');
          setIsTrap(false);
        },
      }
    );
  }

  return (
    <div className="space-y-4 p-4">
      <QueryBoundary
        isLoading={testCasesQuery.isLoading}
        error={testCasesQuery.error ?? null}
        isEmpty={testCasesQuery.data?.length === 0}
        emptyMessage="No test cases yet."
      >
        <div className="space-y-2">
          {testCasesQuery.data?.map((t) => (
            <div key={t.id} className="rounded border border-border p-2.5 text-xs">
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <p className="font-medium">{t.name}</p>
                  <Badge variant="outline">{t.expected_outcome}</Badge>
                  {t.expected_zone && (
                    <Badge variant={t.expected_zone === 'green' ? 'default' : t.expected_zone === 'yellow' ? 'secondary' : 'destructive'}>
                      {t.expected_zone}
                    </Badge>
                  )}
                  {t.is_trap && <Badge variant="outline">trap</Badge>}
                </div>
                <button
                  type="button"
                  onClick={() => deleteTestCase.mutate({ testCaseId: t.id, ruleId })}
                  className="rounded p-1 text-destructive hover:bg-destructive/10"
                  aria-label="Delete test case"
                >
                  <Trash2Icon className="size-3" />
                </button>
              </div>
              {t.sample_text && <p className="text-muted-foreground">{t.sample_text}</p>}
            </div>
          ))}
        </div>
      </QueryBoundary>

      <div className="space-y-2 rounded border border-dashed border-border p-3">
        <p className="text-xs font-semibold">Add test case</p>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className={inputCls} />
        <div className="grid grid-cols-2 gap-2">
          <select
            value={expectedOutcome}
            onChange={(e) => setExpectedOutcome(e.target.value as TestCaseExpectedOutcome)}
            className={inputCls}
          >
            <option value="compliant">compliant</option>
            <option value="acceptable_variant">acceptable_variant</option>
            <option value="fallback">fallback</option>
            <option value="deviation">deviation</option>
            <option value="red_line">red_line</option>
            <option value="missing">missing</option>
          </select>
          <select value={expectedZone} onChange={(e) => setExpectedZone(e.target.value as Zone | '')} className={inputCls}>
            <option value="">zone (optional)</option>
            <option value="green">green</option>
            <option value="yellow">yellow</option>
            <option value="red">red</option>
          </select>
        </div>
        <textarea
          value={sampleText}
          onChange={(e) => setSampleText(e.target.value)}
          placeholder="Sample clause text (empty for a missing-clause case)"
          rows={2}
          className={inputCls}
        />
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={isTrap} onChange={(e) => setIsTrap(e.target.checked)} className="size-3.5" />
          Is trap (look-alike wording that must not trigger)
        </label>
        <Button size="sm" disabled={!name || createTestCase.isPending} onClick={handleAdd}>
          {createTestCase.isPending ? 'Adding…' : 'Add test case'}
        </Button>
      </div>
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

// One row of position-shaped data edited inline in the Details form. Mirrors
// RulePositionInput; `id` is only set for rows that came from the server and
// is preserved on save so the id-sync updates that row instead of recreating
// it.
interface PosRow {
  id?: string;
  label: string;
  language: string;
  zone: Zone | string;
  summary?: string | null;
  approver_role_id?: string | null;
  conditions?: Record<string, unknown> | null;
  give_get?: string | null;
  internal_note?: string | null;
}

function toPosRow(p: RulePosition): PosRow {
  return {
    id: p.id,
    label: p.label,
    language: p.language,
    zone: p.zone,
    summary: p.summary,
    approver_role_id: p.approver_role_id,
    conditions: p.conditions,
    give_get: p.give_get,
    internal_note: p.internal_note,
  };
}

// One row of red-line-shaped data edited inline. `condition` is kept as raw
// JSON text while editing and parsed/validated on submit.
interface RedLineRow {
  id?: string;
  key: string;
  description: string;
  condition_type: string;
  conditionJson: string;
  action: RedLineAction | string;
  approver_role_id?: string | null;
  rationale?: string | null;
}

function toRedLineRow(r: RedLine): RedLineRow {
  return {
    id: r.id,
    key: r.key,
    description: r.description,
    condition_type: r.condition_type,
    conditionJson: JSON.stringify(r.condition ?? {}),
    action: r.action,
    approver_role_id: r.approver_role_id,
    rationale: r.rationale,
  };
}

function RuleEditor({ open, onClose, playbookId, rule }: RuleEditorProps) {
  const isEdit = !!rule;
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();

  const [clauseType, setClauseType] = useState(rule?.clause_type ?? '');
  const [required, setRequired] = useState(rule?.required ?? false);
  // Risk weight is a 1–10 scale (playbook_status.md defect #5 / task 4.9
  // item 4) — previously the form capped it at 1, which did not match the
  // seed data (weights of 2 to 10).
  const [riskWeight, setRiskWeight] = useState(rule?.risk_weight ?? 5);

  // Preferred / acceptable-variant / fallback language used to be flat
  // fields (preferred_language, acceptable_variations, fallback_language).
  // They now live in `positions` child rows, matched by `kind` (and `rung`
  // for the fallback ladder). Any position that doesn't fit one of those
  // three buckets (an unexpected kind, or a duplicate preferred row) is
  // carried through unchanged in `otherPositions` on save, so saving never
  // silently deletes it via the id-sync.
  const initialPositions = rule?.positions ?? [];
  const preferredInit =
    initialPositions.find((p) => p.kind === 'preferred') ?? initialPositions.find((p) => p.rung === 0);
  const variantsInit = initialPositions.filter((p) => p.kind === 'acceptable_variant');
  const fallbacksInit = [...initialPositions.filter((p) => p.kind === 'fallback')].sort(
    (a, b) => (a.rung ?? 0) - (b.rung ?? 0)
  );
  const bucketedIds = new Set(
    [preferredInit?.id, ...variantsInit.map((p) => p.id), ...fallbacksInit.map((p) => p.id)].filter(Boolean)
  );
  const [otherPositions] = useState<RulePosition[]>(initialPositions.filter((p) => !bucketedIds.has(p.id)));

  const [preferred, setPreferred] = useState<PosRow>(
    preferredInit ? toPosRow(preferredInit) : { label: 'Preferred', language: '', zone: 'green' }
  );
  const [variants, setVariants] = useState<PosRow[]>(variantsInit.map(toPosRow));
  const [fallbacks, setFallbacks] = useState<PosRow[]>(fallbacksInit.map(toPosRow));
  // Only sent on save if the user actually touched this section — a
  // scalar-only PATCH must omit `positions`/`red_lines` entirely, or it gets
  // gated by the same 409 version_not_draft check as a child-row edit.
  const [positionsDirty, setPositionsDirty] = useState(false);

  // Prohibited terms used to be a flat string array (prohibited_terms). A
  // prohibited phrase is now a rule-scoped red line with condition_type
  // "phrase" (see the default new row below) — but a red line can express
  // any condition_type, not just phrase matching.
  const [redLines, setRedLines] = useState<RedLineRow[]>((rule?.red_lines ?? []).map(toRedLineRow));
  const [redLinesDirty, setRedLinesDirty] = useState(false);
  const [redLineErrors, setRedLineErrors] = useState<Record<number, string>>({});

  const isPending = createRule.isPending || updateRule.isPending;
  const mutationError = createRule.error ?? updateRule.error;

  function updatePreferred(patch: Partial<PosRow>) {
    setPreferred((p) => ({ ...p, ...patch }));
    setPositionsDirty(true);
  }
  function updateVariant(i: number, patch: Partial<PosRow>) {
    setVariants((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    setPositionsDirty(true);
  }
  function addVariant() {
    setVariants((rows) => [...rows, { label: '', language: '', zone: 'green' }]);
    setPositionsDirty(true);
  }
  function removeVariant(i: number) {
    setVariants((rows) => rows.filter((_, idx) => idx !== i));
    setPositionsDirty(true);
  }
  function updateFallback(i: number, patch: Partial<PosRow>) {
    setFallbacks((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    setPositionsDirty(true);
  }
  function addFallback() {
    setFallbacks((rows) => [...rows, { label: `Fallback ${rows.length + 1}`, language: '', zone: 'yellow' }]);
    setPositionsDirty(true);
  }
  function removeFallback(i: number) {
    setFallbacks((rows) => rows.filter((_, idx) => idx !== i));
    setPositionsDirty(true);
  }
  function moveFallback(i: number, dir: -1 | 1) {
    setFallbacks((rows) => {
      const next = [...rows];
      const j = i + dir;
      if (j < 0 || j >= next.length) return rows;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
    setPositionsDirty(true);
  }

  function updateRedLine(i: number, patch: Partial<RedLineRow>) {
    setRedLines((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    setRedLinesDirty(true);
  }
  function addRedLine() {
    setRedLines((rows) => [
      ...rows,
      {
        key: '',
        description: '',
        condition_type: 'phrase',
        conditionJson: JSON.stringify({ any: [], negation_guard: true }),
        action: 'block',
      },
    ]);
    setRedLinesDirty(true);
  }
  function removeRedLine(i: number) {
    setRedLines((rows) => rows.filter((_, idx) => idx !== i));
    setRedLinesDirty(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const parsedRedLines: RuleRedLineInput[] = [];
    const errors: Record<number, string> = {};
    redLines.forEach((r, idx) => {
      const keyFilled = r.key.trim().length > 0;
      const descFilled = r.description.trim().length > 0;
      if (!keyFilled && !descFilled) return; // a row the user never filled in — skip it, even though
      // condition_type/action/condition start pre-filled by addRedLine's defaults.
      if (keyFilled !== descFilled) {
        errors[idx] = 'A red line needs both a key and a description.';
        return;
      }
      try {
        const parsed = JSON.parse(r.conditionJson || '{}');
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          throw new Error('condition must be an object');
        }
        parsedRedLines.push({
          id: r.id,
          key: r.key,
          description: r.description,
          condition_type: r.condition_type,
          condition: parsed,
          action: r.action,
          approver_role_id: r.approver_role_id ?? undefined,
          rationale: r.rationale || undefined,
        });
      } catch {
        errors[idx] = 'Condition must be valid JSON (an object).';
      }
    });
    setRedLineErrors(errors);
    if (Object.keys(errors).length > 0) return;

    // An existing rule may have no preferred position (e.g. one created via
    // the per-child endpoints, bootstrap, or a seed). Don't force one into
    // existence on a save that never touched it — only include/require it
    // when there's an existing row to update or the user typed something.
    const hasPreferred = !!preferred.id || preferred.language.trim().length > 0;

    const positions: RulePositionInput[] = [
      ...(hasPreferred
        ? [
            {
              id: preferred.id,
              kind: 'preferred',
              rung: 0,
              label: preferred.label || 'Preferred',
              language: preferred.language,
              zone: preferred.zone,
              summary: preferred.summary ?? undefined,
              approver_role_id: preferred.approver_role_id ?? undefined,
              conditions: preferred.conditions ?? undefined,
              give_get: preferred.give_get ?? undefined,
              internal_note: preferred.internal_note ?? undefined,
            },
          ]
        : []),
      ...variants
        .filter((v) => v.language.trim())
        .map((v, i) => ({
          id: v.id,
          kind: 'acceptable_variant',
          rung: undefined,
          label: v.label || `Variant ${i + 1}`,
          language: v.language,
          zone: v.zone,
          summary: v.summary ?? undefined,
          approver_role_id: v.approver_role_id ?? undefined,
          conditions: v.conditions ?? undefined,
          give_get: v.give_get ?? undefined,
          internal_note: v.internal_note ?? undefined,
        })),
      ...fallbacks
        .filter((f) => f.language.trim())
        .map((f, i) => ({
          id: f.id,
          kind: 'fallback',
          rung: i + 1,
          label: f.label || `Fallback ${i + 1}`,
          language: f.language,
          zone: f.zone,
          summary: f.summary ?? undefined,
          approver_role_id: f.approver_role_id ?? undefined,
          conditions: f.conditions ?? undefined,
          give_get: f.give_get ?? undefined,
          internal_note: f.internal_note ?? undefined,
        })),
      ...otherPositions.map((p) => ({
        id: p.id,
        kind: p.kind,
        rung: p.rung,
        label: p.label,
        language: p.language,
        zone: p.zone,
        summary: p.summary ?? undefined,
        approver_role_id: p.approver_role_id ?? undefined,
        conditions: p.conditions ?? undefined,
        give_get: p.give_get ?? undefined,
        internal_note: p.internal_note ?? undefined,
      })),
    ];

    const scalarBody = {
      clause_type: clauseType,
      required,
      risk_weight: riskWeight,
    };

    if (isEdit && rule) {
      const body: UpdateRuleBody = { ...scalarBody };
      if (positionsDirty) body.positions = positions;
      if (redLinesDirty) body.red_lines = parsedRedLines;
      updateRule.mutate({ ruleId: rule.id, playbookId, ...body }, { onSuccess: onClose });
    } else {
      const body: CreateRuleBody = { ...scalarBody, positions, red_lines: parsedRedLines };
      createRule.mutate({ playbookId, ...body }, { onSuccess: onClose });
    }
  }

  const detailsForm = (
    <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-5 overflow-y-auto px-4 py-4">
      <div>
        <label className={labelCls}>Clause type *</label>
        <input required value={clauseType} onChange={(e) => setClauseType(e.target.value)} className={inputCls} placeholder="e.g. indemnification" />
      </div>

      {/* Preferred position (was: preferred_language). Required on create —
          an existing rule may have no preferred position (created via a
          per-child endpoint, bootstrap, or a seed), so editing one shouldn't
          force a value into existence just to save an unrelated change. */}
      <div>
        <label className={labelCls}>Preferred position{!isEdit || !!preferred.id ? ' *' : ''}</label>
        <textarea
          required={!isEdit || !!preferred.id}
          rows={4}
          value={preferred.language}
          onChange={(e) => updatePreferred({ language: e.target.value })}
          className={inputCls}
          placeholder="The clause language we ask for"
        />
        <div className="mt-1.5 grid grid-cols-2 gap-2">
          <input value={preferred.label} onChange={(e) => updatePreferred({ label: e.target.value })} className={inputCls} placeholder="Label" />
          <select value={preferred.zone} onChange={(e) => updatePreferred({ zone: e.target.value as Zone })} className={inputCls}>
            <option value="green">green</option>
            <option value="yellow">yellow</option>
            <option value="red">red</option>
          </select>
        </div>
      </div>

      {/* Acceptable variants (was: acceptable_variations) */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className={labelCls}>Acceptable variants</label>
          <Button type="button" size="sm" variant="ghost" onClick={addVariant}>
            <PlusIcon className="mr-1 size-3" /> Add
          </Button>
        </div>
        <div className="space-y-2">
          {variants.map((v, i) => (
            <div key={v.id ?? `new-variant-${i}`} className="space-y-1.5 rounded border border-border p-2.5">
              <div className="flex items-start gap-2">
                <textarea
                  rows={2}
                  value={v.language}
                  onChange={(e) => updateVariant(i, { language: e.target.value })}
                  className={inputCls}
                  placeholder="Variant language"
                />
                <button type="button" onClick={() => removeVariant(i)} className="shrink-0 rounded p-1 text-destructive hover:bg-destructive/10" aria-label="Remove variant">
                  <Trash2Icon className="size-3.5" />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <input value={v.label} onChange={(e) => updateVariant(i, { label: e.target.value })} className={inputCls} placeholder="Label" />
                <select value={v.zone} onChange={(e) => updateVariant(i, { zone: e.target.value as Zone })} className={inputCls}>
                  <option value="green">green</option>
                  <option value="yellow">yellow</option>
                  <option value="red">red</option>
                </select>
              </div>
            </div>
          ))}
          {variants.length === 0 && <p className="text-xs text-muted-foreground">No acceptable variants.</p>}
        </div>
      </div>

      {/* Fallbacks ladder (was: fallback_language, single) */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className={labelCls}>Fallbacks (in order offered)</label>
          <Button type="button" size="sm" variant="ghost" onClick={addFallback}>
            <PlusIcon className="mr-1 size-3" /> Add
          </Button>
        </div>
        <div className="space-y-2">
          {fallbacks.map((f, i) => (
            <div key={f.id ?? `new-fallback-${i}`} className="space-y-1.5 rounded border border-border p-2.5">
              <div className="flex items-center justify-between">
                <Badge variant="secondary">rung {i + 1}</Badge>
                <div className="flex items-center gap-1">
                  <button type="button" disabled={i === 0} onClick={() => moveFallback(i, -1)} className="rounded p-1 hover:bg-muted disabled:opacity-30" aria-label="Move up">
                    <ArrowUpIcon className="size-3" />
                  </button>
                  <button type="button" disabled={i === fallbacks.length - 1} onClick={() => moveFallback(i, 1)} className="rounded p-1 hover:bg-muted disabled:opacity-30" aria-label="Move down">
                    <ArrowDownIcon className="size-3" />
                  </button>
                  <button type="button" onClick={() => removeFallback(i)} className="rounded p-1 text-destructive hover:bg-destructive/10" aria-label="Remove fallback">
                    <Trash2Icon className="size-3.5" />
                  </button>
                </div>
              </div>
              <textarea
                rows={2}
                value={f.language}
                onChange={(e) => updateFallback(i, { language: e.target.value })}
                className={inputCls}
                placeholder="Fallback language"
              />
              <div className="grid grid-cols-2 gap-2">
                <input value={f.label} onChange={(e) => updateFallback(i, { label: e.target.value })} className={inputCls} placeholder="Label" />
                <select value={f.zone} onChange={(e) => updateFallback(i, { zone: e.target.value as Zone })} className={inputCls}>
                  <option value="green">green</option>
                  <option value="yellow">yellow</option>
                  <option value="red">red</option>
                </select>
              </div>
            </div>
          ))}
          {fallbacks.length === 0 && <p className="text-xs text-muted-foreground">No fallback positions.</p>}
        </div>
      </div>

      {/* Red lines, rule-scoped (was: prohibited_terms as a flat string array) */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className={labelCls}>Red lines</label>
          <Button type="button" size="sm" variant="ghost" onClick={addRedLine}>
            <PlusIcon className="mr-1 size-3" /> Add
          </Button>
        </div>
        <div className="space-y-2">
          {redLines.map((r, i) => (
            <div key={r.id ?? `new-redline-${i}`} className="space-y-1.5 rounded border border-border p-2.5">
              <div className="flex items-start gap-2">
                <input value={r.key} onChange={(e) => updateRedLine(i, { key: e.target.value })} className={inputCls} placeholder="Key" />
                <button type="button" onClick={() => removeRedLine(i)} className="shrink-0 rounded p-1 text-destructive hover:bg-destructive/10" aria-label="Remove red line">
                  <Trash2Icon className="size-3.5" />
                </button>
              </div>
              <textarea
                rows={2}
                value={r.description}
                onChange={(e) => updateRedLine(i, { description: e.target.value })}
                className={inputCls}
                placeholder="What is never acceptable"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={r.condition_type}
                  onChange={(e) => updateRedLine(i, { condition_type: e.target.value })}
                  className={inputCls}
                  placeholder="Condition type (e.g. phrase)"
                />
                <select value={r.action} onChange={(e) => updateRedLine(i, { action: e.target.value as RedLineAction })} className={inputCls}>
                  <option value="block">block</option>
                  <option value="escalate">escalate</option>
                </select>
              </div>
              <textarea
                rows={2}
                value={r.conditionJson}
                onChange={(e) => updateRedLine(i, { conditionJson: e.target.value })}
                className={inputCls}
                placeholder='Condition JSON, e.g. {"any": ["sole discretion"], "negation_guard": true}'
              />
              <textarea
                rows={1}
                value={r.rationale ?? ''}
                onChange={(e) => updateRedLine(i, { rationale: e.target.value })}
                className={inputCls}
                placeholder="Rationale (optional)"
              />
              {redLineErrors[i] && <p className="text-xs text-destructive">{redLineErrors[i]}</p>}
            </div>
          ))}
          {redLines.length === 0 && <p className="text-xs text-muted-foreground">No red lines.</p>}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input type="checkbox" id="rule-required" checked={required} onChange={(e) => setRequired(e.target.checked)} className="size-4" />
        <label htmlFor="rule-required" className="text-sm">Required clause</label>
      </div>
      <div>
        <label className={labelCls}>Risk weight (1–10)</label>
        <input
          type="number"
          min={1}
          max={10}
          step={1}
          value={riskWeight}
          onChange={(e) => setRiskWeight(parseFloat(e.target.value))}
          className={inputCls}
        />
      </div>

      {mutationError && (
        <p className="text-xs text-destructive">
          {mutationError instanceof ApiError && mutationError.code === 'version_not_draft'
            ? 'This playbook version is not a draft — create a new draft version before editing rules.'
            : mutationError.message || 'Something went wrong saving this rule.'}
        </p>
      )}

      <div className="mt-auto">
        <Button type="submit" className="w-full" disabled={isPending}>
          {isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add rule'}
        </Button>
      </div>
    </form>
  );

  return (
    <SlideOver
      open={open}
      onOpenChange={(o) => { if (!o) onClose(); }}
      title={isEdit ? 'Edit Rule' : 'Add Rule'}
      description="Define how this clause type should be governed."
      className="max-w-xl"
    >
      {isEdit && rule ? (
        <Tabs defaultValue="details" className="flex flex-1 flex-col gap-0 overflow-hidden">
          <TabsList variant="line" className="h-auto w-full shrink-0 justify-start overflow-x-auto rounded-none border-b border-border px-2 py-0">
            <TabsTrigger value="details" className="shrink-0 py-2 text-xs">Details</TabsTrigger>
            <TabsTrigger value="parameters" className="shrink-0 py-2 text-xs">Parameters</TabsTrigger>
            <TabsTrigger value="objections" className="shrink-0 py-2 text-xs">Objections</TabsTrigger>
            <TabsTrigger value="testcases" className="shrink-0 py-2 text-xs">Test cases</TabsTrigger>
          </TabsList>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <TabsContent value="details" className="h-full">{detailsForm}</TabsContent>
            <TabsContent value="parameters" className="h-full"><ParametersTab ruleId={rule.id} /></TabsContent>
            <TabsContent value="objections" className="h-full"><ObjectionsTab ruleId={rule.id} /></TabsContent>
            <TabsContent value="testcases" className="h-full"><TestCasesTab ruleId={rule.id} /></TabsContent>
          </div>
        </Tabs>
      ) : (
        detailsForm
      )}
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

// ─── Version header: status, draft and publish actions (task 4.9 item 5) ─────

function VersionHeader({ playbookId }: { playbookId: string }) {
  const versionsQuery = usePlaybookVersions(playbookId);
  const createDraft = useCreateDraftVersion();
  const publish = usePublishVersion();

  const [draftOpen, setDraftOpen] = useState(false);
  const [newVersion, setNewVersion] = useState('');
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [changeSummary, setChangeSummary] = useState('');
  const [approvedBy, setApprovedBy] = useState('');

  const versions = versionsQuery.data ?? [];
  const sorted = [...versions].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  const latest = sorted[0];
  const draftVersion = sorted.find((v) => v.status === 'draft');

  return (
    <div className="flex flex-wrap items-center gap-2">
      {versionsQuery.isLoading ? (
        <span className="text-xs text-muted-foreground">Loading version…</span>
      ) : latest ? (
        <Badge variant={latest.status === 'published' ? 'default' : latest.status === 'draft' ? 'secondary' : 'outline'}>
          v{latest.version} · {latest.status}
        </Badge>
      ) : (
        <span className="text-xs text-muted-foreground">No versions yet</span>
      )}

      <Button size="sm" variant="outline" onClick={() => setDraftOpen((v) => !v)}>
        New draft
      </Button>
      {draftVersion && (
        <Button size="sm" onClick={() => setPublishingId(draftVersion.id)}>
          Publish draft v{draftVersion.version}
        </Button>
      )}

      {draftOpen && (
        <div className="flex items-center gap-1.5">
          <input
            value={newVersion}
            onChange={(e) => setNewVersion(e.target.value)}
            placeholder="e.g. 1.1"
            className="w-20 rounded border border-border bg-background px-1.5 py-1 text-xs outline-none focus:ring-1 focus:ring-primary/50"
          />
          <Button
            size="sm"
            disabled={!newVersion || createDraft.isPending}
            onClick={() =>
              createDraft.mutate(
                { playbookId, version: newVersion },
                { onSuccess: () => { setDraftOpen(false); setNewVersion(''); } }
              )
            }
          >
            {createDraft.isPending ? 'Creating…' : 'Create'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setDraftOpen(false)}>Cancel</Button>
        </div>
      )}

      {publishingId && (
        <div className="flex items-center gap-1.5">
          <input
            value={changeSummary}
            onChange={(e) => setChangeSummary(e.target.value)}
            placeholder="Change summary"
            className="w-40 rounded border border-border bg-background px-1.5 py-1 text-xs outline-none focus:ring-1 focus:ring-primary/50"
          />
          <input
            value={approvedBy}
            onChange={(e) => setApprovedBy(e.target.value)}
            placeholder="Approved by"
            className="w-28 rounded border border-border bg-background px-1.5 py-1 text-xs outline-none focus:ring-1 focus:ring-primary/50"
          />
          <Button
            size="sm"
            disabled={publish.isPending}
            onClick={() =>
              publish.mutate(
                {
                  playbookId,
                  versionId: publishingId,
                  change_summary: changeSummary || undefined,
                  approved_by: approvedBy || undefined,
                },
                {
                  onSuccess: () => {
                    setPublishingId(null);
                    setChangeSummary('');
                    setApprovedBy('');
                  },
                }
              )
            }
          >
            {publish.isPending ? 'Publishing…' : 'Confirm publish'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setPublishingId(null)}>Cancel</Button>
        </div>
      )}
    </div>
  );
}

// ─── Detail panel ─────────────────────────────────────────────────────────────

const PARTY_ROLES = ['vendor', 'customer', 'mutual'];
const PAPER_ORIGINS = ['own', 'counterparty'];
const BOOTSTRAP_CONTRACT_TYPES = ['nda', 'msa', 'sow', 'employment', 'gdpr_dpa'];

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
  // RuleEditor's position/red-line state is seeded from `rule` only on
  // mount, so reopening it for a different rule (or the same rule again
  // after a save) without remounting would carry over stale ids into the
  // next save's id-sync. Bumping this on every open and folding it into the
  // component's `key` forces a fresh mount each time.
  const [editorNonce, setEditorNonce] = useState(0);
  function openRuleEditor(r?: PlaybookRule) {
    setEditingRule(r);
    setEditorNonce((n) => n + 1);
    setRuleEditorOpen(true);
  }
  const [resolveOpen, setResolveOpen] = useState(false);
  const [contractType, setContractType] = useState('');
  const [partyRole, setPartyRole] = useState('vendor');
  const [paperOrigin, setPaperOrigin] = useState('own');
  const [contextJson, setContextJson] = useState('');
  const [bootstrapOpen, setBootstrapOpen] = useState(false);
  const [bootstrapContractType, setBootstrapContractType] = useState(BOOTSTRAP_CONTRACT_TYPES[0]);
  const [bootstrapMessage, setBootstrapMessage] = useState('');

  // Derived from contextJson on every render — not state, so parsing never
  // triggers a setState-during-render re-render loop.
  let resolveContext: Record<string, unknown> | undefined;
  let contextError = '';
  if (contextJson.trim()) {
    try {
      resolveContext = JSON.parse(contextJson);
    } catch {
      resolveContext = undefined;
      contextError = 'Context must be valid JSON — resolving without it.';
    }
  }

  const resolvedQuery = useResolvedRules({
    contract_type: contractType,
    party_role: partyRole,
    paper_origin: paperOrigin,
    context: resolveContext,
  });

  const ruleColumns: ColumnDef<PlaybookRule>[] = [
    { key: 'clause_type', header: 'Clause type', cell: (r) => r.clause_type, sortable: true },
    {
      key: 'preferred_position',
      header: 'Preferred language',
      cell: (r) => (
        <span className="block max-w-[200px] truncate text-xs text-muted-foreground">
          {getPreferredPosition(r)?.language ?? '—'}
        </span>
      ),
    },
    {
      key: 'fallbacks',
      header: 'Fallbacks',
      cell: (r) => {
        const n = getFallbackPositions(r).length;
        return n > 0 ? <Badge variant="outline">{n}</Badge> : <span className="text-muted-foreground">—</span>;
      },
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
          <button type="button" onClick={(e) => { e.stopPropagation(); openRuleEditor(r); }} className="rounded p-1 hover:bg-muted" aria-label="Edit">
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
            <div className="mt-3">
              <VersionHeader playbookId={playbookId} />
            </div>
          </div>

          {/* Rules */}
          <div>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-semibold">Rules</p>
              <Button size="sm" onClick={() => openRuleEditor(undefined)}>
                <PlusIcon className="mr-1 size-3.5" /> Add Rule
              </Button>
            </div>
            <QueryBoundary
              isLoading={rulesQuery.isLoading}
              error={rulesQuery.error ?? null}
              isEmpty={rulesQuery.data?.length === 0}
              emptyMessage="No rules yet."
              emptyAction={<Button size="sm" onClick={() => openRuleEditor(undefined)}>Add first rule</Button>}
            >
              <DataTable<PlaybookRule>
                columns={ruleColumns}
                data={rulesQuery.data ?? []}
                total={rulesQuery.data?.length ?? 0}
                page={1}
                pageSize={rulesQuery.data?.length ?? 50}
                onPageChange={() => {}}
                getRowKey={(r) => r.id}
                onRowClick={(r) => openRuleEditor(r)}
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
                <div className="mb-3 grid grid-cols-3 gap-2">
                  <input value={contractType} onChange={(e) => setContractType(e.target.value)} placeholder="Contract type (e.g. nda)" className={inputCls} />
                  <select value={partyRole} onChange={(e) => setPartyRole(e.target.value)} className={inputCls}>
                    {PARTY_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <select value={paperOrigin} onChange={(e) => setPaperOrigin(e.target.value)} className={inputCls}>
                    {PAPER_ORIGINS.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
                <input
                  value={contextJson}
                  onChange={(e) => setContextJson(e.target.value)}
                  placeholder='Context JSON, e.g. {"deal_value_band": "mid", "regimes": ["hipaa"]}'
                  className={`${inputCls} mb-3`}
                />
                {contextError && <p className="mb-2 text-xs text-destructive">{contextError}</p>}
                {contractType && (
                  <QueryBoundary isLoading={resolvedQuery.isLoading} error={resolvedQuery.error ?? null} isEmpty={resolvedQuery.data?.rules.length === 0} emptyMessage="No resolved rules.">
                    <>
                      {resolvedQuery.data && (
                        <p className="mb-2 text-[11px] text-muted-foreground">
                          Applied playbooks: {resolvedQuery.data.applied_playbook_keys.join(', ') || '—'} · Pinned versions: {resolvedQuery.data.pinned_version_ids.length}
                        </p>
                      )}
                      <table className="w-full text-xs">
                        <thead><tr className="border-b border-border text-left text-muted-foreground"><th className="py-1 pr-3">Clause type</th><th className="py-1 pr-3">Source playbook</th><th className="py-1 pr-3">Required</th><th className="py-1">Risk weight</th></tr></thead>
                        <tbody>
                          {resolvedQuery.data?.rules.map((r) => (
                            <tr key={r.id} className="border-b border-border/50">
                              <td className="py-1.5 pr-3 font-medium">{r.clause_type}</td>
                              <td className="py-1.5 pr-3"><Badge variant="outline" className="text-[10px]">{r.source_playbook_name}</Badge></td>
                              <td className="py-1.5 pr-3">{r.required ? 'Yes' : '—'}</td>
                              <td className="py-1.5">{r.risk_weight.toFixed(1)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  </QueryBoundary>
                )}
              </div>
            )}
          </div>

          {/* Bootstrap */}
          <div className="rounded-lg border border-border">
            <button type="button" onClick={() => setBootstrapOpen((v) => !v)} className="flex w-full items-center justify-between px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:bg-muted/30">
              Bootstrap playbook
              {bootstrapOpen ? <ChevronUpIcon className="size-4" /> : <ChevronDownIcon className="size-4" />}
            </button>
            {bootstrapOpen && (
              <div className="border-t border-border p-4">
                <p className="mb-3 text-xs text-muted-foreground">
                  Mines rules from existing contracts of one type into this playbook.
                </p>
                <div className="mb-4 flex items-center gap-2">
                  <select value={bootstrapContractType} onChange={(e) => setBootstrapContractType(e.target.value)} className={inputCls}>
                    {BOOTSTRAP_CONTRACT_TYPES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                {bootstrapMessage && <p className="mb-2 text-xs text-green-600">{bootstrapMessage}</p>}
                <Button
                  size="sm"
                  disabled={bootstrap.isPending}
                  onClick={() => {
                    bootstrap.mutate(
                      { playbookId, contractType: bootstrapContractType },
                      {
                        onSuccess: (data) => {
                          setBootstrapMessage(`Created ${data.created_rule_count} rules.`);
                        },
                      }
                    );
                  }}
                >
                  {bootstrap.isPending ? 'Bootstrapping…' : 'Bootstrap from contract type'}
                </Button>
              </div>
            )}
          </div>

          <RuleEditor key={`${editingRule?.id ?? 'new'}-${editorNonce}`} open={ruleEditorOpen} onClose={() => setRuleEditorOpen(false)} playbookId={playbookId} rule={editingRule} />
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
