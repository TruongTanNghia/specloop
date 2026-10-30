"""Tác vụ nền: bảng `job` + ThreadPoolExecutor trong tiến trình.

Interface `JobRunner` tách riêng để có thể thay bằng Redis/Arq ở bản sau mà không đổi lớp dịch vụ.
Tiến trình được ghi vào bảng job; SSE (`GET /jobs/{id}/events`) đọc lại bảng này.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from .db import session_scope
from .models import Job, utcnow

log = logging.getLogger("specloop.jobs")

TERMINAL = {"succeeded", "failed", "cancelled"}


class JobCancelled(Exception):
    pass


class JobContext:
    """Truyền cho hàm job: cập nhật tiến trình, kiểm tra cờ hủy."""

    def __init__(self, job_id: str, min_interval: float = 0.3):
        self.job_id = job_id
        self._last = 0.0
        self._min_interval = min_interval
        self._progress: dict[str, Any] = {}
        self._lock = threading.Lock()

    def update(self, force: bool = False, **progress: Any) -> None:
        with self._lock:
            self._progress.update(progress)
            now = time.monotonic()
            if not force and now - self._last < self._min_interval:
                return
            self._last = now
            snapshot = dict(self._progress)
        with session_scope() as db:
            job = db.get(Job, self.job_id)
            if job is not None:
                job.progress = snapshot
                job.updated_at = utcnow()

    def flush(self) -> None:
        self.update(force=True)

    def is_cancelled(self) -> bool:
        with session_scope() as db:
            job = db.get(Job, self.job_id)
            return bool(job and job.cancel_requested)

    def check_cancel(self) -> None:
        if self.is_cancelled():
            raise JobCancelled()


JobFn = Callable[[JobContext], dict | None]


class JobRunner(ABC):
    @abstractmethod
    def submit(self, job_type: str, fn: JobFn, project_id: int | None = None) -> str: ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...

    def wait(self, job_id: str, timeout: float | None = None) -> None:  # tiện cho test
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with session_scope() as db:
                job = db.get(Job, job_id)
                if job is None or job.status in TERMINAL:
                    return
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(job_id)
            time.sleep(0.1)


class ThreadJobRunner(JobRunner):
    def __init__(self, workers: int = 4):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._futures: dict[str, Future] = {}

    def submit(self, job_type: str, fn: JobFn, project_id: int | None = None) -> str:
        with session_scope() as db:
            job = Job(type=job_type, project_id=project_id, status="queued", progress={})
            db.add(job)
            db.flush()
            job_id = job.id
        self._futures[job_id] = self._pool.submit(self._run, job_id, fn)
        return job_id

    def _run(self, job_id: str, fn: JobFn) -> None:
        ctx = JobContext(job_id)
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job.cancel_requested:
                job.status = "cancelled"
                return
            job.status = "running"
            job.updated_at = utcnow()
        status, result, error = "succeeded", None, None
        try:
            result = fn(ctx)
        except JobCancelled:
            status = "cancelled"
        except Exception as e:  # noqa: BLE001
            status = "failed"
            error = f"{type(e).__name__}: {e}"
            log.error("job %s failed\n%s", job_id, traceback.format_exc())
        ctx.flush()
        with session_scope() as db:
            job = db.get(Job, job_id)
            job.status = status
            job.result = result
            job.error = error
            job.updated_at = utcnow()

    def cancel(self, job_id: str) -> bool:
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job is None or job.status in TERMINAL:
                return False
            job.cancel_requested = True
            return True


_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        from .config import get_settings

        _runner = ThreadJobRunner(get_settings().JOB_WORKERS)
    return _runner


def set_runner(runner: JobRunner) -> None:
    global _runner
    _runner = runner
