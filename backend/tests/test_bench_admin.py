"""Trang “Bộ dữ liệu”: xem trước, thêm, xem tệp, xóa API – chạy trên bản sao SpecLoop-Bench trong thư mục tạm."""
from __future__ import annotations

import json
import shutil

import pytest

from app.bench import BENCH_DIR
from app.services import bench_admin

SPEC_31 = """
openapi: 3.1.0
info: {title: Kho Sách Thử, version: '1.0', license: {name: MIT, identifier: MIT}}
servers: [{url: 'http://localhost:9999/v1'}]
paths:
  /books:
    get:
      summary: Liệt kê sách
      parameters:
        - {name: limit, in: query, schema: {type: int, minimum: '1', maximum: '100'}}
        - {name: wide, in: query, schema: {type: boolean, default: 'false'}}
      responses: {'200': {description: OK}}
  /books/{id}:
    get:
      summary: Lấy một cuốn sách (thiếu khai báo tham số path)
      responses: {'200': {description: OK}, '404': {description: Không có}}
"""

SWAGGER_2 = {
    "swagger": "2.0", "info": {"title": "Echo", "version": "1"}, "host": "echo.example.org", "basePath": "/api",
    "schemes": ["https"],
    "paths": {"/echo": {"post": {"consumes": ["application/json"],
                                 "parameters": [{"in": "body", "name": "body", "required": True,
                                                 "schema": {"$ref": "#/definitions/Msg"}}],
                                 "responses": {"200": {"description": "ok", "schema": {"$ref": "#/definitions/Msg"}}}}}},
    "definitions": {"Msg": {"type": "object", "required": ["text"],
                            "properties": {"text": {"type": "string", "maxLength": 50}}}},
}

DOC = "# Echo\n\n" + "Gửi một thông điệp, máy chủ trả lại đúng thông điệp đó. " * 10


@pytest.fixture()
def bench(tmp_path, monkeypatch):
    """Bản sao tối thiểu: tools/ + một API gốc (language-tool, không có added_via → không được xóa)."""
    root = tmp_path / "bench"
    shutil.copytree(BENCH_DIR / "tools", root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "apis").mkdir()
    shutil.copytree(BENCH_DIR / "apis" / "language-tool", root / "apis" / "language-tool")
    monkeypatch.setattr(bench_admin, "BENCH_DIR", root)
    bench_admin.build_dataset.update_manifest(root, None, verbose=False)
    return root


def test_preview_repairs_31_spec(client, bench):
    r = client.post("/api/v1/bench/preview", json={"spec_text": SPEC_31, "filename": "kho.yaml"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["valid"] and p["source_version"] == "OpenAPI 3.1.0" and p["operations"] == 2
    notes = " ".join(p["normalization"])
    assert "hạ cấp OpenAPI 3.1.0" in notes and "tên kiểu không chuẩn" in notes and "tham số path thiếu" in notes
    s = p["suggested"]
    assert s["id"] == "kho-sach-thu" and not s["exists"]  # slug bỏ dấu tiếng Việt
    assert s["base_url"] == "http://localhost:9999/v1" and s["group"] == "A" and s["scope"] == "full"
    assert s["license"] == "MIT" and s["probe_path"] == "/books"


def test_preview_rejects_non_openapi(client, bench):
    r = client.post("/api/v1/bench/preview", json={"spec_text": "xin chào: thế giới"})
    assert r.status_code == 422 and "OpenAPI" in r.json()["detail"]
    assert client.post("/api/v1/bench/preview", json={}).status_code == 422


def test_create_list_file_delete(client, bench):
    body = {"spec_text": SPEC_31, "filename": "kho.yaml", "id": "kho-sach", "name": "Kho Sách Thử", "group": "A",
            "env": "local-docker", "scope": "full", "base_url": "http://localhost:9999/v1", "license": "MIT",
            "description": "API thử nghiệm", "probe_path": "/books", "make_ablated": True, "added_by": "khách"}
    r = client.post("/api/v1/bench/apis", json=body)
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["validation"]["ok"], res["validation"]
    assert res["stats"]["operations"] == 2 and res["stats"]["constraints_no_type"] > 0
    d = bench / "apis" / "kho-sach"
    for rel in ("meta.yaml", "source/openapi_original.yaml", "ground_truth/openapi.yaml", "ground_truth/facts.jsonl",
                "docs/rendered.md", "docs/ablated.md"):
        assert (d / rel).exists(), rel
    man = json.loads((bench / "manifest.json").read_text(encoding="utf-8"))
    assert man["n_apis"] == 2 and all("\\" not in k for e in man["apis"] for k in e["files"])

    rows = {a["id"]: a for a in client.get("/api/v1/bench/apis").json()}
    assert rows["kho-sach"]["deletable"] and rows["kho-sach"]["added_via"] == "web"
    assert not rows["language-tool"]["deletable"]

    detail = client.get("/api/v1/bench/apis/kho-sach").json()
    assert detail["meta"]["source"]["spec_url"].startswith("tải lên trực tiếp")
    assert any(f["path"] == "docs/rendered.md" for f in detail["files"])
    doc = client.get("/api/v1/bench/apis/kho-sach/file", params={"path": "docs/rendered.md"})
    assert doc.status_code == 200 and "Kho Sách Thử" in doc.text
    assert client.get("/api/v1/bench/apis/kho-sach/file", params={"path": "../language-tool/meta.yaml"}).status_code == 404

    assert client.post("/api/v1/bench/apis", json=body).status_code == 409  # trùng id
    assert client.delete("/api/v1/bench/apis/language-tool").status_code == 403  # API gốc
    assert client.delete("/api/v1/bench/apis/kho-sach").status_code == 204
    assert not d.exists() and client.get("/api/v1/bench/apis/kho-sach").status_code == 404
    assert json.loads((bench / "manifest.json").read_text(encoding="utf-8"))["n_apis"] == 1


def test_create_from_swagger2_with_original_doc(client, bench):
    r = client.post("/api/v1/bench/apis", json={
        "spec_text": json.dumps(SWAGGER_2), "filename": "swagger.json", "id": "echo", "name": "Echo",
        "auth": {"type": "apiKey", "in": "header", "name": "X-Key", "env_var": "ECHO_KEY"},
        "doc_original_text": DOC, "doc_original_filename": "echo.md"})
    assert r.status_code == 201, r.text
    assert any("Swagger 2.0" in n for n in r.json()["normalization"])
    meta = client.get("/api/v1/bench/apis/echo").json()["meta"]
    assert meta["docs"]["original"] == "docs/original.md"
    assert meta["environment"]["auth"] == {"type": "apiKey", "in": "header", "name": "X-Key", "env_var": "ECHO_KEY"}
    assert meta["environment"]["base_url"] == "https://echo.example.org/api"


def test_create_rejects_bad_input(client, bench):
    bad_id = client.post("/api/v1/bench/apis", json={"spec_text": SPEC_31, "id": "Kho Sach", "name": "x"})
    assert bad_id.status_code == 422 and "id chỉ gồm" in bad_id.json()["detail"]
    broken = client.post("/api/v1/bench/apis", json={"spec_text": "openapi: 3.0.3\ninfo: {title: x, version: '1'}\npaths: {}",
                                                     "id": "rong", "name": "Rỗng"})
    assert broken.status_code == 422
    assert not (bench / "apis" / "rong").exists()
