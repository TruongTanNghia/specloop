"""Nguồn đặc tả khi thêm API: link GitHub/GitLab/Gist, trang HTML, đặc tả chia nhiều tệp, các lỗi hợp lệ hay gặp.

Không gọi mạng thật: bench_admin._download được thay bằng một "máy chủ" giả trong bộ nhớ."""
from __future__ import annotations

import json
import urllib.error

import pytest
import yaml

from app.services import bench_admin
from app.services.bench_admin import spec_import

from .test_bench_admin import bench  # noqa: F401 – fixture bản sao SpecLoop-Bench

RAW = "https://raw.githubusercontent.com/acme/shop/main/spec"

# đặc tả gốc + 3 tệp con: đường dẫn tách tệp, schema đệ quy (Category.parent -> Category), tham chiếu ngược về tệp gốc
FILES = {
    f"{RAW}/openapi.yaml": """
openapi: 3.0.3
info: {title: Shop, version: '1'}
servers: [{url: 'https://shop.example.org'}]
paths:
  /items: {$ref: './paths/items.yaml'}
components:
  schemas:
    Money: {type: number, minimum: 0}
""",
    f"{RAW}/paths/items.yaml": """
get:
  parameters:
    - {name: limit, in: query, schema: {type: integer, minimum: 1, maximum: 50}}
  responses:
    '200':
      description: OK
      content:
        application/json:
          schema: {type: array, items: {$ref: '../schemas/item.yaml'}}
""",
    f"{RAW}/schemas/item.yaml": """
type: object
required: [id]
properties:
  id: {type: string}
  price: {$ref: '../openapi.yaml#/components/schemas/Money'}
  category: {$ref: './category.yaml'}
""",
    f"{RAW}/schemas/category.yaml": """
type: object
properties:
  name: {type: string, maxLength: 40}
  parent: {$ref: './category.yaml'}
""",
}


@pytest.fixture()
def fake_web(monkeypatch):
    calls: list[str] = []

    def download(url: str):
        calls.append(url)
        if url not in FILES:
            raise bench_admin.BenchError(422, "Không tải được đặc tả", f"Máy chủ trả HTTP 404 cho {url}")
        return FILES[url].encode("utf-8"), "." + url.rsplit(".", 1)[-1]

    monkeypatch.setattr(bench_admin, "_download", download)
    monkeypatch.setattr(bench_admin, "_FETCH_CACHE", {})
    return calls


@pytest.mark.parametrize("url, raw", [
    ("https://github.com/acme/shop/blob/main/spec/openapi.yaml", f"{RAW}/openapi.yaml"),
    ("https://github.com/acme/shop/blob/v2.1/api.json?plain=1#L10", "https://raw.githubusercontent.com/acme/shop/v2.1/api.json"),
    ("https://github.com/acme/shop/raw/main/spec/openapi.yaml", f"{RAW}/openapi.yaml"),
    ("https://gitlab.com/grp/sub/proj/-/blob/main/openapi.yaml", "https://gitlab.com/grp/sub/proj/-/raw/main/openapi.yaml"),
    ("https://gist.github.com/someone/0123abcd", "https://gist.githubusercontent.com/someone/0123abcd/raw"),
    ("https://petstore3.swagger.io/api/v3/openapi.json", "https://petstore3.swagger.io/api/v3/openapi.json"),
])
def test_resolve_spec_url(url, raw):
    assert spec_import.resolve_spec_url(url) == raw


def test_html_page_gets_clear_error(client, bench):  # noqa: F811
    r = client.post("/api/v1/bench/preview", json={"spec_text": "<!DOCTYPE html><html><body>GitHub</body></html>"})
    assert r.status_code == 422
    assert "HTML" in r.json()["detail"] and "Raw" in r.json()["detail"]


