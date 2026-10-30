"""Pha lắp ráp XÁC ĐỊNH: danh sách OperationIR → OpenAPI 3.0.3 (TECH_SPEC 5.2.3).

Bằng chứng được gắn tạm vào từng nút (khóa x-ev / x-evk), sau khi bố trí cuối cùng (kể cả đưa schema trùng vào
components) thì thu về theo JSON Pointer và gỡ khỏi đặc tả.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ...schemas.ir import ConstraintIR, FieldIR, OperationIR

EV = "x-ev"
EVK = "x-evk"
TYPES = ("integer", "number", "string", "boolean", "array", "object")
STATUS_TEXT = {"200": "OK", "201": "Created", "202": "Accepted", "204": "No Content", "400": "Bad Request",
               "401": "Unauthorized", "403": "Forbidden", "404": "Not Found", "409": "Conflict",
               "422": "Unprocessable Entity", "429": "Too Many Requests", "500": "Internal Server Error"}


@dataclass
class EvidenceRec:
    pointer: str
    quote: str
    chunk_id: int | None


def esc(token: str) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def ptr(*parts: Any) -> str:
    return "".join("/" + esc(p) for p in parts)


def _add_ev(node: dict, chunk_id, quote: str | None, kw: str | None = None) -> None:
    if not quote:
        return
    item = [chunk_id, quote]
    if kw is None:
        lst = node.setdefault(EV, [])
    else:
        lst = node.setdefault(EVK, {}).setdefault(kw, [])
    if item not in lst:
        lst.append(item)


def norm_type(t: str | None) -> tuple[str | None, str | None]:
    """Chuẩn hóa kiểu tự do về (type, format)."""
    if not t:
        return None, None
    s = t.strip().lower()
    if s in TYPES:
        return s, None
    if s in ("date-time", "datetime", "timestamp"):
        return "string", "date-time"
    if s == "date":
        return "string", "date"
    if s.startswith(("array", "list")) or s.endswith("[]"):
        return "array", None
    for key, val in (("int", "integer"), ("long", "integer"), ("float", "number"), ("double", "number"),
                     ("decimal", "number"), ("bool", "boolean"), ("str", "string"), ("dict", "object"),
                     ("map", "object"), ("object", "object"), ("number", "number"), ("string", "string")):
        if key in s:
            return val, None
    return None, None


def _coerce(value: Any, typ: str | None) -> Any:
    if typ == "integer" and isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    if typ == "number" and isinstance(value, str):
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return value
    if typ == "boolean" and isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    if typ == "integer" and isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def apply_constraints(schema: dict, constraints: list[ConstraintIR], chunk_id) -> None:
    typ = schema.get("type")
    for c in constraints:
        k, v = c.kind, c.value
        if k in ("exclusiveMinimum", "exclusiveMaximum"):
            base = "minimum" if k == "exclusiveMinimum" else "maximum"
            if isinstance(v, bool):
                if v and base in schema:
                    schema[k] = True
                    _add_ev(schema, chunk_id, c.evidence, k)
                continue
            schema[base] = _coerce(v, typ or "number")
            schema[k] = True
            _add_ev(schema, chunk_id, c.evidence, base)
            _add_ev(schema, chunk_id, c.evidence, k)
            continue
        if k == "enum":
            vals = v if isinstance(v, list) else [v]
            vals = [_coerce(x, typ) for x in vals]
            if not vals:
                continue
            schema["enum"] = list(dict.fromkeys(json.dumps(x) for x in vals))
            schema["enum"] = [json.loads(x) for x in schema["enum"]]
        elif k == "nullable":
            if v is False:
                continue
            schema["nullable"] = True
        elif k == "uniqueItems":
            schema["uniqueItems"] = bool(v) if not isinstance(v, str) else v.lower() == "true"
        elif k in ("minimum", "maximum"):
            schema[k] = _coerce(v, typ or "number")
        elif k in ("minLength", "maxLength", "minItems", "maxItems"):
            try:
                schema[k] = int(v)
            except (TypeError, ValueError):
                continue
        elif k == "default":
            schema["default"] = _coerce(v, typ)
        else:  # pattern, format
            if v in (None, ""):
                continue
            schema[k] = str(v)
        _add_ev(schema, chunk_id, c.evidence, k)


def _typed_schema(t: str | None) -> dict:
    typ, fmt = norm_type(t)
    s: dict = {}
    if typ:
        s["type"] = typ
    if fmt:
        s["format"] = fmt
    if typ == "array":
        s["items"] = {}
    return s


def build_object(fields: list[FieldIR], chunk_id) -> dict:
    """Dựng schema object từ danh sách thuộc tính dạng đường dẫn ("items[].isbn", "a.b")."""
    root: dict = {"type": "object", "properties": {}}
    for f in fields:
        segs = [s for s in re.split(r"\.", f.path.strip()) if s]
        if not segs:
            continue
        node = root
        parent: dict | None = None
        name = None
        for i, seg in enumerate(segs):
            is_arr = seg.endswith("[]")
            name = seg[:-2] if is_arr else seg
            last = i == len(segs) - 1
            if name == "":
                # "[].x" – thân là mảng
                if node is root and root.get("type") != "array":
                    root.clear()
                    root.update({"type": "array", "items": {"type": "object", "properties": {}}})
                node = root["items"] if node is root else node.setdefault("items", {})
                continue
            node.setdefault("type", "object")
            props = node.setdefault("properties", {})
            child = props.setdefault(name, {})
            parent = node
            if is_arr:
                child["type"] = "array"
                items = child.setdefault("items", {})
                if last:
                    t, fmt = norm_type(f.type)
                    if t and t != "array":
                        items["type"] = t
                        if fmt:
                            items["format"] = fmt
                    apply_constraints(items, f.constraints, chunk_id)
                    _add_ev(items, chunk_id, f.evidence)
                    node = items
                    break
                node = items
            else:
                node = child
        if node is root or name is None or name == "":
            continue
        if not segs[-1].endswith("[]"):
            base = _typed_schema(f.type)
            if "type" in base:
                node["type"] = base["type"]
            if "format" in base:
                node.setdefault("format", base["format"])
            if base.get("type") == "array":
                node.setdefault("items", {})
            apply_constraints(node, f.constraints, chunk_id)
            _add_ev(node, chunk_id, f.evidence)
        if f.required and parent is not None:
            req = parent.setdefault("required", [])
            if name not in req:
                req.append(name)
            _add_ev(parent, chunk_id, f.evidence, "required")
    if root.get("type") == "object" and not root.get("properties"):
        root.pop("properties", None)
    return root


def infer_schema(example: Any, chunk_id=None, quote: str | None = None) -> dict:
    """Suy diễn schema từ ví dụ (không suy ra 'required')."""
    if isinstance(example, dict):
        s = {"type": "object", "properties": {k: infer_schema(v, chunk_id, quote) for k, v in example.items()}}
    elif isinstance(example, list):
        merged: dict = {}
        for el in example:
            sub = infer_schema(el, chunk_id, quote)
            if not merged:
                merged = sub
            elif merged.get("type") == "object" and sub.get("type") == "object":
                for k, v in sub.get("properties", {}).items():
                    merged["properties"].setdefault(k, v)
        s = {"type": "array", "items": merged}
    elif isinstance(example, bool):
        s = {"type": "boolean"}
    elif isinstance(example, int):
        s = {"type": "integer"}
    elif isinstance(example, float):
        s = {"type": "number"}
    elif isinstance(example, str):
        s = {"type": "string"}
    else:
        s = {"nullable": True}
    _add_ev(s, chunk_id, quote)
    return s


# ------------------------------------------------------------------ đường dẫn và server
BASE_URL_RE = re.compile(r"base\s*url[^\n`]*?[`\s:*]+(https?://[^\s`'\")]+)", re.I)


def detect_base_url(text: str) -> str | None:
    m = BASE_URL_RE.search(text or "")
    return m.group(1).rstrip("/.") if m else None


def normalize_op_path(path: str, base_url: str | None) -> tuple[str, str | None]:
    """Tách host/base khỏi path. Trả về (path, base_url_phát_hiện_thêm)."""
    found = None
    p = path.strip()
    if p.startswith(("http://", "https://")):
        u = urlparse(p)
        found = f"{u.scheme}://{u.netloc}"
        p = u.path or "/"
    p = p.split("?")[0]
    p = re.sub(r":(\w+)", r"{\1}", p)
    p = re.sub(r"<(\w+)>", r"{\1}", p)
    if not p.startswith("/"):
        p = "/" + p
    base_path = urlparse(base_url).path.rstrip("/") if base_url else ""
    if base_path and (p == base_path or p.startswith(base_path + "/")):
        p = p[len(base_path):] or "/"
    if len(p) > 1:
        p = p.rstrip("/")
    return p, found


def operation_id(method: str, path: str) -> str:
    parts = []
    for seg in path.strip("/").split("/"):
        if not seg:
            continue
        m = re.fullmatch(r"\{(\w+)\}", seg)
        if m:
            parts.append("By" + "".join(w.capitalize() for w in re.split(r"[_\-]", m.group(1))))
        else:
            parts.append("".join(w.capitalize() for w in re.split(r"[_\-.]", seg)))
    return method.lower() + "".join(parts) if parts else method.lower() + "Root"


def _singular(word: str) -> str:
    w = re.sub(r"[^A-Za-z0-9]", "", word)
    if w.endswith("ies"):
        w = w[:-3] + "y"
    elif w.endswith("ses"):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return (w[:1].upper() + w[1:]) or "Schema"


# ------------------------------------------------------------------ lắp ráp
def _score_ev(node: dict) -> int:
    return sum(len(q) for _, q in node.get(EV, [])) + 10 * len(node.get("schema", {}).get(EVK, {}))


def _param_obj(p, chunk_id) -> dict:
    schema = _typed_schema(p.type)
    apply_constraints(schema, p.constraints, chunk_id)
    obj: dict = {"name": p.name, "in": p.location}
    if p.description:
        obj["description"] = p.description
    if p.location == "path":
        obj["required"] = True
    elif p.required:
        obj["required"] = True
    obj["schema"] = schema
    _add_ev(obj, chunk_id, p.evidence)
    if p.required or p.location == "path":
        _add_ev(obj, chunk_id, p.evidence, "required")
    return obj


def _response_obj(r, chunk_id) -> dict:
    desc = r.description or STATUS_TEXT.get(r.status, f"Response {r.status}")
    obj: dict = {"description": desc}
    schema = None
    if r.fields:
        schema = build_object(r.fields, chunk_id)
    elif r.example is not None and isinstance(r.example, (dict, list)):
        schema = infer_schema(r.example, chunk_id, r.evidence)
    if schema is not None:
        obj["content"] = {"application/json": {"schema": schema}}
    _add_ev(obj, chunk_id, r.evidence)
    return obj


def assemble(irs: list[tuple[int | None, OperationIR]], *, title: str = "Generated API",
             base_url: str | None = None, description: str | None = None) -> tuple[dict, list[EvidenceRec], list[str]]:
    warnings: list[str] = []
    ops: dict[tuple[str, str], dict] = {}
    discovered_hosts: list[str] = []
    for chunk_id, ir in irs:
        path, host = normalize_op_path(ir.path, base_url)
        if host:
            discovered_hosts.append(host)
        key = (ir.method.lower(), path)
        op = ops.get(key)
        if op is None:
            op = ops[key] = {"_params": {}, "responses": {}, "_deps": [], "_bodies": []}
            if ir.summary:
                op["summary"] = ir.summary
        elif ir.summary and "summary" not in op:
            op["summary"] = ir.summary
        for p in ir.parameters:
            obj = _param_obj(p, chunk_id)
            pk = (p.location, p.name)
            old = op["_params"].get(pk)
            if old is None or _score_ev(obj) > _score_ev(old):
                if old is not None:
                    warnings.append(f"{ir.method} {path}: xung đột tham số {p.name}, giữ bản có trích dẫn cụ thể hơn")
                op["_params"][pk] = obj
        if ir.request_body is not None:
            op["_bodies"].append((chunk_id, ir.request_body))
        for r in ir.responses:
            obj = _response_obj(r, chunk_id)
            old = op["responses"].get(r.status)
            if old is None or ("content" in obj and "content" not in old):
                op["responses"][r.status] = obj
        for d in ir.dependencies:
            idl = " ".join(d.idl.split())
            if not idl.endswith(";"):
                idl += ";"
            if all(idl != x[0] for x in op["_deps"]):
                op["_deps"].append((idl, chunk_id, d.evidence))

    if not base_url and discovered_hosts:
        base_url = discovered_hosts[0]
    spec: dict = {"openapi": "3.0.3", "info": {"title": title, "version": "1.0.0"}}
    if description:
        spec["info"]["description"] = description
    if base_url:
        spec["servers"] = [{"url": base_url}]
    paths: dict = {}
    used_ids: set[str] = set()
    for (method, path), op in sorted(ops.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        out: dict = {}
        oid = operation_id(method, path)
        while oid in used_ids:
            oid += "_"
        used_ids.add(oid)
        out["operationId"] = oid
        if "summary" in op:
            out["summary"] = op["summary"]
        params = list(op["_params"].values())
        if params:
            out["parameters"] = params
        if op["_bodies"]:
            chunk_id, body = op["_bodies"][0]
            fields = [f for _, b in op["_bodies"] for f in b.fields]
            if fields:
                schema = build_object(fields, chunk_id)
            elif body.example is not None:
                schema = infer_schema(body.example, chunk_id, body.evidence)
            else:
                schema = {}
            rb: dict = {"content": {body.media_type or "application/json": {"schema": schema}}}
            if any(f.required for f in fields):
                rb["required"] = True
            _add_ev(rb, chunk_id, body.evidence)
            out["requestBody"] = rb
        out["responses"] = dict(sorted(op["responses"].items()))
        if op["_deps"]:
            out["x-dependencies"] = [d[0] for d in op["_deps"]]
            for i, (_idl, chunk_id, ev) in enumerate(op["_deps"]):
                _add_ev(out, chunk_id, ev, f"x-dependencies/{i}")
        paths.setdefault(path, {})[method] = out
    spec["paths"] = paths
    hoist_shared_schemas(spec)
    evidence = collect_evidence(spec)
    return spec, evidence, warnings


# ------------------------------------------------------------------ schema dùng chung
def _canon(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _canon(v) for k, v in sorted(node.items()) if k not in (EV, EVK, "description")}
    if isinstance(node, list):
        return [_canon(x) for x in node]
    return node


def _hash(node: dict) -> str:
    return hashlib.sha1(json.dumps(_canon(node), sort_keys=True).encode()).hexdigest()


def _is_obj(node: Any) -> bool:
    return isinstance(node, dict) and node.get("type") == "object" and len(node.get("properties") or {}) >= 2


def _schema_roots(spec: dict):
    """(schema_dict, holder, key, name_hint) cho mọi schema trong requestBody/response."""
    for path, item in spec.get("paths", {}).items():
        segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
        hint = _singular(segs[-1]) if segs else "Root"
        for _m, op in item.items():
            if not isinstance(op, dict):
                continue
            rb = op.get("requestBody", {})
            for mobj in rb.get("content", {}).values():
                if "schema" in mobj:
                    yield mobj, "schema", hint + "Create"
            for st, resp in op.get("responses", {}).items():
                for mobj in resp.get("content", {}).values():
                    if "schema" in mobj:
                        yield mobj, "schema", hint if str(st).startswith("2") else hint + "Error"


def hoist_shared_schemas(spec: dict) -> None:
    counts: dict[str, int] = {}

    def count(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in (EV, EVK):
                    count(v)
            if _is_obj(node):
                counts[_hash(node)] = counts.get(_hash(node), 0) + 1
        elif isinstance(node, list):
            for x in node:
                count(x)

    roots = list(_schema_roots(spec))
    for holder, key, _ in roots:
        count(holder[key])
    shared = {h for h, c in counts.items() if c >= 2}
    if not shared:
        return
    comps = spec.setdefault("components", {}).setdefault("schemas", {})
    name_of: dict[str, str] = {}

    def replace(node, hint):
        if isinstance(node, dict):
            for k in list(node.keys()):
                if k in (EV, EVK):
                    continue
                sub_hint = _singular(k) if k not in ("items", "properties", "schema") else hint
                node[k] = replace(node[k], sub_hint)
            if _is_obj(node):
                h = _hash(node)
                if h in shared:
                    if h not in name_of:
                        name = hint or "Schema"
                        n = 2
                        while name in comps:
                            name = f"{hint}{n}"
                            n += 1
                        name_of[h] = name
                        comps[name] = node
                    else:
                        tgt = comps[name_of[h]]
                        for it in node.get(EV, []):
                            if it not in tgt.setdefault(EV, []):
                                tgt[EV].append(it)
                    return {"$ref": f"#/components/schemas/{name_of[h]}"}
            return node
        if isinstance(node, list):
            return [replace(x, hint) for x in node]
        return node

    for holder, key, hint in roots:
        holder[key] = replace(holder[key], hint)


# ------------------------------------------------------------------ thu bằng chứng
def collect_evidence(spec: dict) -> list[EvidenceRec]:
    out: list[EvidenceRec] = []

    def walk(node, p):
        if isinstance(node, dict):
            for cid, q in node.pop(EV, []) or []:
                out.append(EvidenceRec(p or "/", q, cid))
            for kw, items in (node.pop(EVK, {}) or {}).items():
                kp = p + "/" + "/".join(esc(x) for x in kw.split("/"))
                for cid, q in items:
                    out.append(EvidenceRec(kp, q, cid))
            for k, v in node.items():
                walk(v, p + "/" + esc(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{p}/{i}")

    walk(spec, "")
    return out


def strip_temp(spec: dict) -> dict:
    s = copy.deepcopy(spec)
    collect_evidence(s)
    return s
