'use client';

import {
  HoverCard as HoverCardRoot,
  HoverCardTrigger,
  HoverCardContent,
} from '@/components/ui/hover-card';
import type { PlaybookRule, ContractDetail } from '@/lib/api/types';
import { cn } from '@/lib/utils';

type HoverCardVariant =
  | { variant: 'rule'; rule: PlaybookRule }
  | { variant: 'citation'; char_start: number; char_end: number; text: string }
  | { variant: 'contract-meta'; contract: ContractDetail }
  | { variant: 'counterparty'; name: string; acceptanceRate?: number }
  | { variant: 'custom'; children: React.ReactNode };

interface HoverCardProps {
  trigger: React.ReactNode;
  content: HoverCardVariant;
  side?: 'top' | 'bottom' | 'left' | 'right';
  className?: string;
}

function RuleContent({ rule }: { rule: PlaybookRule }) {
  const positions = rule.positions ?? [];
  const preferred = positions.find((p) => p.kind === 'preferred') ?? positions.find((p) => p.rung === 0);
  const fallbacks = positions
    .filter((p) => p.kind === 'fallback')
    .sort((a, b) => (a.rung ?? 0) - (b.rung ?? 0));
  const redLines = rule.red_lines ?? [];

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {rule.clause_type}
      </div>
      {preferred && <p className="text-sm leading-snug">{preferred.language}</p>}
      {fallbacks.map((f) => (
        <p key={f.id} className="text-xs italic text-muted-foreground">
          Fallback{f.rung != null ? ` ${f.rung}` : ''}: {f.language}
        </p>
      ))}
      {redLines.length > 0 && (
        <div>
          <span className="text-xs font-medium text-destructive">Red lines: </span>
          <span className="text-xs text-muted-foreground">
            {redLines.map((r) => r.key).join(', ')}
          </span>
        </div>
      )}
    </div>
  );
}

function CitationContent({
  char_start,
  char_end,
  text,
}: {
  char_start: number;
  char_end: number;
  text: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs text-muted-foreground">
        chars {char_start}–{char_end}
      </div>
      <blockquote className="border-l-2 border-primary pl-2 text-sm italic leading-snug">
        {text}
      </blockquote>
    </div>
  );
}

function ContractMetaContent({ contract }: { contract: ContractDetail }) {
  const metadata = contract.metadata;
  const counterparty = contract.parties.find((p) => p.role === 'counterparty');
  return (
    <div className="space-y-1.5">
      <div className="text-sm font-medium leading-tight">{contract.title}</div>
      <div className="space-y-0.5 text-xs text-muted-foreground">
        <div>Status: {contract.status}</div>
        {counterparty && <div>Counterparty: {counterparty.name}</div>}
        {metadata?.effective_date && <div>Effective: {metadata.effective_date}</div>}
        {metadata?.expiry_date && <div>Expires: {metadata.expiry_date}</div>}
        {metadata?.governing_law && <div>Law: {metadata.governing_law}</div>}
      </div>
    </div>
  );
}

function CounterpartyContent({
  name,
  acceptanceRate,
}: {
  name: string;
  acceptanceRate?: number;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-sm font-medium">{name}</div>
      {acceptanceRate !== undefined && (
        <div className="text-xs text-muted-foreground">
          Acceptance rate:{' '}
          <span
            className={cn(
              'font-medium',
              acceptanceRate >= 0.7 ? 'text-foreground' : 'text-destructive'
            )}
          >
            {Math.round(acceptanceRate * 100)}%
          </span>
        </div>
      )}
    </div>
  );
}

export function HoverCard({ trigger, content, side = 'bottom', className }: HoverCardProps) {
  return (
    <HoverCardRoot>
      <HoverCardTrigger className="cursor-default">{trigger}</HoverCardTrigger>
      <HoverCardContent side={side} className={cn('w-72', className)}>
        {content.variant === 'rule' && <RuleContent rule={content.rule} />}
        {content.variant === 'citation' && (
          <CitationContent
            char_start={content.char_start}
            char_end={content.char_end}
            text={content.text}
          />
        )}
        {content.variant === 'contract-meta' && (
          <ContractMetaContent contract={content.contract} />
        )}
        {content.variant === 'counterparty' && (
          <CounterpartyContent name={content.name} acceptanceRate={content.acceptanceRate} />
        )}
        {content.variant === 'custom' && content.children}
      </HoverCardContent>
    </HoverCardRoot>
  );
}