def test_github_blob_link_and_multi_file_spec(client, bench, fake_web):  # noqa: F811
    blob = "https://github.com/acme/shop/blob/main/spec/openapi.yaml"
    r = client.post("/api/v1/bench/preview", json={"spec_url": blob})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["resolved_url"] == f"{RAW}/openapi.yaml"
    assert p["valid"] and p["operations"] == 1
    assert any("gộp đặc tả chia nhiều tệp" in n and "3 tệp" in n for n in p["normalization"])
    n_calls = len(fake_web)

    r = client.post("/api/v1/bench/apis", json={"id": "shop-split", "name": "Shop", "group": "B", "env": "public",
                                                 "scope": "read-only", "spec_url": blob})
    assert r.status_code == 201, r.text
    assert len(fake_web) == n_calls, "bước thêm phải dùng lại lượt tải của bước xem trước"
    d = bench / "apis" / "shop-split"
    meta = yaml.safe_load((d / "meta.yaml").read_text(encoding="utf-8"))
    assert meta["source"]["spec_url"] == f"{RAW}/openapi.yaml"
    src = yaml.safe_load((d / "source" / "openapi_original.yaml").read_text(encoding="utf-8"))
    assert "get" in src["paths"]["/items"], "source/ phải là bản đã gộp, dựng lại được khi không có mạng"
    gt = yaml.safe_load((d / "ground_truth" / "openapi.yaml").read_text(encoding="utf-8"))
    item = gt["paths"]["/items"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]
    assert item["properties"]["price"] == {"$ref": "#/components/schemas/Money"}
    cat = gt["components"]["schemas"]["category"]
    assert cat["properties"]["parent"] == {"$ref": "#/components/schemas/category"}
    assert gt["paths"]["/items"]["get"]["parameters"][0]["schema"]["maximum"] == 50


def test_multi_file_spec_needs_url(client, bench):  # noqa: F811
    r = client.post("/api/v1/bench/preview", json={"spec_text": FILES[f"{RAW}/openapi.yaml"], "filename": "openapi.yaml"})
    assert r.status_code == 422
    assert "chia nhiều tệp" in r.json()["detail"]


def test_ref_to_other_host_is_refused(client, bench, fake_web, monkeypatch):  # noqa: F811
    root = f"{RAW}/evil.yaml"
    monkeypatch.setitem(FILES, root, "openapi: 3.0.3\ninfo: {title: x, version: '1'}\npaths:\n"
                                     "  /a: {$ref: 'http://169.254.169.254/latest/meta-data.yaml'}\n")
    r = client.post("/api/v1/bench/preview", json={"spec_url": root})
    assert r.status_code == 422
    assert "ngoài máy chủ" in r.json()["detail"]
    assert all("169.254" not in u for u in fake_web)


