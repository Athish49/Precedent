// ─── Enums ────────────────────────────────────────────────────────────────────

export type PaperOrigin = 'own' | 'counterparty';
export type ContractStatus = 'processing' | 'analyzed' | 'redlined' | 'executed';
export type Severity = 'low' | 'medium' | 'high';
export type FlagType =
  | 'missing'
  | 'prohibited'
  | 'non_standard'
  | 'high_risk'
  | 'vague'
  | 'inconsistent'
  | 'deviation';
export type FlagSource = 'deterministic' | 'llm';
export type RedlineStatus = 'proposed' | 'accepted' | 'rejected' | 'auto_applied' | 'escalated';
export type RedlinePosition = 'preferred' | 'fallback';
export type StanceMode = 'light' | 'balanced' | 'firm';
export type AlertType = 'deadline' | 'renewal' | 'compliance_pass' | 'compliance_fail';
export type GateDecision = 'auto_applied' | 'escalated';
export type VersionRelation = 'version' | 'amendment' | 'addendum';
export type ObligationStatus = 'open' | 'met' | 'overdue';
export type DraftSource = 'playbook' | 'frequency' | 'llm';
export type PracticeArea = 'hipaa' | 'gdpr' | 'saas_msa' | 'nda' | 'dpa';
export type ReviewRunStatus = 'running' | 'completed' | 'failed';
export type ReviewRunTrigger = 'manual' | 'upload_event';
export type DiffChangeType = 'insert' | 'delete' | 'modify';
export type ProvenanceSource = 'playbook' | 'frequency' | 'llm' | 'ai';

// ─── Shared ───────────────────────────────────────────────────────────────────

export interface Paginated<T> {
  items: T[];
  total: number;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: unknown;
}

// ─── Domain objects ───────────────────────────────────────────────────────────

export interface Contract {
  id: string;
  title: string;
  source_format: 'pdf' | 'docx';
  paper_origin: PaperOrigin;
  contract_type?: string;
  counterparty_id?: string;
  current_version_id?: string;
  status: ContractStatus;
  created_at: string;
  updated_at: string;
}

export interface ContractMetadata {
  parties: { name: string; role: string }[];
  effective_date?: string;
  expiry_date?: string;
  governing_law?: string;
  liability_cap?: { value: number; currency: string };
  notice_period_days?: number;
  auto_renewal?: boolean;
  payment_terms?: string;
  financial_fields?: Record<string, unknown>;
  milestone_dates?: string[];
  extracted?: Record<string, unknown>;
}

export interface ContractRow {
  id: string;
  title: string;
  contract_type?: string;
  counterparty_display_name?: string;
  paper_origin: PaperOrigin;
  status: ContractStatus;
  effective_date?: string;
  expiry_date?: string;
  value?: number;
  risk_score?: number;
  max_clause_severity?: Severity;
}

export interface ProcessedContract {
  contract_id: string;
  clauses: Clause[];
  metadata: ContractMetadata;
  paper_origin: PaperOrigin;
  counterparty_id?: string;
}

export interface Clause {
  id: string;
  contract_id: string;
  ordinal: number;
  clause_type: string;
  heading_text: string;
  text: string;
  char_start: number;
  char_end: number;
}

export interface Citation {
  char_start: number;
  char_end: number;
}

export interface Flag {
  id: string;
  contract_id: string;
  clause_id?: string;
  review_run_id?: string;
  flag_type: FlagType;
  severity: Severity;
  source: FlagSource;
  char_start?: number;
  char_end?: number;
  detail: Record<string, unknown>;
  matched_rule_id?: string;
}

export interface Risk {
  score: number;
  max_clause_severity: Severity;
  weights_version?: string;
  per_clause?: { clause_id: string; score: number }[];
}

export interface AnalysisResult {
  flags: Flag[];
  risk: Risk;
}

export interface Redline {
  id: string;
  contract_id: string;
  clause_id: string;
  flag_id?: string;
  review_run_id?: string;
  stance_mode: StanceMode;
  position: RedlinePosition;
  replacement_text: string;
  tracked_changes: Record<string, unknown>;
  alternatives: Record<string, unknown>[];
  explanation: string;
  counterparty_comment: string;
  rationale: Record<string, unknown>;
  status: RedlineStatus;
  created_at: string;
}

export interface RedlineHistoryItem {
  clause_type: string;
  position_offered: RedlinePosition;
  recommended_stance: StanceMode;
  outcome: string;
  final_text?: string;
  created_at: string;
}

export interface Version {
  id: string;
  contract_id: string;
  version_number: number;
  parent_version_id?: string;
  relation: VersionRelation;
  created_at: string;
}

export interface PrecedentClause {
  clause_id: string;
  clause_type: string;
  text: string;
  contract_id: string;
  similarity: number;
}

export interface Playbook {
  id: string;
  name: string;
  practice_area: PracticeArea;
  precedence: number;
}

