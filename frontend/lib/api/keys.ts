import type { AlertFilters, ContractFilters, FlagFilters } from './types';

export const keys = {
  // S1 Documents
  contract: (id: string) => ['contract', id] as const,
  contractClauses: (id: string) => ['contract', id, 'clauses'] as const,
  contractText: (id: string) => ['contract', id, 'text'] as const,

  // S7 Repository & Search
  contracts: (filters?: ContractFilters) => ['contracts', filters ?? null] as const,
  contractSearch: (q: string) => ['contracts', 'search', q] as const,
  contractFacetedSearch: (params: Record<string, unknown>) =>
    ['contracts', 'search', 'faceted', params] as const,
  redlineHistory: (contractId: string) => ['contract', contractId, 'redline-history'] as const,
  versions: (contractId: string) => ['contract', contractId, 'versions'] as const,
  precedentSearch: (clauseType: string, query: string) =>
    ['precedent', clauseType, query] as const,

  // S6 Playbooks & Rules
  playbooks: () => ['playbooks'] as const,
  playbook: (id: string) => ['playbook', id] as const,
  playbookRules: (id: string) => ['playbook', id, 'rules'] as const,
  playbookVersions: (playbookId: string) => ['playbook', playbookId, 'versions'] as const,
  resolvedRules: (params: {
    contract_type: string;
    party_role?: string;
    paper_origin?: string;
    context?: Record<string, unknown>;
  }) => ['resolve', params] as const,

  // Rule children (task 4.8 / 4.9)
  rulePositions: (ruleId: string) => ['rule', ruleId, 'positions'] as const,
  ruleParameters: (ruleId: string) => ['rule', ruleId, 'parameters'] as const,
  ruleRedLines: (ruleId: string) => ['rule', ruleId, 'red-lines'] as const,
  ruleObjections: (ruleId: string) => ['rule', ruleId, 'objections'] as const,
  ruleTestCases: (ruleId: string) => ['rule', ruleId, 'test-cases'] as const,

  // S2 Analysis
  analysis: (contractId: string) => ['analysis', contractId] as const,
  flags: (contractId: string, filters?: FlagFilters) =>
    ['flags', contractId, filters ?? null] as const,

  // S3 Redlines
  redlines: (contractId: string) => ['redlines', contractId] as const,

  // S5 Intelligence
  navigation: (contractId: string) => ['navigation', contractId] as const,

  // S8 Obligations
  obligations: (contractId: string) => ['obligations', contractId] as const,
  // prefix key — cancelQueries/setQueriesData match on ['alerts']
  alerts: (filters?: AlertFilters) => ['alerts', filters ?? null] as const,

  // S9 Analytics
  analyticsIntelligence: () => ['analytics', 'intelligence'] as const,
  portfolioRisk: () => ['analytics', 'portfolio-risk'] as const,
  contractValue: () => ['analytics', 'contract-value'] as const,
  analyticsTabular: (columns?: string[]) => ['analytics', 'tabular', columns ?? null] as const,
  renewals: () => ['analytics', 'renewals'] as const,

  // Review Pipeline
  reviewRuns: () => ['review-runs'] as const,
  reviewRun: (runId: string) => ['review-run', runId] as const,

  // Version Comparison
  versionDiff: (contractId: string, vA: string, vB: string) =>
    ['version-diff', contractId, vA, vB] as const,

  // Health
  health: () => ['health'] as const,
} as const;
