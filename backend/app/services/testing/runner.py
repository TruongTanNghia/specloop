"""Điều phối một lượt kiểm thử: an toàn → reset SUT → engine → lưu observation/finding/proposal."""
from __future__ import annotations

import time

from sqlalchemy import select

from ...config import get_settings
from ...db import SessionLocal, session_scope
from ...jobs import JobCancelled, JobContext
from ...models import Finding, FindingObservation, Observation, Project, Proposal, SpecVersion, TestRun, utcnow
from ...security import decrypt_json
from ..analysis.confidence import tier
from .engine import Engine, EngineConfig
from .opmodel import server_url
from .prober import Prober, check_target

NO_PATCH_CODES = {"D0", "INFO"}


class Recorder:
    """Ghi observation theo lô trong một phiên riêng của luồng job."""

    def __init__(self, test_run_id: int, batch: int = 25):
        self.db = SessionLocal()
        self.test_run_id = test_run_id
        self.batch = batch
        self.pending = 0

    def __call__(self, rec: dict) -> int:
        o = Observation(test_run_id=self.test_run_id, **rec)
        self.db.add(o)
        self.db.flush()
        self.pending += 1
        if self.pending >= self.batch:
            self.db.commit()
            self.pending = 0
        return o.id

    def commit(self) -> None:
        self.db.commit()
        self.pending = 0

    def close(self) -> None:
        self.db.commit()
        self.db.close()


def run_test(test_run_id: int, ctx: JobContext | None = None) -> dict:
    s = get_settings()
    with session_scope() as db:
        tr = db.get(TestRun, test_run_id)
        version = db.get(SpecVersion, tr.spec_version_id)
        project = db.get(Project, version.project_id)
        cfg = dict(tr.config or {})
        spec = version.content
        secrets = decrypt_json(project.secrets_enc)
        auth = dict(project.auth_config or {"type": "none"})
        reset_cfg = project.reset_config
        allowed_hosts = list(project.allowed_hosts or [])
        policy = project.policy or "descriptive"
        project_mode = project.mode
        version_id = version.id
        tr.status = "running"
        tr.started_at = utcnow()
        base_url = cfg.get("base_url") or project.base_url or server_url(spec)
    if not base_url:
        raise ValueError("Chưa có base URL để kiểm thử (cấu hình dự án, lượt kiểm thử hoặc servers trong đặc tả)")
    from urllib.parse import urlparse

    hosts = allowed_hosts or [urlparse(base_url).hostname or ""]
    sandbox = check_target(base_url, hosts, s.allowed_networks)
    mode = cfg.get("mode") or (project_mode if project_mode in ("safe", "full") else None) or (
        "full" if sandbox else "safe")
    cap_rps = s.TEST_SANDBOX_MAX_RPS if sandbox else s.TEST_PUBLIC_MAX_RPS
    rps = min(cfg.get("max_rps") or cap_rps, cap_rps) if cap_rps > 0 else (cfg.get("max_rps") or 0)
    budget = cfg.get("budget_per_operation") or (s.TEST_SANDBOX_BUDGET if sandbox else s.TEST_PUBLIC_BUDGET)
    timeout = cfg.get("timeout_s") or s.TEST_TIMEOUT_S
    effective = {"base_url": base_url, "mode": mode, "sandbox": sandbox, "max_rps": rps, "budget_per_operation": budget,
                 "timeout_s": timeout}

    recorder = Recorder(test_run_id)
    last_cancel_check = [0.0]

    def cancel_check():
        if ctx is None:
            return
        now = time.monotonic()
        if now - last_cancel_check[0] > 1.0:
            last_cancel_check[0] = now
            ctx.check_cancel()

    prober = Prober(base_url, max_rps=rps, budget=budget, timeout=timeout, auth=auth, secret=secrets.get("auth"),
                    extra_redact=set((secrets.get("reset_headers") or {}).keys()), recorder=recorder,
                    cancel_check=cancel_check)
    t0 = time.perf_counter()
    reset_info = None
    if cfg.get("reset", True) and reset_cfg:
        reset_info = prober.reset(reset_cfg, secrets.get("reset_headers"))

    def progress(**kw):
        if ctx is not None:
            recorder.commit()  # nhả khóa ghi SQLite trước khi job cập nhật tiến trình
            ctx.update(test_run_id=test_run_id, **kw)

    eng_cfg = EngineConfig(strategies=set(cfg.get("strategies") or EngineConfig().strategies),
                           repeats=int(cfg.get("repeats") or 3), mode=mode, operations=cfg.get("operations"))
    eng = Engine(spec, prober, eng_cfg, progress)
    status, error = "succeeded", None
    try:
        eng.run()
    except JobCancelled:
        status = "cancelled"
    finally:
        recorder.close()
        prober.close()
    duration = time.perf_counter() - t0
    summary = save_results(test_run_id, version_id, eng, policy) if status == "succeeded" else {}
    stats = {
        "requests": prober.total, "outcomes": prober.outcomes, "duration_s": round(duration, 2),
        "operations": eng.op_status, "requests_by_operation": prober.used, "effective_config": effective,
        "reset": reset_info, "verified": eng.verified, "unverified": eng.unverified, **summary,
    }
    with session_scope() as db:
        tr = db.get(TestRun, test_run_id)
        tr.stats = stats
        tr.status = status
        tr.error = error
        tr.finished_at = utcnow()
    if status == "cancelled":
        raise JobCancelled()
    if ctx is not None:
        ctx.update(force=True, stage="done", done=len(eng.op_status), total=len(eng.op_status),
                   outcomes=prober.outcomes, requests=prober.total)
    return {"test_run_id": test_run_id, "findings": summary.get("findings_by_code", {}),
            "proposals": summary.get("proposals", 0), "requests": prober.total}


