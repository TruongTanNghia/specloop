"""Kiểm thử đơn vị cho các thuật toán lõi (NFR-08)."""
from __future__ import annotations

import re

import pytest

from app.schemas.ir import ConstraintIR, FieldIR, OperationIR, ParamIR, ResponseIR
from app.services.analysis import boundary as bd
from app.services.analysis.confidence import noisy_or, tier, wilson_lower
from app.services.analysis.msg_miner import extract_message, hints_for, is_referential, mine
from app.services.analysis.schema_check import check
from app.services.evaluation.validator import validate_all
from app.services.generation.assembler import assemble, build_object, normalize_op_path
from app.services.generation.repair import deterministic_fix
from app.services.ingestion.segmenter import find_signatures, normalize_markdown, segment
from app.services.testing.opmodel import build_models, gen_from_pattern, gen_value
from app.services.testing.prober import SafetyError, check_target, classify
from app.services.versioning.core import apply_patch, diff_patch


# ------------------------------------------------------------------ M1
def test_segmenter_splits_by_signature_and_marks_global():
    md = normalize_markdown("# API\n\nBase URL: `https://x.io/v1`\n\n## Authentication\nUse a token.\n\n"
                            "## Items\n### List\n`GET /items`\nlimit param\n\n### Get\n`GET /items/{id}`\n"
                            "```bash\ncurl -X DELETE https://x.io/v1/items/1\n```\n")
    chunks = segment(md)
    ops = [c.operation_hint for c in chunks if c.operation_hint]
    assert {"method": "GET", "path": "/items"} in ops
    assert any(c.is_global and c.title == "Authentication" for c in chunks)
    # lệnh curl trong cùng mục tạo phân đoạn riêng
    assert {"method": "DELETE", "path": "/v1/items/1"} in ops
    for c in chunks:
        assert md[c.span_start:c.span_end] == c.text


def test_signatures_ignore_prose():
    sigs = find_signatures("Use a GET request. Call `POST /orders/:id/pay` then GET https://a.b/v2/x?y=1")
    assert [(m, p) for _, m, p in sigs] == [("POST", "/orders/{id}/pay"), ("GET", "/v2/x")]


# ------------------------------------------------------------------ M2
def test_assembler_ir_to_oas():
    ev = "limit (integer) – 1 to 100, defaults to 20"
    ir = OperationIR(method="GET", path="http://localhost/v1/books/:id", parameters=[
        ParamIR(name="limit", location="query", type="integer", evidence=ev, constraints=[
            ConstraintIR(kind="minimum", value=1, evidence=ev), ConstraintIR(kind="maximum", value="100", evidence=ev),
            ConstraintIR(kind="exclusiveMinimum", value=0, evidence=ev)])],
        responses=[ResponseIR(status=200, evidence="Response 200", fields=[
            FieldIR(path="items[].isbn", type="string", required=True, evidence="isbn"),
            FieldIR(path="total", type="int", evidence="total")])])
    spec, evidence, _ = assemble([(1, ir)], base_url="http://localhost/v1")
    assert spec["openapi"] == "3.0.3"
    op = spec["paths"]["/books/{id}"]["get"]
    names = {p["name"]: p for p in op["parameters"]}
    assert "id" not in names  # IR không khai báo tham số path → vòng sửa lỗi xác định bổ sung
    fixed, notes = deterministic_fix(spec)
    pid = next(p for p in fixed["paths"]["/books/{id}"]["get"]["parameters"] if p["name"] == "id")
    assert pid["in"] == "path" and pid["required"] is True and notes
    assert validate_all(fixed) == []
    sch = names["limit"]["schema"]
    assert sch["maximum"] == 100 and sch["exclusiveMinimum"] is True and sch["minimum"] == 0
    resp = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert resp["properties"]["items"]["items"]["required"] == ["isbn"]
    assert resp["properties"]["total"]["type"] == "integer"
    ptrs = {e.pointer for e in evidence}
    assert "/paths/~1books~1{id}/get/parameters/0/schema/maximum" in ptrs
    assert "x-ev" not in str(spec)


def test_assembler_hoists_shared_schemas():
    fields = [FieldIR(path="id", type="integer", evidence="id"), FieldIR(path="name", type="string", evidence="n")]
    a = OperationIR(method="GET", path="/a/{x}", responses=[ResponseIR(status="200", fields=fields, evidence="e")])
    b = OperationIR(method="POST", path="/a", responses=[ResponseIR(status="201", fields=fields, evidence="e")])
    spec, _, _ = assemble([(None, a), (None, b)])
    assert "A" in spec["components"]["schemas"]
    assert spec["paths"]["/a"]["post"]["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/A"}


