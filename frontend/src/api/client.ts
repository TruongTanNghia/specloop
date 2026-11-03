// Client REST có kiểu cho backend SpecLoop (/api/v1). Lỗi theo RFC 7807 được đổi thành ApiError.
import type {
  BenchApi, BenchApiCreate, BenchApiDetail, BenchApiRow, BenchConnectivity, BenchCreateResult, BenchPreview,
  BenchSourceInput, Chunk, Dashboard, DiffResult, DocumentInfo, Evaluation, EvidenceItem, ExperimentListItem,
  ExperimentRequest, ExperimentResults, Finding, GroundTruth, Job, JobAccepted, JsonPatchOp, Observation,
  ObservationPage, Project, ProjectInput, Proposal, Provider, SpecVersion, TestRun, TestRunConfig, ValidationReport,
} from "./types";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  title: string;
  detail: string | null;
  errors: unknown[];

  constructor(status: number, title: string, detail: string | null, errors: unknown[] = []) {
    super(detail ? `${title}: ${detail}` : title);
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.errors = errors;
  }
}

async function request<T>(method: string, path: string, body?: unknown, raw = false): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let title = `HTTP ${res.status}`;
    let detail: string | null = null;
    let errors: unknown[] = [];
    try {
      const p = await res.json();
      title = p.title ?? title;
      detail = p.detail ?? null;
      errors = p.errors ?? [];
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, title, detail, errors);
  }
  if (res.status === 204) return undefined as T;
  if (raw) return (await res.text()) as T;
  return (await res.json()) as T;
}

const get = <T,>(p: string) => request<T>("GET", p);
const post = <T,>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const patch = <T,>(p: string, b: unknown) => request<T>("PATCH", p, b);
const del = (p: string) => request<void>("DELETE", p);

function qs(params: Record<string, unknown>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  }
  const t = s.toString();
  return t ? `?${t}` : "";
}

