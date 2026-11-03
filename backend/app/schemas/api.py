"""Pydantic schema cho request/response của REST API backend."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- project
class AuthConfig(BaseModel):
    type: Literal["none", "bearer", "header", "query"] = "none"
    name: str | None = None  # tên header / query cho type header|query


class ResetConfig(BaseModel):
    method: str = "POST"
    url: str  # tuyệt đối hoặc tương đối với origin của base_url, vd. /__admin/reset


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    base_url: str | None = None
    auth: AuthConfig | None = None
    auth_secret: str | None = Field(default=None, description="Token/khóa API – được mã hóa, không bao giờ trả về")
    allowed_hosts: list[str] = []
    mode: Literal["auto", "safe", "full"] = "auto"
    policy: Literal["descriptive", "prescriptive"] = "descriptive"
    reset: ResetConfig | None = None
    reset_headers: dict[str, str] | None = Field(default=None, description="Header cho lệnh reset (được mã hóa)")


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    base_url: str | None = None
    auth: AuthConfig | None = None
    auth_secret: str | None = None
    allowed_hosts: list[str] | None = None
    mode: Literal["auto", "safe", "full"] | None = None
    policy: Literal["descriptive", "prescriptive"] | None = None
    reset: ResetConfig | None = None
    reset_headers: dict[str, str] | None = None


class ProjectOut(ORM):
    id: int
    name: str
    description: str | None
    base_url: str | None
    auth_config: dict
    has_secret: bool = False
    allowed_hosts: list
    mode: str
    policy: str
    reset_config: dict | None
    created_at: datetime
    stats: dict | None = None


# ---------------------------------------------------------------- documents
class DocumentIn(BaseModel):
    url: str | None = None
    text: str | None = None
    format: Literal["markdown", "html", "text"] | None = None
    filename: str | None = None


class ChunkOut(ORM):
    id: int
    document_id: int
    order: int
    title: str
    operation_hint: dict | None
    text: str
    token_count: int
    span_start: int
    span_end: int
    is_global: bool


class ChunkUpdate(BaseModel):
    title: str | None = None
    text: str | None = None
    is_global: bool | None = None
    operation_hint: dict | None = None


class ChunkMerge(BaseModel):
    chunk_ids: list[int] = Field(min_length=2)


class ChunkSplit(BaseModel):
    offset: int = Field(gt=0, description="Vị trí ký tự trong text của phân đoạn để tách")


class DocumentOut(ORM):
    id: int
    project_id: int
    source_type: str
    source_uri: str | None
    filename: str | None
    sha256: str
    created_at: datetime
    markdown: str | None = None
    chunk_count: int = 0


# ---------------------------------------------------------------- specs
class GenerateRequest(BaseModel):
    document_id: int | None = None
    model: str | None = None  # "fake" để dùng FakeLLM
    repair: bool = True
    max_concurrency: int | None = None


class SpecImport(BaseModel):
    content: dict | None = None
    text: str | None = None  # YAML/JSON
    label: str = "imported"
    note: str | None = None


class SpecVersionCreate(BaseModel):
    content: dict | None = None
    text: str | None = None
    note: str | None = None


class SpecOut(ORM):
    id: int
    project_id: int
    parent_id: int | None
    version_no: int
    label: str
    model: str | None
    note: str | None
    created_by: str
    created_at: datetime
    patch_from_parent: list | None = None
    content: dict | None = None
    stats: dict | None = None


class EvidenceOut(ORM):
    id: int
    json_pointer: str
    chunk_id: int | None
    quote: str
    match_score: float | None
    span_start: int | None
    span_end: int | None


# ---------------------------------------------------------------- ground truth / evaluation
class GroundTruthIn(BaseModel):
    kind: Literal["doc", "behavior"] = "doc"
    content: dict | None = None
    text: str | None = None
    note: str | None = None


class GroundTruthOut(ORM):
    id: int
    project_id: int
    kind: str
    note: str | None
    created_at: datetime


class EvaluationRequest(BaseModel):
    ground_truth_id: int | None = None


class EvaluationOut(ORM):
    id: int
    spec_version_id: int
    ground_truth_id: int | None
    status: str
    metrics: dict | None
    facts: dict | None
    lint_issues: list | None
    job_id: str | None
    created_at: datetime


# ---------------------------------------------------------------- testing
class TestRunConfig(BaseModel):
    __test__ = False
    base_url: str | None = None
    mode: Literal["auto", "safe", "full"] | None = None
    strategies: list[str] = ["S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]
    budget_per_operation: int | None = None
    max_rps: float | None = None
    timeout_s: float | None = None
    repeats: int = Field(default=3, ge=1, le=10)
    seed: int = 42
    operations: list[str] | None = None
    reset: bool = True
    use_llm_messages: bool = False
    schemathesis: bool = False


class TestRunOut(ORM):
    __test__ = False
    id: int
    spec_version_id: int
    config: dict
    status: str
    job_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    stats: dict | None
    error: str | None


class ObservationOut(ORM):
    id: int
    test_run_id: int
    operation_id: str
    strategy: str
    probe: dict | None
    request: dict
    status_code: int | None
    response: dict | None
    outcome: str
    latency_ms: float | None
    repeat_index: int
    created_at: datetime


class FindingOut(ORM):
    id: int
    test_run_id: int
    code: str
    operation_id: str
    location: str | None
    keyword: str | None
    json_pointer: str | None
    summary: str
    details: dict | None
    confidence: float
    doc_conflict: bool
    status: str
    proposal_ids: list[int] = []


class ProposalOut(ORM):
    id: int
    finding_id: int
    spec_version_id: int
    code: str
    target: str | None
    json_patch: list
    evidence: dict | None
    channels: dict | None
    confidence: float
    doc_conflict: bool
    tier: str
    status: str
    applied_version_id: int | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    finding: FindingOut | None = None


class ProposalPatch(BaseModel):
    json_patch: list[dict[str, Any]]


class ApplyRequest(BaseModel):
    proposal_ids: list[int] | None = None  # None = mọi đề xuất đã accepted/edited
    note: str | None = None


class RefineLoopRequest(BaseModel):
    max_iter: int = Field(default=3, ge=1, le=10)
    auto_accept_threshold: float = 0.8
    min_confidence: float = 0.5
    test_config: TestRunConfig = TestRunConfig()


class JobOut(ORM):
    id: str
    project_id: int | None
    type: str
    status: str
    progress: dict | None
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class JobAccepted(BaseModel):
    job_id: str
    status: str = "queued"
    resource_id: int | None = None
    resource_url: str | None = None


# ---------------------------------------------------------------- experiments / llm
class ExperimentRequest(BaseModel):
    name: str = "experiment"
    apis: list[str] = ["bookstore-lab"]
    models: list[str] = ["fake"]
    configs: list[Literal["C0", "C1", "C2"]] = ["C0", "C1", "C2"]
    repeats: int = Field(default=3, ge=1, le=10)
    doc_variant: Literal["original", "rendered", "ablated"] = "original"
    base_url_overrides: dict[str, str] = {}
    max_iter: int = 3
    max_rps: float | None = None


# ---------------------------------------------------------------- bộ dữ liệu SpecLoop-Bench
class BenchSource(BaseModel):
    """Nguồn đặc tả: URL hoặc nội dung (dán / đọc từ tệp tải lên ở trình duyệt)."""
    spec_url: str | None = None
    spec_text: str | None = Field(default=None, max_length=20_000_000)
    filename: str | None = None


class BenchAuth(BaseModel):
    type: Literal["none", "apiKey", "bearer", "oauth2"] = "none"
    in_: Literal["header", "query", "cookie"] | None = Field(default=None, alias="in")
    name: str | None = None
    env_var: str | None = None  # tên biến môi trường chứa khóa trên máy chạy kiểm thử (không lưu khóa)

    model_config = ConfigDict(populate_by_name=True)


class BenchApiCreate(BenchSource):
    id: str = Field(min_length=2, max_length=41)
    name: str = Field(min_length=1, max_length=200)
    group: Literal["A", "B"] = "B"
    env: Literal["local-docker", "public", "offline"] = "public"
    scope: Literal["full", "read-only", "none"] = "read-only"
    base_url: str | None = None
    auth: BenchAuth = BenchAuth()
    description: str | None = Field(default=None, max_length=2000)
    license: str | None = None
    homepage: str | None = None
    docs_url: str | None = None
    rate_limit_rps: float | None = Field(default=None, gt=0, le=100)
    probe_path: str | None = None
    make_ablated: bool = False
    added_by: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    doc_original_text: str | None = Field(default=None, max_length=5_000_000)
    doc_original_filename: str | None = None


class LLMTestRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
