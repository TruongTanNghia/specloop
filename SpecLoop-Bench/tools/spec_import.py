"""Nhập một API mới vào bộ dữ liệu – dùng chung cho tools/add_api.py (dòng lệnh) và giao diện web SpecLoop.

  prepare_spec(raw)            đọc YAML/JSON, Swagger 2.0 -> 3.0, hạ cấp 3.1 -> 3.0.3, sửa các lỗi hợp lệ hay gặp
  suggest_meta(spec)           gợi ý id, tên, base URL, xác thực, giấy phép… từ chính đặc tả
  create_api(root, cfg, raw)   ghi apis/<id>/ (source, ground truth, meta.yaml, tài liệu gốc), dựng facts/tài liệu
                               render, cập nhật manifest.json + stats.csv, chạy kiểm tra toàn vẹn
  delete_api(root, id)         xóa thư mục API và gỡ khỏi manifest

Mọi sửa đổi so với đặc tả gốc đều được ghi vào meta.yaml -> source.normalization.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import shutil
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import yaml

from oas_utils import HTTP_METHODS, dump_yaml, normalize_to_303, validate_spec, write_text_lf
from swagger2_to_oas3 import convert as swagger2_convert

ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,40}")
GROUPS = ("A", "B")
ENV_TYPES = ("local-docker", "public", "offline")
SCOPES = ("full", "read-only", "none")
AUTH_TYPES = ("none", "apiKey", "bearer", "oauth2")
DOC_SUFFIXES = (".md", ".html", ".htm", ".txt")

# ----------------------------------------------------------------- sửa lỗi hợp lệ hay gặp
DROP_KEYS = ("patternProperties", "unevaluatedProperties", "unevaluatedItems", "dependentRequired",
             "dependentSchemas", "if", "then", "else", "prefixItems", "$defs", "contains", "minContains",
             "maxContains", "propertyNames")
BOOL_KEYS = ("deprecated", "nullable", "uniqueItems", "exclusiveMinimum", "exclusiveMaximum", "readOnly",
             "writeOnly", "allowEmptyValue", "explode", "allowReserved")
TYPE_ALIASES = {"int": "integer", "float": "number", "double": "number", "decimal": "number", "bool": "boolean",
                "str": "string", "text": "string", "long": "integer", "list": "array", "dict": "object"}
NUMBER_KEYS = ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "multipleOf",
               "minProperties", "maxProperties")
UNICODE_CLASSES = {r"\p{L}": r"A-Za-zÀ-ɏ", r"\p{N}": "0-9", r"\p{Lu}": r"A-ZÀ-Þ",
                   r"\p{Ll}": r"a-zß-ÿ"}


def _is_bool_str(v) -> bool:
    return isinstance(v, str) and v.lower() in ("true", "false")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fix_values(node, notes: set):
    """Chuỗi 'true'/'false' ở trường boolean, số viết dạng chuỗi, tên kiểu không chuẩn, regex \\p{..}."""
    if isinstance(node, dict):
        out = {}
        is_bool_schema = node.get("type") == "boolean"
        is_str_schema = node.get("type") == "string"
        for k, v in node.items():
            if is_bool_schema and k in ("default", "example") and _is_bool_str(v):
                v = v.lower() == "true"
                notes.add("default/example 'true'/'false' của trường boolean -> boolean")
            elif is_str_schema and k in ("default", "example") and _is_number(v):
                v = str(v)
                notes.add("default/example dạng số của trường chuỗi -> chuỗi")
            elif (k in BOOL_KEYS or k == "required") and _is_bool_str(v):
                v = v.lower() == "true"
                notes.add("chuỗi 'true'/'false' ở trường boolean -> boolean")
            elif k == "type" and isinstance(v, str) and v in TYPE_ALIASES:
                v = TYPE_ALIASES[v]
                notes.add("tên kiểu không chuẩn (int/float/bool/str…) -> kiểu JSON Schema")
            elif k in NUMBER_KEYS and isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v):
                v = float(v) if "." in v else int(v)
                notes.add("giá trị số viết dạng chuỗi ở minimum/maximum/… -> số")
            elif k == "pattern" and isinstance(v, str) and "\\p{" in v:
                for a, b in UNICODE_CLASSES.items():
                    v = v.replace(a, b)
                notes.add("pattern: lớp Unicode \\p{L}/\\p{N} -> khoảng ký tự tương đương (ECMA 262)")
            out[k] = _fix_values(v, notes)
        return out
    if isinstance(node, list):
        return [_fix_values(x, notes) for x in node]
    return node


def _is_null_schema(a) -> bool:
    return isinstance(a, dict) and (a.get("type") == "null" or (a.get("nullable") is True and a.get("enum") == [None]))


def _fix_null_type(node, notes: set):
    """OAS 3.1: schema chỉ có type 'null' hoặc nhánh {type: 'null'} trong oneOf/anyOf -> nullable của OAS 3.0."""
    if isinstance(node, list):
        return [_fix_null_type(x, notes) for x in node]
    if not isinstance(node, dict):
        return node
    node = {k: _fix_null_type(v, notes) for k, v in node.items()}
    for key in ("oneOf", "anyOf"):
        alts = node.get(key)
        if isinstance(alts, list) and any(_is_null_schema(a) for a in alts):
            rest = [a for a in alts if not _is_null_schema(a)]
            node[key] = rest
            if not rest:
                node.pop(key)
                node["enum"] = [None]
            node["nullable"] = True
            notes.add("nhánh {type: 'null'} trong oneOf/anyOf (OAS 3.1) -> nullable: true")
    if node.get("type") == "null":
        node.pop("type")
        node.update(nullable=True, enum=[None])
        notes.add("schema chỉ có type 'null' (OAS 3.1) -> nullable: true, enum: [null]")
    if node.get("required") == []:
        node.pop("required")
        notes.add("bỏ required: [] rỗng (OAS 3.0 yêu cầu ít nhất một phần tử)")
    return node


def _strip_31_keywords(node, dropped: set):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in DROP_KEYS:
                dropped.add(k)
                continue
            out[k] = _strip_31_keywords(v, dropped)
        return out
    if isinstance(node, list):
        return [_strip_31_keywords(x, dropped) for x in node]
    return node


SWAGGER2_ROOT_KEYS = ("host", "basePath", "schemes", "consumes", "produces")
PARAM_SCHEMA_KEYS = ("type", "format", "items", "enum", "default", "minimum", "maximum", "exclusiveMinimum",
                     "exclusiveMaximum", "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems",
                     "multipleOf", "nullable")


def _local_param(spec: dict, p) -> dict:
    """Tham số dạng {$ref: '#/components/parameters/X'} -> đối tượng tham số thật (để đọc name/in)."""
    if isinstance(p, dict) and isinstance(p.get("$ref"), str) and p["$ref"].startswith("#/components/parameters/"):
        return ((spec.get("components") or {}).get("parameters") or {}).get(p["$ref"].rsplit("/", 1)[-1]) or {}
    return p if isinstance(p, dict) else {}


def _iter_params(spec: dict):
    for item in (spec.get("paths") or {}).values():
        if not isinstance(item, dict):
            continue
        yield from item.get("parameters") or []
        for m, op in item.items():
            if m in HTTP_METHODS and isinstance(op, dict):
                yield from op.get("parameters") or []
    yield from ((spec.get("components") or {}).get("parameters") or {}).values()


def _fix_param_schema(spec: dict, notes: set) -> None:
    """Tham số OAS 3 viết kiểu Swagger 2 (type/enum… ngay trên tham số, thiếu schema) -> chuyển vào schema."""
    for p in _iter_params(spec):
        if not isinstance(p, dict) or "$ref" in p or "schema" in p or "content" in p:
            continue
        p["schema"] = {k: p.pop(k) for k in PARAM_SCHEMA_KEYS if k in p}
        notes.add("tham số thiếu schema (type/enum… viết thẳng trên tham số kiểu Swagger 2.0) -> chuyển vào schema")


def _add_missing_path_params(spec: dict, notes: set) -> None:
    """{biến} có trong đường dẫn nhưng không khai báo tham số path -> thêm tham số chuỗi bắt buộc."""
    def path_names(params) -> set:
        return {q.get("name") for q in (_local_param(spec, p) for p in params or []) if q.get("in") == "path"}

    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        tmpl = re.findall(r"\{([^}]+)\}", path)
        if not tmpl:
            continue
        shared = path_names(item.get("parameters"))
        for m, op in item.items():
            if m not in HTTP_METHODS or not isinstance(op, dict):
                continue
            declared = shared | path_names(op.get("parameters"))
            for v in tmpl:
                if v not in declared:
                    op.setdefault("parameters", []).append(
                        {"name": v, "in": "path", "required": True, "schema": {"type": "string"}})
                    notes.add("thêm tham số path thiếu khai báo (chuỗi, bắt buộc) cho các operation có {biến} trong đường dẫn")


# ----------------------------------------------------------------- link tới tệp đặc tả
_GITHUB_FILE = re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/(?:blob|raw)/([^?#]+)")
_GITLAB_FILE = re.compile(r"^(https?://gitlab\.com/[^?#]+?)/-/blob/([^?#]+)")
_GIST = re.compile(r"^https?://gist\.github\.com/([^/]+)/([0-9a-f]+)/?(?:[?#].*)?$")


def resolve_spec_url(url: str) -> str:
    """Link trang xem tệp trên GitHub / GitLab / Gist -> link tệp thô (raw); link khác giữ nguyên.

    github.com/<chủ>/<kho>/blob/<nhánh>/<đường dẫn> trả về trang HTML, không phải tệp YAML/JSON."""
    u = (url or "").strip()
    if m := _GITHUB_FILE.match(u):
        return f"https://raw.githubusercontent.com/{m[1]}/{m[2]}/{m[3]}"
    if m := _GITLAB_FILE.match(u):
        return f"{m[1]}/-/raw/{m[2]}"
    if m := _GIST.match(u):
        return f"https://gist.githubusercontent.com/{m[1]}/{m[2]}/raw"
    return u


# ----------------------------------------------------------------- đặc tả chia nhiều tệp
MAX_REF_FILES = 1000
MAX_BUNDLED_BYTES = 40 * 1024 * 1024


def _external_refs(node, out: set | None = None) -> set:
    out = set() if out is None else out
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            out.add(ref)
        for v in node.values():
            _external_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            _external_refs(v, out)
    return out


def _pointer(doc, frag: str):
    node = doc
    for part in (p for p in frag.split("/") if p):
        part = unquote(part).replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def bundle_external_refs(spec: dict, source_url: str, fetch) -> tuple[dict, int]:
    """$ref tới tệp khác ('./paths/user.yaml', 'common.yaml#/User') -> chép nội dung vào một tệp duy nhất.

    Chỉ tải tệp cùng máy chủ với tệp gốc. Tham chiếu vòng (schema đệ quy) -> đưa vào components/schemas.
    Trả về (đặc tả đã gộp, số tệp đã tải thêm)."""
    host = urlparse(source_url).netloc
    docs: dict[str, object] = {source_url: spec}
    memo: dict[tuple, object] = {}
    hoisted: dict[tuple, str] = {}

    def fetch_doc(url: str):
        if urlparse(url).scheme not in ("http", "https") or urlparse(url).netloc != host:
            raise ValueError(f"$ref trỏ ra ngoài máy chủ của tệp gốc: {url}")
        try:
            return parse_raw(fetch(url))
        except ValueError as e:
            raise ValueError(f"Không đọc được tệp tham chiếu {url}: {e}") from e

    # tải trước theo từng lớp, song song (đặc tả lớn có hàng trăm tệp con)
    frontier = [source_url]
    while frontier:
        new = sorted({urljoin(u, r.partition("#")[0]) for u in frontier for r in _external_refs(docs[u])
                      if r.partition("#")[0]} - set(docs))
        if len(docs) + len(new) > MAX_REF_FILES:
            raise ValueError(f"Đặc tả tham chiếu quá {MAX_REF_FILES} tệp")
        with ThreadPoolExecutor(max_workers=16) as ex:
            docs.update(zip(new, ex.map(fetch_doc, new), strict=True))
        frontier = new

    def load(url: str):
        if url not in docs:
            docs[url] = fetch_doc(url)
        return docs[url]

    def hoist_name(key: tuple) -> str:
        if key not in hoisted:
            base = (key[1].rstrip("/").rsplit("/", 1)[-1] if key[1] else Path(urlparse(key[0]).path).stem) or "Schema"
            name, i = re.sub(r"[^A-Za-z0-9_.-]", "_", base), 2
            taken = set(hoisted.values()) | set(((spec.get("components") or {}).get("schemas") or {}))
            while name in taken:
                name, i = f"{base}_{i}", i + 1
            hoisted[key] = name
        return hoisted[key]

    def walk(node, cur: str, stack: frozenset):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                file_part, _, frag = ref.partition("#")
                target = urljoin(cur, file_part) if file_part else cur
                if target == source_url:
                    return {"$ref": "#" + frag}  # trỏ về chính tệp gốc -> giữ tham chiếu nội bộ
                key = (target, frag)
                if key in stack or key in hoisted:
                    return {"$ref": f"#/components/schemas/{hoist_name(key)}"}
                if key not in memo:
                    try:
                        found = _pointer(load(target), frag)
                    except (KeyError, IndexError, ValueError, TypeError) as e:
                        raise ValueError(f"Không tìm thấy $ref {ref!r} (từ {cur}): {e}") from e
                    memo[key] = walk(found, target, stack | {key})
                return copy.deepcopy(memo[key])
            return {k: walk(v, cur, stack) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, cur, stack) for v in node]
        return node

    out = walk(spec, source_url, frozenset())
    done: set = set()
    while set(hoisted) - done:
        for key in list(set(hoisted) - done):
            done.add(key)
            body = walk(_pointer(load(key[0]), key[1]), key[0], frozenset({key}))
            out.setdefault("components", {}).setdefault("schemas", {})[hoisted[key]] = body
    if len(json.dumps(out, ensure_ascii=False)) > MAX_BUNDLED_BYTES:
        raise ValueError("Đặc tả sau khi gộp các tệp tham chiếu vượt 40 MB")
    return out, len(docs) - 1


def parse_raw(raw: bytes | str) -> dict:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    if re.match(r"\s*<(!doctype|html|head|body|\?xml)", text[:200], re.I):
        raise ValueError("Nội dung là một trang web (HTML), không phải tệp đặc tả YAML/JSON. Hãy dùng link tới chính "
                         "tệp openapi.yaml / swagger.json (trên GitHub: mở tệp rồi bấm nút “Raw”).")
    try:
        data = json.loads(text) if text.lstrip().startswith("{") else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise ValueError(f"Không đọc được YAML/JSON: {str(e).splitlines()[0][:200]}") from e
    if not isinstance(data, dict):
        raise ValueError("Tệp không phải đặc tả OpenAPI/Swagger (nội dung gốc không là đối tượng).")
    return data


def prepare_spec(raw: bytes | str, base_url: str | None = None, *, source_url: str | None = None,
                 fetch=None) -> tuple[dict, list[str], str, list[str]]:
    """Trả về (spec 3.0.3, ghi chú chuẩn hóa, phiên bản gốc, lỗi hợp lệ còn lại).

    source_url + fetch(url) -> bytes: dùng để gộp đặc tả chia nhiều tệp ($ref tới tệp khác).
    ValueError nếu không đọc/chuẩn hóa được (không phải OpenAPI, không có paths…)."""
    src = parse_raw(raw)
    notes: list[str] = []
    if ext := _external_refs(src):
        if not (source_url and fetch):
            raise ValueError(f"Đặc tả chia nhiều tệp ($ref tới tệp khác, ví dụ {sorted(ext)[0]!r}). Hãy dùng chế độ "
                             "“Từ URL” với link Raw của tệp gốc để hệ thống tự tải và gộp các tệp con.")
        src, n_files = bundle_external_refs(src, source_url, fetch)
        notes.append(f"gộp đặc tả chia nhiều tệp: chép nội dung {n_files} tệp được $ref tới vào một tệp")
    if str(src.get("swagger", "")).startswith("2"):
        src_version = f"Swagger {src['swagger']}"
        src = swagger2_convert(src)
        notes.append("chuyển Swagger 2.0 -> OpenAPI 3.0.3 bằng tools/swagger2_to_oas3.py "
                     "(body/formData -> requestBody, definitions -> components, host/basePath -> servers)")
    elif "openapi" in src:
        src_version = f"OpenAPI {src['openapi']}"
        if stray := [k for k in SWAGGER2_ROOT_KEYS if k in src]:
            if not src.get("servers") and src.get("host"):
                scheme = (src.get("schemes") or ["https"])[0]
                src["servers"] = [{"url": f"{scheme}://{src['host']}{(src.get('basePath') or '').rstrip('/')}"}]
            for k in stray:
                src.pop(k)
            notes.append(f"bỏ trường gốc kiểu Swagger 2.0 trong tệp OpenAPI 3 ({', '.join(stray)}); "
                         "host/basePath -> servers nếu chưa có")
    else:
        raise ValueError("Không thấy trường 'openapi' hay 'swagger' – đây không phải đặc tả OpenAPI/Swagger.")
    spec, n = normalize_to_303(src)
    notes += n
    if src_version.startswith("OpenAPI 3.1"):
        dropped: set = set()
        spec = _strip_31_keywords(spec, dropped)
        if dropped:
            notes.append("bỏ từ khóa JSON Schema 2020-12 không có trong OAS 3.0: " + ", ".join(sorted(dropped)))
        null_fixes: set = set()
        spec = _fix_null_type(spec, null_fixes)
        notes += sorted(null_fixes)
    fixes: set = set()
    _fix_param_schema(spec, fixes)
    spec = _fix_values(spec, fixes)
    _add_missing_path_params(spec, fixes)
    notes += sorted(fixes)
    if base_url:
        old = (spec.get("servers") or [{}])[0].get("url")
        if old != base_url:
            spec["servers"] = [{"url": base_url}]
            notes.append(f"servers[0].url: {old!r} -> {base_url!r}")
    return spec, notes, src_version, validate_spec(spec)


def count_operations(spec: dict) -> int:
    return sum(1 for it in (spec.get("paths") or {}).values() if isinstance(it, dict)
               for m, op in it.items() if m in HTTP_METHODS and isinstance(op, dict))


def slugify(text: str) -> str:
    """'Kho Sách Thử API' -> 'kho-sach-thu' (bỏ dấu tiếng Việt, đ -> d)."""
    t = unicodedata.normalize("NFKD", (text or "").replace("đ", "d").replace("Đ", "D"))
    t = "".join(c for c in t if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    s = re.sub(r"-(api|rest|openapi|reference)$", "", s) or s
    return (s or "api")[:41].rstrip("-")


def suggest_meta(spec: dict) -> dict:
    """Gợi ý các trường meta.yaml từ chính đặc tả (người dùng sửa lại trên giao diện)."""
    info = spec.get("info") or {}
    url = ((spec.get("servers") or [{}])[0] or {}).get("url") or ""
    absolute = bool(re.match(r"^https?://[^{}]+$", url))
    local = absolute and re.match(r"^https?://(localhost|127\.|0\.0\.0\.0|\[::1\])", url) is not None
    auth = {"type": "none"}
    for name, sch in ((spec.get("components") or {}).get("securitySchemes") or {}).items():
        if not isinstance(sch, dict):
            continue
        if sch.get("type") == "apiKey":
            auth = {"type": "apiKey", "in": sch.get("in", "header"), "name": sch.get("name", "X-API-Key"),
                    "env_var": re.sub(r"[^A-Z0-9]+", "_", slugify(info.get("title", "api")).upper()) + "_API_KEY"}
        elif sch.get("type") == "http" and str(sch.get("scheme", "")).lower() == "bearer":
            auth = {"type": "bearer", "env_var": re.sub(r"[^A-Z0-9]+", "_", slugify(info.get("title", "api")).upper()) + "_TOKEN"}
        elif sch.get("type") == "oauth2":
            auth = {"type": "oauth2", "env_var": re.sub(r"[^A-Z0-9]+", "_", slugify(info.get("title", "api")).upper()) + "_TOKEN"}
        else:
            continue
        break
    lic = info.get("license") or {}
    desc = " ".join(str(info.get("description") or "").split())
    if len(desc) > 400:
        desc = desc[:400].rsplit(" ", 1)[0] + "…"
    first_get = next((p for p, it in (spec.get("paths") or {}).items()
                      if isinstance(it, dict) and "get" in it and "{" not in p), None)
    return {
        "id": slugify(info.get("title", "")), "name": info.get("title") or "API",
        "description": desc, "base_url": url if absolute else "",
        "group": "A" if local else "B", "env": "local-docker" if local else "public",
        "scope": "full" if local else "read-only", "auth": auth,
        "license": lic.get("name") if isinstance(lic, dict) else "",
        "homepage": ((info.get("contact") or {}).get("url") or "") if isinstance(info.get("contact"), dict) else "",
        "docs_url": ((spec.get("externalDocs") or {}).get("url") or "") if isinstance(spec.get("externalDocs"), dict) else "",
        "probe_path": first_get or "",
    }


# ----------------------------------------------------------------- tạo / xóa API
def _req(cfg: dict, key: str, default="TODO"):
    v = cfg.get(key)
    return v if v not in (None, "") else default


def build_meta(cfg: dict, spec: dict, src_name: str, notes: list[str], doc_original: str | None) -> dict:
    auth = dict(cfg.get("auth") or {"type": "none"})
    if auth.get("type", "none") == "none":
        auth = {"type": "none"}
    else:
        auth = {k: v for k, v in auth.items() if v not in (None, "")}
        auth.setdefault("env_var", "TODO")
    scope = cfg.get("scope") or "read-only"
    env_type = cfg.get("env") or "public"
    probe_path = cfg.get("probe_path") or None
    ablated = bool(cfg.get("make_ablated"))
    return {
        "id": cfg["id"], "name": cfg["name"], "group": cfg.get("group") or "B",
        "description": _req(cfg, "description", "TODO: mô tả ngắn API (lĩnh vực, số endpoint, điểm đáng chú ý về ràng buộc)"),
        "source": {"spec_url": _req(cfg, "spec_url", "tải lên trực tiếp" if cfg.get("added_via") == "web" else "TODO"),
                   "spec_file": f"source/{src_name}", "license": _req(cfg, "license"),
                   "homepage": _req(cfg, "homepage"), "docs_url": _req(cfg, "docs_url"),
                   "retrieved_at": dt.date.today().isoformat(), "normalization": notes},
        "environment": {"type": env_type,
                        "base_url": cfg.get("base_url") or (spec.get("servers") or [{}])[0].get("url", "TODO"),
                        "test_scope": scope, "auth": auth,
                        "rate_limit_rps": cfg.get("rate_limit_rps") or (1 if env_type == "public" else 5),
                        "connectivity_checked": False,
                        "probe": {"method": "GET", "path": probe_path or ("TODO" if scope != "none" else None),
                                  "params": cfg.get("probe_params") or {}}},
        "docs": {"original": doc_original, "rendered": "docs/rendered.md",
                 "ablated": "docs/ablated.md" if ablated else None, "make_ablated": ablated},
        "ground_truth": {"doc": "ground_truth/openapi.yaml", "behavior": None, "behavior_status": "pending",
                         "verified_by": [], "notes": "GT tài liệu = đặc tả chính thức; GT hành vi chưa xác minh."},
        "rq_scope": ["RQ1", "RQ2", "RQ3"] if scope != "none" else ["RQ1"],
        "added_by": _req(cfg, "added_by"), "added_via": cfg.get("added_via") or "cli",
        "notes": cfg.get("notes") or "",
    }


def check_cfg(root: Path, cfg: dict, overwrite: bool = False) -> list[str]:
    errs = []
    api_id = cfg.get("id") or ""
    if not ID_RE.fullmatch(api_id):
        errs.append("id chỉ gồm chữ thường, số, gạch nối (2–41 ký tự, bắt đầu bằng chữ/số)")
    elif (Path(root) / "apis" / api_id).exists() and not overwrite:
        errs.append(f"đã có API '{api_id}' trong bộ dữ liệu")
    if not (cfg.get("name") or "").strip():
        errs.append("thiếu tên API")
    for key, allowed in (("group", GROUPS), ("env", ENV_TYPES), ("scope", SCOPES)):
        if cfg.get(key) and cfg[key] not in allowed:
            errs.append(f"{key} phải thuộc {allowed}")
    if (cfg.get("auth") or {}).get("type", "none") not in AUTH_TYPES:
        errs.append(f"auth.type phải thuộc {AUTH_TYPES}")
    return errs


def create_api(root: Path, cfg: dict, raw: bytes, src_suffix: str = ".yaml", *,
               doc_original: tuple[bytes, str] | None = None, overwrite: bool = False,
               source_url: str | None = None, fetch=None) -> dict:
    """Tạo apis/<id>/ rồi dựng + kiểm tra. cfg: id, name, group, env, scope, base_url, auth, license, homepage,
    docs_url, description, rate_limit_rps, probe_path, make_ablated, spec_url, added_by, added_via, notes.

    Đặc tả chia nhiều tệp (cần source_url + fetch) được gộp trước, và bản gộp được lưu làm source/ để dựng lại
    ground truth mà không cần mạng.
    Ném ValueError (không ghi gì) nếu cấu hình sai hoặc đặc tả không hợp lệ sau khi đã sửa tự động."""
    import build_dataset
    import validate_dataset

    root = Path(root)
    errs = check_cfg(root, cfg, overwrite)
    if errs:
        raise ValueError("; ".join(errs))
    bundle_note = None
    if source_url and fetch and _external_refs(parse_raw(raw)):
        bundled, n_files = bundle_external_refs(parse_raw(raw), source_url, fetch)
        raw, src_suffix = yaml.safe_dump(bundled, sort_keys=False, allow_unicode=True).encode("utf-8"), ".yaml"
        bundle_note = (f"gộp đặc tả chia nhiều tệp: chép nội dung {n_files} tệp được $ref tới vào một tệp "
                       "(source/ lưu bản đã gộp)")
    spec, notes, _ver, verrs = prepare_spec(raw, cfg.get("base_url") or None)
    if bundle_note:
        notes.insert(0, bundle_note)
    if verrs:
        raise ValueError("Đặc tả vẫn chưa hợp lệ OpenAPI 3.0.3 sau khi sửa tự động: " + verrs[0])
    d = root / "apis" / cfg["id"]
    if d.exists() and overwrite:
        shutil.rmtree(d)
    try:
        for sub in ("source", "docs", "ground_truth"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        if src_suffix not in (".json", ".yaml", ".yml"):
            src_suffix = ".json" if text.lstrip().startswith("{") else ".yaml"
        src_name = f"openapi_original{src_suffix}"
        (d / "source" / src_name).write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        dump_yaml(spec, d / "ground_truth" / "openapi.yaml")
        doc_rel = None
        if doc_original:
            content, suffix = doc_original
            suffix = suffix if suffix in DOC_SUFFIXES else ".md"
            doc_rel = f"docs/original{suffix}"
            (d / doc_rel).write_bytes(content.replace(b"\r\n", b"\n"))
        meta = build_meta(cfg, spec, src_name, notes, doc_rel)
        write_text_lf(d / "meta.yaml", yaml.safe_dump(meta, sort_keys=False, allow_unicode=True))
        manifest = build_dataset.update_manifest(root, [cfg["id"]], verbose=False)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        build_dataset.update_manifest(root, [], verbose=False)
        raise
    entry = next(e for e in manifest["apis"] if e["id"] == cfg["id"])
    v_errs, v_warns = validate_dataset.check_api(d, entry["files"], root)
    return {"id": cfg["id"], "path": f"apis/{cfg['id']}", "stats": entry["stats"], "normalization": notes,
            "validation": {"ok": not v_errs, "errors": v_errs, "warnings": v_warns}}


def delete_api(root: Path, api_id: str) -> None:
    import build_dataset

    root = Path(root)
    if not ID_RE.fullmatch(api_id or ""):
        raise ValueError("id không hợp lệ")
    d = root / "apis" / api_id
    if not d.is_dir():
        raise FileNotFoundError(api_id)
    shutil.rmtree(d)
    build_dataset.update_manifest(root, [], verbose=False)
