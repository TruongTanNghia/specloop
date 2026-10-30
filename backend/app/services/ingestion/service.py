"""Nạp tài liệu vào CSDL: chuẩn hóa Markdown, phân đoạn, lưu chunk."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import Chunk, Document
from .fetcher import detect_type, fetch_url, sha256_bytes, to_markdown
from .segmenter import estimate_tokens, normalize_markdown, segment


def save_chunks(db: Session, doc: Document) -> list[Chunk]:
    for c in list(doc.chunks):
        db.delete(c)
    db.flush()
    chunks = []
    for d in segment(doc.markdown):
        c = Chunk(document_id=doc.id, order=d.order, title=d.title[:500], operation_hint=d.operation_hint,
                  text=d.text, token_count=d.token_count, span_start=d.span_start, span_end=d.span_end,
                  is_global=d.is_global, heading_path=d.heading_path)
        db.add(c)
        chunks.append(c)
    db.flush()
    db.refresh(doc)
    return chunks


def ingest(db: Session, project_id: int, *, data: bytes | None = None, url: str | None = None,
           text: str | None = None, filename: str | None = None, content_type: str | None = None,
           fmt: str | None = None) -> Document:
    source_uri = url
    if url:
        data, content_type = fetch_url(url)
        kind = detect_type(url, content_type, data)
        source_type = "url"
    elif text is not None:
        data = text.encode("utf-8")
        kind = fmt or detect_type(filename, content_type, data)
        source_type = "text" if kind == "text" else kind
    elif data is not None:
        kind = detect_type(filename, content_type, data)
        source_type = kind
    else:
        raise ValueError("Cần một trong: tệp, url hoặc text")
    md = to_markdown(data, kind) if kind != "markdown" else normalize_markdown(data.decode("utf-8", "replace"))
    digest = sha256_bytes(data)
    raw_dir = Path(get_settings().DATA_DIR) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ext = {"pdf": ".pdf", "html": ".html", "markdown": ".md"}.get(kind, ".txt")
    raw_path = raw_dir / f"{digest}{ext}"
    if not raw_path.exists():
        raw_path.write_bytes(data)
    doc = Document(project_id=project_id, source_type=source_type, source_uri=source_uri, filename=filename,
                   raw_path=str(raw_path), markdown=md, sha256=digest)
    db.add(doc)
    db.flush()
    save_chunks(db, doc)
    return doc


def recount(chunk: Chunk) -> None:
    chunk.token_count = estimate_tokens(chunk.text)
