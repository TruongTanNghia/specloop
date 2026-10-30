"""G5 – chạy ma trận thực nghiệm API × mô hình × cấu hình (C0/C1/C2) × lần lặp trên SpecLoop-Bench.

C0: chỉ LLM (phiên bản generated). C1: + vòng sửa lỗi (repaired). C2: C1 + tinh chỉnh từ phản hồi kiểm thử
(tối đa K vòng, descriptive, tự chấp nhận đề xuất ≥ 0,8 không mâu thuẫn tài liệu).
RQ1 chấm theo GT tài liệu; RQ3 chấm theo GT hành vi khi có.
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import statistics
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import select

from ..bench import BENCH_DIR, api_dir, oas_utils
from ..db import session_scope
from ..jobs import JobContext
from ..models import Project, SpecVersion, TestRun
from .evaluation.service import compare_with_gt
from .evaluation.validator import count_operations, validate_all
from .generation.service import generate
from .ingestion.service import ingest
from .versioning.refine import run_refine_loop

CSV_FIELDS = ["api", "model", "config", "rep", "status", "note", "valid", "operations", "precision", "recall", "f1",
              "constraint_f1_doc", "constraint_p_doc", "constraint_r_doc", "constraint_f1_behavior",
              "f1_behavior", "requests", "input_tokens", "output_tokens", "duration_s", "iterations",
              "spec_version_id", "project_id"]


def list_apis() -> list[dict]:
    out = []
    for d in sorted((BENCH_DIR / "apis").iterdir()):
        if not d.is_dir() or d.name.startswith("_") or not (d / "meta.yaml").exists():
            continue
        meta = yaml.safe_load((d / "meta.yaml").read_text(encoding="utf-8"))
        env = meta.get("environment") or {}
        docs = meta.get("docs") or {}
        gt = meta.get("ground_truth") or {}
        out.append({"id": meta.get("id", d.name), "name": meta.get("name", d.name), "group": meta.get("group"),
                    "test_scope": env.get("test_scope"), "base_url": env.get("base_url"),
                    "docs": {k: v for k, v in docs.items() if isinstance(v, str)},
                    "has_behavior_gt": bool(gt.get("behavior"))})
    return out


def parse_reset(spec: str | None) -> tuple[dict | None, dict]:
    """'POST /__admin/reset, header X-Admin-Token: reset-me' → ({method, url}, headers)."""
    if not spec:
        return None, {}
    m = re.search(r"\b(GET|POST|PUT|DELETE)\s+(\S+?)[,\s]", spec + " ")
    if not m:
        return None, {}
    headers = {}
    h = re.search(r"header\s+([\w-]+)\s*:\s*([^\s,()]+)", spec)
    if h:
        headers[h.group(1)] = h.group(2)
    return {"method": m.group(1), "url": m.group(2)}, headers


def reachable(base_url: str) -> bool:
    try:
        httpx.get(base_url, timeout=5)
        return True
    except httpx.HTTPError:
        return False


def _gt_scores(spec: dict, gt: dict | None) -> dict:
    if gt is None:
        return {}
    m = compare_with_gt(spec, gt)["metrics"]
    c = m["constraint_no_type"]
    return {"precision": m["micro"]["precision"], "recall": m["micro"]["recall"], "f1": m["micro"]["f1"],
            "c_f1": c["f1"], "c_p": c["precision"], "c_r": c["recall"]}


def run_matrix(cfg: dict, out_dir: Path, ctx: JobContext | None = None, log=print) -> dict:
    apis = cfg.get("apis") or ["bookstore-lab"]
    if apis == ["all"] or apis == "all":
        apis = [a["id"] for a in list_apis()]
    models = cfg.get("models") or ["fake"]
    configs = cfg.get("configs") or ["C0", "C1", "C2"]
    repeats = int(cfg.get("repeats") or 3)
    variant = cfg.get("doc_variant") or "original"
    overrides = cfg.get("base_url_overrides") or {}
    max_iter = int(cfg.get("max_iter") or 3)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    total = len(apis) * len(models) * repeats
    done = 0
    t_all = time.perf_counter()
    for api in apis:
        d = api_dir(api)
        meta = yaml.safe_load((d / "meta.yaml").read_text(encoding="utf-8"))
        docs = meta.get("docs") or {}
        doc_rel = docs.get(variant) if isinstance(docs.get(variant), str) else None
        if not doc_rel or not (d / doc_rel).exists():
            doc_rel = docs.get("original") if isinstance(docs.get("original"), str) and (
                d / docs["original"]).exists() else docs.get("rendered")
        doc_text = (d / doc_rel).read_text(encoding="utf-8")
        gtm = meta.get("ground_truth") or {}
        doc_gt = oas_utils.load_spec(d / gtm.get("doc", "ground_truth/openapi.yaml"))
        beh_gt = oas_utils.load_spec(d / gtm["behavior"]) if gtm.get("behavior") and (d / gtm["behavior"]).exists() \
            else None
        env = meta.get("environment") or {}
        scope = env.get("test_scope") or "none"
        # ghi đè: cấu hình > biến môi trường SUT_<API_ID> (vd. SUT_BOOKSTORE_LAB trong docker) > meta.yaml
        base_url = overrides.get(api) or os.environ.get("SUT_" + re.sub(r"\W", "_", api).upper()) or env.get(
            "base_url")
        reset_cfg, reset_headers = parse_reset(env.get("reset"))
        for model in models:
            for rep in range(1, repeats + 1):
                done += 1
                if ctx:
                    ctx.update(force=True, stage="experiment", api=api, model=model, rep=rep, done=done - 1,
                               total=total)
                    ctx.check_cancel()
                log(f"[{done}/{total}] {api} · {model} · lần {rep}")
                rows += _run_one(api, model, rep, configs, doc_text, doc_rel, doc_gt, beh_gt, scope, base_url,
                                 reset_cfg, reset_headers, max_iter, cfg, log)
                _write_csv(rows, out_dir / "results.csv")
    summary = summarize(rows)
    summary["duration_s"] = round(time.perf_counter() - t_all, 1)
    summary["config"] = cfg
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str),
                                          encoding="utf-8")
    (out_dir / "summary.md").write_text(summary_markdown(summary), encoding="utf-8")
    return {"rows": rows, "summary": summary, "output_dir": str(out_dir)}


def _run_one(api, model, rep, configs, doc_text, doc_rel, doc_gt, beh_gt, scope, base_url, reset_cfg, reset_headers,
             max_iter, cfg, log) -> list[dict]:
    from ..security import encrypt_json

    rows = []
    with session_scope() as db:
        p = Project(name=f"[TN] {api} · {model} · lần {rep}", description=f"Thực nghiệm – tài liệu {doc_rel}",
                    base_url=base_url, mode="full" if scope == "full" else "safe", policy="descriptive",
                    reset_config=reset_cfg, allowed_hosts=[])
        if reset_headers:
            p.secrets_enc = encrypt_json({"reset_headers": reset_headers})
        db.add(p)
        db.flush()
        ingest(db, p.id, text=doc_text, filename=Path(doc_rel).name)
        pid = p.id
    base = {"api": api, "model": model, "rep": rep, "project_id": pid}
    try:
        gen = generate(pid, model=model, repair=True, use_cache=bool(cfg.get("use_cache", False)))
    except Exception as e:  # noqa: BLE001
        for c in configs:
            rows.append({**base, "config": c, "status": "failed", "note": f"sinh lỗi: {e}"[:300]})
        return rows
    st = gen["stats"]
    tok = {"input_tokens": st["input_tokens"], "output_tokens": st["output_tokens"]}
    versions = {"C0": gen["generated_version_id"], "C1": gen["version_id"]}

    def score(vid: int, extra: dict) -> dict:
        with session_scope() as db:
            spec = db.get(SpecVersion, vid).content
        s_doc = _gt_scores(spec, doc_gt)
        s_beh = _gt_scores(spec, beh_gt) if beh_gt else {}
        return {**base, **tok, "status": "ok", "valid": int(not validate_all(spec)),
                "operations": count_operations(spec), "precision": s_doc.get("precision"),
                "recall": s_doc.get("recall"), "f1": s_doc.get("f1"), "constraint_f1_doc": s_doc.get("c_f1"),
                "constraint_p_doc": s_doc.get("c_p"), "constraint_r_doc": s_doc.get("c_r"),
                "constraint_f1_behavior": s_beh.get("c_f1"), "f1_behavior": s_beh.get("f1"),
                "spec_version_id": vid, **extra}

    gen_dur = st.get("duration_s", 0)
    if "C0" in configs:
        rows.append(score(versions["C0"], {"config": "C0", "requests": 0, "duration_s": gen_dur, "iterations": 0}))
    if "C1" in configs:
        rows.append(score(versions["C1"], {"config": "C1", "requests": 0, "duration_s": gen_dur, "iterations": 0,
                                           "note": f"{len(st.get('repair_notes') or [])} sửa"}))
    if "C2" in configs:
        if scope in (None, "none"):
            rows.append({**base, "config": "C2", "status": "skipped", "note": "test_scope none"})
        elif not base_url or not reachable(base_url):
            rows.append({**base, "config": "C2", "status": "skipped", "note": f"SUT không truy cập được: {base_url}"})
        else:
            t0 = time.perf_counter()
            test_cfg = {"base_url": base_url, "reset": True, "repeats": 3}
            if cfg.get("max_rps"):
                test_cfg["max_rps"] = cfg["max_rps"]
            try:
                res = run_refine_loop(versions["C1"], max_iter=max_iter, auto_accept_threshold=0.8,
                                      min_confidence=0.5, test_config=test_cfg)
                with session_scope() as db:
                    run_ids = [it["test_run_id"] for it in res["iterations"]]
                    reqs = sum((db.get(TestRun, i).stats or {}).get("requests", 0) for i in run_ids)
                rows.append(score(res["final_spec_id"], {"config": "C2", "requests": reqs,
                                                         "duration_s": round(gen_dur + time.perf_counter() - t0, 2),
                                                         "iterations": len(res["iterations"]),
                                                         "note": res["stop_reason"]}))
            except Exception as e:  # noqa: BLE001
                rows.append({**base, "config": "C2", "status": "failed", "note": f"{type(e).__name__}: {e}"[:300]})
    for r in rows:
        log(f"   {r['config']}: {r.get('status')} F1={r.get('f1')} cF1(doc)={r.get('constraint_f1_doc')} "
            f"cF1(beh)={r.get('constraint_f1_behavior')} req={r.get('requests')}")
    return rows


def _write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _median(vals: list) -> float | None:
    v = [x for x in vals if isinstance(x, (int, float))]
    return round(statistics.median(v), 4) if v else None


def bootstrap_ci(diffs: list[float], n: int = 10000, seed: int = 42) -> tuple[float, float] | None:
    if len(diffs) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)


def wilcoxon(a: list[float], b: list[float]) -> dict:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    out: dict[str, Any] = {"n": len(diffs), "mean_diff": round(statistics.fmean(diffs), 4) if diffs else None,
                           "ci95": bootstrap_ci(diffs)}
    if len([d for d in diffs if d != 0]) < 2:
        out["note"] = "không đủ cặp khác 0 để kiểm định"
        return out
    from scipy import stats

    res = stats.wilcoxon(b, a, zero_method="wilcox")
    p = float(res.pvalue)
    z = float(stats.norm.isf(p / 2)) * (1 if out["mean_diff"] >= 0 else -1)
    out.update({"statistic": float(res.statistic), "p_value": round(p, 5), "effect_r": round(z / len(diffs) ** 0.5, 4)})
    return out


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("status") == "ok"]
    table: dict[str, dict[str, dict]] = {}
    for r in ok:
        key = f"{r['api']}|{r['model']}"
        table.setdefault(key, {}).setdefault(r["config"], []).append(r)
    agg: list[dict] = []
    for key, by_c in table.items():
        api, model = key.split("|")
        for c, rs in sorted(by_c.items()):
            agg.append({"api": api, "model": model, "config": c, "n": len(rs),
                        **{m: _median([x.get(m) for x in rs]) for m in
                           ("f1", "constraint_f1_doc", "constraint_f1_behavior", "requests", "input_tokens",
                            "output_tokens", "duration_s", "valid", "iterations")}})

    def metric(row):  # RQ3: ưu tiên GT hành vi
        return row["constraint_f1_behavior"] if row.get("constraint_f1_behavior") is not None else \
            row.get("constraint_f1_doc")

    tests = {}
    for a_cfg, b_cfg in (("C1", "C2"), ("C0", "C1")):
        pairs = {}
        for r in agg:
            pairs.setdefault((r["api"], r["model"]), {})[r["config"]] = r
        xa, xb = [], []
        for _, v in sorted(pairs.items()):
            if a_cfg in v and b_cfg in v and metric(v[a_cfg]) is not None and metric(v[b_cfg]) is not None:
                xa.append(metric(v[a_cfg]))
                xb.append(metric(v[b_cfg]))
        tests[f"{b_cfg}_vs_{a_cfg}"] = wilcoxon(xa, xb)
    ps = sorted(((k, t["p_value"]) for k, t in tests.items() if "p_value" in t), key=lambda x: x[1])
    m = len(ps)
    running = 0.0
    for i, (k, p) in enumerate(ps):  # Holm
        running = max(running, min(1.0, (m - i) * p))
        tests[k]["p_holm"] = round(running, 5)
    macro = {}
    for c in ("C0", "C1", "C2"):
        rs = [r for r in agg if r["config"] == c]
        if rs:
            macro[c] = {"f1": _mean([r["f1"] for r in rs]), "constraint_f1_doc": _mean([r["constraint_f1_doc"]
                                                                                        for r in rs]),
                        "constraint_f1_behavior": _mean([r["constraint_f1_behavior"] for r in rs])}
    return {"aggregate": agg, "tests": tests, "macro": macro, "rows": len(rows), "ok_rows": len(ok),
            "skipped": [r for r in rows if r.get("status") != "ok"]}


def _mean(vals):
    v = [x for x in vals if isinstance(x, (int, float))]
    return round(statistics.fmean(v), 4) if v else None


def summary_markdown(s: dict) -> str:
    lines = ["# Tổng hợp thực nghiệm SpecLoop", "",
             "Trung vị theo API qua các lần lặp. F1 ràng buộc tính không kèm từ khóa `type`.", "",
             "| API | Mô hình | Cấu hình | n | F1 (GT tài liệu) | F1 ràng buộc (GT tài liệu) | F1 ràng buộc (GT hành vi) "
             "| Request | Token vào | Token ra | Thời gian (s) | Vòng |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in s["aggregate"]:
        lines.append(f"| {r['api']} | {r['model']} | {r['config']} | {r['n']} | {_f(r['f1'])} | "
                     f"{_f(r['constraint_f1_doc'])} | {_f(r['constraint_f1_behavior'])} | {_f(r['requests'], 0)} | "
                     f"{_f(r['input_tokens'], 0)} | {_f(r['output_tokens'], 0)} | {_f(r['duration_s'], 1)} | "
                     f"{_f(r['iterations'], 0)} |")
    lines += ["", "## Trung bình macro theo cấu hình", "", "| Cấu hình | F1 | F1 ràng buộc (tài liệu) | F1 ràng buộc (hành vi) |",
              "|---|---:|---:|---:|"]
    for c, m in s["macro"].items():
        lines.append(f"| {c} | {_f(m['f1'])} | {_f(m['constraint_f1_doc'])} | {_f(m['constraint_f1_behavior'])} |")
    lines += ["", "## Kiểm định Wilcoxon dấu-hạng (ghép cặp theo API × mô hình)", "",
              "| So sánh | n | ΔF1 trung bình | KTC 95% bootstrap | p | p (Holm) | r | Ghi chú |",
              "|---|---:|---:|---|---:|---:|---:|---|"]
    for k, t in s["tests"].items():
        ci = t.get("ci95")
        lines.append(f"| {k.replace('_vs_', ' vs ')} | {t['n']} | {_f(t.get('mean_diff'))} | "
                     f"{f'[{ci[0]}, {ci[1]}]' if ci else '–'} | {_f(t.get('p_value'), 5)} | {_f(t.get('p_holm'), 5)} | "
                     f"{_f(t.get('effect_r'))} | {t.get('note', '')} |")
    if s.get("skipped"):
        lines += ["", "## Lượt bị bỏ qua / lỗi", ""]
        for r in s["skipped"]:
            lines.append(f"- {r['api']} · {r['model']} · {r['config']} · lần {r['rep']}: {r.get('status')} – "
                         f"{r.get('note')}")
    lines += ["", "Do số API nhỏ, kết quả cần diễn giải thận trọng; ưu tiên cỡ hiệu ứng và khoảng tin cậy.", ""]
    return "\n".join(lines)


def _f(v, nd: int = 3) -> str:
    if v is None:
        return "–"
    if nd == 0:
        return f"{v:.0f}"
    return f"{v:.{nd}f}"


def latest_project_versions(project_id: int) -> list[int]:
    with session_scope() as db:
        return [v.id for v in db.scalars(select(SpecVersion).where(SpecVersion.project_id == project_id))]
