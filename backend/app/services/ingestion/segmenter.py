"""Chuẩn hóa Markdown và phân đoạn tài liệu theo operation (TECH_SPEC 5.1)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_CHUNK_TOKENS = 3000
METHODS = "GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS"
SIG_RE = re.compile(rf"\b({METHODS})\s+(?:https?://[^\s/`'\"]+)?(/[\w\-./{{}}:]*)")
CURL_RE = re.compile(rf"curl\b[^\n]*?(?:-X|--request)\s*({METHODS})\b[^\n]*?['\"]?(https?://[^\s'\"]+)", re.I)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
GLOBAL_RE = re.compile(
    r"\b(auth|authentication|authori[sz]ation|pagination|paging|errors?|error codes?|status codes|conventions?|rate[- ]?limit\w*|"
    r"common (parameters|headers)|base url|versioning|getting started|overview|introduction|general)\b", re.I)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def normalize_markdown(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    lines = [ln.rstrip() for ln in text.split("\n")]
    out, blank = [], 0
    for ln in lines:
        blank = blank + 1 if not ln.strip() else 0
        if blank <= 2:
            out.append(ln)
    return "\n".join(out).strip("\n") + "\n"


def clean_path(path: str) -> str:
    path = path.split("?")[0].rstrip(".,;:)")
    path = re.sub(r":(\w+)", r"{\1}", path)
    path = re.sub(r"<(\w+)>", r"{\1}", path)
    return path if path == "/" else path.rstrip("/")


@dataclass
class Section:
    level: int
    title: str
    start: int  # offset của dòng tiêu đề (hoặc 0 cho phần mở đầu)
    end: int
    heading_path: list[str] = field(default_factory=list)


@dataclass
class ChunkDraft:
    order: int
    title: str
    text: str
    span_start: int
    span_end: int
    is_global: bool = False
    operation_hint: dict | None = None
    heading_path: list[str] = field(default_factory=list)

    @property
    def token_count(self) -> int:
        return estimate_tokens(self.text)


def _line_offsets(md: str) -> list[int]:
    offs, pos = [], 0
    for ln in md.split("\n"):
        offs.append(pos)
        pos += len(ln) + 1
    return offs


def _sections(md: str) -> list[Section]:
    lines = md.split("\n")
    offs = _line_offsets(md)
    heads: list[tuple[int, int, str]] = []  # (line_idx, level, title)
    in_code = False
    for i, ln in enumerate(lines):
        if FENCE_RE.match(ln):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADING_RE.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    secs: list[Section] = []
    first = heads[0][0] if heads else len(lines)
    if first > 0 and md[: offs[first] if first < len(offs) else len(md)].strip():
        secs.append(Section(0, "Giới thiệu", 0, offs[first] if first < len(offs) else len(md)))
    stack: list[tuple[int, str]] = []
    for k, (i, level, title) in enumerate(heads):
        end = offs[heads[k + 1][0]] if k + 1 < len(heads) else len(md)
        while stack and stack[-1][0] >= level:
            stack.pop()
        secs.append(Section(level, title, offs[i], end, [t for _, t in stack]))
        stack.append((level, title))
    return secs


def find_signatures(text: str) -> list[tuple[int, str, str]]:
    """Trả về [(offset, METHOD, path)] – chữ ký operation và lệnh curl."""
    found: list[tuple[int, str, str]] = []
    for m in SIG_RE.finditer(text):
        found.append((m.start(), m.group(1).upper(), clean_path(m.group(2))))
    for m in CURL_RE.finditer(text):
        url = m.group(2)
        path = "/" + url.split("://", 1)[-1].split("/", 1)[-1] if "/" in url.split("://", 1)[-1] else "/"
        found.append((m.start(), m.group(1).upper(), clean_path(path)))
    found.sort()
    return found


def _split_long(d: ChunkDraft) -> list[ChunkDraft]:
    if d.token_count <= MAX_CHUNK_TOKENS:
        return [d]
    # tách theo đoạn văn (dòng trống ngoài khối mã)
    parts, cur, cur_start, in_code, pos = [], [], 0, False, 0
    lines = d.text.split("\n")
    for ln in lines:
        if FENCE_RE.match(ln):
            in_code = not in_code
        cur.append(ln)
        pos += len(ln) + 1
        if not in_code and not ln.strip() and estimate_tokens("\n".join(cur)) >= MAX_CHUNK_TOKENS * 0.8:
            parts.append((cur_start, "\n".join(cur)))
            cur, cur_start = [], pos
    if cur:
        parts.append((cur_start, "\n".join(cur)))
    out = []
    for i, (off, txt) in enumerate(parts):
        out.append(ChunkDraft(0, f"{d.title} ({i + 1}/{len(parts)})", txt, d.span_start + off,
                              d.span_start + off + len(txt), d.is_global, d.operation_hint, d.heading_path))
    return out


def segment(md: str) -> list[ChunkDraft]:
    """Phân đoạn Markdown đã chuẩn hóa. Offset tính trên chính chuỗi `md`."""
    drafts: list[ChunkDraft] = []
    secs = _sections(md)
    if not secs:
        secs = [Section(0, "Tài liệu", 0, len(md))]
    for s in secs:
        text = md[s.start:s.end]
        sigs = find_signatures(text)
        distinct: list[tuple[int, str, str]] = []
        seen = set()
        for off, meth, path in sigs:
            if (meth, path) not in seen:
                seen.add((meth, path))
                distinct.append((off, meth, path))
        if not distinct:
            if not text.strip():
                continue
            body_only = "\n".join(text.split("\n")[1:]).strip() if s.level else text.strip()
            is_global = bool(GLOBAL_RE.search(s.title)) or s.level == 0 or (
                s.level == 1 and s is secs[0])
            if not body_only and not is_global:
                continue
            drafts.append(ChunkDraft(0, s.title, text, s.start, s.end, is_global, None, s.heading_path))
            continue
        if len(distinct) == 1:
            _, meth, path = distinct[0]
            drafts.append(ChunkDraft(0, s.title or f"{meth} {path}", text, s.start, s.end, False,
                                     {"method": meth, "path": path}, s.heading_path))
            continue
        # nhiều operation trong cùng một mục: tách tại dòng chứa chữ ký
        cuts = []
        for off, meth, path in distinct:
            line_start = text.rfind("\n", 0, off) + 1
            cuts.append((line_start, meth, path))
        cuts[0] = (0, cuts[0][1], cuts[0][2])
        for i, (st, meth, path) in enumerate(cuts):
            en = cuts[i + 1][0] if i + 1 < len(cuts) else len(text)
            drafts.append(ChunkDraft(0, f"{meth} {path}", text[st:en], s.start + st, s.start + en, False,
                                     {"method": meth, "path": path}, s.heading_path + ([s.title] if s.title else [])))
    out: list[ChunkDraft] = []
    for d in drafts:
        out.extend(_split_long(d))
    for i, d in enumerate(out):
        d.order = i
    return out


def build_context(chunks: list, target, max_tokens: int = 1500) -> str:
    """Ngữ cảnh chung cho prompt: các phân đoạn global + phân đoạn tổ tiên (không phải operation)."""
    parts: list[str] = []
    budget = max_tokens
    ancestors = set(target.heading_path or [])
    for c in chunks:
        if c is target or c.operation_hint:
            continue
        if c.is_global or c.title in ancestors:
            t = c.text.strip()
            cost = estimate_tokens(t)
            if cost > budget:
                t = t[: budget * 4]
                cost = budget
            if t:
                parts.append(t)
                budget -= cost
            if budget <= 0:
                break
    return "\n\n".join(parts)
