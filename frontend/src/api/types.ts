// Kiểu dữ liệu khớp backend/app/schemas/api.py

export type Json = any;

export interface ProjectStats {
  documents: number;
  versions: number;
  open_findings: number;
  pending_proposals: number;
  latest_version_id: number | null;
  latest_version_label: string | null;
}

export interface AuthConfig {
  type: "none" | "bearer" | "header" | "query";
  name?: string | null;
}

export interface ResetConfig {
  method: string;
  url: string;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  base_url: string | null;
  auth_config: AuthConfig;
  has_secret: boolean;
  allowed_hosts: string[];
  mode: "auto" | "safe" | "full";
  policy: "descriptive" | "prescriptive";
  reset_config: ResetConfig | null;
  created_at: string;
  stats: ProjectStats | null;
}

export interface ProjectInput {
  name?: string;
  description?: string | null;
  base_url?: string | null;
  auth?: AuthConfig | null;
  auth_secret?: string | null;
  allowed_hosts?: string[];
  mode?: "auto" | "safe" | "full";
  policy?: "descriptive" | "prescriptive";
  reset?: ResetConfig | null;
  reset_headers?: Record<string, string> | null;
}

export interface DocumentInfo {
  id: number;
  project_id: number;
  source_type: string;
  source_uri: string | null;
  filename: string | null;
  sha256: string;
  created_at: string;
  markdown: string | null;
  chunk_count: number;
}

export interface Chunk {
  id: number;
  document_id: number;
  order: number;
  title: string;
  operation_hint: { method: string; path: string } | null;
  text: string;
  token_count: number;
  span_start: number;
  span_end: number;
  is_global: boolean;
}

export interface SpecVersion {
  id: number;
  project_id: number;
  parent_id: number | null;
  version_no: number;
  label: string;
  model: string | null;
  note: string | null;
  created_by: string;
  created_at: string;
  patch_from_parent: JsonPatchOp[] | null;
  content: Json | null;
  stats: { operations?: number; warnings?: string[] } | null;
}

export interface EvidenceItem {
  id: number;
  json_pointer: string;
  chunk_id: number | null;
  quote: string;
  match_score: number | null;
  span_start: number | null;
  span_end: number | null;
}

export interface JobAccepted {
  job_id: string;
  status: string;
  resource_id: number | null;
  resource_url: string | null;
}

