"""Mô hình dữ liệu (TECH_SPEC mục 6)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auth_config: Mapped[dict] = mapped_column(JSON, default=dict)        # {type, name, in} – không chứa secret
    secrets_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet(JSON) – không bao giờ trả về
    allowed_hosts: Mapped[list] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String(20), default="auto")        # auto | safe | full
    policy: Mapped[str] = mapped_column(String(20), default="descriptive")  # descriptive | prescriptive
    reset_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {method, url}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list[Document]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "document"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(20))  # url | html | markdown | pdf | text
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    raw_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    markdown: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                               order_by="Chunk.order")


class Chunk(Base):
    __tablename__ = "chunk"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500), default="")
    operation_hint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    span_start: Mapped[int] = mapped_column(Integer, default=0)
    span_end: Mapped[int] = mapped_column(Integer, default=0)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)
    heading_path: Mapped[list | None] = mapped_column(JSON, nullable=True)  # tiêu đề tổ tiên, dùng làm ngữ cảnh

    document: Mapped[Document] = relationship(back_populates="chunks")


class SpecVersion(Base):
    __tablename__ = "spec_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("spec_version.id"), nullable=True)
    version_no: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(50))  # generated | repaired | refined-k | manual | imported
    content: Mapped[dict] = mapped_column(JSON)
    patch_from_parent: Mapped[list | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spec_version_id: Mapped[int] = mapped_column(ForeignKey("spec_version.id", ondelete="CASCADE"), index=True)
    json_pointer: Mapped[str] = mapped_column(String(1000), index=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunk.id", ondelete="SET NULL"), nullable=True)
    quote: Mapped[str] = mapped_column(Text)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GroundTruth(Base):
    __tablename__ = "ground_truth"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # doc | behavior
    content: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evaluation(Base):
    __tablename__ = "evaluation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spec_version_id: Mapped[int] = mapped_column(ForeignKey("spec_version.id", ondelete="CASCADE"), index=True)
    ground_truth_id: Mapped[int | None] = mapped_column(ForeignKey("ground_truth.id", ondelete="SET NULL"),
                                                        nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    facts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lint_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestRun(Base):
    __tablename__ = "test_run"
    __test__ = False  # không để pytest thu thập
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spec_version_id: Mapped[int] = mapped_column(ForeignKey("spec_version.id", ondelete="CASCADE"), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Observation(Base):
    __tablename__ = "observation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_run.id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[str] = mapped_column(String(300), index=True)
    strategy: Mapped[str] = mapped_column(String(50))
    probe: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request: Mapped[dict] = mapped_column(JSON)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    repeat_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Finding(Base):
    __tablename__ = "finding"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_run.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(10))  # D0–D9 | INFO
    operation_id: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(100), nullable=True)
    json_pointer: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    doc_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | verified | reopened | reported


class FindingObservation(Base):
    __tablename__ = "finding_observation"
    finding_id: Mapped[int] = mapped_column(ForeignKey("finding.id", ondelete="CASCADE"), primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observation.id", ondelete="CASCADE"),
                                                primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="support")  # support | contradict


class Proposal(Base):
    __tablename__ = "proposal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("finding.id", ondelete="CASCADE"), index=True)
    spec_version_id: Mapped[int] = mapped_column(ForeignKey("spec_version.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(10))
    target: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    json_patch: Mapped[list] = mapped_column(JSON)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    channels: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    doc_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str] = mapped_column(String(20), default="review")  # auto | review | suggestion
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | accepted | rejected | edited | applied | verified
    applied_version_id: Mapped[int | None] = mapped_column(ForeignKey("spec_version.id"), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "job"
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: uuid.uuid4().hex)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=True)
    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed|cancelled
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMCall(Base):
    __tablename__ = "llm_call"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMCache(Base):
    __tablename__ = "llm_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(model + prompt)
    model: Mapped[str] = mapped_column(String(200))
    response: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Experiment(Base):
    __tablename__ = "experiment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
