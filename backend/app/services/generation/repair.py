"""Vòng tự sửa lỗi (TECH_SPEC 5.2.4): sửa xác định trước, sau đó LLM sửa cục bộ ≤ 2 vòng."""
from __future__ import annotations

import copy
import json
import re

from ...bench import oas_utils
from ..evaluation.validator import validate_all
from ..llm.gateway import BaseLLM, LLMError
from .prompts import SYSTEM_REPAIR, USER_REPAIR

MAX_LLM_ROUNDS = 2


def deterministic_fix(spec: dict) -> tuple[dict, list[str]]:
    spec = copy.deepcopy(spec)
    notes: list[str] = []
    spec.setdefault("openapi", "3.0.3")
    spec.setdefault("info", {"title": "API", "version": "1.0.0"})
    spec["info"].setdefault("title", "API")
    spec["info"].setdefault("version", "1.0.0")
    spec.setdefault("paths", {})
    used: set[str] = set()
    for path, item in spec["paths"].items():
        if not isinstance(item, dict):
            continue
        tmpl = re.findall(r"\{([^}]+)\}", path)
        for method in oas_utils.HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            opk = f"{method.upper()} {path}"
            params = op.setdefault("parameters", [])
            declared = {p.get("name") for p in oas_utils.merged_parameters(spec, op, item) if p.get("in") == "path"}
            for p in list(params):
                if isinstance(p, dict) and p.get("in") == "path" and p.get("name") not in tmpl:
                    params.remove(p)
                    notes.append(f"{opk}: bỏ tham số path '{p.get('name')}' không có trong đường dẫn")
            for v in tmpl:
                if v not in declared:
                    params.append({"name": v, "in": "path", "required": True, "schema": {"type": "string"}})
                    notes.append(f"{opk}: thêm tham số path thiếu '{v}'")
            for p in params:
                if isinstance(p, dict) and p.get("in") == "path" and p.get("required") is not True:
                    p["required"] = True
                    notes.append(f"{opk}: tham số path '{p.get('name')}' phải required")
                if isinstance(p, dict) and "schema" not in p and "content" not in p and "$ref" not in p:
                    p["schema"] = {"type": "string"}
                    notes.append(f"{opk}: thêm schema cho tham số '{p.get('name')}'")
            if not params:
                op.pop("parameters")
            if not op.get("responses"):
                op["responses"] = {"default": {"description": "Default response"}}
                notes.append(f"{opk}: thêm response mặc định")
            for st, r in list(op["responses"].items()):
                if isinstance(r, dict) and "$ref" not in r and "description" not in r:
                    r["description"] = f"Response {st}"
                    notes.append(f"{opk}: thêm description cho response {st}")
            oid = op.get("operationId")
            if oid:
                new = oid
                while new in used:
                    new += "_"
                if new != oid:
                    op["operationId"] = new
                    notes.append(f"{opk}: đổi operationId trùng '{oid}' → '{new}'")
                used.add(new)
    _fix_schemas(spec, notes)
    return spec, notes


def _fix_schemas(node, notes, pointer=""):
    if isinstance(node, dict):
        for kw in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "pattern", "format",
                   "default", "multipleOf"):
            if kw in node and node[kw] is None:
                node.pop(kw)
                notes.append(f"{pointer}: bỏ {kw} rỗng (null)")
        if isinstance(node.get("enum"), list) and None in node["enum"] and node.get("nullable") is not True:
            node["enum"] = [x for x in node["enum"] if x is not None]
            notes.append(f"{pointer}: bỏ null khỏi enum")
        if node.get("type") == "array" and "items" not in node:
            node["items"] = {}
            notes.append(f"{pointer}: thêm items cho mảng")
        if "enum" in node and isinstance(node["enum"], list) and not node["enum"]:
            node.pop("enum")
            notes.append(f"{pointer}: bỏ enum rỗng")
        for kw, base in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
            if kw in node and base not in node:
                node.pop(kw)
                notes.append(f"{pointer}: bỏ {kw} không có {base}")
        if "type" in node and node["type"] not in ("integer", "number", "string", "boolean", "array", "object"):
            notes.append(f"{pointer}: bỏ type không hợp lệ {node['type']!r}")
            node.pop("type")
        for k, v in list(node.items()):
            if k not in ("example", "examples", "default", "enum"):
                _fix_schemas(v, notes, f"{pointer}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _fix_schemas(v, notes, f"{pointer}/{i}")


def llm_fix(spec: dict, errors: list[dict], llm: BaseLLM, job_id: str | None = None) -> tuple[dict, list[str]]:
    spec = copy.deepcopy(spec)
    notes = []
    by_op: dict[tuple[str, str], list[str]] = {}
    for e in errors:
        p = e.get("path") or []
        if len(p) >= 3 and p[0] == "paths" and p[2] in oas_utils.HTTP_METHODS:
            by_op.setdefault((p[1], p[2]), []).append(e["message"])
    for (path, method), msgs in by_op.items():
        op = spec["paths"].get(path, {}).get(method)
        if not isinstance(op, dict):
            continue
        user = USER_REPAIR.format(path=path, method=method.upper(), errors="\n".join(msgs[:10]),
                                  operation=json.dumps(op, ensure_ascii=False)[:12000])
        try:
            res = llm.chat_json(SYSTEM_REPAIR, user, purpose="repair", job_id=job_id)
        except LLMError:
            continue
        new = (res.data or {}).get("operation_object") if isinstance(res.data, dict) else None
        if isinstance(new, dict) and new.get("responses"):
            spec["paths"][path][method] = new
            notes.append(f"{method.upper()} {path}: LLM sửa cục bộ ({len(msgs)} lỗi)")
    return spec, notes


def repair(spec: dict, llm: BaseLLM | None = None, job_id: str | None = None) -> tuple[dict, list[str], list[dict]]:
    """Trả về (spec_đã_sửa, ghi_chú, lỗi_còn_lại)."""
    fixed, notes = deterministic_fix(spec)
    errors = validate_all(fixed)
    rounds = 0
    while errors and llm is not None and rounds < MAX_LLM_ROUNDS:
        rounds += 1
        cand, n2 = llm_fix(fixed, errors, llm, job_id)
        if not n2:
            break
        cand, n3 = deterministic_fix(cand)
        new_errors = validate_all(cand)
        if len(new_errors) <= len(errors):
            fixed, errors = cand, new_errors
            notes += n2 + n3
        else:
            break
    return fixed, notes, errors
