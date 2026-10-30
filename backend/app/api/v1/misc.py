"""Thực nghiệm, nhà cung cấp LLM, thống kê tổng quan, sức khỏe."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db, session_scope
from ...jobs import get_runner
from ...models import Experiment, Finding, LLMCall, Project, Proposal, SpecVersion, TestRun
from ...schemas.api import ExperimentRequest, JobAccepted, LLMTestRequest
from ...services.experiments import CSV_FIELDS, list_apis, run_matrix
from ...services.llm.gateway import LLMError, get_llm, providers_info
from ..deps import Problem, get_or_404

router = APIRouter(tags=["misc"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    s = get_settings()
    return {"status": "ok", "llm_configured": s.llm_configured, "bench_dir_exists": Path(s.BENCH_DIR).exists()}


@router.get("/llm/providers")
def llm_providers():
    return providers_info()


@router.post("/llm/test")
def llm_test(body: LLMTestRequest):
    """Thử kết nối LLM (base_url/model tạm thời hoặc theo .env). Khóa API không được lưu."""
    try:
        llm = get_llm(body.model, body.base_url, body.api_key)
        llm.cache_enabled = False
        res = llm.chat_json("Return ONLY a JSON object.", 'Return {"ok": true}', purpose="ping")
        return {"ok": True, "model": llm.model, "provider": llm.provider, "latency_ms": round(res.latency_ms, 1),
                "response": res.data if res.data is not None else res.text[:200]}
    except LLMError as e:
        return {"ok": False, "error": str(e)[:500]}


@router.get("/llm/usage")
def llm_usage(db: Session = Depends(get_db)):
    rows = db.execute(select(LLMCall.model, func.count(), func.sum(LLMCall.input_tokens),
                             func.sum(LLMCall.output_tokens), func.sum(case((LLMCall.cached.is_(True), 1), else_=0)))
                      .group_by(LLMCall.model)).all()
    return [{"model": m, "calls": n, "input_tokens": i or 0, "output_tokens": o or 0, "cached": c or 0}
            for m, n, i, o, c in rows]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    def count(model, *where):
        q = select(func.count()).select_from(model)
        for w in where:
            q = q.where(w)
        return db.scalar(q) or 0

    tok = db.execute(select(func.coalesce(func.sum(LLMCall.input_tokens), 0),
                            func.coalesce(func.sum(LLMCall.output_tokens), 0), func.count())).one()
    recent = [{"id": p.id, "name": p.name, "created_at": p.created_at}
              for p in db.scalars(select(Project).order_by(Project.id.desc()).limit(8))]
    by_code = dict(db.execute(select(Finding.code, func.count()).group_by(Finding.code)).all())
    return {"projects": count(Project), "versions": count(SpecVersion), "test_runs": count(TestRun),
            "open_findings": count(Finding, Finding.status == "open"),
            "pending_proposals": count(Proposal, Proposal.status == "pending"),
            "findings_by_code": by_code,
            "llm": {"input_tokens": tok[0], "output_tokens": tok[1], "calls": tok[2]}, "recent_projects": recent}


# ------------------------------------------------------------------ thực nghiệm
@router.get("/experiments/apis")
def experiment_apis():
    return list_apis()


@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db)):
    return [{"id": e.id, "name": e.name, "status": e.status, "job_id": e.job_id, "created_at": e.created_at,
             "config": e.config, "rows": len(e.results or [])}
            for e in db.scalars(select(Experiment).order_by(Experiment.id.desc()))]


@router.post("/experiments", response_model=JobAccepted, status_code=202)
def create_experiment(body: ExperimentRequest, db: Session = Depends(get_db)):
    known = {a["id"] for a in list_apis()}
    bad = [a for a in body.apis if a not in known and a != "all"]
    if bad:
        raise Problem(422, "API không có trong SpecLoop-Bench", ", ".join(bad))
    exp = Experiment(name=body.name, config=body.model_dump(), status="queued")
    db.add(exp)
    db.commit()
    exp_id = exp.id
    out_dir = Path(get_settings().DATA_DIR) / "experiments" / f"{exp_id}-{body.name}"

    def job(ctx):
        with session_scope() as s:
            s.get(Experiment, exp_id).status = "running"
        try:
            res = run_matrix(body.model_dump(), out_dir, ctx, log=lambda *_: None)
        except Exception:
            with session_scope() as s:
                s.get(Experiment, exp_id).status = "failed"
            raise
        with session_scope() as s:
            e = s.get(Experiment, exp_id)
            e.status = "succeeded"
            e.results = res["rows"]
            e.summary = res["summary"]
            e.output_dir = res["output_dir"]
        return {"experiment_id": exp_id, "rows": len(res["rows"])}

    job_id = get_runner().submit("experiment", job, None)
    exp.job_id = job_id
    db.commit()
    return JobAccepted(job_id=job_id, resource_id=exp_id, resource_url=f"/api/v1/experiments/{exp_id}/results")


@router.get("/experiments/{exp_id}/results")
def experiment_results(exp_id: int, format: str | None = Query(None, pattern="^(csv|md)$"),
                       db: Session = Depends(get_db)):
    e = get_or_404(db, Experiment, exp_id, "Thực nghiệm")
    if format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in e.results or []:
            w.writerow(r)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="experiment_{exp_id}.csv"'})
    if format == "md":
        p = Path(e.output_dir or "") / "summary.md"
        return PlainTextResponse(p.read_text(encoding="utf-8") if p.exists() else "", media_type="text/markdown")
    return {"id": e.id, "name": e.name, "status": e.status, "job_id": e.job_id, "config": e.config,
            "rows": e.results or [], "summary": e.summary, "output_dir": e.output_dir}