def test_missing_raw_file_hint(client, bench, monkeypatch):  # noqa: F811
    def not_found(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(bench_admin.urllib.request, "urlopen", not_found)
    monkeypatch.setattr(bench_admin, "_FETCH_CACHE", {})
    r = client.post("/api/v1/bench/preview", json={"spec_url": "https://github.com/acme/shop/blob/dev/nope.yaml"})
    assert r.status_code == 422
    assert "404" in r.json()["detail"] and "private" in r.json()["detail"]


def test_api_key_read_from_dotenv(client, bench, tmp_path, monkeypatch):  # noqa: F811
    """Khóa API ghi trong .env (như khóa LLM) được dùng khi kiểm tra kết nối; meta chỉ lưu tên biến."""
    spec = ("openapi: 3.0.3\ninfo: {title: Kho khóa, version: '1'}\nservers: [{url: 'https://k.example.org'}]\n"
            "paths:\n  /ping: {get: {responses: {'200': {description: ok}}}}\n")
    r = client.post("/api/v1/bench/apis", json={
        "spec_text": spec, "id": "kho-khoa", "name": "Kho khóa", "probe_path": "/ping",
        "auth": {"type": "apiKey", "in": "query", "name": "key", "env_var": "KHO_KHOA_KEY"}})
    assert r.status_code == 201, r.text
    assert "k-123" not in (bench / "apis" / "kho-khoa" / "meta.yaml").read_text(encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("LLM_MODEL=x\nKHO_KHOA_KEY=k-123\n", encoding="utf-8")
    monkeypatch.setattr(bench_admin, "DOTENV_PATH", env)
    monkeypatch.setenv("KHO_KHOA_KEY", "")  # để monkeypatch dọn biến sau test
    seen = {}

    def fake_probe(meta):
        seen["key"] = bench_admin.os.environ.get(meta["environment"]["auth"]["env_var"])
        return {"status": 200, "ms": 1, "url": "https://k.example.org/ping"}

    monkeypatch.setattr(bench_admin.check_connectivity, "probe", fake_probe)
    res = client.post("/api/v1/bench/apis/kho-khoa/connectivity").json()
    assert res["ok"] and seen["key"] == "k-123"


def test_swagger2_shared_parameters_responses_and_file():
    src = {
        "swagger": "2.0", "info": {"title": "Files", "version": "1"}, "host": "f.example.org",
        "parameters": {"page": {"name": "page", "in": "query", "type": "integer", "minimum": 1},
                       "upload": {"name": "file", "in": "formData", "type": "file", "required": True}},
        "responses": {"Blob": {"description": "raw", "schema": {"type": "file"}},
                      "Err": {"description": "lỗi", "schema": {"$ref": "#/definitions/Err"},
                              "examples": {"application/json": {"message": "x"}}}},
        "definitions": {"Err": {"type": "object", "properties": {"message": {"type": "string"}}}},
        "paths": {"/files": {
            "get": {"parameters": [{"$ref": "#/parameters/page"}],
                    "responses": {"200": {"$ref": "#/responses/Blob"}, "400": {"$ref": "#/responses/Err"}}},
            "post": {"consumes": ["multipart/form-data"], "parameters": [{"$ref": "#/parameters/upload"}],
                     "responses": {"201": {"description": "ok"}}}}},
    }
    spec, notes, ver, errs = spec_import.prepare_spec(json.dumps(src))
    assert ver == "Swagger 2.0" and not errs, errs
    get = spec["paths"]["/files"]["get"]
    assert get["parameters"] == [{"$ref": "#/components/parameters/page"}]
    assert get["responses"]["200"] == {"$ref": "#/components/responses/Blob"}
    comps = spec["components"]
    assert comps["parameters"]["page"]["schema"] == {"type": "integer", "minimum": 1}
    assert comps["responses"]["Blob"]["content"]["application/json"]["schema"] == {"type": "string", "format": "binary"}
    assert comps["responses"]["Err"]["content"]["application/json"]["example"] == {"message": "x"}
    body = spec["paths"]["/files"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert body["properties"]["file"] == {"type": "string", "format": "binary"} and body["required"] == ["file"]


def test_oas3_written_with_swagger2_habits():
    src = {
        "openapi": "3.0.0", "info": {"title": "Disease", "version": "3"}, "host": "disease.example.org",
        "basePath": "/", "schemes": ["https"], "produces": ["application/json"],
        "components": {"parameters": {"day": {"name": "day", "in": "query", "type": "string", "enum": ["1", "0"]}}},
        "paths": {"/v3/{country}": {"get": {
            "parameters": [{"name": "country", "in": "path", "required": True, "type": "string"},
                           {"name": "lastdays", "in": "query", "type": "string", "default": 30},
                           {"$ref": "#/components/parameters/day"}],
            "responses": {"200": {"description": "ok"}}}}},
    }
    spec, notes, _ver, errs = spec_import.prepare_spec(json.dumps(src))
    assert not errs, errs
    assert spec["servers"] == [{"url": "https://disease.example.org"}] and "host" not in spec
    ps = spec["paths"]["/v3/{country}"]["get"]["parameters"]
    assert len(ps) == 3, "tham số path khai báo đủ, kể cả khi có tham số $ref – không được thêm bản trùng"
    assert ps[1]["schema"] == {"type": "string", "default": "30"}
    assert spec["components"]["parameters"]["day"]["schema"] == {"type": "string", "enum": ["1", "0"]}


def test_path_param_declared_by_ref_is_not_duplicated():
    src = {"openapi": "3.0.3", "info": {"title": "H", "version": "1"},
           "components": {"parameters": {"hid": {"name": "hero_id", "in": "path", "required": True,
                                                 "schema": {"type": "integer"}}}},
           "paths": {"/heroes/{hero_id}": {"get": {"parameters": [{"$ref": "#/components/parameters/hid"}],
                                                    "responses": {"200": {"description": "ok"}}}}}}
    spec, notes, _ver, errs = spec_import.prepare_spec(json.dumps(src))
    assert not errs and spec["paths"]["/heroes/{hero_id}"]["get"]["parameters"] == [{"$ref": "#/components/parameters/hid"}]
    assert not any("tham số path thiếu" in n for n in notes)


def test_31_null_types_and_empty_required():
    src = """
openapi: 3.1.0
info: {title: Chess, version: '1'}
paths:
  /games:
    get:
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: object
                required: []
                properties:
                  id: {type: 'null'}
                  opponent:
                    oneOf: [{type: object, properties: {name: {type: string}}}, {type: 'null'}]
"""
    spec, notes, _ver, errs = spec_import.prepare_spec(src)
    assert not errs, errs
    sch = spec["paths"]["/games"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "required" not in sch
    assert sch["properties"]["id"] == {"nullable": True, "enum": [None]}
    opp = sch["properties"]["opponent"]
    assert opp["nullable"] is True and '"null"' not in json.dumps(opp)
    loose = {"type": "object", "properties": {"a": {"oneOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]}}}
    fixed = spec_import._fix_null_type(loose, set())["properties"]["a"]
    assert fixed == {"oneOf": [{"type": "string"}, {"type": "integer"}], "nullable": True}