def test_build_object_nested():
    o = build_object([FieldIR(path="a.b", type="string", required=True), FieldIR(path="tags[]", type="string")], 1)
    assert o["properties"]["a"]["required"] == ["b"]
    assert o["properties"]["tags"]["type"] == "array"
    assert o["properties"]["tags"]["items"]["type"] == "string"


def test_normalize_path():
    assert normalize_op_path("/v1/books/<id>", "http://h/v1") == ("/books/{id}", None)


# ------------------------------------------------------------------ M5
def test_wilson_and_noisy_or_match_tech_spec():
    assert round(wilson_lower(6, 6), 2) == 0.61
    assert round(noisy_or({"probe": 0.61, "error_message": 0.8}), 2) == 0.92
    assert tier(0.92, False) == "auto" and tier(0.92, True) == "review" and tier(0.3, False) == "suggestion"


def test_boundary_search_example_from_tech_spec():
    calls = []

    def probe(v):
        calls.append(v)
        return bd.ACCEPT if 1 <= v <= 100 else bd.REJECT

    up = bd.search(probe, 20, upper=True)
    assert up.status == "bound" and up.value == 100
    assert calls[:3] == [40, 80, 160]
    lo = bd.search(probe, 20, upper=False)
    assert lo.status == "bound" and lo.value == 1


def test_boundary_number_inclusive_vs_exclusive():
    up = bd.search(lambda v: bd.ACCEPT if v >= 0 else bd.REJECT, 1.0, upper=False, integer=False)
    assert up.value == 0 and not up.exclusive
    ex = bd.search(lambda v: bd.ACCEPT if v > 0 else bd.REJECT, 5.0, upper=False, integer=False)
    assert ex.value == 0 and ex.exclusive


def test_boundary_unknown_and_info():
    r = bd.search(lambda v: bd.ACCEPT if v < 50 else bd.UNKNOWN, 1, upper=True)
    assert r.status == "unknown"
    r = bd.search(lambda v: bd.ACCEPT if v < 13 else bd.INFO, 1, upper=True)
    assert r.status == "info"
    r = bd.search(lambda v: bd.ACCEPT, 1, upper=True, cap=1000)
    assert r.status == "none"


@pytest.mark.parametrize("msg,param,kind,value", [
    ("limit must be between 1 and 100", "limit", "maximum", 100),
    ("title must be between 1 and 200 characters", "title", "maxLength", 200),
    ("tags must contain at most 5 items", "tags", "maxItems", 5),
    ("price must be greater than or equal to 0", "price", "minimum", 0),
    ("genre must be one of: fiction, science, history, children", "genre", "enum",
     ["fiction", "science", "history", "children"]),
    ("q must be at least 2 characters", "q", "minLength", 2),
    ("book_id must be a positive integer", "book_id", "minimum", 1),
])
def test_message_mining(msg, param, kind, value):
    assert any(h.kind == kind and h.value == value for h in hints_for(msg, param))


def test_message_dependency_and_referential():
    h = mine("voucher_type is required when coupon_code is provided")
    assert h[0].kind == "dependency" and h[0].value == "IF coupon_code THEN voucher_type;"
    assert is_referential("author_id does not refer to an existing author", "author_id")
    assert not is_referential("limit must be between 1 and 100", "limit")
    assert extract_message({"error": "x"}) == "x"
    assert extract_message({"errors": {"email": ["can't be blank"]}}) == "email can't be blank"


def test_schema_check_follows_refs():
    spec = {"components": {"schemas": {"B": {"type": "object", "required": ["id"], "properties": {
        "id": {"type": "integer"}, "isbn": {"type": "string"}, "g": {"type": "string", "enum": ["a"]}}}}}}
    v = check({"isbn": None, "g": "b", "x": 1}, {"$ref": "#/components/schemas/B"}, "/r", spec)
    kinds = {(x.kind, x.schema_ptr) for x in v}
    assert ("null", "/components/schemas/B/properties/isbn") in kinds
    assert ("enum", "/components/schemas/B/properties/g") in kinds
    assert ("required", "/components/schemas/B") in kinds
    assert ("additional", "/components/schemas/B") in kinds