export interface PlaybookRule {
  id: string;
  playbook_id: string;
  clause_type: string;
  preferred_language: string;
  acceptable_variations: string[];
  prohibited_terms: string[];
  fallback_language?: string;
  required: boolean;
  risk_weight: number;
  escalation_threshold?: number;
}

export interface ResolvedRule extends PlaybookRule {
  source_playbook_id: string;
  source_playbook_name: string;
}

export interface DraftResult {
  text: string;
  source: DraftSource;
}

export interface NavIndexEntry {
  clause_type: string;
  clause_id: string;
  char_start: number;
}

export interface Obligation {
  id: string;
  contract_id: string;
  commitment: string;
  owner: string;
  deadline?: string;
  deliverable: string;
  char_start?: number;
  char_end?: number;
  status: ObligationStatus;
}

export interface Alert {
  id: string;
  contract_id: string;
  alert_type: AlertType;
  payload: Record<string, unknown>;
  fired_at: string;
  acknowledged: boolean;
}

export interface ReviewRun {
  id: string;
  contract_id: string;
  trigger: ReviewRunTrigger;
  gate_decision?: GateDecision;
  gate_reason?: Record<string, unknown>;
  status: ReviewRunStatus;
  started_at: string;
  completed_at?: string;
}

export interface ChangeSet {
  changes: {
    type: DiffChangeType;
    clause_id?: string;
    char_start: number;
    char_end: number;
    text?: string;
  }[];
}

export interface RenewalRow {
  contract_id: string;
  title: string;
  expiry_date: string;
  days_remaining: number;
  risk_score?: number;
  recommendation?: string;
}

// ─── Analytics response types ─────────────────────────────────────────────────

export interface PortfolioRisk {
  total_contracts: number;
  total_high_flags: number;
  total_medium_flags: number;
  total_low_flags: number;
  total_flags: number;
  avg_weighted_flag_score: number | null;
  avg_risk_score: number | null;
  contracts_high_severity: number;
  contracts_medium_severity: number;
  contracts_low_severity: number;
}

export interface ContractValueRow {
  contract_id: string;
  title: string;
  contract_type: string | null;
  counterparty_id: string | null;
  counterparty_name: string | null;
  total_value: string | null;
  currency: string | null;
  annual_value: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  status: ContractStatus;
}

export type ContractValue = ContractValueRow[];

export interface AnalyticsTabular {
  columns: string[];
  rows: Record<string, unknown>[];
}

export type AnalyticsIntelligence = Record<string, unknown>;

export interface HealthStatus {
  db: boolean;
  embedding_model: boolean;
  object_storage: boolean;
}

export interface ComplianceCheckResult {
  pass: boolean;
  issues: Record<string, unknown>[];
}

// ─── Request / filter types ───────────────────────────────────────────────────

export interface ContractFilters {
  contract_type?: string;
  counterparty_id?: string;
  status?: ContractStatus;
  effective_date_from?: string;
  effective_date_to?: string;
  value_min?: number;
  value_max?: number;
  limit?: number;
  offset?: number;
}

export interface FlagFilters {
  flag_type?: FlagType;
  severity?: Severity;
}

export interface AlertFilters {
  type?: AlertType;
  acknowledged?: boolean;
}

export interface SmartSearchResult extends Paginated<ContractRow> {
  filters: Record<string, unknown>;
  semantic_query?: string;
}

export interface CreatePlaybookBody {
  name: string;
  practice_area: PracticeArea;
  precedence: number;
}

export interface UpdatePlaybookBody {
  name?: string;
  precedence?: number;
}

export interface CreateRuleBody {
  clause_type: string;
  preferred_language: string;
  acceptable_variations: string[];
  prohibited_terms: string[];
  fallback_language?: string;
  required: boolean;
  risk_weight: number;
  escalation_threshold?: number;
}

export type UpdateRuleBody = Partial<CreateRuleBody>;

export interface RedlineDecisionBody {
  outcome: 'accepted' | 'rejected';
  final_text?: string;
}

export interface DraftClauseBody {
  clause_type: string;
  context: string;
  mode?: string;
}

export interface DraftDocumentBody {
  template: string;
  variables: Record<string, string>;
  polish?: boolean;
}

export interface DraftPrecedentBody {
  clause_type: string;
  context: string;
}

export interface DraftMemoBody {
  context: string;
}

export interface QABody {
  question: string;
}

export interface QAResult {
  answer: string;
  citations: Citation[];
}

export interface SummarizeResult {
  summary: string;
}

export interface EasyPromptBody {
  instruction: string;
}

export interface EasyPromptResult {
  structured_prompt: string;
  route: 's3' | 's4';
}

export interface ResearchBody {
  query: string;
}

export interface ResearchResult {
  answer: string;
  sources: { title: string; url: string }[];
}

export interface DiffSummaryResult {
  summary: string;
}

export interface PrecedentDraftResult {
  text: string;
  precedents: PrecedentClause[];
}
