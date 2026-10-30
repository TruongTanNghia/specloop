"""Áp dụng đề xuất → phiên bản mới; vòng lặp tinh chỉnh tự động (TECH_SPEC 5.5.8)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import session_scope
from ...jobs import JobContext
from ...models import Proposal, SpecVersion, TestRun, utcnow
from ..evaluation.validator import validate_all
from .core import apply_patch, create_version, refined_label


class ApplyError(Exception):
    pass


def apply_proposals(db: Session, spec_id: int, proposal_ids: list[int] | None, *, note: str | None = None,
                    reviewer: str = "user") -> tuple[SpecVersion, list[str]]:
    parent = db.get(SpecVersion, spec_id)
    if parent is None:
        raise ApplyError("Không tìm thấy phiên bản")
    q = select(Proposal).where(Proposal.spec_version_id == spec_id)
    if proposal_ids:
        q = q.where(Proposal.id.in_(proposal_ids))
    else:
        q = q.where(Proposal.status.in_(("accepted", "edited")))
    props = list(db.scalars(q.order_by(Proposal.id)))
    if proposal_ids and len(props) != len(set(proposal_ids)):
        raise ApplyError("Có đề xuất không thuộc phiên bản này")
    props = [p for p in props if p.status in ("accepted", "edited", "pending")]
    if not props:
        raise ApplyError("Không có đề xuất nào được chấp nhận để áp dụng")
    ops: list[dict] = []
    for p in props:
        ops += p.json_patch
    content, warnings = apply_patch(parent.content, ops)
    errors = validate_all(content)
    if errors:
        warnings.append(f"Phiên bản mới có {len(errors)} lỗi validate: {errors[0]['message']}")
    v = create_version(db, parent.project_id, content, label=refined_label(db, parent), parent=parent, patch=ops,
                       note=note or f"Áp dụng {len(props)} đề xuất: " + ", ".join(f"#{p.id}" for p in props),
                       created_by=reviewer)
    for p in props:
        if p.status == "pending":
            p.reviewed_by = reviewer
            p.reviewed_at = utcnow()
        p.status = "applied"
        p.applied_version_id = v.id
    return v, warnings


def run_refine_loop(spec_id: int, *, max_iter: int, auto_accept_threshold: float, min_confidence: float,
                    test_config: dict, ctx: JobContext | None = None) -> dict:
    from ..testing.runner import run_test

    current = spec_id
    iterations = []
    stop_reason = f"đạt số vòng tối đa K={max_iter}"
    for k in range(1, max_iter + 1):
        if ctx:
            ctx.update(force=True, stage="refine", iteration=k, max_iter=max_iter, spec_id=current)
            ctx.check_cancel()
        with session_scope() as db:
            tr = TestRun(spec_version_id=current, config=test_config, status="queued",
                         job_id=ctx.job_id if ctx else None)
            db.add(tr)
            db.flush()
            tr_id = tr.id
        run_test(tr_id, ctx)
        with session_scope() as db:
            props = list(db.scalars(select(Proposal).where(Proposal.spec_version_id == current,
                                                           Proposal.status == "pending")))
            significant = [p for p in props if p.confidence >= min_confidence]
            auto = [p for p in significant if p.confidence >= auto_accept_threshold and not p.doc_conflict]
            info = {"iteration": k, "spec_id": current, "test_run_id": tr_id, "proposals": len(props),
                    "significant": len(significant), "auto_accepted": [p.id for p in auto],
                    "needs_review": [p.id for p in significant if p not in auto]}
            if not significant:
                iterations.append(info)
                stop_reason = "hội tụ: không còn đề xuất mới có độ tin cậy ≥ %.2f" % min_confidence
                break
            if not auto:
                iterations.append(info)
                stop_reason = "còn đề xuất cần người duyệt (dưới ngưỡng tự chấp nhận hoặc mâu thuẫn tài liệu)"
                break
            for p in auto:
                p.status = "accepted"
                p.reviewed_by = "auto"
                p.reviewed_at = utcnow()
            db.flush()
            v, warnings = apply_proposals(db, current, [p.id for p in auto], reviewer="auto",
                                          note=f"Vòng lặp tự động – vòng {k}")
            info["new_spec_id"] = v.id
            info["warnings"] = warnings
            iterations.append(info)
            current = v.id
    return {"final_spec_id": current, "iterations": iterations, "stop_reason": stop_reason}
