"""LLM Gateway: điểm duy nhất gọi LLM – cache theo (model, hash prompt), đếm token, ghi bảng llm_call.

Một adapter dùng openai SDK với base_url/api_key/model từ .env → chạy với OpenAI, Gemini (endpoint
OpenAI-compatible), Ollama (http://localhost:11434/v1), LM Studio. FakeLLM dùng cho test/offline.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from ...config import get_settings
from ...db import session_scope
from ...models import LLMCache, LLMCall


class LLMError(Exception):
    pass


class LLMNotConfigured(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    data: Any
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cached: bool
    model: str


def parse_json_text(text: str) -> Any:
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


_semaphores: dict[int, threading.BoundedSemaphore] = {}


def _semaphore(n: int) -> threading.BoundedSemaphore:
    if n not in _semaphores:
        _semaphores[n] = threading.BoundedSemaphore(n)
    return _semaphores[n]


class BaseLLM:
    provider = "base"

    def __init__(self, model: str):
        self.model = model
        s = get_settings()
        self.cache_enabled = s.LLM_CACHE_ENABLED
        self.sem = _semaphore(max(1, s.LLM_MAX_CONCURRENCY))

    # Lớp con cài đặt: trả về (text, input_tokens, output_tokens)
    def _complete(self, system: str, user: str, purpose: str) -> tuple[str, int, int]:
        raise NotImplementedError

    def chat_json(self, system: str, user: str, *, purpose: str = "extract", job_id: str | None = None) -> LLMResult:
        key = hashlib.sha256(f"{self.provider}|{self.model}|{system}\n---\n{user}".encode()).hexdigest()
        if self.cache_enabled:
            with session_scope() as db:
                hit = db.get(LLMCache, key)
                if hit is not None:
                    db.add(LLMCall(job_id=job_id, provider=self.provider, model=self.model, purpose=purpose,
                                   prompt_hash=key, input_tokens=hit.input_tokens, output_tokens=hit.output_tokens,
                                   latency_ms=0.0, cached=True))
                    return LLMResult(hit.response, _safe_parse(hit.response), hit.input_tokens, hit.output_tokens,
                                     0.0, True, self.model)
        t0 = time.perf_counter()
        err = None
        text, tin, tout = "", 0, 0
        try:
            with self.sem:
                text, tin, tout = self._complete(system, user, purpose)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        latency = (time.perf_counter() - t0) * 1000
        with session_scope() as db:
            db.add(LLMCall(job_id=job_id, provider=self.provider, model=self.model, purpose=purpose,
                           prompt_hash=key, input_tokens=tin, output_tokens=tout, latency_ms=latency, cached=False,
                           error=err))
            if err is None and self.cache_enabled and _safe_parse(text) is not None:
                db.merge(LLMCache(key=key, model=self.model, response=text, input_tokens=tin, output_tokens=tout))
        if err is not None:
            raise LLMError(err)
        return LLMResult(text, _safe_parse(text), tin, tout, latency, False, self.model)


def _safe_parse(text: str) -> Any:
    try:
        return parse_json_text(text)
    except Exception:  # noqa: BLE001
        return None


class OpenAICompatLLM(BaseLLM):
    provider = "openai-compatible"

    def __init__(self, model: str, base_url: str, api_key: str):
        super().__init__(model)
        from openai import OpenAI

        s = get_settings()
        self.client = OpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=s.LLM_TIMEOUT_S,
                             max_retries=2)
        self.json_mode = s.LLM_JSON_MODE
        self.provider = _provider_name(base_url)

    def _complete(self, system: str, user: str, purpose: str) -> tuple[str, int, int]:
        kwargs: dict[str, Any] = {
            "model": self.model, "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # một số máy chủ không hỗ trợ response_format
            if self.json_mode and "response_format" in str(e).lower():
                kwargs.pop("response_format")
                resp = self.client.chat.completions.create(**kwargs)
            else:
                raise
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        tin = getattr(usage, "prompt_tokens", 0) or 0
        tout = getattr(usage, "completion_tokens", 0) or 0
        return text, tin, tout


def _provider_name(base_url: str) -> str:
    u = base_url.lower()
    if "openai.com" in u:
        return "openai"
    if "googleapis" in u or "gemini" in u:
        return "gemini"
    if ":11434" in u or "ollama" in u:
        return "ollama"
    if ":1234" in u:
        return "lmstudio"
    return "openai-compatible"


def get_llm(model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> BaseLLM:
    """model='fake' → FakeLLM; ngược lại dùng adapter OpenAI-compatible theo .env."""
    s = get_settings()
    if model == "fake":
        from .fake import FakeLLM

        return FakeLLM()
    url = base_url or s.LLM_BASE_URL
    name = model or s.LLM_MODEL
    if not url or not name:
        raise LLMNotConfigured("Chưa cấu hình LLM (LLM_BASE_URL, LLM_MODEL trong .env). Dùng model='fake' để chạy thử.")
    return OpenAICompatLLM(name, url, api_key if api_key is not None else s.LLM_API_KEY)


def providers_info() -> list[dict]:
    s = get_settings()
    out = [{"id": "fake", "name": "FakeLLM (trích xuất theo luật, dùng cho test/offline)", "available": True,
            "models": ["fake"]}]
    out.append({"id": _provider_name(s.LLM_BASE_URL) if s.LLM_BASE_URL else "openai-compatible",
                "name": "OpenAI-compatible (.env)", "available": s.llm_configured, "base_url": s.LLM_BASE_URL or None,
                "models": [s.LLM_MODEL] if s.LLM_MODEL else [], "default": s.llm_configured})
    return out