def save_results(test_run_id: int, version_id: int, eng: Engine, policy: str) -> dict:
    by_code: dict[str, int] = {}
    n_props = 0
    with session_scope() as db:
        for f in eng.findings:
            conf = f.confidence
            fd = Finding(test_run_id=test_run_id, code=f.code, operation_id=f.op, location=f.location,
                         keyword=f.keyword, json_pointer=f.pointer, summary=f.summary,
                         details={k: v for k, v in f.details.items() if k != "list_edit"} | (
                             {"message": f.message} if f.message else {}),
                         confidence=conf, doc_conflict=f.doc_conflict,
                         status="reported" if f.code in NO_PATCH_CODES else "open")
            db.add(fd)
            db.flush()
            seen = set()
            for oid in f.support:
                if oid not in seen:
                    seen.add(oid)
                    db.add(FindingObservation(finding_id=fd.id, observation_id=oid, role="support"))
            for oid in f.contradict:
                if oid not in seen:
                    seen.add(oid)
                    db.add(FindingObservation(finding_id=fd.id, observation_id=oid, role="contradict"))
            by_code[f.code] = by_code.get(f.code, 0) + 1
            if f.code in NO_PATCH_CODES or not f.patch:
                continue
            if policy == "prescriptive" and f.doc_conflict:
                fd.status = "reported"
                continue
            db.add(Proposal(finding_id=fd.id, spec_version_id=version_id, code=f.code, target=f.pointer,
                            json_patch=f.patch, evidence={"runtime": f.support[:50], "message": f.message,
                                                          "doc": []},
                            channels=f.channels, confidence=conf, doc_conflict=f.doc_conflict,
                            tier=tier(conf, f.doc_conflict), status="pending"))
            n_props += 1
        _attach_doc_evidence(db, version_id)
        _regression(db, version_id, eng)
    return {"findings_by_code": by_code, "findings": sum(by_code.values()), "proposals": n_props}


def _attach_doc_evidence(db, version_id: int) -> None:
    """Gắn trích dẫn tài liệu (nếu có) cho đề xuất – theo JSON Pointer của phần tử bị sửa hoặc tổ tiên gần nhất."""
    from ...models import Evidence

    evs = list(db.scalars(select(Evidence).where(Evidence.spec_version_id == version_id)))
    if not evs:
        return
    for p in db.scalars(select(Proposal).where(Proposal.spec_version_id == version_id, Proposal.status == "pending")):
        target = p.target or ""
        best = None
        for ev in evs:
            if target.startswith(ev.json_pointer) and (best is None or len(ev.json_pointer) > len(best.json_pointer)):
                best = ev
        if best is not None:
            e = dict(p.evidence or {})
            e["doc"] = [{"chunk_id": best.chunk_id, "quote": best.quote, "pointer": best.json_pointer}]
            p.evidence = e


def _regression(db, version_id: int, eng: Engine) -> None:
    """Kiểm thử hồi quy: đề xuất đã áp dụng để tạo phiên bản này → verified nếu không còn finding cùng vị trí."""
    applied = list(db.scalars(select(Proposal).where(Proposal.applied_version_id == version_id)))
    if not applied:
        return
    open_ptrs = {(f.code, f.pointer) for f in eng.findings if f.patch}
    for p in applied:
        f = db.get(Finding, p.finding_id)
        if (p.code, p.target) in open_ptrs:
            f.status = "reopened"
        else:
            p.status = "verified"
            f.status = "verified"
