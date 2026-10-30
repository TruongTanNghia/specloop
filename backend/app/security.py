"""Mã hóa secret (Fernet) và che dữ liệu nhạy cảm trong vết."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "api-key",
                     "x-auth-token", "x-admin-token", "x-access-token"}
SENSITIVE_KEYS = re.compile(r"(pass(word)?|secret|token|api[_-]?key|authorization)", re.I)
REDACTED = "***"


def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode("utf-8")).decode("ascii")


def decrypt_json(token: str | None) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode("ascii")))
    except (InvalidToken, ValueError):
        return {}


def redact_headers(headers: dict[str, Any], extra: set[str] | None = None) -> dict[str, Any]:
    names = SENSITIVE_HEADERS | {h.lower() for h in (extra or set())}
    return {k: (REDACTED if k.lower() in names else v) for k, v in headers.items()}


def redact_query(query: dict[str, Any], extra: set[str] | None = None) -> dict[str, Any]:
    names = {h.lower() for h in (extra or set())}
    return {k: (REDACTED if k.lower() in names or SENSITIVE_KEYS.search(k) else v) for k, v in query.items()}


def redact_text(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s and len(s) >= 4:
            text = text.replace(s, REDACTED)
    return text
