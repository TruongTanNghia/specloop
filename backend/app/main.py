"""Khởi tạo FastAPI: CORS, router /api/v1, lỗi RFC 7807 (application/problem+json)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.deps import Problem
from .api.v1 import bench, jobs, misc, projects, specs, testing
from .config import get_settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
for _noisy in ("httpx", "httpcore", "openai"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)  # mỗi probe là một request – không ghi log từng cái
PROBLEM = "application/problem+json"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="SpecLoop API", version="1.0.0", lifespan=lifespan,
              description="Sinh đặc tả OpenAPI từ tài liệu REST bằng LLM và tinh chỉnh ràng buộc từ phản hồi kiểm thử.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


def _problem(request: Request, status: int, title: str, detail: str | None, errors: list | None = None,
             type_: str = "about:blank") -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, "detail": detail, "instance": str(request.url.path)}
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


@app.exception_handler(Problem)
async def _problem_handler(request: Request, e: Problem):
    return _problem(request, e.status_code, e.title, e.detail, e.errors, e.type)


@app.exception_handler(StarletteHTTPException)
async def _http_handler(request: Request, e: StarletteHTTPException):
    return _problem(request, e.status_code, str(e.detail), None)


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, e: RequestValidationError):
    errs = [{"loc": list(x.get("loc", [])), "msg": x.get("msg")} for x in e.errors()]
    return _problem(request, 422, "Dữ liệu không hợp lệ", errs[0]["msg"] if errs else None, errs)


@app.exception_handler(Exception)
async def _unhandled(request: Request, e: Exception):
    logging.getLogger("specloop").exception("Lỗi không xử lý")
    return _problem(request, 500, "Lỗi máy chủ", f"{type(e).__name__}: {str(e)[:300]}")


for r in (projects.router, specs.router, testing.router, jobs.router, misc.router, bench.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health")
def root_health():
    return {"status": "ok"}
