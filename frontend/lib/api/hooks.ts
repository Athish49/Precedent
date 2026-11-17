'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './client';
import { keys } from './keys';
import type {
  Alert,
  AlertFilters,
  AnalysisResult,
  AnalyticsIntelligence,
  AnalyticsTabular,
  ChangeSet,
  Clause,
  ComplianceCheckResult,
  Contract,
  ContractFilters,
  ContractMetadata,
  ContractValue,
  CreatePlaybookBody,
  CreateRuleBody,
  DiffSummaryResult,
  DraftClauseBody,
  DraftDocumentBody,
  DraftMemoBody,
  DraftPrecedentBody,
  DraftResult,
  EasyPromptBody,
  EasyPromptResult,
  FlagFilters,
  HealthStatus,
  NavIndexEntry,
  Obligation,
  Paginated,
  PaperOrigin,
  Playbook,
  PlaybookRule,
  PortfolioRisk,
  PrecedentClause,
  PrecedentDraftResult,
  ProcessedContract,
  QABody,
  QAResult,
  Redline,
  RedlineDecisionBody,
  RedlineHistoryItem,
  RenewalRow,
  ResearchBody,
  ResearchResult,
  ResolvedRule,
  ReviewRun,
  SmartSearchResult,
  StanceMode,
  SummarizeResult,
  ContractRow,
  UpdatePlaybookBody,
  UpdateRuleBody,
  Version,
  VersionRelation,
} from './types';

// ─── S1 Documents ─────────────────────────────────────────────────────────────

export function useContract(id: string) {
  return useQuery({
    queryKey: keys.contract(id),
    queryFn: () =>
      apiFetch<Contract & { metadata: ContractMetadata }>(`/documents/${id}`),
    enabled: !!id,
  });
}

export function useContractClauses(id: string) {
  return useQuery({
    queryKey: keys.contractClauses(id),
    queryFn: () => apiFetch<Clause[]>(`/documents/${id}/clauses`),
    enabled: !!id,
  });
}

export function useContractText(id: string) {
  return useQuery({
    queryKey: keys.contractText(id),
    queryFn: () => apiFetch<{ canonical_text: string }>(`/documents/${id}/text`),
    enabled: !!id,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, paper_origin }: { file: File; paper_origin: PaperOrigin }) => {
      const form = new FormData();
      form.append('file', file);
      form.append('paper_origin', paper_origin);
      return apiFetch<ProcessedContract>('/documents', { method: 'POST', body: form });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
}

// ─── S7 Repository & Search ───────────────────────────────────────────────────

export function useContracts(filters?: ContractFilters) {
  return useQuery({
    queryKey: keys.contracts(filters),
    queryFn: () =>
      apiFetch<Paginated<ContractRow>>('/repository/contracts', {
        params: filters as Record<string, string | number | boolean | undefined | null>,
      }),
  });
}

export function useContractSearch(q: string) {
  return useQuery({
    queryKey: keys.contractSearch(q),
    queryFn: () =>
      apiFetch<Paginated<ContractRow>>('/repository/search', { params: { q } }),
    enabled: q.length > 0,
  });
}

export function useSmartSearch() {
  return useMutation({
    mutationFn: (query: string) =>
      apiFetch<SmartSearchResult>('/repository/smart-search', {
        method: 'POST',
        body: { query },
      }),
  });
}

export function useRedlineHistory(contractId: string) {
  return useQuery({
    queryKey: keys.redlineHistory(contractId),
    queryFn: () =>
      apiFetch<RedlineHistoryItem[]>(`/repository/contracts/${contractId}/redline-history`),
    enabled: !!contractId,
  });
}

export function useContractVersions(contractId: string) {
  return useQuery({
    queryKey: keys.versions(contractId),
    queryFn: () =>
      apiFetch<Version[]>(`/repository/contracts/${contractId}/versions`),
    enabled: !!contractId,
  });
}

export function useStoreVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      contractId,
      file,
      relation,
    }: {
      contractId: string;
      file: File;
      relation: VersionRelation;
    }) => {
      const form = new FormData();
      form.append('file', file);
      form.append('relation', relation);
      return apiFetch<Version>(`/repository/contracts/${contractId}/versions`, {
        method: 'POST',
        body: form,
      });
    },
    onSuccess: (_data, { contractId }) => {
      queryClient.invalidateQueries({ queryKey: keys.versions(contractId) });
    },
  });
}

