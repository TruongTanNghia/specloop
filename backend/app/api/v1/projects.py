"""Dự án, tài liệu, phân đoạn."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Chunk, Document, Finding, Project, Proposal, SpecVersion, TestRun
from ...schemas.api import (
    ChunkMerge,
    ChunkOut,
    ChunkSplit,
    ChunkUpdate,
    DocumentIn,
    DocumentOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from ...security import decrypt_json, encrypt_json
from ...services.ingestion.fetcher import FetchError
from ...services.ingestion.segmenter import estimate_tokens
from ...services.ingestion.service import ingest, save_chunks
from ..deps import Problem, get_or_404

router = APIRouter(tags=["projects"])


def project_out(db: Session, p: Project) -> ProjectOut:
    out = ProjectOut.model_validate(p)
    out.has_secret = bool(decrypt_json(p.secrets_enc).get("auth"))
    versions = db.scalar(select(func.count()).select_from(SpecVersion).where(SpecVersion.project_id == p.id))
    docs = db.scalar(select(func.count()).select_from(Document).where(Document.project_id == p.id))
    open_findings = db.scalar(
        select(func.count()).select_from(Finding).join(TestRun, Finding.test_run_id == TestRun.id)
        .join(SpecVersion, TestRun.spec_version_id == SpecVersion.id)
        .where(SpecVersion.project_id == p.id, Finding.status == "open"))
    pending = db.scalar(
        select(func.count()).select_from(Proposal).join(SpecVersion, Proposal.spec_version_id == SpecVersion.id)
        .where(SpecVersion.project_id == p.id, Proposal.status == "pending"))
    latest = db.scalars(select(SpecVersion).where(SpecVersion.project_id == p.id)
                        .order_by(SpecVersion.version_no.desc())).first()
    out.stats = {"documents": docs, "versions": versions, "open_findings": open_findings,
                 "pending_proposals": pending, "latest_version_id": latest.id if latest else None,
                 "latest_version_label": latest.label if latest else None}
    return out


def _apply_secret_fields(p: Project, body: ProjectCreate | ProjectUpdate) -> None:
    secrets = decrypt_json(p.secrets_enc)
    changed = False
    if body.auth_secret is not None:
        secrets["auth"] = body.auth_secret or None
        changed = True
    if body.reset_headers is not None:
        secrets["reset_headers"] = body.reset_headers
        changed = True
    if changed:
        p.secrets_enc = encrypt_json(secrets)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(name=body.name, description=body.description, base_url=body.base_url,
                auth_config=(body.auth.model_dump() if body.auth else {"type": "none"}),
                allowed_hosts=body.allowed_hosts, mode=body.mode, policy=body.policy,
                reset_config=body.reset.model_dump() if body.reset else None)
    _apply_secret_fields(p, body)
    db.add(p)
    db.commit()
    db.refresh(p)
    return project_out(db, p)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return [project_out(db, p) for p in db.scalars(select(Project).order_by(Project.id.desc()))]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    return project_out(db, get_or_404(db, Project, project_id, "Dự án"))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = get_or_404(db, Project, project_id, "Dự án")
    data = body.model_dump(exclude_unset=True)
    for k in ("name", "description", "base_url", "allowed_hosts", "mode", "policy"):
        if k in data:
            setattr(p, k, data[k])
    if "auth" in data:
        p.auth_config = body.auth.model_dump() if body.auth else {"type": "none"}
    if "reset" in data:
        p.reset_config = body.reset.model_dump() if body.reset else None
    _apply_secret_fields(p, body)
    db.commit()
    db.refresh(p)
    return project_out(db, p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Project, project_id, "Dự án")
    db.delete(p)
    db.commit()


# ------------------------------------------------------------------ tài liệu
def doc_out(d: Document, with_md: bool = False) -> DocumentOut:
    out = DocumentOut.model_validate(d)
    out.chunk_count = len(d.chunks)
    if with_md:
        out.markdown = d.markdown
    return out


@router.post("/projects/{project_id}/documents", response_model=DocumentOut, status_code=201)
async def add_document(project_id: int, request: Request, db: Session = Depends(get_db)):
    """Nạp tài liệu: multipart (field `file`) hoặc JSON {url} | {text, format?}."""
    get_or_404(db, Project, project_id, "Dự án")
    ctype = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in ctype:
            form = await request.form()
            f = form.get("file")
            if f is not None and hasattr(f, "read"):
                data = await f.read()
                if len(data) > 10 * 1024 * 1024:
                    raise Problem(413, "Tệp quá lớn", "Giới hạn 10 MB")
                doc = ingest(db, project_id, data=data, filename=f.filename, content_type=f.content_type)
            elif form.get("url"):
                doc = ingest(db, project_id, url=str(form.get("url")))
            elif form.get("text"):
                doc = ingest(db, project_id, text=str(form.get("text")), fmt=form.get("format") or None)
            else:
                raise Problem(422, "Thiếu dữ liệu", "Cần tệp, url hoặc text")
        else:
            try:
                body = DocumentIn.model_validate(json.loads(await request.body() or b"{}"))
            except Exception as e:  # noqa: BLE001
                raise Problem(422, "Dữ liệu không hợp lệ", str(e)[:300]) from e
            if body.url:
                doc = ingest(db, project_id, url=body.url)
            elif body.text:
                doc = ingest(db, project_id, text=body.text, fmt=body.format, filename=body.filename)
            else:
                raise Problem(422, "Thiếu dữ liệu", "Cần url hoặc text")
    except FetchError as e:
        raise Problem(400, "Không tải được tài liệu", str(e)) from e
    db.commit()
    db.refresh(doc)
    return doc_out(doc)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(project_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id, "Dự án")
    return [doc_out(d) for d in db.scalars(select(Document).where(Document.project_id == project_id)
                                           .order_by(Document.id.desc()))]


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    return doc_out(get_or_404(db, Document, document_id, "Tài liệu"), with_md=True)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Document, document_id, "Tài liệu"))
    db.commit()


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
def list_chunks(document_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Document, document_id, "Tài liệu")
    return list(db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.order)))


@router.post("/documents/{document_id}/resegment", response_model=list[ChunkOut])
def resegment(document_id: int, db: Session = Depends(get_db)):
    doc = get_or_404(db, Document, document_id, "Tài liệu")
    chunks = save_chunks(db, doc)
    db.commit()
    return chunks


@router.patch("/chunks/{chunk_id}", response_model=ChunkOut)
def update_chunk(chunk_id: int, body: ChunkUpdate, db: Session = Depends(get_db)):
    c = get_or_404(db, Chunk, chunk_id, "Phân đoạn")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    if "text" in data:
        c.token_count = estimate_tokens(c.text)
    db.commit()
    db.refresh(c)
    return c


@router.post("/documents/{document_id}/chunks/merge", response_model=list[ChunkOut])
def merge_chunks(document_id: int, body: ChunkMerge, db: Session = Depends(get_db)):
    get_or_404(db, Document, document_id, "Tài liệu")
    chunks = [get_or_404(db, Chunk, i, "Phân đoạn") for i in body.chunk_ids]
    if any(c.document_id != document_id for c in chunks):
        raise Problem(422, "Phân đoạn không thuộc tài liệu")
    chunks.sort(key=lambda c: c.order)
    first = chunks[0]
    first.text = "\n".join(c.text.rstrip("\n") for c in chunks) + "\n"
    first.span_end = max(c.span_end for c in chunks)
    first.token_count = estimate_tokens(first.text)
    first.operation_hint = first.operation_hint or next((c.operation_hint for c in chunks if c.operation_hint), None)
    for c in chunks[1:]:
        db.delete(c)
    db.flush()
    _renumber(db, document_id)
    db.commit()
    return list(db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.order)))


@router.post("/chunks/{chunk_id}/split", response_model=list[ChunkOut])
def split_chunk(chunk_id: int, body: ChunkSplit, db: Session = Depends(get_db)):
    c = get_or_404(db, Chunk, chunk_id, "Phân đoạn")
    if body.offset >= len(c.text):
        raise Problem(422, "Vị trí tách không hợp lệ")
    second_text = c.text[body.offset:]
    new = Chunk(document_id=c.document_id, order=c.order + 1, title=f"{c.title} (tách)", operation_hint=None,
                text=second_text, token_count=estimate_tokens(second_text), span_start=c.span_start + body.offset,
                span_end=c.span_end, is_global=c.is_global, heading_path=c.heading_path)
    c.text = c.text[:body.offset]
    c.span_end = c.span_start + body.offset
    c.token_count = estimate_tokens(c.text)
    for other in db.scalars(select(Chunk).where(Chunk.document_id == c.document_id, Chunk.order > c.order)):
        other.order += 1
    db.add(new)
    db.commit()
    return list(db.scalars(select(Chunk).where(Chunk.document_id == c.document_id).order_by(Chunk.order)))


@router.delete("/chunks/{chunk_id}", status_code=204)
def delete_chunk(chunk_id: int, db: Session = Depends(get_db)):
    c = get_or_404(db, Chunk, chunk_id, "Phân đoạn")
    doc_id = c.document_id
    db.delete(c)
    db.flush()
    _renumber(db, doc_id)
    db.commit()


def _renumber(db: Session, document_id: int) -> None:
    for i, c in enumerate(db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.order))):
        c.order = i
