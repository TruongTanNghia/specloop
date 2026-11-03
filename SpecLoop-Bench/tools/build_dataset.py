"""Dựng lại toàn bộ (hoặc một) API trong bộ dữ liệu từ ground truth + meta.yaml:
  - kiểm tra hợp lệ OAS 3.0.3
  - ground_truth/facts.jsonl (và behavior_facts.jsonl nếu có đặc tả hành vi)
  - docs/rendered.md; docs/ablated.md + ground_truth/ablation.json nếu meta.docs.make_ablated = true
  - manifest.json, stats.csv ở thư mục gốc

Dùng:  python tools/build_dataset.py            # tất cả
       python tools/build_dataset.py --api petstore3
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_facts import PROBEABLE, extract, summarize, write_jsonl  # noqa: E402
from oas_utils import load_spec, sha256_file, validate_spec, write_text_lf  # noqa: E402
from render_docs import render  # noqa: E402

DATASET_NAME = "SpecLoop-Bench"
DATASET_VERSION = "0.1.0"
ABLATION_RATIO = 0.4


def select_ablation(facts, api_id, ratio=ABLATION_RATIO):
    cands = [f for f in facts if f["category"] == "constraint" and f["keyword"] in PROBEABLE
             and (f["location"] or "").split(":")[0] in ("query", "path", "header", "body", "operation")
             and not (f["keyword"] == "required" and (f["location"] or "").startswith("path:"))
             and f["location"] != "body"]
    seed = int(hashlib.sha1(api_id.encode()).hexdigest()[:8], 16)
    rnd = random.Random(seed)
    k = max(1, round(len(cands) * ratio)) if cands else 0
    chosen = rnd.sample(cands, k) if k else []
    # ẩn theo cặp: minimum <-> exclusiveMinimum, maximum <-> exclusiveMaximum (tránh đổi nghĩa ràng buộc)
    by_key = {f["key"]: f for f in facts}
    pair = {"minimum": "exclusiveMinimum", "exclusiveMinimum": "minimum",
            "maximum": "exclusiveMaximum", "exclusiveMaximum": "maximum"}
    for f in list(chosen):
        if f["keyword"] in pair:
            k2 = f["key"].rsplit("|", 1)[0] + "|" + pair[f["keyword"]]
            if k2 in by_key and by_key[k2] not in chosen:
                chosen.append(by_key[k2])
    chosen = sorted(chosen, key=lambda f: f["key"])
    return {"seed": seed, "ratio": ratio, "n_candidates": len(cands), "n_hidden": len(chosen),
            "hidden_keys": [f["key"] for f in chosen], "hidden_fact_ids": [f["id"] for f in chosen],
            "note": "Các ràng buộc này bị ẩn trong docs/ablated.md (kể cả câu mô tả có nhắc tới giá trị). "
                    "Dùng để đo 'constraint recovery' nhờ phản hồi kiểm thử."}


def word_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split()) if path.exists() else 0


def build_api(api_dir: Path, verbose=True, root: Path = ROOT) -> dict:
    meta = yaml.safe_load((api_dir / "meta.yaml").read_text(encoding="utf-8"))
    api_id = meta["id"]
    gt_path = api_dir / "ground_truth" / "openapi.yaml"
    spec = load_spec(gt_path)
    errors = validate_spec(spec)
    if errors:
        raise SystemExit(f"[{api_id}] ground truth KHÔNG hợp lệ: {errors}")
    facts = extract(spec)
    write_jsonl(facts, api_dir / "ground_truth" / "facts.jsonl")
    (api_dir / "docs").mkdir(exist_ok=True)
    text, _ = render(spec)
    write_text_lf(api_dir / "docs" / "rendered.md", text)
    abl = None
    if (meta.get("docs") or {}).get("make_ablated"):
        abl = select_ablation(facts, api_id)
        text_a, used = render(spec, abl["hidden_keys"], title_suffix=" (ablated)")
        missing = set(abl["hidden_keys"]) - used
        if missing:
            print(f"  ! [{api_id}] {len(missing)} khóa ẩn không xuất hiện khi render (bỏ qua)")
        write_text_lf(api_dir / "docs" / "ablated.md", text_a)
        write_text_lf(api_dir / "ground_truth" / "ablation.json", json.dumps(abl, ensure_ascii=False, indent=1))
    beh_path = api_dir / "ground_truth" / "behavior_openapi.yaml"
    beh_facts = None
    if beh_path.exists():
        beh = load_spec(beh_path)
        berr = validate_spec(beh)
        if berr:
            raise SystemExit(f"[{api_id}] behavior_openapi.yaml KHÔNG hợp lệ: {berr}")
        beh_facts = extract(beh)
        write_jsonl(beh_facts, api_dir / "ground_truth" / "behavior_facts.jsonl")
    s = summarize(facts)
    n_disc = 0
    dpath = api_dir / "ground_truth" / "discrepancies.json"
    if dpath.exists():
        n_disc = len(json.loads(dpath.read_text(encoding="utf-8"))["discrepancies"])
    stats = {
        "id": api_id, "name": meta["name"], "group": meta["group"],
        "environment": meta["environment"]["type"], "test_scope": meta["environment"]["test_scope"],
        "auth": (meta["environment"].get("auth") or {}).get("type", "none"),
        "operations": s.get("endpoint", 0), "parameters": s.get("parameter", 0),
        "request_fields": s.get("request_field", 0), "responses": s.get("response", 0),
        "response_fields": s.get("response_field", 0), "constraints": s.get("constraint", 0),
        "constraints_no_type": s.get("constraint", 0) - s["constraint_by_keyword"].get("type", 0),
        "facts_total": len(facts),
        "doc_original_words": word_count(api_dir / "docs" / "original.md"),
        "doc_rendered_words": word_count(api_dir / "docs" / "rendered.md"),
        "ablated_hidden": abl["n_hidden"] if abl else 0,
        "behavior_gt": meta["ground_truth"].get("behavior_status", "pending"),
        "behavior_facts": len(beh_facts) if beh_facts else 0,
        "seeded_discrepancies": n_disc,
        "rq_scope": ",".join(meta.get("rq_scope", [])),
        "constraint_by_keyword": s["constraint_by_keyword"],
    }
    files = {}
    for p in sorted(api_dir.rglob("*")):
        if p.is_file() and p.suffix != ".pyc" and not any(
                part == "__pycache__" or part.startswith(".") for part in p.relative_to(api_dir).parts):
            files[p.relative_to(root).as_posix()] = sha256_file(p)  # luôn dùng "/" để manifest giống nhau mọi hệ điều hành
    if verbose:
        print(f"  ✓ {api_id:<20} ops={stats['operations']:<4} params={stats['parameters']:<4} "
              f"constraints={stats['constraints']:<5} facts={stats['facts_total']}")
    return {"meta": meta, "stats": stats, "files": files}


def update_manifest(root: Path = ROOT, apis: list[str] | None = None, verbose: bool = True) -> dict:
    """Dựng lại các API trong `apis` (None = tất cả, [] = không dựng, chỉ gỡ API đã xóa) rồi ghi manifest.json,
    stats.csv. Trả về manifest mới."""
    root = Path(root)
    api_dirs = sorted(d for d in (root / "apis").iterdir() if d.is_dir() and not d.name.startswith("_"))
    man_path = root / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    entries = {e["id"]: e for e in manifest.get("apis", [])}
    if verbose:
        print(f"Dựng {DATASET_NAME} v{DATASET_VERSION}:")
    for d in api_dirs:
        if apis is not None and d.name not in apis:
            continue
        r = build_api(d, verbose, root)
        m = r["meta"]
        entries[m["id"]] = {"id": m["id"], "name": m["name"], "group": m["group"], "path": f"apis/{d.name}",
                            "stats": r["stats"], "files": r["files"]}
    entries = {k: v for k, v in entries.items() if (root / "apis" / k / "meta.yaml").exists()}
    manifest = {"name": DATASET_NAME, "version": DATASET_VERSION,
                "built_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "openapi_target": "3.0.3", "n_apis": len(entries),
                "apis": [entries[k] for k in sorted(entries)]}
    write_text_lf(man_path, json.dumps(manifest, ensure_ascii=False, indent=1))
    cols = ["id", "name", "group", "environment", "test_scope", "auth", "operations", "parameters", "request_fields",
            "responses", "response_fields", "constraints", "constraints_no_type", "facts_total", "doc_original_words",
            "doc_rendered_words", "ablated_hidden", "behavior_gt", "behavior_facts", "seeded_discrepancies", "rq_scope"]
    with open(root / "stats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for e in manifest["apis"]:
            w.writerow(e["stats"])
        if manifest["apis"]:
            tot = {c: sum(e["stats"][c] for e in manifest["apis"]) for c in cols
                   if isinstance(manifest["apis"][0]["stats"][c], int)}
            w.writerow({"id": "TOTAL", **tot})
    if verbose:
        print(f"Đã cập nhật manifest.json ({len(entries)} API) và stats.csv")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api")
    a = ap.parse_args()
    update_manifest(ROOT, [a.api] if a.api else None)


if __name__ == "__main__":
    main()