export function usePrecedentSearch(clauseType: string, query: string) {
  return useQuery({
    queryKey: keys.precedentSearch(clauseType, query),
    queryFn: () =>
      apiFetch<PrecedentClause[]>('/repository/precedent-search', {
        params: { clause_type: clauseType, query },
      }),
    enabled: !!clauseType && !!query,
  });
}

// ─── S6 Playbooks & Rules ─────────────────────────────────────────────────────

export function usePlaybooks() {
  return useQuery({
    queryKey: keys.playbooks(),
    queryFn: () => apiFetch<Playbook[]>('/playbooks'),
  });
}

export function usePlaybook(id: string) {
  return useQuery({
    queryKey: keys.playbook(id),
    queryFn: () => apiFetch<Playbook & { rules: PlaybookRule[] }>(`/playbooks/${id}`),
    enabled: !!id,
  });
}

export function usePlaybookRules(id: string) {
  return useQuery({
    queryKey: keys.playbookRules(id),
    queryFn: () => apiFetch<PlaybookRule[]>(`/playbooks/${id}/rules`),
    enabled: !!id,
  });
}

export function useResolvedRules(contractType: string) {
  return useQuery({
    queryKey: keys.resolvedRules(contractType),
    queryFn: () =>
      apiFetch<ResolvedRule[]>('/playbooks/resolve', { params: { contract_type: contractType } }),
    enabled: !!contractType,
  });
}

export function useCreatePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePlaybookBody) =>
      apiFetch<Playbook>('/playbooks', { method: 'POST', body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.playbooks() });
    },
  });
}

export function useUpdatePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & UpdatePlaybookBody) =>
      apiFetch<Playbook>(`/playbooks/${id}`, { method: 'PATCH', body }),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: keys.playbook(id) });
      queryClient.invalidateQueries({ queryKey: keys.playbooks() });
    },
  });
}

export function useDeletePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/playbooks/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.playbooks() });
    },
  });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ playbookId, ...body }: { playbookId: string } & CreateRuleBody) =>
      apiFetch<PlaybookRule>(`/playbooks/${playbookId}/rules`, { method: 'POST', body }),
    onSuccess: (_data, { playbookId }) => {
      queryClient.invalidateQueries({ queryKey: keys.playbookRules(playbookId) });
      queryClient.invalidateQueries({ queryKey: keys.playbook(playbookId) });
    },
  });
}

export function useUpdateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { ruleId: string; playbookId: string } & UpdateRuleBody) => {
      const { ruleId, ...body } = vars;
      return apiFetch<PlaybookRule>(`/playbooks/rules/${ruleId}`, { method: 'PATCH', body });
    },
    onSuccess: (_data, { playbookId }) => {
      queryClient.invalidateQueries({ queryKey: keys.playbookRules(playbookId) });
    },
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ruleId }: { ruleId: string; playbookId: string }) =>
      apiFetch<void>(`/playbooks/rules/${ruleId}`, { method: 'DELETE' }),
    onSuccess: (_data, { playbookId }) => {
      queryClient.invalidateQueries({ queryKey: keys.playbookRules(playbookId) });
    },
  });
}

export function useBootstrapPlaybooks() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (corpus: string[]) =>
      apiFetch<{ created_count: number }>('/playbooks/bootstrap', {
        method: 'POST',
        body: { corpus },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.playbooks() });
    },
  });
}

// ─── S2 Analysis ──────────────────────────────────────────────────────────────

export function useAnalysis(contractId: string) {
  return useQuery({
    queryKey: keys.analysis(contractId),
    queryFn: () => apiFetch<AnalysisResult>(`/analysis/${contractId}`),
    enabled: !!contractId,
  });
}

