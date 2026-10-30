"""Kiểm tra một giá trị JSON theo schema OAS 3.0, ghi lại JSON Pointer của nút schema vi phạm.

Theo dõi $ref để pointer trỏ đúng vị trí cần sửa (ví dụ /components/schemas/Book/properties/isbn).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

MAX_ITEMS_CHECK = 200


@dataclass
class Violation:
    kind: str           # type | null | enum | required | additional | minimum | maximum | minLength | ...
    schema_ptr: str     # JSON Pointer của nút schema (sau khi theo $ref)
    data_path: str      # vị trí trong dữ liệu, vd. items[3].isbn
    expected: Any = None
    actual: Any = None
    prop: str | None = None  # với required/additional: tên thuộc tính


def resolve(spec: dict, node: Any, pointer: str, depth: int = 0) -> tuple[Any, str]:
    while isinstance(node, dict) and isinstance(node.get("$ref"), str) and node["$ref"].startswith("#/") \
            and depth < 20:
        pointer = node["$ref"][1:]
        node = get_pointer(spec, pointer)
        depth += 1
    return node, pointer


def get_pointer(doc: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return doc
    node = doc
    for raw in pointer.lstrip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(part)]
        else:
            node = node[part]
    return node


def type_ok(value: Any, typ: str) -> bool:
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if typ == "string":
        return isinstance(value, str)
    if typ == "boolean":
        return isinstance(value, bool)
    if typ == "array":
        return isinstance(value, list)
    if typ == "object":
        return isinstance(value, dict)
    return True


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def format_ok(value: str, fmt: str) -> bool:
    try:
        if fmt == "date":
            date.fromisoformat(value)
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
        if fmt == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return "T" in value or " " in value
        if fmt == "email":
            return bool(EMAIL_RE.match(value))
        if fmt == "uuid":
            return bool(UUID_RE.match(value))
        if fmt in ("uri", "url"):
            return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value))
    except ValueError:
        return False
    return True


def check(value: Any, schema: Any, pointer: str, spec: dict, data_path: str = "", depth: int = 0,
          report_additional: bool = True) -> list[Violation]:
    if depth > 30 or not isinstance(schema, dict):
        return []
    schema, pointer = resolve(spec, schema, pointer)
    if not isinstance(schema, dict):
        return []
    out: list[Violation] = []
    for i, part in enumerate(schema.get("allOf") or []):
        out += check(value, part, f"{pointer}/allOf/{i}", spec, data_path, depth + 1, report_additional)
    for comb in ("oneOf", "anyOf"):
        branches = schema.get(comb)
        if isinstance(branches, list) and branches:
            results = [check(value, b, f"{pointer}/{comb}/{i}", spec, data_path, depth + 1, report_additional)
                       for i, b in enumerate(branches)]
            if all(r for r in results):
                out.append(Violation(comb, pointer, data_path, None, json_type(value)))
    if value is None:
        if schema.get("nullable") is True:
            return out
        if "type" in schema or "properties" in schema or "enum" in schema:
            out.append(Violation("null", pointer, data_path, schema.get("type"), None))
        return out
    typ = schema.get("type")
    if typ and not type_ok(value, typ):
        out.append(Violation("type", pointer, data_path, typ, json_type(value)))
        return out
    if "enum" in schema and isinstance(schema["enum"], list) and value not in schema["enum"]:
        out.append(Violation("enum", pointer, data_path, schema["enum"], value))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(Violation("minLength", pointer, data_path, schema["minLength"], len(value)))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(Violation("maxLength", pointer, data_path, schema["maxLength"], len(value)))
        if "pattern" in schema:
            try:
                if not re.search(schema["pattern"], value):
                    out.append(Violation("pattern", pointer, data_path, schema["pattern"], value))
            except re.error:
                pass
        if "format" in schema and not format_ok(value, schema["format"]):
            out.append(Violation("format", pointer, data_path, schema["format"], value))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema:
            mn = schema["minimum"]
            if value < mn or (schema.get("exclusiveMinimum") is True and value == mn):
                out.append(Violation("minimum", pointer, data_path, mn, value))
        if "maximum" in schema:
            mx = schema["maximum"]
            if value > mx or (schema.get("exclusiveMaximum") is True and value == mx):
                out.append(Violation("maximum", pointer, data_path, mx, value))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(Violation("minItems", pointer, data_path, schema["minItems"], len(value)))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(Violation("maxItems", pointer, data_path, schema["maxItems"], len(value)))
        items = schema.get("items")
        if isinstance(items, dict):
            for i, el in enumerate(value[:MAX_ITEMS_CHECK]):
                out += check(el, items, f"{pointer}/items", spec, f"{data_path}[{i}]", depth + 1, report_additional)
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in value:
                out.append(Violation("required", pointer, data_path, name, None, prop=name))
        for name, sub in props.items():
            if name in value:
                dp = f"{data_path}.{name}" if data_path else name
                out += check(value[name], sub, f"{pointer}/properties/{_esc(name)}", spec, dp, depth + 1,
                             report_additional)
        ap = schema.get("additionalProperties", True)
        for name in value:
            if name in props:
                continue
            dp = f"{data_path}.{name}" if data_path else name
            if isinstance(ap, dict):
                out += check(value[name], ap, f"{pointer}/additionalProperties", spec, dp, depth + 1,
                             report_additional)
            elif report_additional and props:
                out.append(Violation("additional", pointer, data_path, None, value[name], prop=name))
    return out


def _esc(s: str) -> str:
    return s.replace("~", "~0").replace("/", "~1")
