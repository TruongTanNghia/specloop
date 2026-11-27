"""Quản lý bộ dữ liệu SpecLoop-Bench từ giao diện: liệt kê, xem, xem trước đặc tả, thêm, xóa, kiểm tra kết nối.

Toàn bộ xử lý đặc tả dùng lại tools/spec_import.py, build_dataset.py, validate_dataset.py, check_connectivity.py
của bộ dữ liệu (cùng logic với dòng lệnh add_api.py). Các thao tác ghi được tuần tự hóa bằng khóa vì cùng sửa
manifest.json / stats.csv.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import dotenv_values

from ..bench import BENCH_DIR  # import này đưa SpecLoop-Bench/tools vào sys.path – phải đứng trước khối dưới
from ..config import REPO_ROOT

# isort: split
import build_dataset  # noqa: E402
import check_connectivity  # noqa: E402
import spec_import  # noqa: E402

DOTENV_PATH = REPO_ROOT / ".env"
MAX_SPEC_BYTES = 20 * 1024 * 1024
MAX_FILE_VIEW_BYTES = 3 * 1024 * 1024
_LOCK = threading.Lock()


class BenchError(Exception):
    """Lỗi do dữ liệu người dùng (đặc tả sai, id trùng…) – trả 4xx."""

    def __init__(self, status: int, title: str, detail: str | None = None):
        super().__init__(detail or title)
        self.status, self.title, self.detail = status, title, detail


def root() -> Path:
    return BENCH_DIR


def _api_dir(api_id: str) -> Path:
    if not spec_import.ID_RE.fullmatch(api_id or ""):
        raise BenchError(404, "Không tìm thấy", f"API '{api_id}' không có trong bộ dữ liệu")
    d = root() / "apis" / api_id
    if not (d / "meta.yaml").exists():
        raise BenchError(404, "Không tìm thấy", f"API '{api_id}' không có trong bộ dữ liệu")
    return d


def _manifest() -> dict:
    p = root() / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"apis": []}


def _meta(d: Path) -> dict:
    return yaml.safe_load((d / "meta.yaml").read_text(encoding="utf-8")) or {}


# ----------------------------------------------------------------- đọc
def list_apis() -> list[dict]:
    entries = {e["id"]: e for e in _manifest().get("apis", [])}
    out = []
    for d in sorted((root() / "apis").iterdir()):
        if not d.is_dir() or d.name.startswith("_") or not (d / "meta.yaml").exists():
            continue
        m = _meta(d)
        env = m.get("environment") or {}
        src = m.get("source") or {}
        docs = m.get("docs") or {}
        st = (entries.get(d.name) or {}).get("stats") or {}
        out.append({
            "id": d.name, "name": m.get("name", d.name), "group": m.get("group"), "description": m.get("description"),
            "environment": env.get("type"), "test_scope": env.get("test_scope"), "base_url": env.get("base_url"),
            "auth": (env.get("auth") or {}).get("type", "none"),
            "connectivity_checked": bool(env.get("connectivity_checked")),
            "license": src.get("license"), "retrieved_at": src.get("retrieved_at"),
            "has_original_doc": bool(docs.get("original")), "has_ablated_doc": bool(docs.get("ablated")),
            "behavior_gt": (m.get("ground_truth") or {}).get("behavior_status", "pending"),
            "added_by": m.get("added_by"), "added_via": m.get("added_via"),
            "deletable": m.get("added_via") == "web",
            "operations": st.get("operations"), "parameters": st.get("parameters"),
            "constraints": st.get("constraints_no_type"), "facts": st.get("facts_total"),
        })
    return out


def get_api(api_id: str) -> dict:
    d = _api_dir(api_id)
    entry = next((e for e in _manifest().get("apis", []) if e["id"] == api_id), {})
    files = []
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d)
        if p.is_file() and not any(x.startswith(".") or x == "__pycache__" for x in rel.parts):
            files.append({"path": rel.as_posix(), "size": p.stat().st_size})
    m = _meta(d)
    return {"id": api_id, "meta": m, "stats": entry.get("stats"), "files": files,
            "deletable": m.get("added_via") == "web"}


def read_file(api_id: str, rel: str) -> tuple[str, str]:
    """Đọc một tệp văn bản trong apis/<id>/ (chỉ tệp có trong danh sách, không cho đi ra ngoài thư mục)."""
    d = _api_dir(api_id)
    allowed = {f["path"] for f in get_api(api_id)["files"]}
    if rel not in allowed:
        raise BenchError(404, "Không tìm thấy", f"Tệp '{rel}' không thuộc API '{api_id}'")
    p = (d / rel).resolve()
    if d.resolve() not in p.parents:
        raise BenchError(404, "Không tìm thấy", rel)
    if p.stat().st_size > MAX_FILE_VIEW_BYTES:
        raise BenchError(413, "Tệp quá lớn để xem trên web", f"{rel}: {p.stat().st_size // 1024} KB")
    media = {".md": "text/markdown", ".json": "application/json", ".jsonl": "application/x-ndjson",
             ".yaml": "application/yaml", ".yml": "application/yaml", ".html": "text/html"}.get(p.suffix, "text/plain")
    return p.read_text(encoding="utf-8", errors="replace"), media


# ----------------------------------------------------------------- nguồn đặc tả
_FETCH_CACHE: dict[str, tuple[float, bytes]] = {}  # url -> (thời điểm, nội dung): bước xem trước và bước thêm
FETCH_CACHE_TTL_S = 900                             # dùng chung lượt tải (đặc tả nhiều tệp có thể hàng trăm tệp)
FETCH_CACHE_MAX_BYTES = 200 * 1024 * 1024


def fetch_url(url: str) -> tuple[bytes, str]:
    if not re.match(r"^https?://", url or ""):
        raise BenchError(422, "URL không hợp lệ", "URL đặc tả phải bắt đầu bằng http:// hoặc https://")
    hit = _FETCH_CACHE.get(url)
    if hit and time.monotonic() - hit[0] < FETCH_CACHE_TTL_S:
        return hit[1], Path(urlparse(url).path).suffix.lower()
    data, suffix = _download(url)
    if sum(len(v[1]) for v in _FETCH_CACHE.values()) + len(data) > FETCH_CACHE_MAX_BYTES:
        _FETCH_CACHE.clear()
    _FETCH_CACHE[url] = (time.monotonic(), data)
    return data, suffix


def _download(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "SpecLoop/1.0 (+bench import)",
                                               "Accept": "application/json, application/yaml, text/yaml, */*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(MAX_SPEC_BYTES + 1)
    except urllib.error.HTTPError as e:
        hint = (" – kiểm tra lại tên nhánh / đường dẫn tệp; kho riêng tư (private) không tải được, hãy tải tệp về "
                "rồi dùng “Tải tệp lên”") if e.code == 404 and "githubusercontent.com" in url else ""
        raise BenchError(422, "Không tải được đặc tả", f"Máy chủ trả HTTP {e.code} cho {url}{hint}") from e
    except Exception as e:  # noqa: BLE001
        raise BenchError(422, "Không tải được đặc tả", f"{url}: {e}") from e
    if len(data) > MAX_SPEC_BYTES:
        raise BenchError(413, "Đặc tả quá lớn", "Tệp đặc tả vượt 20 MB")
    return data, Path(urlparse(url).path).suffix.lower()


def load_source(spec_url: str | None, spec_text: str | None, filename: str | None) -> tuple[bytes, str]:
    if spec_text and spec_text.strip():
        return spec_text.encode("utf-8"), Path(filename or "").suffix.lower()
    if spec_url and spec_url.strip():
        return fetch_url(spec_import.resolve_spec_url(spec_url))
    raise BenchError(422, "Thiếu đặc tả", "Nhập URL, dán nội dung hoặc tải tệp OpenAPI/Swagger lên")


def _resolved_url(spec_url: str | None, spec_text: str | None) -> str | None:
    """Link thật sự được tải (chỉ khi nguồn là URL); dùng làm gốc để tải các tệp con khi đặc tả chia nhiều tệp."""
    if (spec_text or "").strip() or not (spec_url or "").strip():
        return None
    return spec_import.resolve_spec_url(spec_url)


def _fetch_bytes(url: str) -> bytes:
    return fetch_url(url)[0]


def preview(spec_url: str | None, spec_text: str | None, filename: str | None) -> dict:
    raw, _suffix = load_source(spec_url, spec_text, filename)
    resolved = _resolved_url(spec_url, spec_text)
    try:
        spec, notes, src_version, errors = spec_import.prepare_spec(raw, source_url=resolved, fetch=_fetch_bytes)
    except BenchError:
        raise
    except ValueError as e:
        raise BenchError(422, "Không đọc được đặc tả", str(e)) from e
    info = spec.get("info") or {}
    sug = spec_import.suggest_meta(spec)
    if spec_url and not sug["docs_url"]:
        sug["docs_url"] = ""
    sug["exists"] = (root() / "apis" / sug["id"]).exists()
    return {
        "source_version": src_version, "title": info.get("title"), "version": info.get("version"),
        "operations": spec_import.count_operations(spec), "paths": len(spec.get("paths") or {}),
        "servers": [s.get("url") for s in spec.get("servers") or [] if isinstance(s, dict)],
        "security_schemes": list(((spec.get("components") or {}).get("securitySchemes") or {}).keys()),
        "tags": [t.get("name") for t in spec.get("tags") or [] if isinstance(t, dict)][:30],
        "size_bytes": len(raw), "valid": not errors, "errors": errors, "normalization": notes, "suggested": sug,
        "resolved_url": resolved,
    }


# ----------------------------------------------------------------- ghi
def create(body: dict) -> dict:
    raw, suffix = load_source(body.get("spec_url"), body.get("spec_text"), body.get("filename"))
    auth = body.get("auth") or {}
    if "in_" in auth:
        auth["in"] = auth.pop("in_")
    cfg = {**{k: v for k, v in body.items() if k not in ("spec_text", "doc_original_text", "doc_original_filename")},
           "auth": auth, "added_via": "web",
           "spec_url": _resolved_url(body.get("spec_url"), body.get("spec_text"))}
    if cfg.get("spec_url") is None and body.get("filename"):
        cfg["spec_url"] = f"tải lên trực tiếp ({body['filename']})"
    doc = None
    if (body.get("doc_original_text") or "").strip():
        doc = (body["doc_original_text"].encode("utf-8"), Path(body.get("doc_original_filename") or "x.md").suffix.lower())
    with _LOCK:
        try:
            return spec_import.create_api(root(), cfg, raw, suffix, doc_original=doc,
                                          source_url=_resolved_url(body.get("spec_url"), body.get("spec_text")),
                                          fetch=_fetch_bytes)
        except BenchError:
            raise
        except ValueError as e:
            status = 409 if "đã có API" in str(e) else 422
            raise BenchError(status, "Không thêm được API", str(e)) from e


def delete(api_id: str) -> None:
    d = _api_dir(api_id)
    if _meta(d).get("added_via") != "web":
        raise BenchError(403, "Không được xóa", "Chỉ xóa được API thêm từ giao diện web; API gốc của bộ dữ liệu "
                                                 "chỉ sửa/xóa thủ công trong thư mục SpecLoop-Bench.")
    with _LOCK:
        spec_import.delete_api(root(), api_id)


def _key_from_dotenv(meta: dict) -> None:
    """Khóa API (tên biến ghi ở auth.env_var) chưa có trong biến môi trường -> lấy từ tệp .env ở gốc repo, để người
    dùng chỉ cần ghi khóa vào .env như khóa LLM. Khóa vẫn không bao giờ ghi vào bộ dữ liệu."""
    var = ((meta.get("environment") or {}).get("auth") or {}).get("env_var") or ""
    if var and not os.environ.get(var) and DOTENV_PATH.exists():
        val = dotenv_values(DOTENV_PATH).get(var)
        if val:
            os.environ[var] = val


def check_connectivity_of(api_id: str) -> dict:
    d = _api_dir(api_id)
    meta = _meta(d)
    _key_from_dotenv(meta)
    res = check_connectivity.probe(meta)
    ok = isinstance(res.get("status"), int) and 200 <= res["status"] < 300
    if ok and not (meta.get("environment") or {}).get("connectivity_checked"):
        with _LOCK:
            mp = d / "meta.yaml"
            text = mp.read_text(encoding="utf-8").replace("connectivity_checked: false", "connectivity_checked: true")
            mp.write_text(text, encoding="utf-8", newline="\n")
            build_dataset.update_manifest(root(), [api_id], verbose=False)
    return {"ok": ok, **res}