export function useFlags(contractId: string, filters?: FlagFilters) {
  return useQuery({
    queryKey: keys.flags(contractId, filters),
    queryFn: () =>
      apiFetch<AnalysisResult['flags']>(`/analysis/${contractId}/flags`, {
        params: filters as Record<string, string | undefined>,
      }),
    enabled: !!contractId,
  });
}

export function useRunAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contractId: string) =>
      apiFetch<AnalysisResult>(`/analysis/${contractId}`, { method: 'POST' }),
    onSuccess: (_data, contractId) => {
      queryClient.invalidateQueries({ queryKey: keys.analysis(contractId) });
      queryClient.invalidateQueries({ queryKey: ['flags', contractId] });
    },
  });
}

// ─── S3 Redlines ──────────────────────────────────────────────────────────────

export function useRedlines(contractId: string) {
  return useQuery({
    queryKey: keys.redlines(contractId),
    queryFn: () => apiFetch<Redline[]>(`/redlines/${contractId}`),
    enabled: !!contractId,
  });
}

export function useGenerateRedlines() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ contractId, stance_mode }: { contractId: string; stance_mode: StanceMode }) =>
      apiFetch<Redline[]>(`/redlines/${contractId}`, {
        method: 'POST',
        body: { stance_mode },
      }),
    onSuccess: (_data, { contractId }) => {
      queryClient.invalidateQueries({ queryKey: keys.redlines(contractId) });
    },
  });
}

export function useToggleFallback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ redlineId }: { redlineId: string; contractId: string }) =>
      apiFetch<Redline>(`/redlines/${redlineId}/toggle-fallback`, { method: 'POST' }),
    onMutate: async ({ redlineId, contractId }) => {
      await queryClient.cancelQueries({ queryKey: keys.redlines(contractId) });
      const previous = queryClient.getQueryData<Redline[]>(keys.redlines(contractId));
      queryClient.setQueryData<Redline[]>(keys.redlines(contractId), (old) =>
        old?.map((r) =>
          r.id === redlineId
            ? { ...r, position: r.position === 'preferred' ? 'fallback' : 'preferred' }
            : r,
        ),
      );
      return { previous };
    },
    onError: (_err, { contractId }, context) => {
      if (context?.previous) {
        queryClient.setQueryData(keys.redlines(contractId), context.previous);
      }
    },
    onSettled: (_data, _err, { contractId }) => {
      queryClient.invalidateQueries({ queryKey: keys.redlines(contractId) });
    },
  });
}

export function useRefineRedline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      redlineId,
      instruction,
    }: {
      redlineId: string;
      contractId: string;
      instruction: string;
    }) =>
      apiFetch<Redline>(`/redlines/${redlineId}/refine`, {
        method: 'POST',
        body: { instruction },
      }),
    onSuccess: (_data, { contractId }) => {
      queryClient.invalidateQueries({ queryKey: keys.redlines(contractId) });
    },
  });
}

export function useDecideRedline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      redlineId,
      body,
    }: {
      redlineId: string;
      contractId: string;
      body: RedlineDecisionBody;
    }) =>
      apiFetch<Redline>(`/redlines/${redlineId}/decision`, { method: 'POST', body }),
    onMutate: async ({ redlineId, contractId, body }) => {
      await queryClient.cancelQueries({ queryKey: keys.redlines(contractId) });
      const previous = queryClient.getQueryData<Redline[]>(keys.redlines(contractId));
      queryClient.setQueryData<Redline[]>(keys.redlines(contractId), (old) =>
        old?.map((r) =>
          r.id === redlineId
            ? { ...r, status: body.outcome === 'accepted' ? 'accepted' : 'rejected' }
            : r,
        ),
      );
      return { previous };
    },
    onError: (_err, { contractId }, context) => {
      if (context?.previous) {
        queryClient.setQueryData(keys.redlines(contractId), context.previous);
      }
    },
    onSettled: (_data, _err, { contractId }) => {
      queryClient.invalidateQueries({ queryKey: keys.redlines(contractId) });
    },
  });
}

// ─── S4 Drafting ──────────────────────────────────────────────────────────────

