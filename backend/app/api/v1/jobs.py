"""Job nền và luồng sự kiện SSE."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import SessionLocal, get_db
from ...jobs import TERMINAL, get_runner
from ...models import Job
from ...schemas.api import JobOut
from ..deps import get_or_404

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(project_id: int | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = select(Job)
    if project_id is not None:
        q = q.where(Job.project_id == project_id)
    return list(db.scalars(q.order_by(Job.created_at.desc()).limit(limit)))


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Job, job_id, "Job")


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Job, job_id, "Job")
    get_runner().cancel(job_id)
    job = db.get(Job, job_id)
    db.refresh(job)
    return job


def _snapshot(job_id: str) -> dict | None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return None
        return {"job_id": job.id, "type": job.type, "status": job.status, "progress": job.progress or {},
                "result": job.result, "error": job.error}
    finally:
        db.close()


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    """SSE: `progress` khi tiến trình thay đổi (≤ 0,5 s/lần), `finished` khi job kết thúc."""

    async def stream():
        last = None
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            snap = await asyncio.to_thread(_snapshot, job_id)
            if snap is None:
                yield f"event: error\ndata: {json.dumps({'job_id': job_id, 'error': 'not found'})}\n\n"
                return
            payload = {"job_id": job_id, "status": snap["status"], **snap["progress"]}
            text = json.dumps(payload, ensure_ascii=False, default=str)
            if text != last:
                last = text
                idle = 0
                yield f"event: progress\ndata: {text}\n\n"
            else:
                idle += 1
                if idle % 30 == 0:
                    yield ": keep-alive\n\n"
            if snap["status"] in TERMINAL:
                fin = {"job_id": job_id, "status": snap["status"], "result": snap["result"], "error": snap["error"]}
                yield f"event: finished\ndata: {json.dumps(fin, ensure_ascii=False, default=str)}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
