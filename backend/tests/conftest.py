"""Fixture dùng chung: CSDL SQLite tạm, TestClient, Bookstore-Lab chạy bằng uvicorn trong luồng nền."""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="specloop-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["TEST_SANDBOX_MAX_RPS"] = "0"  # không giới hạn tốc độ khi test với SUT cục bộ
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_MODEL"] = ""
os.environ.setdefault("SECRET_KEY", "test-secret")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.bench import BENCH_DIR  # noqa: E402
from app.db import init_db  # noqa: E402

BOOKSTORE = BENCH_DIR / "apis" / "bookstore-lab"


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def sut():
    """Chạy Bookstore-Lab (SpecLoop-Bench/apis/bookstore-lab/sut/app.py) trên cổng ngẫu nhiên."""
    import uvicorn

    spec = importlib.util.spec_from_file_location("bookstore_sut", BOOKSTORE / "sut" / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(mod.app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield {"base_url": f"http://127.0.0.1:{port}/v1", "origin": f"http://127.0.0.1:{port}"}
    server.should_exit = True
    th.join(timeout=5)


def wait_job(client, job_id: str, timeout: float = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/v1/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(0.2)
    raise TimeoutError(job_id)
