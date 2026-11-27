"""Thêm một REST API mới vào bộ dữ liệu (dòng lệnh). Giao diện web SpecLoop có trang “Bộ dữ liệu” làm cùng việc.

Ví dụ:
  python tools/add_api.py --id httpbin --name "httpbin" --group B \
      --spec https://raw.githubusercontent.com/<...>/openapi.yaml \
      --base-url https://httpbin.org --env public --scope read-only \
      --doc-original duong_dan/trang_tai_lieu.html --source-url https://httpbin.org \
      --license "ISC" --ablated

Script sẽ:
  1. đọc đặc tả (OpenAPI 3.0/3.1 hoặc Swagger 2.0), chuẩn hóa về OpenAPI 3.0.3 và sửa các lỗi hợp lệ hay gặp
     (tools/spec_import.py) – mọi thay đổi ghi vào meta.yaml -> source.normalization
  2. tạo apis/<id>/ (source/, docs/, ground_truth/), sao chép tài liệu gốc (nếu có)
  3. sinh meta.yaml (các trường chưa biết ghi TODO), dựng facts/tài liệu render, cập nhật manifest, kiểm tra
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from spec_import import create_api, resolve_spec_url  # noqa: E402


def fetch(src: str) -> tuple[bytes, str]:
    if re.match(r"^https?://", src):
        src = resolve_spec_url(src)
        req = urllib.request.Request(src, headers={"User-Agent": "SpecLoop-Bench/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read(), Path(src.split("?")[0]).suffix or ".txt"
    p = Path(src)
    return p.read_bytes(), p.suffix or ".txt"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="chữ thường, số, gạch nối; ví dụ my-api")
    ap.add_argument("--name", required=True)
    ap.add_argument("--group", choices=["A", "B"], required=True, help="A: tự triển khai/kiểm soát; B: công khai")
    ap.add_argument("--spec", required=True, help="đường dẫn hoặc URL tới OpenAPI 3.x / Swagger 2.0 (YAML/JSON)")
    ap.add_argument("--base-url", help="URL gốc dùng để kiểm thử (ghi đè servers[0].url)")
    ap.add_argument("--env", choices=["local-docker", "public", "offline"], default="public")
    ap.add_argument("--scope", choices=["full", "read-only", "none"], default="read-only")
    ap.add_argument("--auth", choices=["none", "apiKey", "bearer", "oauth2"], default="none")
    ap.add_argument("--auth-env", help="tên biến môi trường chứa khóa, ví dụ OMDB_API_KEY")
    ap.add_argument("--doc-original", help="tài liệu gốc viết cho con người (HTML/MD/TXT) – đường dẫn hoặc URL")
    ap.add_argument("--source-url", default="TODO")
    ap.add_argument("--docs-url", default="TODO")
    ap.add_argument("--license", default="TODO")
    ap.add_argument("--ablated", action="store_true", help="sinh thêm biến thể tài liệu lược ràng buộc")
    ap.add_argument("--force", action="store_true", help="ghi đè nếu thư mục đã tồn tại")
    a = ap.parse_args()

    raw, suffix = fetch(a.spec)
    doc = None
    if a.doc_original:
        draw, dsuf = fetch(a.doc_original)
        doc = (draw, dsuf)
    cfg = {"id": a.id, "name": a.name, "group": a.group, "env": a.env, "scope": a.scope, "base_url": a.base_url,
           "auth": {"type": a.auth, "env_var": a.auth_env}, "license": a.license, "homepage": a.source_url,
           "docs_url": a.docs_url, "make_ablated": a.ablated, "added_via": "cli",
           "spec_url": resolve_spec_url(a.spec) if a.spec.startswith("http") else None}
    try:
        res = create_api(ROOT, cfg, raw, suffix, doc_original=doc, overwrite=a.force,
                         source_url=cfg["spec_url"], fetch=lambda u: fetch(u)[0])
    except ValueError as e:
        sys.exit(f"Không thêm được: {e}")
    s = res["stats"]
    print(f"Đã tạo {res['path']}: {s['operations']} operation, {s['constraints_no_type']} ràng buộc, {s['facts_total']} facts")
    for n in res["normalization"]:
        print("  chuẩn hóa:", n)
    v = res["validation"]
    print("Kiểm tra:", "ĐẠT" if v["ok"] else "LỖI")
    for e in v["errors"]:
        print("  LỖI:", e)
    for w in v["warnings"]:
        print("  lưu ý:", w)
    print("\nViệc còn lại: mở meta.yaml điền các mục TODO (mô tả, giấy phép, probe kết nối), "
          "sau đó chạy lại: python tools/build_dataset.py --api", a.id)


if __name__ == "__main__":
    main()