def test_value_generation():
    assert gen_from_pattern("^[0-9]{13}$") == "0" * 13
    assert re.fullmatch(r"[A-Z]{2}-\d{3}", gen_from_pattern(r"^[A-Z]{2}-\d{3}$"))
    assert gen_value({"type": "number", "minimum": 0, "exclusiveMinimum": True}, {}) == 1
    assert gen_value({"type": "string", "format": "date"}, {}) == "2024-01-15"
    assert gen_value({"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"},
                                                                          "b": {"type": "string"}}}, {}) == {"a": 1}


def test_build_models_pointers():
    spec = {"paths": {"/b/{id}": {"parameters": [{"name": "id", "in": "path", "required": True,
                                                  "schema": {"type": "integer"}}],
                                  "post": {"requestBody": {"content": {"application/json": {"schema": {
                                      "$ref": "#/components/schemas/C"}}}}, "responses": {"201": {
                                      "description": "ok"}}}}},
            "components": {"schemas": {"C": {"type": "object", "required": ["t"], "properties": {
                "t": {"type": "string"}}}}}}
    om = build_models(spec)[0]
    assert om.params[0].holder_ptr == "/paths/~1b~1{id}/parameters/0"
    t = om.body_fields[0]
    assert t.schema_ptr == "/components/schemas/C/properties/t" and t.required and t.holder_ptr == \
        "/components/schemas/C"


def test_prober_classification_and_safety():
    assert [classify(s) for s in (200, 400, 422, 401, 404, 429, 500, 302)] == [
        "ACCEPT", "REJECT", "REJECT", "AUTH", "NOT_FOUND", "RATE", "SERVER_ERR", "OTHER"]
    assert check_target("http://127.0.0.1:1/v1", [], ["127.0.0.0/8"]) is True
    with pytest.raises(SafetyError):
        check_target("http://127.0.0.1:1/v1", [], [])
    with pytest.raises(SafetyError):
        check_target("http://127.0.0.1:1/v1", ["example.com"], ["127.0.0.0/8"])


def test_parse_llm_json_with_code_fence_inside_evidence():
    from app.schemas.ir import ResponseIR
    from app.services.llm.gateway import parse_json_text

    raw = '{"evidence": "Response:\\n```json\\n{ \\"items\\": [] }\\n```", "ok": 1}'
    assert parse_json_text(raw)["ok"] == 1
    assert parse_json_text('```json\n{"a": 2}\n```')["a"] == 2
    assert parse_json_text('Here: {"a": 3} done')["a"] == 3
    assert [ResponseIR(status=s, evidence="x").status for s in ("200 OK", "HTTP 404", 201, "4xx")] == [
        "200", "404", "201", "4XX"]


def test_repair_drops_undeclared_path_params():
    spec = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {"/books": {"post": {
        "parameters": [{"name": "path", "in": "path", "required": True, "schema": {"type": "string"}}],
        "responses": {"201": {"description": "ok"}}}}}}
    fixed, notes = deterministic_fix(spec)
    assert "parameters" not in fixed["paths"]["/books"]["post"] and notes
    assert validate_all(fixed) == []


def test_null_constraints_and_bad_field_paths_are_dropped():
    o = build_object([FieldIR(path="id", type="integer", constraints=[ConstraintIR(kind="minimum", value=None,
                                                                                    evidence="e")]),
                      FieldIR(path=": ", type="object"),
                      FieldIR(path="s", type="string", constraints=[ConstraintIR(kind="enum", value=[None, "a"],
                                                                                  evidence="e")])], 1)
    assert set(o["properties"]) == {"id", "s"}
    assert "minimum" not in o["properties"]["id"] and o["properties"]["s"]["enum"] == ["a"]
    spec = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {"/x": {"get": {"responses": {
        "200": {"description": "ok", "content": {"application/json": {"schema": {"type": "object", "properties": {
            "q": {"type": "integer", "minimum": None}, "e": {"type": "string", "enum": [None]}}}}}}}}}}}
    fixed, _ = deterministic_fix(spec)
    assert validate_all(fixed) == []


# ------------------------------------------------------------------ M6
def test_json_patch_and_diff():
    doc = {"a": {"b": 1, "l": [1, 2]}, "r": {"200": {"d": "x"}}}
    out, warns = apply_patch(doc, [{"op": "add", "path": "/a/c", "value": 2},
                                   {"op": "remove", "path": "/a/missing"},
                                   {"op": "replace", "path": "/a/l/0", "value": 9},
                                   {"op": "move", "from": "/r/200", "path": "/r/201"}])
    assert out == {"a": {"b": 1, "l": [9, 2], "c": 2}, "r": {"201": {"d": "x"}}}
    assert warns and doc["a"]["l"][0] == 1
    assert apply_patch(doc, diff_patch(doc, out))[0] == out
