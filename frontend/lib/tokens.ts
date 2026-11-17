import type {
  ContractStatus,
  RedlineStatus,
  Severity,
  FlagType,
  AlertType,
  GateDecision,
  ProvenanceSource,
} from '@/lib/api/types';

export type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'ghost';

export interface StatusToken {
  label: string;
  variant: BadgeVariant;
  icon: string;
}

export interface SeverityToken {
  label: string;
  variant: BadgeVariant;
  icon: string;
  weight: 'low' | 'medium' | 'high';
}

export interface FlagTypeToken {
  label: string;
  icon: string;
}

export interface AlertTypeToken {
  label: string;
  icon: string;
  variant: BadgeVariant;
}

export interface GateDecisionToken {
  label: string;
  variant: BadgeVariant;
  icon: string;
}

export interface ProvenanceToken {
  label: string;
  icon: string;
}

export const contractStatusTokens: Record<ContractStatus, StatusToken> = {
  processing: { label: 'Processing', variant: 'outline', icon: 'Loader2' },
  analyzed: { label: 'Analyzed', variant: 'default', icon: 'CheckCircle2' },
  redlined: { label: 'Redlined', variant: 'secondary', icon: 'Pencil' },
  executed: { label: 'Executed', variant: 'default', icon: 'BadgeCheck' },
};

export const redlineStatusTokens: Record<RedlineStatus, StatusToken> = {
  proposed: { label: 'Proposed', variant: 'outline', icon: 'Clock' },
  accepted: { label: 'Accepted', variant: 'default', icon: 'CheckCircle2' },
  rejected: { label: 'Rejected', variant: 'destructive', icon: 'XCircle' },
  auto_applied: { label: 'Auto-applied', variant: 'secondary', icon: 'Zap' },
  escalated: { label: 'Escalated', variant: 'ghost', icon: 'ArrowUpCircle' },
};

export const severityTokens: Record<Severity, SeverityToken> = {
  low: { label: 'Low', variant: 'secondary', icon: 'ArrowDown', weight: 'low' },
  medium: { label: 'Medium', variant: 'outline', icon: 'ArrowRight', weight: 'medium' },
  high: { label: 'High', variant: 'destructive', icon: 'ArrowUp', weight: 'high' },
};

export const flagTypeTokens: Record<FlagType, FlagTypeToken> = {
  missing: { label: 'Missing', icon: 'FileMinus' },
  prohibited: { label: 'Prohibited', icon: 'Ban' },
  non_standard: { label: 'Non-Standard', icon: 'ShieldAlert' },
  high_risk: { label: 'High Risk', icon: 'Shield' },
  vague: { label: 'Vague', icon: 'HelpCircle' },
  inconsistent: { label: 'Inconsistent', icon: 'AlertTriangle' },
  deviation: { label: 'Deviation', icon: 'GitBranch' },
};

export const alertTypeTokens: Record<AlertType, AlertTypeToken> = {
  deadline: { label: 'Deadline', icon: 'CalendarX2', variant: 'destructive' },
  renewal: { label: 'Renewal', icon: 'RefreshCcw', variant: 'outline' },
  compliance_pass: { label: 'Compliance Pass', icon: 'CheckCircle2', variant: 'default' },
  compliance_fail: { label: 'Compliance Fail', icon: 'XCircle', variant: 'destructive' },
};

export const gateDecisionTokens: Record<GateDecision, GateDecisionToken> = {
  auto_applied: { label: 'Auto-applied', variant: 'default', icon: 'Zap' },
  escalated: { label: 'Escalated', variant: 'outline', icon: 'ArrowUpCircle' },
};

export const provenanceTokens: Record<ProvenanceSource, ProvenanceToken> = {
  playbook: { label: 'Playbook', icon: 'BookOpen' },
  frequency: { label: 'Frequency', icon: 'BarChart2' },
  llm: { label: 'AI', icon: 'Sparkles' },
  ai: { label: 'AI', icon: 'Sparkles' },
};
