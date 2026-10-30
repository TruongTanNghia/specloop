"""Điều phối M2: phân đoạn → trích IR (song song) → lắp ráp → (vòng sửa lỗi) → lưu phiên bản + bằng chứng."""
from __future__ import annotations

import re
import time

from rapidfuzz import fuzz
from sqlalchemy import select

from ...config import get_settings
from ...db import session_scope
from ...models import Chunk, Document, Evidence, Project
from ..evaluation.validator import validate_all
from ..llm.gateway import get_llm
from ..versioning.core import create_version, diff_patch
from .assembler import assemble, detect_base_url
from .extractor import extract_all
from .repair import repair as run_repair


def locate_quote(markdown: str, quote: str) -> tuple[int | None, int | None, float]:
    if not quote:
        return None, None, 0.0
    i = markdown.find(quote)
    if i >= 0:
        return i, i + len(quote), 100.0
    norm_q = " ".join(quote.split())
    # so khớp bỏ khác biệt khoảng trắng
    pattern = r"\s+".join(re.escape(w) for w in norm_q.split(" ") if w)
    if pattern:
        m = re.search(pattern, markdown)
        if m:
            return m.start(), m.end(), 100.0
    al = fuzz.partial_ratio_alignment(norm_q, markdown)
    if al is not None:
        return al.dest_start, al.dest_end, round(al.score, 1)
    return None, None, 0.0


def save_evidence(db, version_id: int, evidence, markdown: str) -> int:
    n = 0
    for e in evidence:
        st, en, score = locate_quote(markdown, e.quote)
        db.add(Evidence(spec_version_id=version_id, json_pointer=e.pointer, chunk_id=e.chunk_id, quote=e.quote,
                        match_score=score, span_start=st, span_end=en))
        n += 1
    return n


def generate(project_id: int, *, document_id: int | None = None, model: str | None = None, repair: bool = True,
             max_concurrency: int | None = None, job_id: str | None = None, on_progress=None,
             use_cache: bool | None = None) -> dict:
    t0 = time.perf_counter()
    llm = get_llm(model)
    if use_cache is not None:
        llm.cache_enabled = use_cache
    with session_scope() as db:
        project = db.get(Project, project_id)
        if project is None:
            raise ValueError("Không tìm thấy dự án")
        q = select(Document).where(Document.project_id == project_id).order_by(Document.id.desc())
        doc = db.get(Document, document_id) if document_id else db.scalars(q).first()
        if doc is None or doc.project_id != project_id:
            raise ValueError("Dự án chưa có tài liệu")
        chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.order)))
        for c in chunks:
            db.expunge(c)
        markdown, doc_id, project_name, base_url = doc.markdown, doc.id, project.name, project.base_url

    def prog(done, total):
        if on_progress:
            on_progress(stage="extract", done=done, total=total)

    outcomes = extract_all(llm, chunks, max_concurrency=max_concurrency or get_settings().LLM_MAX_CONCURRENCY,
                           job_id=job_id, on_progress=prog)
    irs = [(o.chunk_id, o.ir) for o in outcomes if o.ir is not None]
    failed = [{"chunk_id": o.chunk_id, "title": o.title, "error": o.error} for o in outcomes
              if o.ir is None and o.error]
    title_m = re.search(r"^#\s+(.+)$", markdown, re.M)
    title = (title_m.group(1).strip() if title_m else project_name)[:200]
    title = re.sub(r"\s+documentation$", "", title, flags=re.I)
    base = detect_base_url(markdown) or base_url
    if on_progress:
        on_progress(stage="assemble")
    spec, evidence, warnings = assemble(irs, title=title, base_url=base)
    errors_v0 = validate_all(spec)
    stats = {
        "chunks": len(chunks), "extracted": len(outcomes), "operations": len(irs), "failed": failed,
        "input_tokens": sum(o.input_tokens for o in outcomes), "output_tokens": sum(o.output_tokens for o in outcomes),
        "attempts": sum(o.attempts for o in outcomes), "cached_calls": sum(o.cached_calls for o in outcomes),
        "warnings": warnings, "validation_errors_generated": len(errors_v0), "document_id": doc_id,
    }
    if repair:
        # gọi LLM (ghi bảng llm_call) trước khi mở transaction ghi phiên bản để SQLite không bị khóa
        if on_progress:
            on_progress(stage="repair")
        fixed, notes, remaining = run_repair(spec, llm if llm.provider != "fake" else None, job_id)
        stats["repair_notes"] = notes
        stats["validation_errors_repaired"] = len(remaining)
    with session_scope() as db:
        v0 = create_version(db, project_id, spec, label="generated", model=llm.model,
                            note=f"Sinh từ tài liệu #{doc_id} bằng {llm.model}")
        save_evidence(db, v0.id, evidence, markdown)
        result = {"generated_version_id": v0.id, "version_id": v0.id}
        if repair:
            if fixed != spec:
                v1 = create_version(db, project_id, fixed, label="repaired", parent=v0, patch=diff_patch(spec, fixed),
                                    model=llm.model, note=f"Vòng sửa lỗi: {len(notes)} thay đổi")
                result["repaired_version_id"] = v1.id
                result["version_id"] = v1.id
        stats["duration_s"] = round(time.perf_counter() - t0, 3)
        result["stats"] = stats
    return result