export const api = {
  // dự án
  projects: () => get<Project[]>("/projects"),
  project: (id: number) => get<Project>(`/projects/${id}`),
  createProject: (b: ProjectInput) => post<Project>("/projects", b),
  updateProject: (id: number, b: ProjectInput) => patch<Project>(`/projects/${id}`, b),
  deleteProject: (id: number) => del(`/projects/${id}`),

  // tài liệu & phân đoạn
  documents: (pid: number) => get<DocumentInfo[]>(`/projects/${pid}/documents`),
  document: (id: number) => get<DocumentInfo>(`/documents/${id}`),
  addDocumentJson: (pid: number, b: { url?: string; text?: string; format?: string; filename?: string }) =>
    post<DocumentInfo>(`/projects/${pid}/documents`, b),
  addDocumentFile: (pid: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<DocumentInfo>("POST", `/projects/${pid}/documents`, fd);
  },
  deleteDocument: (id: number) => del(`/documents/${id}`),
  chunks: (docId: number) => get<Chunk[]>(`/documents/${docId}/chunks`),
  resegment: (docId: number) => post<Chunk[]>(`/documents/${docId}/resegment`),
  updateChunk: (id: number, b: Partial<Pick<Chunk, "title" | "text" | "is_global">>) => patch<Chunk>(`/chunks/${id}`, b),
  mergeChunks: (docId: number, ids: number[]) => post<Chunk[]>(`/documents/${docId}/chunks/merge`, { chunk_ids: ids }),
  splitChunk: (id: number, offset: number) => post<Chunk[]>(`/chunks/${id}/split`, { offset }),
  deleteChunk: (id: number) => del(`/chunks/${id}`),

  // đặc tả
  generate: (pid: number, b: { document_id?: number | null; model?: string | null; repair?: boolean }) =>
    post<JobAccepted>(`/projects/${pid}/generate`, b),
  importSpec: (pid: number, text: string, note?: string) =>
    post<SpecVersion>(`/projects/${pid}/specs/import`, { text, note }),
  specs: (pid: number) => get<SpecVersion[]>(`/projects/${pid}/specs`),
  spec: (id: number) => get<SpecVersion>(`/specs/${id}`),
  specYaml: (id: number) => request<string>("GET", `/specs/${id}?format=yaml`, undefined, true),
  manualVersion: (id: number, text: string, note?: string) => post<SpecVersion>(`/specs/${id}/versions`, { text, note }),
  evidence: (id: number, pointer?: string) => get<EvidenceItem[]>(`/specs/${id}/evidence${qs({ pointer })}`),
  validate: (id: number) => post<ValidationReport>(`/specs/${id}/validate`),
  diff: (id: number, against?: number) => get<DiffResult>(`/specs/${id}/diff${qs({ against })}`),
  exportUrl: (id: number, format: string, strip: boolean, evidence: boolean) =>
    `${API_BASE}/specs/${id}/export${qs({ format, strip_extensions: strip, include_evidence: evidence })}`,

  // ground truth & đánh giá
  groundTruths: (pid: number) => get<GroundTruth[]>(`/projects/${pid}/ground-truths`),
  addGroundTruth: (pid: number, kind: string, text: string, note?: string) =>
    post<GroundTruth>(`/projects/${pid}/ground-truths`, { kind, text, note }),
  evaluate: (specId: number, gtId: number | null) => post<JobAccepted>(`/specs/${specId}/evaluations`, { ground_truth_id: gtId }),
  evaluations: (specId: number) => get<Evaluation[]>(`/specs/${specId}/evaluations`),
  evaluation: (id: number) => get<Evaluation>(`/evaluations/${id}`),

  // kiểm thử
  startTestRun: (specId: number, cfg: TestRunConfig) => post<JobAccepted>(`/specs/${specId}/test-runs`, cfg),
  projectTestRuns: (pid: number) => get<TestRun[]>(`/projects/${pid}/test-runs`),
  testRun: (id: number) => get<TestRun>(`/test-runs/${id}`),
  cancelTestRun: (id: number) => post<TestRun>(`/test-runs/${id}/cancel`),
  observations: (runId: number, f: { operation?: string; strategy?: string; outcome?: string; page?: number; size?: number }) =>
    get<ObservationPage>(`/test-runs/${runId}/observations${qs(f)}`),
  findings: (runId: number) => get<Finding[]>(`/test-runs/${runId}/findings`),
  finding: (id: number) => get<{ finding: Finding; observations: Observation[] }>(`/findings/${id}`),

  // đề xuất
  proposals: (specId: number, status?: string) => get<Proposal[]>(`/specs/${specId}/proposals${qs({ status })}`),
  accept: (id: number) => post<Proposal>(`/proposals/${id}/accept`),
  reject: (id: number) => post<Proposal>(`/proposals/${id}/reject`),
  editProposal: (id: number, json_patch: JsonPatchOp[]) => patch<Proposal>(`/proposals/${id}`, { json_patch }),
  acceptThreshold: (specId: number, threshold: number, includeConflicts: boolean) =>
    post<Proposal[]>(`/specs/${specId}/proposals/accept-threshold${qs({ threshold, include_conflicts: includeConflicts })}`),
  apply: (specId: number, proposalIds?: number[]) =>
    post<SpecVersion>(`/specs/${specId}/apply`, { proposal_ids: proposalIds ?? null }),
  refineLoop: (specId: number, b: { max_iter: number; auto_accept_threshold: number; min_confidence: number; test_config: TestRunConfig }) =>
    post<JobAccepted>(`/specs/${specId}/refine-loop`, b),

  // job
  job: (id: string) => get<Job>(`/jobs/${id}`),
  jobs: (pid?: number) => get<Job[]>(`/jobs${qs({ project_id: pid })}`),
  cancelJob: (id: string) => post<Job>(`/jobs/${id}/cancel`),

  // bộ dữ liệu SpecLoop-Bench
  benchList: () => get<BenchApiRow[]>("/bench/apis"),
  benchDetail: (id: string) => get<BenchApiDetail>(`/bench/apis/${encodeURIComponent(id)}`),
  benchFile: (id: string, path: string) =>
    request<string>("GET", `/bench/apis/${encodeURIComponent(id)}/file${qs({ path })}`, undefined, true),
  benchPreview: (b: BenchSourceInput) => post<BenchPreview>("/bench/preview", b),
  benchCreate: (b: BenchApiCreate) => post<BenchCreateResult>("/bench/apis", b),
  benchDelete: (id: string) => del(`/bench/apis/${encodeURIComponent(id)}`),
  benchConnectivity: (id: string) => post<BenchConnectivity>(`/bench/apis/${encodeURIComponent(id)}/connectivity`),

  // khác
  health:() => get<{ status: string; llm_configured: boolean }>("/health"),
  dashboard: () => get<Dashboard>("/dashboard"),
  providers: () => get<Provider[]>("/llm/providers"),
  llmTest: (b: { base_url?: string; api_key?: string; model?: string }) =>
    post<{ ok: boolean; model?: string; provider?: string; latency_ms?: number; response?: unknown; error?: string }>("/llm/test", b),
  llmUsage: () => get<{ model: string; calls: number; input_tokens: number; output_tokens: number; cached: number }[]>("/llm/usage"),
  benchApis: () => get<BenchApi[]>("/experiments/apis"),
  experiments: () => get<ExperimentListItem[]>("/experiments"),
  startExperiment: (b: ExperimentRequest) => post<JobAccepted>("/experiments", b),
  experimentResults: (id: number) => get<ExperimentResults>(`/experiments/${id}/results`),
  experimentMarkdown: (id: number) => request<string>("GET", `/experiments/${id}/results?format=md`, undefined, true),
  experimentCsvUrl: (id: number) => `${API_BASE}/experiments/${id}/results?format=csv`,
};

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.detail ? `${e.title} – ${e.detail}` : e.title;
  if (e instanceof Error) return e.message;
  return String(e);
}

export type { Observation };
