"""Kiểm thử, observation, finding, đề xuất, áp dụng, vòng lặp tinh chỉnh."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...jobs import get_runner
from ...models import Finding, FindingObservation, Observation, Proposal, SpecVersion, TestRun, utcnow
from ...schemas.api import (
    ApplyRequest,
    FindingOut,
    JobAccepted,
    ObservationOut,
    ProposalOut,
    ProposalPatch,
    RefineLoopRequest,
    SpecOut,
    TestRunConfig,
    TestRunOut,
)
from ...services.analysis.confidence import tier
from ...services.versioning.refine import ApplyError, apply_proposals, run_refine_loop
from ..deps import Problem, get_or_404
from .specs import spec_out

router = APIRouter(tags=["testing"])


@router.post("/specs/{spec_id}/test-runs", response_model=JobAccepted, status_code=202)
def create_test_run(spec_id: int, body: TestRunConfig, db: Session = Depends(get_db)):
    v = get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    tr = TestRun(spec_version_id=spec_id, config=body.model_dump(exclude_none=True), status="queued")
    db.add(tr)
    db.commit()
    tr_id = tr.id

    def job(ctx):
        from ...services.testing.runner import run_test

        try:
            return run_test(tr_id, ctx)
        except Exception as e:
            from ...db import session_scope

            with session_scope() as s:
                t = s.get(TestRun, tr_id)
                if t.status not in ("cancelled",):
                    t.status = "cancelled" if type(e).__name__ == "JobCancelled" else "failed"
                    t.error = f"{type(e).__name__}: {e}"
                    t.finished_at = utcnow()
            raise

    job_id = get_runner().submit("test_run", job, v.project_id)
    tr.job_id = job_id
    db.commit()
    return JobAccepted(job_id=job_id, resource_id=tr_id, resource_url=f"/api/v1/test-runs/{tr_id}")


@router.get("/specs/{spec_id}/test-runs", response_model=list[TestRunOut])
def list_test_runs(spec_id: int, db: Session = Depends(get_db)):
    return list(db.scalars(select(TestRun).where(TestRun.spec_version_id == spec_id).order_by(TestRun.id.desc())))


@router.get("/projects/{project_id}/test-runs", response_model=list[TestRunOut])
def list_project_test_runs(project_id: int, db: Session = Depends(get_db)):
    q = (select(TestRun).join(SpecVersion, TestRun.spec_version_id == SpecVersion.id)
         .where(SpecVersion.project_id == project_id).order_by(TestRun.id.desc()))
    return list(db.scalars(q))


@router.get("/test-runs/{run_id}", response_model=TestRunOut)
def get_test_run(run_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, TestRun, run_id, "Lượt kiểm thử")


@router.post("/test-runs/{run_id}/cancel", response_model=TestRunOut)
def cancel_test_run(run_id: int, db: Session = Depends(get_db)):
    tr = get_or_404(db, TestRun, run_id, "Lượt kiểm thử")
    if tr.job_id:
        get_runner().cancel(tr.job_id)
    db.refresh(tr)
    return tr


@router.get("/test-runs/{run_id}/observations")
def list_observations(run_id: int, operation: str | None = None, strategy: str | None = None,
                      outcome: str | None = None, status_code: int | None = None,
                      page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    get_or_404(db, TestRun, run_id, "Lượt kiểm thử")
    q = select(Observation).where(Observation.test_run_id == run_id)
    if operation:
        q = q.where(Observation.operation_id == operation)
    if strategy:
        q = q.where(Observation.strategy.like(f"{strategy}%"))
    if outcome:
        q = q.where(Observation.outcome == outcome)
    if status_code:
        q = q.where(Observation.status_code == status_code)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Observation.id).offset((page - 1) * size).limit(size))
    facets = {
        "operations": [r[0] for r in db.execute(select(Observation.operation_id).where(
            Observation.test_run_id == run_id).distinct())],
        "strategies": sorted({r[0].split(".")[0] for r in db.execute(select(Observation.strategy).where(
            Observation.test_run_id == run_id).distinct())}),
    }
    return {"total": total, "page": page, "size": size, "facets": facets,
            "items": [ObservationOut.model_validate(o) for o in rows]}


@router.get("/observations/{obs_id}", response_model=ObservationOut)
def get_observation(obs_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Observation, obs_id, "Observation")


def finding_out(db: Session, f: Finding) -> FindingOut:
    out = FindingOut.model_validate(f)
    out.proposal_ids = [p.id for p in db.scalars(select(Proposal).where(Proposal.finding_id == f.id))]
    return out


@router.get("/test-runs/{run_id}/findings", response_model=list[FindingOut])
def list_findings(run_id: int, code: str | None = None, db: Session = Depends(get_db)):
    get_or_404(db, TestRun, run_id, "Lượt kiểm thử")
    q = select(Finding).where(Finding.test_run_id == run_id)
    if code:
        q = q.where(Finding.code == code)
    return [finding_out(db, f) for f in db.scalars(q.order_by(Finding.code, Finding.confidence.desc()))]


@router.get("/findings/{finding_id}")
def get_finding(finding_id: int, db: Session = Depends(get_db)):
    f = get_or_404(db, Finding, finding_id, "Finding")
    links = list(db.scalars(select(FindingObservation).where(FindingObservation.finding_id == f.id)))
    obs = {o.id: o for o in db.scalars(select(Observation).where(Observation.id.in_([x.observation_id
                                                                                       for x in links])))}
    return {"finding": finding_out(db, f),
            "observations": [{"role": link.role, **ObservationOut.model_validate(obs[link.observation_id]).model_dump()}
                             for link in links if link.observation_id in obs]}


def proposal_out(db: Session, p: Proposal) -> ProposalOut:
    out = ProposalOut.model_validate(p)
    f = db.get(Finding, p.finding_id)
    out.finding = finding_out(db, f) if f else None
    return out


@router.get("/specs/{spec_id}/proposals", response_model=list[ProposalOut])
def list_proposals(spec_id: int, status: str | None = None, test_run_id: int | None = None,
                   db: Session = Depends(get_db)):
    get_or_404(db, SpecVersion, spec_id, "Phiên bản")
    q = select(Proposal).where(Proposal.spec_version_id == spec_id)
    if status:
        q = q.where(Proposal.status.in_(status.split(",")))
    if test_run_id:
        q = q.join(Finding, Proposal.finding_id == Finding.id).where(Finding.test_run_id == test_run_id)
    return [proposal_out(db, p) for p in db.scalars(q.order_by(Proposal.confidence.desc(), Proposal.id))]


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: int, db: Session = Depends(get_db)):
    return proposal_out(db, get_or_404(db, Proposal, proposal_id, "Đề xuất"))


def _review(db: Session, proposal_id: int, status: str) -> ProposalOut:
    p = get_or_404(db, Proposal, proposal_id, "Đề xuất")
    if p.status in ("applied", "verified"):
        raise Problem(409, "Đề xuất đã được áp dụng")
    p.status = status
    p.reviewed_by = "user"
    p.reviewed_at = utcnow()
    db.commit()
    return proposal_out(db, p)


@router.post("/proposals/{proposal_id}/accept", response_model=ProposalOut)
def accept(proposal_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Proposal, proposal_id, "Đề xuất")
    return _review(db, proposal_id, "edited" if p.status == "edited" else "accepted")


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
def reject(proposal_id: int, db: Session = Depends(get_db)):
    return _review(db, proposal_id, "rejected")


@router.patch("/proposals/{proposal_id}", response_model=ProposalOut)
def edit_proposal(proposal_id: int, body: ProposalPatch, db: Session = Depends(get_db)):
    p = get_or_404(db, Proposal, proposal_id, "Đề xuất")
    if p.status in ("applied", "verified"):
        raise Problem(409, "Đề xuất đã được áp dụng")
    for op in body.json_patch:
        if op.get("op") not in ("add", "remove", "replace", "move", "copy", "test") or "path" not in op:
            raise Problem(422, "JSON Patch không hợp lệ", f"Thao tác không hợp lệ: {op}")
    p.json_patch = body.json_patch
    p.status = "edited"
    p.reviewed_by = "user"
    p.reviewed_at = utcnow()
    db.commit()
    return proposal_out(db, p)


@router.post("/specs/{spec_id}/proposals/accept-threshold", response_model=list[ProposalOut])
def accept_by_threshold(spec_id: int, threshold: float = Query(0.8, ge=0, le=1), include_conflicts: bool = False,
                        db: Session = Depends(get_db)):
    """Chấp nhận hàng loạt các đề xuất đang chờ có độ tin cậy ≥ ngưỡng."""
    out = []
    for p in db.scalars(select(Proposal).where(Proposal.spec_version_id == spec_id, Proposal.status == "pending")):
        if p.confidence >= threshold and (include_conflicts or not p.doc_conflict):
            p.status = "accepted"
            p.reviewed_by = "user"
            p.reviewed_at = utcnow()
            out.append(p)
    db.commit()
    return [proposal_out(db, p) for p in out]


@router.post("/specs/{spec_id}/apply", response_model=SpecOut, status_code=201)
def apply(spec_id: int, body: ApplyRequest, db: Session = Depends(get_db)):
    try:
        v, warnings = apply_proposals(db, spec_id, body.proposal_ids, note=body.note)
    except ApplyError as e:
        raise Problem(409, "Không áp dụng được", str(e)) from e
    db.commit()
    out = spec_out(v, True)
    out.stats = {**(out.stats or {}), "warnings": warnings}
    return out


@router.post("/specs/{spec_id}/refine-loop", response_model=JobAccepted, status_code=202)
def refine_loop(spec_id: int, body: RefineLoopRequest, db: Session = Depends(get_db)):
    v = get_or_404(db, SpecVersion, spec_id, "Phiên bản")

    def job(ctx):
        return run_refine_loop(spec_id, max_iter=body.max_iter, auto_accept_threshold=body.auto_accept_threshold,
                               min_confidence=body.min_confidence,
                               test_config=body.test_config.model_dump(exclude_none=True), ctx=ctx)

    return JobAccepted(job_id=get_runner().submit("refine_loop", job, v.project_id))


__all__ = ["router", "tier"]
