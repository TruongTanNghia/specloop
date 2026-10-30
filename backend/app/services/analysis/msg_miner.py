"""Khai thác thông báo lỗi (TECH_SPEC 5.5.3) – tầng 1: thư viện mẫu regex.

Kết quả chỉ là giả thuyết; luôn được kiểm chứng bằng probe trước khi thành đề xuất.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

NUM = r"(-?\d+(?:\.\d+)?)"
P = r"[`'\"]?(?P<p>[A-Za-z_][\w.\-\[\]]*)[`'\"]?"


@dataclass
class Hint:
    param: str | None
    kind: str      # minimum | maximum | minLength | maxLength | minItems | maxItems | enum | required | type | format
    value: Any     # | pattern | dependency | referential | exclusiveMinimum | exclusiveMaximum
    source: str = "regex"


def _num(s: str) -> int | float:
    f = float(s)
    return int(f) if f.is_integer() else f


def _vals(s: str) -> list[str]:
    s = s.strip().strip("[](){}.")
    parts = re.split(r"\s*,\s*|\s+or\s+|\s*\|\s*", s)
    return [p.strip().strip("`'\"") for p in parts if p.strip().strip("`'\"")]


RULES: list[tuple[re.Pattern, Any]] = []


def rule(pattern: str):
    def deco(fn):
        RULES.append((re.compile(pattern, re.I), fn))
        return fn
    return deco


@rule(P + r" is required when " + r"[`'\"]?(?P<q>[\w.\-]+)[`'\"]? is (?:provided|present|set|given)")
def _dep(m):
    return [Hint(m.group("q"), "dependency", f"IF {m.group('q')} THEN {m.group('p')};")]


@rule(P + r" must (?:be|have|contain) between " + NUM + r" and " + NUM + r"\s*(?P<u>characters|chars|items|elements)?")
def _between(m):
    a, b = _num(m.group(2)), _num(m.group(3))
    u = (m.group("u") or "").lower()
    if u.startswith("char"):
        return [Hint(m.group("p"), "minLength", a), Hint(m.group("p"), "maxLength", b)]
    if u in ("items", "elements"):
        return [Hint(m.group("p"), "minItems", a), Hint(m.group("p"), "maxItems", b)]
    return [Hint(m.group("p"), "minimum", a), Hint(m.group("p"), "maximum", b)]


@rule(P + r" must (?:be|contain|have) (?:at least|no (?:less|fewer) than|a minimum of) " + NUM +
      r"\s*(?P<u>characters|chars|items|elements)?")
def _atleast(m):
    u = (m.group("u") or "").lower()
    v = _num(m.group(2))
    kind = "minLength" if u.startswith("char") else "minItems" if u in ("items", "elements") else "minimum"
    return [Hint(m.group("p"), kind, v)]


@rule(P + r" must (?:be|contain|have) (?:at most|no more than|a maximum of) " + NUM +
      r"\s*(?P<u>characters|chars|items|elements)?")
def _atmost(m):
    u = (m.group("u") or "").lower()
    v = _num(m.group(2))
    kind = "maxLength" if u.startswith("char") else "maxItems" if u in ("items", "elements") else "maximum"
    return [Hint(m.group("p"), kind, v)]


@rule(P + r"(?: length)? must be (?:greater than or equal to|>=|at least) " + NUM)
def _ge(m):
    return [Hint(m.group("p"), "minimum", _num(m.group(2)))]


@rule(P + r"(?: length)? must be (?:less than or equal to|<=) " + NUM)
def _le(m):
    return [Hint(m.group("p"), "maximum", _num(m.group(2)))]


@rule(P + r" must be (?:greater|larger|more) than " + NUM)
def _gt(m):
    return [Hint(m.group("p"), "exclusiveMinimum", _num(m.group(2)))]


@rule(P + r" must be (?:less|smaller|lower) than " + NUM)
def _lt(m):
    return [Hint(m.group("p"), "exclusiveMaximum", _num(m.group(2)))]


@rule(P + r" must be a positive (?:integer|number)")
def _pos(m):
    return [Hint(m.group("p"), "minimum", 1)]


@rule(P + r" (?:must be|should be|is not) (?:one of|in|a valid value among)[:\s]+(?P<vals>.+)$")
def _enum(m):
    return [Hint(m.group("p"), "enum", _vals(m.group("vals")))]


@rule(r"(?:invalid value for|unknown value for) " + P + r"[^:]*:\s*(?:expected|allowed)?\s*(?:one of)?[:\s]*(?P<vals>.+)$")
def _enum2(m):
    return [Hint(m.group("p"), "enum", _vals(m.group("vals")))]


@rule(P + r" (?:is required|is missing|must be provided|may not be (?:null|empty)|cannot be (?:null|blank))")
def _req(m):
    return [Hint(m.group("p"), "required", True)]


@rule(r"(?:missing (?:required )?(?:parameter|field|property))[:\s]+" + P)
def _req2(m):
    return [Hint(m.group("p"), "required", True)]


@rule(P + r" must be an? (?P<t>integer|number|string|boolean|array|object)\b(?! of)")
def _type(m):
    return [Hint(m.group("p"), "type", m.group("t").lower())]


@rule(P + r" must be an array of (?P<t>\w+)")
def _arr(m):
    return [Hint(m.group("p"), "type", "array")]


@rule(P + r" must be a (?:valid )?(?P<f>date|date-time|datetime|email|uuid|uri|url)\b")
def _fmt(m):
    f = m.group("f").lower().replace("datetime", "date-time").replace("url", "uri")
    return [Hint(m.group("p"), "format", f)]


@rule(r"invalid (?P<f>date|date-time|email|uuid|uri) (?:format )?for " + P)
def _fmt2(m):
    return [Hint(m.group("p"), "format", m.group("f").lower())]


@rule(P + r" (?:must match|does not match) (?:the )?(?:pattern )?[`'\"]?(?P<re>\^?[^`'\"\s]+\$?)")
def _pattern(m):
    return [Hint(m.group("p"), "pattern", m.group("re"))]


@rule(P + r" (?:does not refer to an? (?:existing|known|valid)|refers to an? (?:unknown|missing)|"
      r"does not exist|not found|is unknown)")
def _ref(m):
    return [Hint(m.group("p"), "referential", True)]


REFERENTIAL_RE = re.compile(r"does not refer to|does not exist|not found|no such|unknown \w+ id", re.I)


def mine(message: str | None) -> list[Hint]:
    if not message:
        return []
    out: list[Hint] = []
    for sentence in re.split(r"(?<=[.;])\s+|\n", message):
        for rx, fn in RULES:
            m = rx.search(sentence)
            if m:
                out += fn(m)
                if fn in (_dep, _between):
                    break
    # khử trùng lặp
    seen, uniq = set(), []
    for h in out:
        k = (h.param, h.kind, repr(h.value))
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    return uniq


def hints_for(message: str | None, param: str) -> list[Hint]:
    p = param.lower()
    return [h for h in mine(message) if h.param and h.param.lower().split(".")[-1] == p]


def is_referential(message: str | None, param: str | None = None) -> bool:
    if not message:
        return False
    if param is not None:
        return any(h.kind == "referential" for h in hints_for(message, param)) or (
            bool(REFERENTIAL_RE.search(message)) and param.lower() in message.lower())
    return bool(REFERENTIAL_RE.search(message))


def extract_message(body: Any) -> str | None:
    """Lấy thông báo lỗi từ body phản hồi (error/message/detail/...)."""
    if isinstance(body, str):
        return body[:500] or None
    if isinstance(body, dict):
        for k in ("error", "message", "detail", "msg", "error_description", "title", "description"):
            v = body.get(k)
            if isinstance(v, str) and v:
                return v[:500]
            if isinstance(v, dict):
                inner = extract_message(v)
                if inner:
                    return inner
            if isinstance(v, list) and v:
                inner = extract_message(v[0])
                if inner:
                    return inner
        errs = body.get("errors")
        if isinstance(errs, list) and errs:
            return extract_message(errs[0])
        if isinstance(errs, dict) and errs:
            k, v = next(iter(errs.items()))
            return f"{k} {v[0] if isinstance(v, list) and v else v}"
    if isinstance(body, list) and body:
        return extract_message(body[0])
    return None
