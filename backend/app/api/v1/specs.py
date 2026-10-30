"""Sinh / nhập / xem / sửa / so sánh / xuất đặc tả; ground truth và đánh giá."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...bench import oas_utils
from ...db import get_db, session_scope
from ...jobs import get_runner
from ...models import Document, Evaluation, Evidence, GroundTruth, Project, SpecVersion
from ...schemas.api import (
    EvaluationOut,
    EvaluationRequest,
    EvidenceOut,
    GenerateRequest,
    GroundTruthIn,
    GroundTruthOut,
    JobAccepted,
    SpecImport,
    SpecOut,
    SpecVersionCreate,
)
from ...services.evaluation.service import facts_summary, run_evaluation, static_report
from ...services.evaluation.validator import count_operations, parse_text
from ...services.llm.gateway import LLMNotConfigured, get_llm
from ...services.versioning.core import (
    create_version,
    diff_patch,
    semantic_diff,
    strip_extensions,
    text_diff,
    to_yaml,
    with_evidence,
)
from ..deps import Problem, get_or_404

router = APIRouter(tags=["specs"])


def _parse_content(content: dict | None, text: str | None) -> dict:
    if content is None and text is None:
        raise Problem(422, "Thiếu nội dung", "Cần content (JSON) hoặc text (YAML/JSON)")
    if content is None:
        content, err = parse_text(text)
        if err:
            raise Problem(422, "Không đọc được đặc tả (L1)", err)
    try:
        content, _ = oas_utils.normalize_to_303(content)
    except ValueError as e:
        raise Problem(422, "Đặc tả không được hỗ trợ", str(e)) from e
    return content


def spec_out(v: SpecVersion, with_content: bool = False) -> SpecOut:
    out = SpecOut.model_validate(v)
    out.stats = {"operations": count_operations(v.content)}
    if not with_content:
        out.content = None
        out.patch_from_parent = None
    return out


@router.post("/projects/{project_id}/generate", response_model=JobAccepted, status_code=202)
def generate(project_id: int, body: GenerateRequest, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Dự án")
    if not db.scalars(select(Document).where(Document.project_id == project_id)).first():
        raise Problem(409, "Chưa có tài liệu", "Hãy nạp tài liệu trước khi sinh đặc tả")
    try:
        get_llm(body.model)
    except LLMNotConfigured as e:
        raise Problem(409, "Chưa cấu hình LLM", str(e)) from e
    from ...services.generation.service import generate as run_gen

    def job(ctx):
        def prog(**kw):
            ctx.update(**kw)
        return run_gen(project_id, document_id=body.document_id, model=body.model, repair=body.repair,
                       max_concurrency=body.max_concurrency, job_id=ctx.job_id, on_progress=prog)

    job_id = get_runner().submit("generate", job, project_id)
    return JobAccepted(job_id=job_id)


@router.post("/projects/{project_id}/specs/import", response_model=SpecOut, status_code=201)
def import_spec(project_id: int, body: SpecImport, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Dự án")
    content = _parse_content(body.content, body.text)
    v = create_version(db, project_id, content, label=body.label or "imported", note=body.note, created_by="user")
    db.commit()
    return spec_out(v, True)


@router.get("/projects/{project_id}/specs", response_model=list[SpecOut])
def list_specs(project_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Dự án")
    return [spec_out(v) for v in db.scalars(select(SpecVersion).where(SpecVersion.project_id == project_id)
                                            .order_by(SpecVersion.version_no.desc()))]


@router.get("/specs/{spec_id}")
def get_spec(spec_id: int, format: str | None = Query(None, pattern="^(yaml|json)$"), db: Session = Depends(get_db)):
    v = get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    if format == "yaml":
        return PlainTextResponse(to_yaml(v.content), media_type="application/yaml")
    if format == "json":
        return Response(json.dumps(v.content, ensure_ascii=False, indent=2), media_type="application/json")
    return spec_out(v, True)


@router.post("/specs/{spec_id}/versions", response_model=SpecOut, status_code=201)
def manual_version(spec_id: int, body: SpecVersionCreate, db: Session = Depends(get_db)):
    parent = get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    content = _parse_content(body.content, body.text)
    from ...services.evaluation.validator import validate_all

    errors = validate_all(content)
    if errors:
        raise Problem(422, "Đặc tả chưa hợp lệ OAS 3.0.3", errors[0]["message"], errors=errors)
    v = create_version(db, parent.project_id, content, label="manual", parent=parent,
                       patch=diff_patch(parent.content, content), note=body.note or "Sửa tay", created_by="user")
    db.commit()
    return spec_out(v, True)


@router.get("/specs/{spec_id}/evidence", response_model=list[EvidenceOut])
def get_evidence(spec_id: int, pointer: str | None = None, db: Session = Depends(get_db)):
    get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    q = select(Evidence).where(Evidence.spec_version_id == spec_id)
    rows = list(db.scalars(q.order_by(Evidence.json_pointer)))
    if pointer is not None:
        exact = [e for e in rows if e.json_pointer == pointer]
        if exact:
            return exact
        # phần tử con hoặc tổ tiên gần nhất
        desc = [e for e in rows if e.json_pointer.startswith(pointer + "/")]
        if desc:
            return desc
        anc = [e for e in rows if pointer.startswith(e.json_pointer + "/")]
        if anc:
            best = max(len(e.json_pointer) for e in anc)
            return [e for e in anc if len(e.json_pointer) == best]
        return []
    return rows


@router.post("/specs/{spec_id}/validate")
def validate(spec_id: int, db: Session = Depends(get_db)):
    v = get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    report = static_report(db, v)
    report["facts"] = facts_summary(v.content)
    db.commit()
    return report


@router.get("/specs/{spec_id}/diff")
def diff(spec_id: int, against: int | None = None, db: Session = Depends(get_db)):
    v = get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    other_id = against or v.parent_id
    if other_id is None:
        raise Problem(422, "Thiếu phiên bản so sánh", "Phiên bản gốc – hãy truyền ?against=")
    o = get_or_404(db, SpecVersion, other_id, "Phiên bản")
    return {"from": {"id": o.id, "version_no": o.version_no, "label": o.label, "yaml": to_yaml(o.content)},
            "to": {"id": v.id, "version_no": v.version_no, "label": v.label, "yaml": to_yaml(v.content)},
            "text_diff": text_diff(o.content, v.content, f"v{o.version_no}", f"v{v.version_no}"),
            "semantic": semantic_diff(o.content, v.content)}


@router.get("/specs/{spec_id}/export")
def export(spec_id: int, format: str = Query("yaml", pattern="^(yaml|json)$"), strip_extensions_: bool = Query(
        False, alias="strip_extensions"), include_evidence: bool = False, db: Session = Depends(get_db)):
    v = get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    content = v.content
    if include_evidence:
        content = with_evidence(content, list(db.scalars(select(Evidence).where(Evidence.spec_version_id == v.id))))
    if strip_extensions_:
        content = strip_extensions(content)
    name = f"openapi_v{v.version_no}.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{name}"'}
    if format == "json":
        return Response(json.dumps(content, ensure_ascii=False, indent=2), media_type="application/json",
                        headers=headers)
    return PlainTextResponse(to_yaml(content), media_type="application/yaml", headers=headers)


# ------------------------------------------------------------------ ground truth & đánh giá
@router.post("/projects/{project_id}/ground-truths", response_model=GroundTruthOut, status_code=201)
def add_ground_truth(project_id: int, body: GroundTruthIn, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Dự án")
    content = _parse_content(body.content, body.text)
    gt = GroundTruth(project_id=project_id, kind=body.kind, content=content, note=body.note)
    db.add(gt)
    db.commit()
    db.refresh(gt)
    return gt


@router.get("/projects/{project_id}/ground-truths", response_model=list[GroundTruthOut])
def list_ground_truths(project_id: int, db: Session = Depends(get_db)):
    return list(db.scalars(select(GroundTruth).where(GroundTruth.project_id == project_id)
                           .order_by(GroundTruth.id.desc())))


@router.post("/specs/{spec_id}/evaluations", response_model=JobAccepted, status_code=202)
def create_evaluation(spec_id: int, body: EvaluationRequest, db: Session = Depends(get_db)):
    v = get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    gt_id = body.ground_truth_id
    if gt_id is not None:
        gt = get_or_404(db, GroundTruth, gt_id, "Ground truth")
        if gt.project_id != v.project_id:
            raise Problem(422, "Ground truth không thuộc dự án")
    ev = Evaluation(spec_version_id=spec_id, ground_truth_id=gt_id, status="queued")
    db.add(ev)
    db.commit()
    ev_id = ev.id

    def job(ctx):
        ctx.update(force=True, stage="evaluate", evaluation_id=ev_id)
        with session_scope() as s:
            e = s.get(Evaluation, ev_id)
            try:
                metrics = run_evaluation(s, e)
            except Exception:
                e.status = "failed"
                raise
        return {"evaluation_id": ev_id, "f1": (metrics.get("L5") or {}).get("micro", {}).get("f1")}

    job_id = get_runner().submit("evaluate", job, v.project_id)
    ev.job_id = job_id
    db.commit()
    return JobAccepted(job_id=job_id, resource_id=ev_id, resource_url=f"/api/v1/evaluations/{ev_id}")


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationOut)
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Evaluation, evaluation_id, "Đánh giá")


@router.get("/specs/{spec_id}/evaluations", response_model=list[EvaluationOut])
def list_evaluations(spec_id: int, db: Session = Depends(get_db)):
    return list(db.scalars(select(Evaluation).where(Evaluation.spec_version_id == spec_id)
                           .order_by(Evaluation.id.desc())))
