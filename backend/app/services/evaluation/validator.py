"""L1 parse, L2 validate OAS 3.0.3, L3 lint (TECH_SPEC bảng 7)."""
from __future__ import annotations

import json
import re
from typing import Any

import yaml

from ...bench import oas_utils
from ..analysis.schema_check import check, resolve

HTTP_METHODS = oas_utils.HTTP_METHODS


def parse_text(text: str) -> tuple[dict | None, str | None]:
    """L1: đọc YAML/JSON. Trả về (spec, lỗi)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            return None, f"YAML không hợp lệ: {str(e)[:300]}"
    if not isinstance(data, dict):
        return None, "Nội dung không phải một đối tượng OpenAPI"
    return data, None


def validate_all(spec: dict, limit: int = 50) -> list[dict]:
    """L2: danh sách lỗi theo openapi-spec-validator (kèm đường dẫn)."""
    try:
        from openapi_spec_validator import OpenAPIV30SpecValidator

        errs = []
        for e in OpenAPIV30SpecValidator(spec).iter_errors():
            path = list(getattr(e, "absolute_path", None) or getattr(e, "path", None) or [])
            errs.append({"message": str(getattr(e, "message", e)).split("\n")[0][:400],
                         "path": [str(x) for x in path]})
            if len(errs) >= limit:
                break
        return errs
    except ImportError:
        return [{"message": m, "path": []} for m in oas_utils.validate_spec(spec)]
    except Exception as e:  # noqa: BLE001 – validator có thể ném lỗi khi đặc tả hỏng nặng
        return [{"message": f"{type(e).__name__}: {str(e)[:300]}", "path": []}]


def _issue(rule: str, pointer: str, message: str, severity: str = "warning", op: str | None = None) -> dict:
    return {"rule": rule, "severity": severity, "pointer": pointer, "message": message, "operation": op}


def _esc(s: str) -> str:
    return str(s).replace("~", "~0").replace("/", "~1")


def _iter_schemas(node: Any, pointer: str):
    if isinstance(node, dict):
        if any(k in node for k in ("type", "enum", "minimum", "maximum", "default", "properties", "items")):
            yield node, pointer
        for k, v in node.items():
            if k in ("example", "examples", "x-evidence"):
                continue
            yield from _iter_schemas(v, f"{pointer}/{_esc(k)}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _iter_schemas(v, f"{pointer}/{i}")


def lint(spec: dict) -> list[dict]:
    issues: list[dict] = []
    seen_ids: dict[str, str] = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        tmpl = set(re.findall(r"\{([^}]+)\}", path))
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            opk = f"{method.upper()} {path}"
            base = f"/paths/{_esc(path)}/{method}"
            resps = op.get("responses") or {}
            if not any(str(s).startswith("2") for s in resps):
                issues.append(_issue("operation-2xx-response", base + "/responses",
                                     f"{opk}: không có response 2xx", "warning", opk))
            declared = {p.get("name") for p in oas_utils.merged_parameters(spec, op, item) if p.get("in") == "path"}
            for v in sorted(tmpl - declared):
                issues.append(_issue("path-params-declared", base + "/parameters",
                                     f"{opk}: tham số path '{v}' chưa được khai báo", "error", opk))
            for v in sorted(declared - tmpl):
                issues.append(_issue("path-params-declared", base + "/parameters",
                                     f"{opk}: tham số path '{v}' không có trong đường dẫn", "error", opk))
            oid = op.get("operationId")
            if oid:
                if oid in seen_ids:
                    issues.append(_issue("operation-id-unique", base + "/operationId",
                                         f"operationId '{oid}' trùng với {seen_ids[oid]}", "error", opk))
                seen_ids[oid] = opk
    for node, p in _iter_schemas(spec, ""):
        if "enum" in node and isinstance(node["enum"], list) and not node["enum"]:
            issues.append(_issue("enum-not-empty", p + "/enum", "enum rỗng", "error"))
        for lo, hi in (("minimum", "maximum"), ("minLength", "maxLength"), ("minItems", "maxItems")):
            if isinstance(node.get(lo), (int, float)) and isinstance(node.get(hi), (int, float)) and node[lo] > node[hi]:
                issues.append(_issue("min-le-max", p, f"{lo}={node[lo]} > {hi}={node[hi]}", "error"))
        if "default" in node:
            schema_wo_default = {k: v for k, v in node.items() if k not in ("default", "example")}
            v = check(node["default"], schema_wo_default, p, spec, report_additional=False)
            if v:
                issues.append(_issue("default-valid", p + "/default",
                                     f"default {node['default']!r} không thỏa ràng buộc ({v[0].kind})", "warning"))
        if "example" in node and "$ref" not in node:
            schema_wo_ex = {k: v for k, v in node.items() if k not in ("example",)}
            v = check(node["example"], schema_wo_ex, p, spec, report_additional=False)
            if v:
                issues.append(_issue("example-valid", p + "/example",
                                     f"example không thỏa schema ({v[0].kind} tại {v[0].data_path or '/'})", "warning"))
    # example ở media type
    for path, item in (spec.get("paths") or {}).items():
        for method in HTTP_METHODS:
            op = (item or {}).get(method)
            if not isinstance(op, dict):
                continue
            medias = []
            for st, r in (op.get("responses") or {}).items():
                r, _ = resolve(spec, r, "")
                for mt, mobj in ((r or {}).get("content") or {}).items():
                    medias.append((f"/paths/{_esc(path)}/{method}/responses/{st}/content/{_esc(mt)}", mobj))
            for mt, mobj in ((op.get("requestBody") or {}).get("content") or {}).items():
                medias.append((f"/paths/{_esc(path)}/{method}/requestBody/content/{_esc(mt)}", mobj))
            for p, mobj in medias:
                if isinstance(mobj, dict) and "example" in mobj and "schema" in mobj:
                    v = check(mobj["example"], mobj["schema"], p + "/schema", spec, report_additional=False)
                    if v:
                        issues.append(_issue("example-valid", p + "/example",
                                             f"example không thỏa schema ({v[0].kind} tại {v[0].data_path or '/'})",
                                             "warning", f"{method.upper()} {path}"))
    return issues


def count_operations(spec: dict) -> int:
    return sum(1 for _ in oas_utils.iter_operations(spec))
