'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FileText, UploadCloud, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SlideOver } from '@/components/primitives/slide-over';
import { useUploadDocument, useRunReviewUpload, useReviewRun } from '@/lib/api/hooks';
import type { GateDecision, PaperOrigin } from '@/lib/api/types';
import { cn } from '@/lib/utils';

type IntakeMode = 'process' | 'review';
type WizardStep = 'upload' | 'mode' | 'submitting' | 'polling' | 'done' | 'error';

interface DoneState {
  contractId: string;
  clauseCount?: number;
  counterpartyDetected?: boolean;
  gateDecision?: GateDecision;
}

interface WizardState {
  step: WizardStep;
  file: File | null;
  paperOrigin: PaperOrigin;
  mode: IntakeMode;
  runId: string | null;
  done: DoneState | null;
  errorMessage: string | null;
  contractType: string;
  partyRole: string;
  contextJson: string;
}

const INITIAL: WizardState = {
  step: 'upload',
  file: null,
  paperOrigin: 'counterparty',
  mode: 'process',
  runId: null,
  done: null,
  errorMessage: null,
  contractType: '',
  partyRole: '',
  contextJson: '',
};

const PARTY_ROLE_OPTIONS = ['vendor', 'customer', 'mutual'] as const;

const MODE_OPTIONS: { value: IntakeMode; label: string; description: string }[] = [
  {
    value: 'process',
    label: 'Process only',
    description: 'Extract clauses and metadata. Review manually in the workspace.',
  },
  {
    value: 'review',
    label: 'Process + autonomous review',
    description:
      'Run the full AI review pipeline — flags, redlines, and compliance gates — automatically.',
  },
];

interface NewContractSlideOverProps {
  open: boolean;
  onClose: () => void;
}

