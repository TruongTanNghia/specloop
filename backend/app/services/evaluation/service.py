"""M3 – đánh giá đặc tả: L1 parse, L2 validate, L3 lint, L4 grounding, L5 so GT (atomic facts của SpecLoop-Bench)."""
from __future__ import annotations

import re

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...bench import bench_evaluate, bench_facts
from ...models import Document, Evaluation, Evidence, GroundTruth, SpecVersion
from .validator import count_operations, lint, validate_all

GROUNDING_THRESHOLD = 90


def grounding(db: Session, version: SpecVersion) -> dict:
    """L4: mỗi trích dẫn phải tìm thấy trong tài liệu (rapidfuzz.partial_ratio ≥ 90)."""
    evs = list(db.scalars(select(Evidence).where(Evidence.spec_version_id == version.id)))
    if not evs:
        return {"applicable": False, "note": "Phiên bản không có bằng chứng tài liệu (nhập sẵn/sửa tay)"}
    doc = db.scalars(select(Document).where(Document.project_id == version.project_id)
                     .order_by(Document.id.desc())).first()
    text = doc.markdown if doc else ""
    norm_text = " ".join(text.split())
    flagged, scores = [], []
    for ev in evs:
        q = " ".join((ev.quote or "").split())
        if not q:
            score = 0.0
        elif q in norm_text:
            score = 100.0
        else:
            score = float(fuzz.partial_ratio(q, norm_text))
        ev.match_score = round(score, 1)
        scores.append(score)
        if score < GROUNDING_THRESHOLD:
            flagged.append({"pointer": ev.json_pointer, "quote": ev.quote, "score": round(score, 1)})
    pointers = {ev.json_pointer for ev in evs}
    elements = _elements(version.content)
    ungrounded = [p for p in elements if not any(q == p or q.startswith(p + "/") or p.startswith(q + "/")
                                                 for q in pointers)]
    return {
        "applicable": True, "evidence": len(evs), "grounded": len(evs) - len(flagged),
        "grounded_rate": round((len(evs) - len(flagged)) / len(evs), 4),
        "suspected_hallucination": flagged[:200], "elements": len(elements),
        "elements_without_evidence": ungrounded[:200], "elements_without_evidence_count": len(ungrounded),
        "mean_score": round(sum(scores) / len(scores), 2),
    }


def _elements(spec: dict) -> list[str]:
    """Pointer của các phần tử cần có căn cứ: tham số, response, thuộc tính, ràng buộc."""
    out: list[str] = []
    kws = ("minimum", "maximum", "minLength", "maxLength", "pattern", "enum", "format", "minItems", "maxItems",
           "default", "nullable", "exclusiveMinimum", "exclusiveMaximum")

    def walk(node, p):
        if isinstance(node, dict):
            for k, v in node.items():
                kp = f"{p}/{str(k).replace('~', '~0').replace('/', '~1')}"
                if k in kws and not isinstance(v, dict):
                    out.append(kp)
                walk(v, kp)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{p}/{i}")

    for path, item in (spec.get("paths") or {}).items():
        base = "/paths/" + path.replace("~", "~0").replace("/", "~1")
        for m, op in (item or {}).items():
            if not isinstance(op, dict):
                continue
            for i, _ in enumerate(op.get("parameters") or []):
                out.append(f"{base}/{m}/parameters/{i}")
            for st in op.get("responses") or {}:
                out.append(f"{base}/{m}/responses/{st}")
            walk(op, f"{base}/{m}")
    walk((spec.get("components") or {}).get("schemas") or {}, "/components/schemas")
    return sorted(set(out))


def static_report(db: Session, version: SpecVersion) -> dict:
    spec = version.content
    errors = validate_all(spec)
    issues = lint(spec)
    n_ops = count_operations(spec)
    return {
        "L1_parse": {"ok": isinstance(spec, dict)},
        "L2_valid": {"ok": not errors, "errors": errors},
        "L3_lint": {"issues": issues, "count": len(issues), "density": round(len(issues) / n_ops, 3) if n_ops else 0},
        "L4_grounding": grounding(db, version),
        "operations": n_ops,
    }


def compare_with_gt(spec: dict, gt: dict, doc_text: str | None = None) -> dict:
    gt_facts = bench_facts.extract(gt)
    pr_facts = bench_facts.extract(spec)
    full = bench_evaluate.compare(gt_facts, pr_facts)
    kws = {f["keyword"] for f in gt_facts + pr_facts if f["category"] == "constraint"} - {"type"}
    no_type = bench_evaluate.compare(gt_facts, pr_facts, kws)
    out = {
        "micro": full["micro"], "by_category": full["by_category"],
        "constraint_by_keyword": full["constraint_by_keyword"],
        "constraint_no_type": no_type["by_category"]["constraint"],
        "n_gt_facts": len(gt_facts), "n_pred_facts": len(pr_facts),
    }
    if doc_text is not None and pr_facts:
        low = doc_text.lower()
        fp_keys = set(full["fp"])
        halluc = [k for k in fp_keys if (k.split("|")[3] or "").split(".")[-1].replace("[]", "").lower() not in low]
        out["hallucination_rate"] = round(len(halluc) / len(pr_facts), 4)
        out["hallucinated_examples"] = sorted(halluc)[:30]
    out["omission_rate"] = full["micro"]["omission_rate"]
    details = {"fp": full["fp"], "fn": full["fn"], "wrong_value": full["wrong_value"]}
    return {"metrics": out, "facts": details}


def run_evaluation(db: Session, evaluation: Evaluation) -> dict:
    version = db.get(SpecVersion, evaluation.spec_version_id)
    report = static_report(db, version)
    metrics: dict = {"static": {k: v for k, v in report.items() if k != "L3_lint"},
                     "lint_count": report["L3_lint"]["count"], "lint_density": report["L3_lint"]["density"]}
    facts = None
    if evaluation.ground_truth_id:
        gt = db.get(GroundTruth, evaluation.ground_truth_id)
        doc = db.scalars(select(Document).where(Document.project_id == version.project_id)
                         .order_by(Document.id.desc())).first()
        cmp = compare_with_gt(version.content, gt.content, doc.markdown if doc else None)
        metrics["L5"] = cmp["metrics"]
        metrics["ground_truth_kind"] = gt.kind
        facts = cmp["facts"]
    evaluation.metrics = metrics
    evaluation.facts = facts
    evaluation.lint_issues = report["L3_lint"]["issues"]
    evaluation.status = "succeeded"
    return metrics


def facts_summary(spec: dict) -> dict:
    return bench_facts.summarize(bench_facts.extract(spec))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
