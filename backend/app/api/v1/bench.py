"""Bộ dữ liệu SpecLoop-Bench: người dùng tự thêm / xem / xóa API (đặc tả OpenAPI làm ground truth)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Response
from fastapi.responses import PlainTextResponse

from ...schemas.api import BenchApiCreate, BenchSource
from ...services import bench_admin
from ..deps import Problem

router = APIRouter(tags=["bench"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except bench_admin.BenchError as e:
        raise Problem(e.status, e.title, e.detail) from e


@router.get("/bench/apis")
def list_bench_apis():
    return _call(bench_admin.list_apis)


@router.get("/bench/apis/{api_id}")
def get_bench_api(api_id: str):
    return _call(bench_admin.get_api, api_id)


@router.get("/bench/apis/{api_id}/file", response_class=PlainTextResponse)
def get_bench_file(api_id: str, path: str = Query(..., max_length=300)):
    text, media = _call(bench_admin.read_file, api_id, path)
    return PlainTextResponse(text, media_type=f"{media}; charset=utf-8")


@router.post("/bench/preview")
def preview_bench_spec(body: BenchSource):
    """Đọc + chuẩn hóa thử đặc tả (không ghi gì): phiên bản gốc, số operation, lỗi hợp lệ, gợi ý meta."""
    return _call(bench_admin.preview, body.spec_url, body.spec_text, body.filename)


@router.post("/bench/apis", status_code=201)
def create_bench_api(body: BenchApiCreate):
    return _call(bench_admin.create, body.model_dump(by_alias=False))


@router.delete("/bench/apis/{api_id}", status_code=204)
def delete_bench_api(api_id: str):
    _call(bench_admin.delete, api_id)
    return Response(status_code=204)


@router.post("/bench/apis/{api_id}/connectivity")
def check_bench_connectivity(api_id: str):
    return _call(bench_admin.check_connectivity_of, api_id)
