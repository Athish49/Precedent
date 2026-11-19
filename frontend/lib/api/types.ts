// ─── Enums ────────────────────────────────────────────────────────────────────

export type PaperOrigin = 'own' | 'counterparty';
export type ContractStatus = 'processing' | 'failed' | 'ready' | 'analyzed' | 'redlined' | 'executed';
export type ContractTypeSource = 'user' | 'extracted';
export type FieldSource = 'extract' | 'derived' | 'user';
export type FieldConfidence = 'high' | 'low';
export type ClauseTypeSource = 'extract' | 'dictionary' | 'none';
export type PartyRole = 'own' | 'counterparty' | 'other';
// `status_reason` values a `failed` contract can carry
// (document_processing_implementation.md section 4.3).
export type DocumentStatusReason =
  | 'password_protected'
  | 'unsupported_format'
  | 'too_large'
  | 'unreadable'
  | 'no_text'
  | 'extraction_failed'
  | 'timeout'
  | 'provider_unavailable'
  | 'storage_failed';
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

// Matches the `contract_metadata` projection columns surfaced by
// `GET /api/documents/{id}` (`metadata`), per
// document_processing_implementation.md section 4.3 / `_METADATA_FIELDS` in
// `backend/app/api/routes/documents.py`. The legacy free-form columns this
// interface used to mirror (see document_processing_implementation.md
// section 4.1, task list item 1, for the full removal list) no longer exist
// on the backend.
export interface ContractMetadata {
  effective_date?: string | null;
  expiry_date?: string | null;
  expiry_is_derived?: boolean | null;
  initial_term_months?: number | null;
  renewal_term_months?: number | null;
  renewal_notice_days?: number | null;
  governing_law?: string | null;
  dispute_resolution?: string | null;
  total_value_amount?: number | null;
  currency?: string | null;
  liability_cap_amount?: number | null;
  liability_cap_basis?: string | null;
  payment_terms_days?: number | null;
  termination_for_convenience?: boolean | null;
  termination_notice_days?: number | null;
}

// `GET /api/documents/{id}` → `parties[]`.
export interface ContractPartyRow {
  party_id: string;
  name: string;
  role: PartyRole | string;
  role_label?: string | null;
  entity_type?: string | null;
  jurisdiction?: string | null;
  address?: string | null;
}

// `GET /api/documents/{id}` → `signatories[]`.
export interface Signatory {
  printed_name?: string | null;
  title?: string | null;
  party_name?: string | null;
  is_signed?: boolean | null;
  signed_date?: string | null;
}

// `GET /api/documents/{id}` → `fields[]` — the value in force per field key
// (`user` over `extract` over `derived`).
export interface ContractField {
  field_key: string;
  value: unknown;
  source: FieldSource | string;
  confidence?: FieldConfidence | string | null;
  quote?: string | null;
  page?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  clause_id?: string | null;
}

// `GET /api/documents/{id}` — the full document detail shape
// (document_processing_implementation.md section 4.3). Replaces the old
// `ProcessedContract` returned synchronously from the upload route; the
// upload route now returns `UploadAcceptedResponse` (202) and this is
// fetched/polled separately.
export interface ContractDetail {
  id: string;
  title: string;
  original_filename?: string | null;
  status: ContractStatus;
  status_reason?: DocumentStatusReason | string | null;
  paper_origin: PaperOrigin;
  source_format: 'pdf' | 'docx';
  contract_type?: string | null;
  contract_type_source?: ContractTypeSource | string | null;
  party_role?: string | null;
  context?: Record<string, unknown> | null;
  counterparty_id?: string | null;
  current_version_id?: string | null;
  page_count?: number | null;
  created_at: string;
  updated_at: string;
  parties: ContractPartyRow[];
  signatories: Signatory[];
  fields: ContractField[];
  metadata: ContractMetadata;
  warnings: string[];
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

// `GET /api/documents/{id}/clauses`. `id` is a real UUID (not the old
// synthetic `c0000`-style string); `clause_key` is a stable UUID that
// survives re-ingestion. The old `ProcessedContract` (returned
// synchronously from `POST /documents`) no longer exists — upload is now
// `202` + poll (see `UploadAcceptedResponse` / `useUploadDocument`).
export interface Clause {
  id: string;
  clause_key: string;
  ordinal: number;
  level: number;
  parent_id?: string | null;
  section_number?: string | null;
  title?: string | null;
  heading_text?: string | null;
  clause_type: string;
  type_source: ClauseTypeSource | string;
  issue_keys: string[];
  text: string;
  char_start: number;
  char_end: number;
  page_start?: number | null;
  page_end?: number | null;
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
  created_at?: string;
  updated_at?: string;
}

// A rule's negotiating language is not a flat field — it lives in child rows
// (see RuleCreate/RuleUpdate below). `positions` carries preferred (kind
// "preferred", rung 0), fallback (kind "fallback", rung 1+) and
// acceptable-variant (kind "acceptable_variant", rung null) language.
// `red_lines` carries rule-scoped red lines, including prohibited phrasing.
export interface PlaybookRule {
  id: string;
  playbook_id: string;
  playbook_version_id?: string | null;
  clause_type: string;
  issue_id?: string | null;
  rule_key?: string | null;
  title?: string | null;
  position_summary?: string | null;
  risk_rationale?: string | null;
  required: boolean;
  negotiable?: boolean | null;
  risk_weight: number;
  default_zone?: Zone | string | null;
  needs_human_judgment?: boolean | null;
  judgment_note?: string | null;
  applies_when?: Record<string, unknown> | null;
  detection_guidance?: string | null;
  source_ref?: string | null;
  authored_by?: string | null;
  approved_by?: string | null;
  last_reviewed_at?: string | null;

