"""Mô hình operation phục vụ kiểm thử: tham số / thuộc tính body kèm JSON Pointer tới schema để sinh JSON Patch."""
from __future__ import annotations

import copy
import random
import re
import string
from dataclasses import dataclass, field
from typing import Any

from ...bench import oas_utils
from ..analysis.schema_check import resolve

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def esc(s: str) -> str:
    return str(s).replace("~", "~0").replace("/", "~1")


@dataclass
class Target:
    """Một phần tử đầu vào có thể dò: tham số (query/path/header/cookie) hoặc thuộc tính cấp 1 của body JSON."""
    location: str            # query | path | header | cookie | body
    name: str
    schema: dict             # schema đã phân giải $ref
    schema_ptr: str          # pointer tới nút schema (sau $ref)
    holder_ptr: str          # tham số: pointer của object tham số; body: pointer của schema object cha
    required: bool

    @property
    def label(self) -> str:
        return f"{self.location}:{self.name}"

    @property
    def type(self) -> str | None:
        t = self.schema.get("type")
        if t is None and "enum" in self.schema and self.schema["enum"]:
            v = self.schema["enum"][0]
            return "integer" if isinstance(v, int) and not isinstance(v, bool) else "string"
        return t


@dataclass
class OperationModel:
    method: str
    path: str
    op_ptr: str
    op: dict
    params: list[Target] = field(default_factory=list)
    body_fields: list[Target] = field(default_factory=list)
    body_ptr: str | None = None           # pointer schema body (sau $ref)
    body_schema: dict | None = None
    body_required: bool = False
    body_media: str | None = None
    body_example: Any = None
    responses: dict[str, tuple[dict | None, str | None]] = field(default_factory=dict)
    responses_ptr: str = ""

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def targets(self) -> list[Target]:
        return self.params + self.body_fields

    def target(self, label: str) -> Target | None:
        return next((t for t in self.targets if t.label == label), None)

    @property
    def dependencies(self) -> list[str]:
        return [str(d) for d in (self.op.get("x-dependencies") or [])]


def build_models(spec: dict) -> list[OperationModel]:
    out: list[OperationModel] = []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            op_ptr = f"/paths/{esc(path)}/{method}"
            om = OperationModel(method.upper(), path, op_ptr, op, responses_ptr=op_ptr + "/responses")
            params: dict[tuple, Target] = {}
            for base_ptr, plist in ((f"/paths/{esc(path)}/parameters", item.get("parameters") or []),
                                    (op_ptr + "/parameters", op.get("parameters") or [])):
                for i, p in enumerate(plist):
                    pnode, pptr = resolve(spec, p, f"{base_ptr}/{i}")
                    if not isinstance(pnode, dict) or "name" not in pnode:
                        continue
                    snode, sptr = resolve(spec, pnode.get("schema") or {}, pptr + "/schema")
                    params[(pnode.get("in"), pnode["name"])] = Target(
                        pnode.get("in", "query"), pnode["name"], snode if isinstance(snode, dict) else {}, sptr, pptr,
                        bool(pnode.get("required")) or pnode.get("in") == "path")
            om.params = list(params.values())
            rb, rb_ptr = resolve(spec, op.get("requestBody") or {}, op_ptr + "/requestBody")
            if isinstance(rb, dict) and rb.get("content"):
                media = next((m for m in rb["content"] if "json" in m), None)
                if media:
                    mobj = rb["content"][media] or {}
                    sch, sptr = resolve(spec, mobj.get("schema") or {}, f"{rb_ptr}/content/{esc(media)}/schema")
                    om.body_media, om.body_ptr, om.body_schema = media, sptr, sch
                    om.body_required = bool(rb.get("required"))
                    om.body_example = mobj.get("example")
                    if isinstance(sch, dict):
                        sch = merge_allof(spec, sch)
                        req = set(sch.get("required") or [])
                        for name, ps in (sch.get("properties") or {}).items():
                            pnode, pptr = resolve(spec, ps, f"{sptr}/properties/{esc(name)}")
                            om.body_fields.append(Target("body", name, pnode if isinstance(pnode, dict) else {},
                                                         pptr, sptr, name in req))
            for st, r in (op.get("responses") or {}).items():
                rnode, rptr = resolve(spec, r, f"{op_ptr}/responses/{esc(str(st))}")
                schema, sptr = None, None
                for media, mobj in ((rnode or {}).get("content") or {}).items():
                    if "json" in media and isinstance(mobj, dict) and "schema" in mobj:
                        schema, sptr = mobj["schema"], f"{rptr}/content/{esc(media)}/schema"
                        break
                om.responses[str(st)] = (schema, sptr)
            out.append(om)
    return out