export function NewContractSlideOver({ open, onClose }: NewContractSlideOverProps) {
  const router = useRouter();
  const [state, setState] = useState<WizardState>(INITIAL);

  const uploadDoc = useUploadDocument();
  const uploadReview = useRunReviewUpload();
  const reviewRunQuery = useReviewRun(state.runId ?? '');

  useEffect(() => {
    if (state.step !== 'polling' || !state.runId || !reviewRunQuery.data) return;
    const { status, contract_id, gate_decision } = reviewRunQuery.data;
    if (status === 'completed') {
      setState((s) => ({
        ...s,
        step: 'done',
        done: { contractId: contract_id, gateDecision: gate_decision },
      }));
    } else if (status === 'failed') {
      setState((s) => ({
        ...s,
        step: 'error',
        errorMessage: 'Autonomous review failed. You can open the contract and review manually.',
      }));
    }
  }, [state.step, state.runId, reviewRunQuery.data]);

  function handleFileSelect(file: File) {
    setState((s) => ({ ...s, file }));
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.pdf') || file.name.endsWith('.docx'))) {
      handleFileSelect(file);
    }
  }

  function handleSubmit() {
    if (!state.file) return;
    setState((s) => ({ ...s, step: 'submitting' }));

    if (state.mode === 'process') {
      let context: Record<string, unknown> | undefined;
      if (state.contextJson.trim()) {
        try {
          context = JSON.parse(state.contextJson);
        } catch {
          setState((s) => ({
            ...s,
            step: 'error',
            errorMessage: 'Context must be valid JSON.',
          }));
          return;
        }
      }
      uploadDoc.mutate(
        {
          file: state.file,
          paper_origin: state.paperOrigin,
          contract_type: state.contractType || undefined,
          party_role: state.partyRole || undefined,
          context,
        },
        {
          onSuccess: (data) => {
            setState((s) => ({
              ...s,
              step: 'done',
              done: {
                contractId: data.contract_id,
                clauseCount: data.clauses.length,
                counterpartyDetected: !!data.counterparty_id,
              },
            }));
          },
          onError: (err) => {
            setState((s) => ({
              ...s,
              step: 'error',
              errorMessage: err instanceof Error ? err.message : 'Upload failed. Please try again.',
            }));
          },
        }
      );
    } else {
      uploadReview.mutate(
        { file: state.file, paper_origin: state.paperOrigin },
        {
          onSuccess: (data) => {
            setState((s) => ({ ...s, step: 'polling', runId: data.id }));
          },
          onError: (err) => {
            setState((s) => ({
              ...s,
              step: 'error',
              errorMessage: err instanceof Error ? err.message : 'Upload failed. Please try again.',
            }));
          },
        }
      );
    }
  }

  function handleOpenContract() {
    if (!state.done?.contractId) return;
    router.push(`/contracts/${state.done.contractId}`);
    handleDismiss();
  }

  function handleDismiss() {
    onClose();
    if (state.step !== 'submitting' && state.step !== 'polling') {
      setState(INITIAL);
      uploadDoc.reset();
      uploadReview.reset();
    }
  }

  function handleReset() {
    uploadDoc.reset();
    uploadReview.reset();
    setState(INITIAL);
  }

  return (
    <SlideOver
      open={open}
      onOpenChange={(o) => {
        if (!o) handleDismiss();
      }}
      title="New Contract"
      description={
        state.step === 'upload'
          ? 'Upload a PDF or DOCX to begin processing.'
          : state.step === 'mode'
            ? 'Choose how to process this contract.'
            : undefined
      }
    >
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
        {/* ── Step 1: Upload + paper origin ── */}
        {state.step === 'upload' && (
          <>
            <div
              role="button"
              tabIndex={0}
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => document.getElementById('intake-file-input')?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ')
                  document.getElementById('intake-file-input')?.click();
              }}
              className={cn(
                'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-border p-8 text-center transition-colors hover:border-primary/50 hover:bg-muted/20',
                state.file && 'border-primary/40 bg-primary/5'
              )}
            >
              <input
                id="intake-file-input"
                type="file"
                accept=".pdf,.docx"
                className="sr-only"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFileSelect(f);
                }}
              />
              {state.file ? (
                <>
                  <FileText className="size-8 text-primary" />
                  <div>
                    <p className="text-sm font-medium">{state.file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(state.file.size / 1024).toFixed(0)} KB
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setState((s) => ({ ...s, file: null }));
                    }}
                    className="text-xs text-muted-foreground underline hover:text-foreground"
                  >
                    Remove
                  </button>
                </>
              ) : (
                <>
                  <UploadCloud className="size-8 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">Drop PDF or DOCX here</p>
                    <p className="text-xs text-muted-foreground">or click to browse</p>
                  </div>
                </>
              )}
            </div>

            <div className="space-y-1.5">
              <p className="text-sm font-medium">Paper origin</p>
              <div className="flex gap-2">
                {(['own', 'counterparty'] as const).map((origin) => (
                  <button
                    key={origin}
                    type="button"
                    onClick={() => setState((s) => ({ ...s, paperOrigin: origin }))}
                    className={cn(
                      'flex-1 rounded-md border px-3 py-2 text-sm font-medium capitalize transition-colors',
                      state.paperOrigin === origin
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border hover:bg-muted/40'
                    )}
                  >
                    {origin}
                  </button>
                ))}
              </div>
            </div>

            {/* Contract type, party role and context (task 4.9 item 6 — wired
                to the optional POST /documents form fields). */}
            <div className="space-y-1.5">
              <p className="text-sm font-medium">
                Contract type <span className="text-xs font-normal text-muted-foreground">(optional)</span>
              </p>
              <input
                value={state.contractType}
                onChange={(e) => setState((s) => ({ ...s, contractType: e.target.value }))}
                placeholder="e.g. nda, saas_msa, dpa"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50"
              />
            </div>

            <div className="space-y-1.5">
              <p className="text-sm font-medium">
                Party role <span className="text-xs font-normal text-muted-foreground">(optional)</span>
              </p>
              <div className="flex gap-2">
                {PARTY_ROLE_OPTIONS.map((role) => (
                  <button
                    key={role}
                    type="button"
                    onClick={() =>
                      setState((s) => ({ ...s, partyRole: s.partyRole === role ? '' : role }))
                    }
                    className={cn(
                      'flex-1 rounded-md border px-3 py-2 text-sm font-medium capitalize transition-colors',
                      state.partyRole === role
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border hover:bg-muted/40'
                    )}
                  >
                    {role}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <p className="text-sm font-medium">
                Context <span className="text-xs font-normal text-muted-foreground">(optional, JSON)</span>
              </p>
              <input
                value={state.contextJson}
                onChange={(e) => setState((s) => ({ ...s, contextJson: e.target.value }))}
                placeholder='{"deal_value_band": "mid", "regimes": ["hipaa"]}'
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50"
              />
              {state.mode === 'review' && (state.contractType || state.partyRole || state.contextJson) && (
                <p className="text-xs text-amber-600">
                  Contract type, party role and context only apply to &ldquo;Process only&rdquo; uploads.
                </p>
              )}
            </div>

            <div className="mt-auto">
              <Button
                className="w-full"
                disabled={!state.file}
                onClick={() => setState((s) => ({ ...s, step: 'mode' }))}
              >
                Continue
              </Button>
            </div>
          </>
        )}

        {/* ── Step 2: Mode selection ── */}
        {state.step === 'mode' && (
          <>
            <div className="space-y-2">
              {MODE_OPTIONS.map(({ value, label, description }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setState((s) => ({ ...s, mode: value }))}
                  className={cn(
                    'w-full rounded-md border p-3 text-left transition-colors',
                    state.mode === value
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:bg-muted/30'
                  )}
                >
                  <p className="text-sm font-medium">{label}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
                </button>
              ))}
            </div>

            <div className="mt-auto flex gap-2">
              <Button
                variant="outline"
                onClick={() => setState((s) => ({ ...s, step: 'upload' }))}
              >
                Back
              </Button>
              <Button className="flex-1" onClick={handleSubmit}>
                Submit
              </Button>
            </div>
          </>
        )}

        {/* ── Submitting / Polling ── */}
        {(state.step === 'submitting' || state.step === 'polling') && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 py-12">
            <div className="size-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <div className="text-center">
              <p className="text-sm font-medium">
                {state.step === 'submitting'
                  ? 'Uploading & processing…'
                  : 'Running autonomous review…'}
              </p>
              {state.file && (
                <p className="mt-1 text-xs text-muted-foreground">{state.file.name}</p>
              )}
            </div>
            <p className="max-w-xs text-center text-xs text-muted-foreground">
              You can close this panel — processing continues in the background.
            </p>
          </div>
        )}

        {/* ── Done ── */}
        {state.step === 'done' && state.done && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 py-12 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-primary/10">
              <svg
                className="size-6 text-primary"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold">Contract processed</p>
              {state.done.clauseCount !== undefined && (
                <p className="text-xs text-muted-foreground">
                  {state.done.clauseCount} clauses extracted
                </p>
              )}
              {state.done.counterpartyDetected && (
                <p className="text-xs text-muted-foreground">Counterparty detected</p>
              )}
              {state.done.gateDecision && (
                <p className="text-xs capitalize text-muted-foreground">
                  Gate: {state.done.gateDecision.replace('_', ' ')}
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <Button onClick={handleOpenContract}>Open contract</Button>
              <Button variant="outline" onClick={handleReset}>
                New upload
              </Button>
            </div>
          </div>
        )}

        {/* ── Error ── */}
        {state.step === 'error' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 py-12 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-destructive/10">
              <X className="size-6 text-destructive" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold">Something went wrong</p>
              <p className="max-w-xs text-xs text-muted-foreground">{state.errorMessage}</p>
            </div>
            <Button variant="outline" onClick={handleReset}>
              Try again
            </Button>
          </div>
        )}
      </div>
    </SlideOver>
  );
}