export interface Job {
  id: string;
  project_id: number | null;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: Record<string, Json> | null;
  result: Record<string, Json> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface LintIssue {
  rule: string;
  severity: string;
  pointer: string;
  message: string;
  operation: string | null;
}

export interface ValidationReport {
  L1_parse: { ok: boolean };
  L2_valid: { ok: boolean; errors: { message: string; path: string[] }[] };
  L3_lint: { issues: LintIssue[]; count: number; density: number };
  L4_grounding: {
    applicable: boolean;
    note?: string;
    evidence?: number;
    grounded?: number;
    grounded_rate?: number;
    suspected_hallucination?: { pointer: string; quote: string; score: number }[];
    elements?: number;
    elements_without_evidence?: string[];
    elements_without_evidence_count?: number;
    mean_score?: number;
  };
  operations: number;
  facts?: Record<string, Json>;
}

export interface GroundTruth {
  id: number;
  project_id: number;
  kind: "doc" | "behavior";
  note: string | null;
  created_at: string;
}

export interface PRF {
  gt?: number;
  pred?: number;
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
}

export interface Evaluation {
  id: number;
  spec_version_id: number;
  ground_truth_id: number | null;
  status: string;
  metrics: {
    static?: Json;
    lint_count?: number;
    lint_density?: number;
    ground_truth_kind?: string;
    L5?: {
      micro: PRF & { omission_rate: number };
      by_category: Record<string, PRF>;
      constraint_by_keyword: Record<string, PRF>;
      constraint_no_type: PRF;
      n_gt_facts: number;
      n_pred_facts: number;
      hallucination_rate?: number;
      omission_rate: number;
    };
  } | null;
  facts: { fp: string[]; fn: string[]; wrong_value: { key: string; gt: Json; pred: Json }[] } | null;
  lint_issues: LintIssue[] | null;
  job_id: string | null;
  created_at: string;
}

export interface TestRunConfig {
  base_url?: string | null;
  mode?: "auto" | "safe" | "full" | null;
  strategies?: string[];
  budget_per_operation?: number | null;
  max_rps?: number | null;
  timeout_s?: number | null;
  repeats?: number;
  seed?: number;
  operations?: string[] | null;
  reset?: boolean;
}

export interface TestRun {
  id: number;
  spec_version_id: number;
  config: TestRunConfig;
  status: string;
  job_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  stats: {
    requests?: number;
    outcomes?: Record<string, number>;
    duration_s?: number;
    operations?: Record<string, string>;
    requests_by_operation?: Record<string, number>;
    effective_config?: Record<string, Json>;
    reset?: Json;
    verified?: { operation: string; location: string; check: string; observations: number }[];
    unverified?: { operation: string; location: string; check: string; reason: string }[];
    findings_by_code?: Record<string, number>;
    findings?: number;
    proposals?: number;
  } | null;
  error: string | null;
}

export interface Observation {
  id: number;
  test_run_id: number;
  operation_id: string;
  strategy: string;
  probe: Record<string, Json> | null;
  request: { method: string; url: string; query?: Json; headers?: Json; body?: Json; path_params?: Json };
  status_code: number | null;
  response: { headers?: Json; body?: Json; error?: string | null } | null;
  outcome: string;
  latency_ms: number | null;
  repeat_index: number;
  created_at: string;
  role?: string;
}

export interface ObservationPage {
  total: number;
  page: number;
  size: number;
  facets: { operations: string[]; strategies: string[] };
  items: Observation[];
}

export interface Finding {
  id: number;
  test_run_id: number;
  code: string;
  operation_id: string;
  location: string | null;
  keyword: string | null;
  json_pointer: string | null;
  summary: string;
  details: Record<string, Json> | null;
  confidence: number;
  doc_conflict: boolean;
  status: string;
  proposal_ids: number[];
}

export interface JsonPatchOp {
  op: "add" | "remove" | "replace" | "move" | "copy" | "test";
  path: string;
  from?: string;
  value?: Json;
}

export interface Proposal {
  id: number;
  finding_id: number;
  spec_version_id: number;
  code: string;
  target: string | null;
  json_patch: JsonPatchOp[];
  evidence: { runtime?: number[]; message?: string | null; doc?: { chunk_id: number | null; quote: string; pointer: string }[] } | null;
  channels: Record<string, number> | null;
  confidence: number;
  doc_conflict: boolean;
  tier: "auto" | "review" | "suggestion";
  status: string;
  applied_version_id: number | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  finding: Finding | null;
}

export interface DiffResult {
  from: { id: number; version_no: number; label: string; yaml: string };
  to: { id: number; version_no: number; label: string; yaml: string };
  text_diff: string;
  semantic: { changes: number; by_operation: Record<string, { type: string; path: string; old?: Json; new?: Json }[]> };
}

export interface Provider {
  id: string;
  name: string;
  available: boolean;
  base_url?: string | null;
  models: string[];
  default?: boolean;
}

export interface Dashboard {
  projects: number;
  versions: number;
  test_runs: number;
  open_findings: number;
  pending_proposals: number;
  findings_by_code: Record<string, number>;
  llm: { input_tokens: number; output_tokens: number; calls: number };
  recent_projects: { id: number; name: string; created_at: string }[];
}

export interface BenchApi {
  id: string;
  name: string;
  group: string | null;
  test_scope: string | null;
  base_url: string | null;
  docs: Record<string, string>;
  has_behavior_gt: boolean;
}

// ---- bộ dữ liệu SpecLoop-Bench (trang “Bộ dữ liệu”)
export type BenchGroup = "A" | "B";
export type BenchEnv = "local-docker" | "public" | "offline";
export type BenchScope = "full" | "read-only" | "none";

export interface BenchAuth {
  type: "none" | "apiKey" | "bearer" | "oauth2";
  in?: "header" | "query" | "cookie" | null;
  name?: string | null;
  env_var?: string | null;
}

export interface BenchApiRow {
  id: string;
  name: string;
  group: BenchGroup | null;
  description: string | null;
  environment: BenchEnv | null;
  test_scope: BenchScope | null;
  base_url: string | null;
  auth: string;
  connectivity_checked: boolean;
  license: string | null;
  retrieved_at: string | null;
  has_original_doc: boolean;
  has_ablated_doc: boolean;
  behavior_gt: string;
  added_by: string | null;
  added_via: string | null;
  deletable: boolean;
  operations: number | null;
  parameters: number | null;
  constraints: number | null;
  facts: number | null;
}

export interface BenchStats {
  operations: number;
  parameters: number;
  request_fields: number;
  responses: number;
  response_fields: number;
  constraints: number;
  constraints_no_type: number;
  facts_total: number;
  doc_original_words: number;
  doc_rendered_words: number;
  ablated_hidden: number;
  constraint_by_keyword: Record<string, number>;
  [k: string]: unknown;
}

export interface BenchApiDetail {
  id: string;
  meta: {
    name: string;
    group: BenchGroup;
    description: string;
    source: { spec_url: string; spec_file: string; license: string; homepage: string; docs_url: string;
      retrieved_at: string; normalization: string[] };
    environment: { type: BenchEnv; base_url: string; test_scope: BenchScope; auth: BenchAuth; rate_limit_rps: number;
      connectivity_checked: boolean; probe: { method: string; path: string | null; params: Record<string, unknown> } };
    docs: { original: string | null; rendered: string; ablated: string | null };
    ground_truth: { behavior_status: string };
    added_by?: string;
    added_via?: string;
    notes?: string;
  };
  stats: BenchStats | null;
  files: { path: string; size: number }[];
  deletable: boolean;
}

export interface BenchSourceInput {
  spec_url?: string | null;
  spec_text?: string | null;
  filename?: string | null;
}

export interface BenchSuggested {
  id: string;
  name: string;
  description: string;
  base_url: string;
  group: BenchGroup;
  env: BenchEnv;
  scope: BenchScope;
  auth: BenchAuth;
  license: string;
  homepage: string;
  docs_url: string;
  probe_path: string;
  exists: boolean;
}

export interface BenchPreview {
  source_version: string;
  title: string | null;
  version: string | null;
  operations: number;
  paths: number;
  servers: string[];
  security_schemes: string[];
  tags: string[];
  size_bytes: number;
  valid: boolean;
  errors: string[];
  normalization: string[];
  suggested: BenchSuggested;
}

export interface BenchApiCreate extends BenchSourceInput {
  id: string;
  name: string;
  group: BenchGroup;
  env: BenchEnv;
  scope: BenchScope;
  base_url?: string | null;
  auth: BenchAuth;
  description?: string | null;
  license?: string | null;
  homepage?: string | null;
  docs_url?: string | null;
  rate_limit_rps?: number | null;
  probe_path?: string | null;
  make_ablated: boolean;
  added_by?: string | null;
  doc_original_text?: string | null;
  doc_original_filename?: string | null;
}

export interface BenchCreateResult {
  id: string;
  path: string;
  stats: BenchStats;
  normalization: string[];
  validation: { ok: boolean; errors: string[]; warnings: string[] };
}

export interface BenchConnectivity {
  ok: boolean;
  status: number | string;
  latency_ms?: number;
  url?: string;
  reason?: string;
  error?: string;
}

export interface ExperimentRequest {
  name: string;
  apis: string[];
  models: string[];
  configs: ("C0" | "C1" | "C2")[];
  repeats: number;
  doc_variant: "original" | "rendered" | "ablated";
  base_url_overrides: Record<string, string>;
  max_iter: number;
  max_rps?: number | null;
}

export interface ExperimentRow {
  api: string;
  model: string;
  config: string;
  rep: number;
  status: string;
  note?: string;
  valid?: number;
  operations?: number;
  precision?: number;
  recall?: number;
  f1?: number;
  constraint_f1_doc?: number;
  constraint_f1_behavior?: number | null;
  requests?: number;
  input_tokens?: number;
  output_tokens?: number;
  duration_s?: number;
  iterations?: number;
  spec_version_id?: number;
  project_id?: number;
}

export interface ExperimentSummary {
  aggregate: (Record<string, Json> & { api: string; model: string; config: string; n: number })[];
  tests: Record<string, { n: number; mean_diff: number | null; ci95: [number, number] | null; p_value?: number; p_holm?: number; effect_r?: number; note?: string }>;
  macro: Record<string, { f1: number | null; constraint_f1_doc: number | null; constraint_f1_behavior: number | null }>;
  rows: number;
  ok_rows: number;
  duration_s?: number;
}

export interface ExperimentResults {
  id: number;
  name: string;
  status: string;
  job_id: string | null;
  config: ExperimentRequest;
  rows: ExperimentRow[];
  summary: ExperimentSummary | null;
  output_dir: string | null;
}

export interface ExperimentListItem {
  id: number;
  name: string;
  status: string;
  job_id: string | null;
  created_at: string;
  config: ExperimentRequest;
  rows: number;
}
