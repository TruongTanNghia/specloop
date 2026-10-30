"""FakeLLM: "LLM giả lập" xác định, trích IR bằng luật từ tài liệu dạng Markdown phổ biến.

Dùng cho test (không cần mạng) và làm baseline offline. Nó nhận đúng prompt mà LLM thật nhận
(GLOBAL CONTEXT + SECTION) và trả JSON theo schema OperationIR, mọi phần tử có evidence trích nguyên văn.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..ingestion.segmenter import SIG_RE, clean_path
from .gateway import BaseLLM

BULLET_RE = re.compile(r"^\s*[-*+]\s+`(?P<name>[\w.\[\]-]+)`\s*\*?\((?P<meta>[^)]*)\)\*?\s*(?:[–—:-]\s*)?(?P<desc>.*)$")
TABLE_ROW_RE = re.compile(r"^\s*\|\s*`?(?P<name>[\w.\[\]-]+)`?\s*\|\s*(?P<type>[^|]*)\|\s*(?P<desc>[^|]*)\|?\s*$")
RESP_RE = re.compile(r"Response\s+`?(?P<status>[1-5]\d\d)(?:\s+[A-Za-z][A-Za-z ]*)?`?\s*:?\s*(?P<rest>.*)")
STATUS_MENTION_RE = re.compile(r"`(?P<status>[1-5]\d\d)\s+[A-Z][A-Za-z ]+`")
TYPES = ("integer", "number", "string", "boolean", "array", "object")


def _ev(line: str) -> str:
    return line.strip()[:200]


def _coerce(v: str, typ: str | None) -> Any:
    v = v.strip().strip("`'\".")
    if typ == "integer":
        try:
            return int(v)
        except ValueError:
            return v
    if typ == "number":
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return v
    if typ == "boolean":
        return v.lower() == "true"
    return v


def _parse_meta(meta: str) -> tuple[str | None, bool | None, bool, str | None]:
    m = meta.lower()
    typ = None
    items = None
    if m.startswith("array"):
        typ = "array"
        for t in TYPES:
            if f"of {t}" in m:
                items = t
    else:
        for t in TYPES:
            if t in m:
                typ = t
                break
    required = True if re.search(r"\brequired\b", m) else (False if "optional" in m else None)
    nullable = "null" in m
    return typ, required, nullable, items


def _constraints(desc: str, typ: str | None, ev: str) -> list[dict]:
    out: list[dict] = []
    d = desc

    def add(kind, value):
        out.append({"kind": kind, "value": value, "evidence": ev})

    m = re.search(r"defaults? to\s+`?([\w.-]+)`?", d, re.I)
    if m:
        add("default", _coerce(m.group(1), typ))
    m = re.search(r"at least (\d+) characters", d, re.I)
    if m:
        add("minLength", int(m.group(1)))
    m = re.search(r"at most (\d+) characters", d, re.I)
    if m:
        add("maxLength", int(m.group(1)))
    m = re.search(r"from (-?[\d.]+) up to (?:a maximum of )?(-?[\d.]+)", d, re.I) or \
        re.search(r"between (-?[\d.]+) and (-?[\d.]+)", d, re.I)
    if m and typ in ("integer", "number"):
        add("minimum", _coerce(m.group(1), typ))
        add("maximum", _coerce(m.group(2), typ))
    else:
        m = re.search(r"greater than or equal to (-?[\d.]+)", d, re.I)
        if m:
            add("minimum", _coerce(m.group(1), typ))
        else:
            m = re.search(r"greater than (-?[\d.]+)", d, re.I)
            if m:
                add("exclusiveMinimum", _coerce(m.group(1), typ))
        m = re.search(r"(?:maximum of|at most|up to) (-?[\d.]+)(?! characters)", d, re.I)
        if m and typ in ("integer", "number"):
            add("maximum", _coerce(m.group(1), typ))
        m = re.search(r"starting (?:from|at) (-?\d+)", d, re.I)
        if m and typ == "integer":
            add("minimum", int(m.group(1)))
    m = re.search(r"(\d+)-digit", d)
    if m and re.search(r"digits only", d, re.I):
        add("pattern", f"^[0-9]{{{m.group(1)}}}$")
    if re.search(r"YYYY-MM-DD(?!T)", d):
        add("format", "date")
    elif re.search(r"date-time|ISO 8601", d, re.I):
        add("format", "date-time")
    for sentence in re.split(r"(?<=[.;])\s+", d):
        if not re.search(r"\bone of\b|\bor\b", sentence, re.I):
            continue
        # bỏ các giá trị là ví dụ/định dạng
        vals = [t for t in re.findall(r"`([^`\s]+)`", sentence) if not re.match(r"^(YYYY|\d{6,})", t)]
        if len(vals) >= 2:
            add("enum", [_coerce(v, typ) for v in vals])
            break
    return out


def _dependency(name: str, desc: str, ev: str) -> dict | None:
    m = re.search(r"only (?:used|valid|allowed) (?:together )?with `([\w.-]+)`", desc, re.I) or \
        re.search(r"requires `([\w.-]+)`", desc, re.I)
    if m:
        return {"idl": f"IF {name} THEN {m.group(1)};", "evidence": ev}
    return None


def _object_defs(text: str) -> dict[str, list[dict]]:
    """Tìm định nghĩa đối tượng trong ngữ cảnh: bảng Field|Type|Notes hoặc danh sách gạch đầu dòng sau
    câu 'A **book** object ...' / 'An **order** object contains:'."""
    defs: dict[str, list[dict]] = {}
    lines = text.split("\n")
    current = None
    for ln in lines:
        m = re.search(r"\*\*(\w+)\*\*\s+(?:object\s+)?(?:has|contains)", ln, re.I) or \
            re.search(r"An? \*\*(\w+)\*\* object", ln, re.I)
        if m:
            current = m.group(1).lower()
            defs.setdefault(current, [])
            # định nghĩa nội dòng: "has an `id` (integer), a `name` (string)"
            for nm, typ in re.findall(r"`(\w+)`\s*\((\w+)\)", ln):
                defs[current].append({"path": nm, "type": typ if typ in TYPES else None, "evidence": _ev(ln)})
            continue
        if current is None:
            continue
        b = BULLET_RE.match(ln)
        t = TABLE_ROW_RE.match(ln)
        if b:
            typ, _, nullable, _ = _parse_meta(b.group("meta"))
            f = {"path": b.group("name"), "type": typ, "evidence": _ev(ln),
                 "constraints": _constraints(b.group("desc"), typ, _ev(ln))}
            if nullable:
                f["constraints"].append({"kind": "nullable", "value": True, "evidence": _ev(ln)})
            defs[current].append(f)
        elif t and t.group("name").lower() not in ("field", "name") and not set(t.group("name")) <= set("-"):
            typ, _, nullable, _ = _parse_meta(t.group("type"))
            f = {"path": t.group("name"), "type": typ, "evidence": _ev(ln),
                 "constraints": _constraints(t.group("desc"), typ, _ev(ln))}
            defs[current].append(f)
        elif ln.startswith("#"):
            current = None
    return {k: v for k, v in defs.items() if v}


def _json_after(lines: list[str], i: int) -> Any:
    """JSON trong khối mã ngay sau dòng i (bỏ qua dòng trống)."""
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and lines[j].strip().startswith("```"):
        k = j + 1
        buf = []
        while k < len(lines) and not lines[k].strip().startswith("```"):
            buf.append(lines[k])
            k += 1
        try:
            return json.loads("\n".join(buf))
        except json.JSONDecodeError:
            return None
    return None


def rule_extract(section: str, context: str) -> dict:
    sig = SIG_RE.search(section)
    if not sig:
        return {"operation": None}
    method, path = sig.group(1).upper(), clean_path(sig.group(2))
    lines = section.split("\n")
    summary = None
    for ln in lines:
        if ln.startswith("#"):
            summary = ln.lstrip("#").strip()
            break
    objects = _object_defs(context + "\n" + section)
    params: list[dict] = []
    body_fields: list[dict] = []
    body: dict | None = None
    responses: dict[str, dict] = {}
    deps: list[dict] = []
    mode = None
    for i, ln in enumerate(lines):
        low = ln.lower()
        if "query parameter" in low and ln.rstrip().endswith(":"):
            mode = "query"
            continue
        if "path parameter" in low and ln.rstrip().endswith(":"):
            mode = "path"
            continue
        if "header" in low and ln.rstrip().endswith(":") and not ln.lstrip().startswith("-"):
            mode = "header"
            continue
        if ("request body" in low or "json object with" in low or "send a json" in low) and \
                not ln.lstrip().startswith("-"):
            mode = "body"
            if body is None:
                body = {"media_type": "application/json", "fields": [], "evidence": _ev(ln)}
            continue
        if re.search(r"example request", low):
            ex = _json_after(lines, i)
            if ex is not None:
                body = body or {"media_type": "application/json", "fields": [], "evidence": _ev(ln)}
                body["example"] = ex
            continue
        pieces = [m for m in (RESP_RE.match(p) for p in re.split(r"(?=Response\s+`)", ln)) if m]
        for rm in pieces:
            st = rm.group("status")
            r = responses.setdefault(st, {"status": st, "description": rm.group("rest").strip()[:200] or None,
                                          "fields": [], "evidence": _ev(ln)})
            rest = rm.group("rest").lower()
            om = re.search(r"(?:the|new|created) (?:new |created )?(\w+) object", rest)
            if om and om.group(1) in objects and not r["fields"]:
                r["fields"] = objects[om.group(1)]
            if rest.strip() in ("", ":") or ln.rstrip().endswith(":"):
                ex = _json_after(lines, i)
                if ex is not None:
                    r["example"] = ex
            mode = None
        if not RESP_RE.search(ln):
            for sm in STATUS_MENTION_RE.finditer(ln):
                st = sm.group("status")
                responses.setdefault(st, {"status": st, "description": None, "fields": [], "evidence": _ev(ln)})
        b = BULLET_RE.match(ln)
        if b and mode in ("query", "path", "header"):
            typ, req, nullable, _ = _parse_meta(b.group("meta"))
            ev = _ev(ln)
            p = {"name": b.group("name"), "location": mode, "type": typ, "evidence": ev,
                 "description": b.group("desc").strip()[:200] or None,
                 "constraints": _constraints(b.group("desc"), typ, ev)}
            if req is not None:
                p["required"] = req
            if nullable:
                p["constraints"].append({"kind": "nullable", "value": True, "evidence": ev})
            params.append(p)
            dep = _dependency(b.group("name"), b.group("desc"), ev)
            if dep:
                deps.append(dep)
        elif b and mode == "body":
            typ, req, nullable, items = _parse_meta(b.group("meta"))
            ev = _ev(ln)
            f = {"path": b.group("name"), "type": typ, "evidence": ev,
                 "constraints": _constraints(b.group("desc"), typ, ev)}
            if req is not None:
                f["required"] = req
            if nullable:
                f["constraints"].append({"kind": "nullable", "value": True, "evidence": ev})
            body_fields.append(f)
            if items:
                body_fields.append({"path": f"{b.group('name')}[]", "type": items, "evidence": ev})
            dep = _dependency(b.group("name"), b.group("desc"), ev)
            if dep:
                deps.append(dep)
    # tham số đường dẫn mô tả bằng văn xuôi: "`book_id` is the positive integer identifier"
    declared = {p["name"] for p in params}
    for var in re.findall(r"\{(\w+)\}", path):
        if var in declared:
            continue
        p = {"name": var, "location": "path", "required": True, "evidence": _ev(sig.group(0))}
        for ln in lines:
            m = re.search(rf"`{var}`\s+is\s+(?:the|a|an)\s+(positive\s+)?(integer|number|string)", ln)
            if m:
                p["type"] = m.group(2)
                p["evidence"] = _ev(ln)
                if m.group(1) and m.group(2) in ("integer", "number"):
                    p["constraints"] = [{"kind": "minimum", "value": 1, "evidence": _ev(ln)}]
                break
        params.append(p)
    if body is not None:
        body["fields"] = body_fields
    op = {"method": method, "path": path, "summary": summary, "parameters": params,
          "request_body": body, "responses": list(responses.values()), "dependencies": deps}
    return {"operation": op}


class FakeLLM(BaseLLM):
    provider = "fake"

    def __init__(self):
        super().__init__("fake")

    def _complete(self, system: str, user: str, purpose: str) -> tuple[str, int, int]:
        if purpose == "extract":
            ctx = ""
            m = re.search(r"GLOBAL CONTEXT[^\n]*:\n(.*?)\n\nSECTION:\n", user, re.S)
            if m:
                ctx = m.group(1)
            sec = user.split("SECTION:\n", 1)[-1].split("\n\nJSON Schema", 1)[0]
            out = rule_extract(sec, ctx)
        elif purpose == "repair":
            out = {"operation": None}
        else:
            out = {}
        text = json.dumps(out, ensure_ascii=False)
        return text, len(system + user) // 4, len(text) // 4