def merge_allof(spec: dict, s: dict) -> dict:
    if "allOf" not in s:
        return s
    out = {k: v for k, v in s.items() if k != "allOf"}
    props = dict(out.get("properties") or {})
    req = list(out.get("required") or [])
    for part in s["allOf"]:
        part, _ = resolve(spec, part, "")
        if isinstance(part, dict):
            part = merge_allof(spec, part)
            props.update(part.get("properties") or {})
            req += part.get("required") or []
    out["properties"], out["required"] = props, req
    return out


# ------------------------------------------------------------------ sinh giá trị
def gen_from_pattern(pattern: str, rng: random.Random | None = None) -> str | None:
    """Sinh một chuỗi khớp pattern cho tập con regex phổ biến (lớp ký tự, \\d \\w, lượng từ, nhóm |)."""
    rng = rng or random.Random(0)
    p = pattern
    if p.startswith("^"):
        p = p[1:]
    if p.endswith("$") and not p.endswith("\\$"):
        p = p[:-1]
    pos = 0

    def parse_seq(stop: str = "") -> str:
        nonlocal pos
        out = ""
        while pos < len(p) and p[pos] not in stop:
            atom = parse_atom()
            out += apply_quant(atom)
        return out

    def parse_atom():
        nonlocal pos
        c = p[pos]
        if c == "(":
            pos += 1
            if p.startswith("?:", pos):
                pos += 2
            alts = [parse_seq("|)")]
            while pos < len(p) and p[pos] == "|":
                pos += 1
                alts.append(parse_seq("|)"))
            pos += 1  # ')'
            return ("lit", alts[0])
        if c == "[":
            end = p.index("]", pos + 1)
            body = p[pos + 1:end]
            pos = end + 1
            neg = body.startswith("^")
            if neg:
                return ("lit", "a" if "a" not in body else "Z")
            m = re.match(r"\\?(.)-(.)", body)
            if m:
                return ("class", m.group(1))
            return ("class", body.lstrip("\\")[0])
        if c == "\\":
            nxt = p[pos + 1]
            pos += 2
            return ("lit", {"d": "0", "w": "a", "s": " ", "D": "a", "W": "-", "S": "a"}.get(nxt, nxt))
        if c == ".":
            pos += 1
            return ("lit", "a")
        pos += 1
        return ("lit", c)

    def apply_quant(atom):
        nonlocal pos
        s = atom[1]
        n = 1
        if pos < len(p):
            q = p[pos]
            if q == "{":
                end = p.index("}", pos)
                spec = p[pos + 1:end]
                pos = end + 1
                n = int(spec.split(",")[0] or 1)
            elif q == "+":
                pos += 1
                n = 1
            elif q == "*" or q == "?":
                pos += 1
                n = 0 if q == "?" else 1
            if pos < len(p) and p[pos] == "?":
                pos += 1
        return s * n

    try:
        val = parse_seq()
        if re.search(pattern, val):
            return val
    except (ValueError, IndexError, re.error):
        return None
    return None


FORMAT_SAMPLES = {"date": "2024-01-15", "date-time": "2024-01-15T10:00:00Z", "email": "user@example.com",
                  "uuid": "123e4567-e89b-12d3-a456-426614174000", "uri": "https://example.com/x",
                  "url": "https://example.com/x", "hostname": "example.com", "ipv4": "192.0.2.1",
                  "byte": "U3BlY0xvb3A=", "password": "Passw0rd!"}


