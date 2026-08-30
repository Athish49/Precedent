'use client';

import { useState } from 'react';
import { ChevronLeft, ChevronRight, Copy, Check, Edit2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { Redline, DiffChangeType } from '@/lib/api/types';
import { redlineStatusTokens } from '@/lib/tokens';
import { cn } from '@/lib/utils';

interface DiffSpan {
  type: DiffChangeType;
  text: string;
  original?: string;
}

function parseDiffSpans(tracked: Record<string, unknown>): DiffSpan[] {
  const raw = tracked.spans;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((s): DiffSpan[] => {
    if (typeof s !== 'object' || s === null) return [];
    const span = s as Record<string, unknown>;
    const type = span.type as DiffChangeType | undefined;
    const text = typeof span.text === 'string' ? span.text : '';
    if (!type || !text) return [];
    return [
      {
        type,
        text,
        original: typeof span.original === 'string' ? span.original : undefined,
      },
    ];
  });
}

function DiffView({ spans }: { spans: DiffSpan[] }) {
  return (
    <p className="text-sm leading-relaxed">
      {spans.map((span, i) => {
        if (span.type === 'delete') {
          return (
            <span key={i} className="bg-destructive/10 text-destructive/80 line-through">
              {span.text}
            </span>
          );
        }
        if (span.type === 'insert') {
          return (
            <span key={i} className="bg-primary/10 text-foreground underline decoration-primary">
              {span.text}
            </span>
          );
        }
        return (
          <span key={i}>
            {span.original && (
              <span className="bg-destructive/10 text-destructive/80 line-through">
                {span.original}
              </span>
            )}
            <span className="bg-primary/10 text-foreground underline decoration-primary">
              {span.text}
            </span>
          </span>
        );
      })}
    </p>
  );
}

const STANCE_LABELS: Record<string, string> = {
  light: 'Light',
  balanced: 'Balanced',
  firm: 'Firm',
};

interface RedlineBlockProps {
  redline: Redline;
  onSelect?: (clauseId: string) => void;
  onToggleFallback?: () => void;
  onRefine?: (instruction: string) => void;
  onAccept?: () => void;
  onReject?: () => void;
  onAcceptWithEdit?: (finalText: string) => void;
  className?: string;
}

export function RedlineBlock({
  redline,
  onSelect,
  onToggleFallback,
  onRefine,
  onAccept,
  onReject,
  onAcceptWithEdit,
  className,
}: RedlineBlockProps) {
  const [altIndex, setAltIndex] = useState(0);
  const [copied, setCopied] = useState(false);
  const [refineOpen, setRefineOpen] = useState(false);
  const [refineText, setRefineText] = useState('');
  const [editOpen, setEditOpen] = useState(false);
  const [editText, setEditText] = useState(redline.replacement_text);

  const spans = parseDiffSpans(redline.tracked_changes);
  const statusToken = redlineStatusTokens[redline.status];
  const alternatives = redline.alternatives ?? [];
  const hasAlts = alternatives.length > 0;
  const isSettled = redline.status === 'accepted' || redline.status === 'rejected';

  function handleCopyComment() {
    navigator.clipboard.writeText(redline.counterparty_comment).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  function handleRefineSubmit() {
    const trimmed = refineText.trim();
    if (!trimmed) return;
    onRefine?.(trimmed);
    setRefineText('');
    setRefineOpen(false);
  }

  function handleAcceptWithEdit() {
    onAcceptWithEdit?.(editText);
    setEditOpen(false);
  }

  return (
    <div
      className={cn('rounded-md border border-border bg-card text-card-foreground', className)}
      onClick={() => onSelect?.(redline.clause_id)}
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Badge variant={statusToken.variant} className="shrink-0">
          {statusToken.label}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {STANCE_LABELS[redline.stance_mode] ?? redline.stance_mode}
        </span>
        <span className="ml-auto text-xs capitalize text-muted-foreground">
          {redline.position}
        </span>
      </div>

      {/* Diff / replacement */}
      <div className="px-3 py-2">
        {spans.length > 0 ? (
          <DiffView spans={spans} />
        ) : (
          <p className="text-sm leading-relaxed">{redline.replacement_text}</p>
        )}
      </div>

      {/* Explanation */}
      {redline.explanation && (
        <div className="border-t border-border bg-muted/30 px-3 py-1.5 text-xs leading-snug text-muted-foreground">
          {redline.explanation}
        </div>
      )}

      {/* Counterparty comment */}
      {redline.counterparty_comment && (
        <div className="flex items-start gap-2 border-t border-border px-3 py-1.5">
          <p className="flex-1 text-xs italic leading-snug text-muted-foreground">
            {redline.counterparty_comment}
          </p>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleCopyComment();
            }}
            className="shrink-0 text-muted-foreground hover:text-foreground"
            aria-label="Copy counterparty comment"
          >
            {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          </button>
        </div>
      )}

      {/* Alternatives cycler */}
      {hasAlts && (
        <div className="flex items-center gap-2 border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
          <span>
            Alt {altIndex + 1}/{alternatives.length}
          </span>
          <button
            type="button"
            aria-label="Previous alternative"
            disabled={altIndex === 0}
            onClick={(e) => {
              e.stopPropagation();
              setAltIndex((i) => Math.max(0, i - 1));
            }}
            className="disabled:opacity-30"
          >
            <ChevronLeft className="size-3.5" />
          </button>
          <button
            type="button"
            aria-label="Next alternative"
            disabled={altIndex === alternatives.length - 1}
            onClick={(e) => {
              e.stopPropagation();
              setAltIndex((i) => Math.min(alternatives.length - 1, i + 1));
            }}
            className="disabled:opacity-30"
          >
            <ChevronRight className="size-3.5" />
          </button>
          {onToggleFallback && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleFallback();
              }}
              className="ml-auto text-xs text-primary hover:underline"
            >
              {redline.position === 'fallback' ? 'Use preferred' : 'Use fallback'}
            </button>
          )}
        </div>
      )}

      {/* Action controls */}
      {!isSettled && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-border px-3 py-2">
          <Button
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              onAccept?.();
            }}
          >
            Accept
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className="h-6 px-2 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              onReject?.();
            }}
          >
            Reject
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              setEditOpen((o) => !o);
              setEditText(redline.replacement_text);
            }}
          >
            <Edit2 className="mr-1 size-3" />
            Edit
          </Button>
          {onRefine && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                setRefineOpen((o) => !o);
              }}
            >
              <RefreshCw className="mr-1 size-3" />
              Refine
            </Button>
          )}
        </div>
      )}

      {/* Accept-with-edit panel */}
      {editOpen && (
        <div
          className="space-y-1.5 border-t border-border px-3 pb-2 pt-2"
          onClick={(e) => e.stopPropagation()}
        >
          <textarea
            className="w-full resize-none rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            rows={3}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
          />
          <div className="flex gap-1.5">
            <Button size="sm" className="h-6 px-2 text-xs" onClick={handleAcceptWithEdit}>
              Accept with edit
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-xs"
              onClick={() => setEditOpen(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Refine panel */}
      {refineOpen && (
        <div
          className="space-y-1.5 border-t border-border px-3 pb-2 pt-2"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="text"
            className="w-full rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="Refinement instruction…"
            value={refineText}
            onChange={(e) => setRefineText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRefineSubmit();
            }}
          />
          <div className="flex gap-1.5">
            <Button size="sm" className="h-6 px-2 text-xs" onClick={handleRefineSubmit}>
              Refine
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-xs"
              onClick={() => setRefineOpen(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