export function useDraftClause() {
  return useMutation({
    mutationFn: (body: DraftClauseBody) =>
      apiFetch<DraftResult>('/drafting/clause', { method: 'POST', body }),
  });
}

export function useDraftDocument() {
  return useMutation({
    mutationFn: (body: DraftDocumentBody) =>
      apiFetch<{ document: string }>('/drafting/document', { method: 'POST', body }),
  });
}

export function useDraftPrecedent() {
  return useMutation({
    mutationFn: (body: DraftPrecedentBody) =>
      apiFetch<PrecedentDraftResult>('/drafting/precedent', { method: 'POST', body }),
  });
}

export function useDraftMemo() {
  return useMutation({
    mutationFn: (body: DraftMemoBody) =>
      apiFetch<{ text: string }>('/drafting/memo', { method: 'POST', body }),
  });
}

// ─── S5 Intelligence ──────────────────────────────────────────────────────────

export function useNavigation(contractId: string) {
  return useQuery({
    queryKey: keys.navigation(contractId),
    queryFn: () => apiFetch<NavIndexEntry[]>(`/intelligence/${contractId}/navigation`),
    enabled: !!contractId,
  });
}

export function useSummarize() {
  return useMutation({
    mutationFn: (contractId: string) =>
      apiFetch<SummarizeResult>(`/intelligence/${contractId}/summarize`, { method: 'POST' }),
  });
}

export function useSummarizeRedlines() {
  return useMutation({
    mutationFn: (contractId: string) =>
      apiFetch<SummarizeResult>(`/intelligence/${contractId}/summarize-redlines`, {
        method: 'POST',
      }),
  });
}

export function useQA() {
  return useMutation({
    mutationFn: ({ contractId, body }: { contractId: string; body: QABody }) =>
      apiFetch<QAResult>(`/intelligence/${contractId}/qa`, { method: 'POST', body }),
  });
}

export function useEasyPrompt() {
  return useMutation({
    mutationFn: ({ contractId, body }: { contractId: string; body: EasyPromptBody }) =>
      apiFetch<EasyPromptResult>(`/intelligence/${contractId}/easy-prompt`, {
        method: 'POST',
        body,
      }),
  });
}

export function useResearch() {
  return useMutation({
    mutationFn: ({ contractId, body }: { contractId: string; body: ResearchBody }) =>
      apiFetch<ResearchResult>(`/intelligence/${contractId}/research`, { method: 'POST', body }),
  });
}

// ─── S8 Obligations ───────────────────────────────────────────────────────────

export function useObligations(contractId: string) {
  return useQuery({
    queryKey: keys.obligations(contractId),
    queryFn: () => apiFetch<Obligation[]>(`/obligations/${contractId}`),
    enabled: !!contractId,
  });
}

export function useExtractObligations() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contractId: string) =>
      apiFetch<Obligation[]>(`/obligations/${contractId}/extract`, { method: 'POST' }),
    onSuccess: (_data, contractId) => {
      queryClient.invalidateQueries({ queryKey: keys.obligations(contractId) });
    },
  });
}