  // Children
  positions: RulePosition[];
  parameters: RuleParameter[];
  red_lines: RedLine[];
  objections: RuleObjection[];
  dependencies: RuleDependency[];
  test_cases: RuleTestCase[];
}

// ─── Playbook versions (task 4.8 / 4.9) ───────────────────────────────────────

export type PlaybookVersionStatus = 'draft' | 'published' | 'superseded';

export interface PlaybookVersion {
  id: string;
  playbook_id: string;
  version: string;
  status: PlaybookVersionStatus | string;
  effective_from?: string | null;
  effective_to?: string | null;
  change_summary?: string | null;
  created_by?: string | null;
  approved_by?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateDraftVersionBody {
  version: string;
  created_by?: string;
}

export interface PublishVersionBody {
  change_summary?: string;
  approved_by?: string;
}

// ─── Rule children: positions, parameters, red lines, objections,
// dependencies, test cases (playbook_plan.md sections 3.5–3.10) ──────────────

export type PositionKind = 'preferred' | 'fallback' | 'acceptable_variant';
export type Zone = 'green' | 'yellow' | 'red';

export interface RulePosition {
  id: string;
  rule_id: string;
  kind: PositionKind | string;
  rung?: number | null;
  label: string;
  language: string;
  summary?: string | null;
  zone: Zone | string;
  approver_role_id?: string | null;
  conditions?: Record<string, unknown> | null;
  give_get?: string | null;
  internal_note?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateRulePositionBody {
  kind: PositionKind | string;
  label: string;
  language: string;
  zone: Zone | string;
  rung?: number;
  summary?: string;
  approver_role_id?: string;
  give_get?: string;
  internal_note?: string;
}

// A position written inline with a rule create/update (RuleCreate.positions /
// RuleUpdate.positions). On update, the full `positions` list on the rule is
// a full id-sync: entries with an `id` of an existing position of this rule
// update it in place, entries without an `id` create a new row, and existing
// positions not included in the list are deleted.
export interface RulePositionInput {
  id?: string;
  kind: PositionKind | string;
  rung?: number | null;
  label: string;
  language: string;
  zone: Zone | string;
  summary?: string | null;
  approver_role_id?: string | null;
  conditions?: Record<string, unknown> | null;
  give_get?: string | null;
  internal_note?: string | null;
}

export type ParameterValueType =
  | 'number'
  | 'duration_days'
  | 'percent'
  | 'currency_usd'
  | 'enum'
  | 'boolean';
export type ParameterDirection =
  | 'higher_is_better'
  | 'lower_is_better'
  | 'exact'
  | 'set_membership';

export interface RuleParameter {
  id: string;
  rule_id: string;
  key: string;
  label: string;
  value_type: ParameterValueType | string;
  unit?: string | null;
  direction: ParameterDirection | string;
  preferred_value?: unknown;
  green_limit?: unknown;
  yellow_limit?: unknown;
  allowed_values?: unknown[] | null;
  extraction_hint?: string | null;
  context_overrides?: unknown;
  created_at: string;
  updated_at: string;
}

export interface CreateRuleParameterBody {
  key: string;
  label: string;
  value_type: ParameterValueType | string;
  direction: ParameterDirection | string;
  unit?: string;
  preferred_value?: unknown;
  green_limit?: unknown;
  yellow_limit?: unknown;
  allowed_values?: unknown[];
  extraction_hint?: string;
}

export type RedLineScope = 'rule' | 'playbook' | 'global';
export type RedLineAction = 'block' | 'escalate';

export interface RedLine {
  id: string;
  scope: RedLineScope | string;
  rule_id?: string | null;
  playbook_id?: string | null;
  key: string;
  description: string;
  condition_type: string;
  condition: Record<string, unknown>;
  action: RedLineAction | string;
  approver_role_id?: string | null;
  rationale?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateRedLineBody {
  key: string;
  description: string;
  condition_type: string;
  condition: Record<string, unknown>;
  action: RedLineAction | string;
  approver_role_id?: string;
  rationale?: string;
}

// A rule-scoped red line written inline with a rule create/update
// (RuleCreate.red_lines / RuleUpdate.red_lines). `scope` is always "rule" and
// is not accepted here. Same id-sync rules as RulePositionInput on update.
export interface RuleRedLineInput {
  id?: string;
  key: string;
  description: string;
  condition_type: string;
  condition: Record<string, unknown>;
  action: RedLineAction | string;
  approver_role_id?: string | null;
  rationale?: string | null;
}

export interface RuleObjection {
  id: string;
  rule_id: string;
  objection: string;
  their_rationale?: string | null;
  response: string;
  talking_points?: string[] | null;
  recommended_position_id?: string | null;
  frequency?: string | null;
  counterparty_profile?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateRuleObjectionBody {
  objection: string;
  response: string;
  their_rationale?: string;
  talking_points?: string[];
  recommended_position_id?: string;
  frequency?: string;
  counterparty_profile?: string;
}

export interface RuleDependency {
  id: string;
  rule_id: string;
  related_rule_key: string;
  relation: string;
  note?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateRuleDependencyBody {
  related_rule_key: string;
  relation: string;
  note?: string;
}

export type TestCaseExpectedOutcome =
  | 'compliant'
  | 'acceptable_variant'
  | 'fallback'
  | 'deviation'
  | 'red_line'
  | 'missing';

export interface RuleTestCase {
  id: string;
  rule_id: string;
  name: string;
  sample_text?: string | null;
  context?: Record<string, unknown> | null;
  expected_outcome: TestCaseExpectedOutcome | string;
  expected_zone?: Zone | string | null;
  expected_position_rung?: number | null;
  expected_red_line_key?: string | null;
  is_trap: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateRuleTestCaseBody {
  name: string;
  expected_outcome: TestCaseExpectedOutcome | string;
  sample_text?: string;
  context?: Record<string, unknown>;
  expected_zone?: Zone | string;
  expected_position_rung?: number;
  expected_red_line_key?: string;
  is_trap?: boolean;
}

// ─── Resolve (task 4.2 / 4.9): GET /playbooks/resolve ────────────────────────

export interface ResolvedRule extends PlaybookRule {
  // Provenance
  source_playbook_id: string;
  source_playbook_name: string;
  source_version: string;
}

export interface ResolveParams {
  contract_type: string;
  party_role?: string;
  paper_origin?: string;
  context?: Record<string, unknown>;
}

export interface ResolveResponse {
  contract_type: string;
  party_role: string;
  paper_origin: string;
  rules: ResolvedRule[];
  pinned_version_ids: string[];
  applied_playbook_keys: string[];
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

export interface UploadDocumentBody {
  file: File;
  paper_origin: PaperOrigin;
  contract_type?: string;
  party_role?: string;
  context?: Record<string, unknown>;
  /** Bypass the `409 duplicate_file` check (section 4.3). */
  force?: boolean;
}

// `POST /api/documents` — 202 body (section 4.3). Upload is now
// fire-and-poll: the route schedules the Extend ingest in the background
// and returns immediately with the ids to poll via `useContract`.
export interface UploadAcceptedResponse {
  contract_id: string;
  version_id: string;
  status: 'processing';
}

// `409 duplicate_file` error body's `detail` (ApiError.detail).
export interface DuplicateFileDetail {
  existing_contract_id: string;
}

export interface ContractContextUpdateBody {
  contract_type?: string | null;
  party_role?: string | null;
  context?: Record<string, unknown> | null;
}

export interface ContractContextResponse {
  id: string;
  contract_type?: string | null;
  party_role?: string | null;
  context?: Record<string, unknown> | null;
}

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

// Body for POST /playbooks/{playbook_id}/rules. Unknown fields, including the
// five removed legacy fields (preferred_language, acceptable_variations,
// prohibited_terms, fallback_language, escalation_threshold), are rejected by
// the API with 422. A rule's negotiating language and red lines are carried
// inline via `positions` / `red_lines` instead (see RulePositionInput /
// RuleRedLineInput).
export interface CreateRuleBody {
  clause_type: string;
  playbook_version_id?: string;
  issue_id?: string;
  rule_key?: string;
  title?: string;
  position_summary?: string;
  risk_rationale?: string;
  required?: boolean;
  negotiable?: boolean;
  risk_weight?: number;
  default_zone?: Zone | string;
  needs_human_judgment?: boolean;
  judgment_note?: string;
  applies_when?: Record<string, unknown>;
  detection_guidance?: string;
  source_ref?: string;
  authored_by?: string;
  approved_by?: string;
  last_reviewed_at?: string;
  positions?: RulePositionInput[];
  red_lines?: RuleRedLineInput[];
}

// Body for PATCH /playbooks/rules/{rule_id}. An omitted field is left
// unchanged; a nullable scalar sent as `null` is cleared. `positions` /
// `red_lines`, when present (even as []), fully replace that child set by
// id-sync; omitted (or null), they are left untouched.
export interface UpdateRuleBody {
  clause_type?: string;
  issue_id?: string | null;
  rule_key?: string | null;
  title?: string | null;
  position_summary?: string | null;
  risk_rationale?: string | null;
  required?: boolean;
  negotiable?: boolean | null;
  risk_weight?: number;
  default_zone?: Zone | string | null;
  needs_human_judgment?: boolean | null;
  judgment_note?: string | null;
  applies_when?: Record<string, unknown> | null;
  detection_guidance?: string | null;
  source_ref?: string | null;
  authored_by?: string | null;
  approved_by?: string | null;
  last_reviewed_at?: string | null;
  positions?: RulePositionInput[] | null;
  red_lines?: RuleRedLineInput[] | null;
}

// ─── Playbook rule version diff (task 5.5 child-row diff) ────────────────────
// Nothing in the frontend renders this yet (no playbook version diff/change
// log UI exists), but the types are kept current with the API contract.

export interface RuleFieldChange {
  field: string;
  old_value: unknown;
  new_value: unknown;
}

export interface ChildCountDiff {
  count_a: number;
  count_b: number;
}

export interface ChildRowChange {
  child_type: 'positions' | 'parameters' | 'red_lines' | 'objections' | 'dependencies' | 'test_cases' | string;
  key: string;
  change_type: 'added' | 'removed' | 'modified';
  changed_fields: string[];
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
}

export interface RuleDiffEntry {
  rule_key: string;
  change_type: string;
  field_changes: RuleFieldChange[];
  child_counts: Record<string, ChildCountDiff>;
  child_changes: ChildRowChange[];
}

export interface PlaybookVersionDiffResponse {
  version_a_id: string;
  version_b_id: string;
  rules_added: string[];
  rules_removed: string[];
  rules_modified: RuleDiffEntry[];
}

// ─── Bootstrap (task 4.1 / 4.9): POST /playbooks/bootstrap ───────────────────

export interface BootstrapBody {
  playbook_id: string;
  contract_ids?: string[];
  contract_type?: string;
}

export interface BootstrapResponse {
  created_rule_count: number;
}

export interface RedlineDecisionBody {
  outcome: 'accepted' | 'rejected';
  final_text?: string;
}

/** Where the backend's draft_clause cascade starts (override → playbook → frequency → LLM). */
export type DraftClauseMode = 'playbook' | 'frequency' | 'llm';

export interface DraftClauseBody {
  clause_type: string;
  /** Free-text description of what the clause should cover (LLM prompt only). */
  context?: string;
  /** Extra LLM instruction, e.g. an NL rewrite request. */
  instruction?: string;
  mode?: DraftClauseMode;
  /** Playbook resolution facts — all optional; backend falls back to ''/'vendor'/'own'. */
  contract_type?: string;
  party_role?: string;
  paper_origin?: PaperOrigin;
  /** Structured resolution context matched against overlay/rule `applies_when`. */
  deal_context?: Record<string, unknown>;
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