def gen_value(schema: dict, spec: dict, depth: int = 0) -> Any:
    """Giá trị hợp lệ theo schema: example → default → enum[0] → sinh theo kiểu và ràng buộc."""
    schema, _ = resolve(spec, schema, "")
    if not isinstance(schema, dict) or depth > 6:
        return "sample"
    schema = merge_allof(spec, schema)
    if "example" in schema:
        return copy.deepcopy(schema["example"])
    if "default" in schema:
        return copy.deepcopy(schema["default"])
    if schema.get("enum"):
        return copy.deepcopy(schema["enum"][0])
    for comb in ("oneOf", "anyOf"):
        if schema.get(comb):
            return gen_value(schema[comb][0], spec, depth + 1)
    t = schema.get("type") or ("object" if "properties" in schema else "array" if "items" in schema else "string")
    if t in ("integer", "number"):
        lo, hi = schema.get("minimum"), schema.get("maximum")
        step = 1
        if lo is not None:
            v = lo + (step if schema.get("exclusiveMinimum") is True else 0)
        else:
            v = 1
        if hi is not None and v > hi:
            v = hi - (step if schema.get("exclusiveMaximum") is True else 0)
        if t == "integer":
            v = int(v)
        mult = schema.get("multipleOf")
        if mult:
            v = mult * max(1, round(v / mult))
        return v
    if t == "boolean":
        return True
    if t == "string":
        fmt = schema.get("format")
        if "pattern" in schema:
            g = gen_from_pattern(schema["pattern"])
            if g is not None:
                return g
        if fmt in FORMAT_SAMPLES:
            return FORMAT_SAMPLES[fmt]
        s = "sample"
        mn, mx = schema.get("minLength"), schema.get("maxLength")
        if mn is not None and len(s) < mn:
            s = s + "x" * (mn - len(s))
        if mx is not None and len(s) > mx:
            s = s[:mx] if mx > 0 else ""
        return s
    if t == "array":
        n = max(1, schema.get("minItems") or 0)
        items = schema.get("items") or {}
        vals = []
        for i in range(n):
            v = gen_value(items, spec, depth + 1)
            if schema.get("uniqueItems") and isinstance(v, str):
                v = f"{v}{i}" if i else v
            vals.append(v)
        return vals
    if t == "object":
        out = {}
        req = set(schema.get("required") or [])
        for name, ps in (schema.get("properties") or {}).items():
            if name in req:
                out[name] = gen_value(ps, spec, depth + 1)
        return out
    return "sample"


def string_of_length(n: int, schema: dict | None = None) -> str:
    base = string.ascii_lowercase
    return (base * (n // len(base) + 1))[:n]


def array_of_length(n: int, schema: dict, spec: dict) -> list:
    items = (schema or {}).get("items") or {}
    items, _ = resolve(spec, items, "")
    t = items.get("type") if isinstance(items, dict) else None
    if t == "integer":
        return list(range(1, n + 1))
    if t == "number":
        return [float(i) for i in range(1, n + 1)]
    if t == "string" or t is None:
        return [f"t{i}" for i in range(n)]
    return [gen_value(items, spec) for _ in range(n)]


def server_url(spec: dict) -> str | None:
    servers = spec.get("servers") or []
    if servers and isinstance(servers[0], dict) and servers[0].get("url"):
        url = servers[0]["url"]
        for name, var in (servers[0].get("variables") or {}).items():
            url = url.replace("{" + name + "}", str(var.get("default", "")))
        return url
    return None


def parent_collection(path: str) -> str | None:
    segs = path.rstrip("/").split("/")
    if len(segs) >= 2 and re.fullmatch(r"\{[^}]+\}", segs[-1]):
        return "/".join(segs[:-1]) or "/"
    return None


__all__ = ["Target", "OperationModel", "build_models", "gen_value", "gen_from_pattern", "string_of_length",
           "array_of_length", "server_url", "parent_collection", "SAFE_METHODS", "oas_utils"]