export function useMonitorRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ alerts_fired: number }>('/obligations/monitor/run', { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useComplianceCheck() {
  return useMutation({
    mutationFn: (contractId: string) =>
      apiFetch<ComplianceCheckResult>(`/obligations/${contractId}/compliance-check`, {
        method: 'POST',
      }),
  });
}

export function useAlerts(filters?: AlertFilters) {
  return useQuery({
    queryKey: keys.alerts(filters),
    queryFn: () =>
      apiFetch<Alert[]>('/obligations/alerts', {
        params: {
          type: filters?.type,
          acknowledged:
            filters?.acknowledged !== undefined ? String(filters.acknowledged) : undefined,
        },
      }),
  });
}

export function useAckAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) =>
      apiFetch<Alert>(`/obligations/alerts/${alertId}/ack`, { method: 'POST' }),
    onMutate: async (alertId) => {
      // Cancel all in-flight alert queries (prefix match on ['alerts'])
      await queryClient.cancelQueries({ queryKey: ['alerts'] });
      // Snapshot all cached alert variants
      const snapshots = queryClient.getQueriesData<Alert[]>({ queryKey: ['alerts'] });
      // Optimistically mark acknowledged across all cached variants
      queryClient.setQueriesData<Alert[]>({ queryKey: ['alerts'] }, (old) =>
        old?.map((a) => (a.id === alertId ? { ...a, acknowledged: true } : a)),
      );
      return { snapshots };
    },
    onError: (_err, _alertId, context) => {
      // Roll back all snapshots
      context?.snapshots.forEach(([queryKey, data]) => {
        queryClient.setQueryData(queryKey, data);
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

// ─── S9 Analytics ─────────────────────────────────────────────────────────────

export function useAnalyticsIntelligence() {
  return useQuery({
    queryKey: keys.analyticsIntelligence(),
    queryFn: () => apiFetch<AnalyticsIntelligence>('/analytics/intelligence'),
  });
}

export function usePortfolioRisk() {
  return useQuery({
    queryKey: keys.portfolioRisk(),
    queryFn: () => apiFetch<PortfolioRisk>('/analytics/portfolio-risk'),
  });
}

export function useContractValue() {
  return useQuery({
    queryKey: keys.contractValue(),
    queryFn: () => apiFetch<ContractValue>('/analytics/contract-value'),
  });
}

export function useAnalyticsTabular(columns?: string[]) {
  return useQuery({
    queryKey: keys.analyticsTabular(columns),
    queryFn: () =>
      apiFetch<AnalyticsTabular>('/analytics/tabular', {
        params: columns?.length ? { columns: columns.join(',') } : undefined,
      }),
  });
}

export function useRenewals() {
  return useQuery({
    queryKey: keys.renewals(),
    queryFn: () => apiFetch<RenewalRow[]>('/analytics/renewals'),
  });
}

// ─── Review Pipeline ──────────────────────────────────────────────────────────

export function useReviewRuns() {
  return useQuery({
    queryKey: keys.reviewRuns(),
    queryFn: () => apiFetch<ReviewRun[]>('/review/runs'),
  });
}

export function useReviewRun(runId: string) {
  return useQuery({
    queryKey: keys.reviewRun(runId),
    queryFn: () => apiFetch<ReviewRun>(`/review/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || data.status === 'running') return 3000;
      return false;
    },
  });
}

export function useRunReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contractId: string) =>
      apiFetch<ReviewRun>('/review/run', { method: 'POST', body: { contract_id: contractId } }),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.reviewRun(data.id), data);
    },
  });
}

export function useRunReviewUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, paper_origin }: { file: File; paper_origin: string }) => {
      const form = new FormData();
      form.append('file', file);
      form.append('paper_origin', paper_origin);
      return apiFetch<ReviewRun>('/review/run', { method: 'POST', body: form });
    },
    onSuccess: (data) => {
      queryClient.setQueryData(keys.reviewRun(data.id), data);
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
}

export function useConfigureWebhook() {
  return useMutation({
    mutationFn: (config: Record<string, unknown>) =>
      apiFetch<void>('/review/webhook', { method: 'POST', body: config }),
  });
}

// ─── Version Comparison ───────────────────────────────────────────────────────

export function useVersionDiff(contractId: string, vA: string, vB: string) {
  return useQuery({
    queryKey: keys.versionDiff(contractId, vA, vB),
    queryFn: () =>
      apiFetch<ChangeSet>('/versions/diff', {
        params: { contract_id: contractId, v_a: vA, v_b: vB },
      }),
    enabled: !!contractId && !!vA && !!vB,
  });
}

export function useDiffSummary() {
  return useMutation({
    mutationFn: ({
      contractId,
      vA,
      vB,
    }: {
      contractId: string;
      vA: string;
      vB: string;
    }) =>
      apiFetch<DiffSummaryResult>('/versions/diff/summary', {
        method: 'POST',
        body: { contract_id: contractId, v_a: vA, v_b: vB },
      }),
  });
}

// ─── Health ───────────────────────────────────────────────────────────────────

export function useHealth() {
  return useQuery({
    queryKey: keys.health(),
    queryFn: () => apiFetch<HealthStatus>('/health'),
    staleTime: 30_000,
  });
}
