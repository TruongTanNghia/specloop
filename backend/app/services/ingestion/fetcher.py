"""Tải tài liệu (URL/HTML/MD/PDF/TXT) và chuyển về Markdown, có chống SSRF."""
from __future__ import annotations

import hashlib
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from ...config import get_settings
from .segmenter import normalize_markdown

MAX_BYTES = 10 * 1024 * 1024


class FetchError(Exception):
    pass


def ip_allowed(ip: str, allowed_networks: list[str]) -> bool:
    addr = ipaddress.ip_address(ip)
    if not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
            or addr.is_multicast or addr.is_unspecified):
        return True
    return any(addr in ipaddress.ip_network(n, strict=False) for n in allowed_networks)


def check_url_safe(url: str, allowed_networks: list[str] | None = None) -> None:
    """Phân giải DNS rồi kiểm tra IP trước khi kết nối (chống SSRF)."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise FetchError(f"URL không hợp lệ: {url}")
    nets = get_settings().allowed_networks if allowed_networks is None else allowed_networks
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
    except socket.gaierror as e:
        raise FetchError(f"Không phân giải được host {u.hostname}: {e}") from e
    for info in infos:
        ip = info[4][0]
        if not ip_allowed(ip, nets):
            raise FetchError(f"Host {u.hostname} ({ip}) thuộc dải mạng nội bộ không được phép")


def fetch_url(url: str, max_redirects: int = 5) -> tuple[bytes, str]:
    s = get_settings()
    with httpx.Client(timeout=s.TEST_TIMEOUT_S * 3, follow_redirects=False,
                      headers={"User-Agent": "SpecLoop/1.0 (+docs ingestion)"}) as client:
        for _ in range(max_redirects + 1):
            check_url_safe(url)
            r = client.get(url)
            if r.is_redirect:
                url = urljoin(url, r.headers.get("location", ""))
                continue
            r.raise_for_status()
            if len(r.content) > MAX_BYTES:
                raise FetchError("Tài liệu vượt quá 10 MB")
            return r.content, r.headers.get("content-type", "")
    raise FetchError("Quá nhiều lần chuyển hướng")


def html_to_markdown(html: str) -> str:
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "form", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    md = markdownify(str(main), heading_style="ATX", code_language="", bullets="-")
    if len(md.strip()) < 50:
        try:
            import trafilatura

            alt = trafilatura.extract(html, output_format="markdown", include_tables=True, favor_recall=True)
            if alt and len(alt) > len(md):
                md = alt
        except Exception:  # noqa: BLE001
            pass
    return md


def pdf_to_markdown(data: bytes) -> str:
    import fitz  # PyMuPDF

    parts = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n\n".join(parts)


def detect_type(filename: str | None, content_type: str | None, data: bytes) -> str:
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if name.endswith(".pdf") or "pdf" in ct or data[:5] == b"%PDF-":
        return "pdf"
    if name.endswith((".html", ".htm")) or "html" in ct:
        return "html"
    if name.endswith((".md", ".markdown")) or "markdown" in ct:
        return "markdown"
    head = data[:2000].decode("utf-8", errors="ignore").lower()
    if "<html" in head or "<!doctype html" in head or "<body" in head:
        return "html"
    return "text"


def to_markdown(data: bytes, kind: str) -> str:
    if kind == "pdf":
        md = pdf_to_markdown(data)
    elif kind == "html":
        md = html_to_markdown(data.decode("utf-8", errors="replace"))
    else:
        md = data.decode("utf-8", errors="replace")
    return normalize_markdown(md)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
