"""Pha trích xuất: mỗi phân đoạn → LLM → OperationIR (validate Pydantic, retry ≤ 2 lần kèm lỗi)."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pydantic import ValidationError

from ...schemas.ir import OperationIR, parse_extraction
from ..ingestion.segmenter import build_context
from ..llm.gateway import BaseLLM, LLMError
from .prompts import build_extract_prompt

MAX_RETRIES = 2


@dataclass
class ExtractOutcome:
    chunk_id: int | None
    title: str
    ir: OperationIR | None = None
    error: str | None = None
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_calls: int = 0
    raw: list[str] = field(default_factory=list)


def extract_one(llm: BaseLLM, chunk, all_chunks, job_id: str | None = None) -> ExtractOutcome:
    out = ExtractOutcome(getattr(chunk, "id", None), chunk.title)
    system, user = build_extract_prompt(build_context(all_chunks, chunk), chunk.text)
    prompt = user
    for attempt in range(MAX_RETRIES + 1):
        out.attempts = attempt + 1
        try:
            res = llm.chat_json(system, prompt, purpose="extract", job_id=job_id)
        except LLMError as e:
            out.error = str(e)
            continue
        out.input_tokens += res.input_tokens
        out.output_tokens += res.output_tokens
        out.cached_calls += int(res.cached)
        out.raw.append(res.text[:4000])
        if res.data is None:
            err = "Output is not valid JSON."
        else:
            try:
                out.ir = parse_extraction(res.data)
                out.error = None
                return out
            except ValidationError as e:
                err = "Output does not validate against OperationIR: " + json.dumps(
                    [{"loc": list(x["loc"]), "msg": x["msg"]} for x in e.errors()[:10]])
        out.error = err
        prompt = (user + "\n\nYOUR PREVIOUS OUTPUT WAS INVALID:\n" + err +
                  "\nReturn a corrected JSON object only.")
    return out


def operation_chunks(chunks) -> list:
    ops = [c for c in chunks if c.operation_hint]
    if ops:
        return ops
    return [c for c in chunks if not c.is_global]


def extract_all(llm: BaseLLM, chunks, *, max_concurrency: int = 4, job_id: str | None = None,
                on_progress=None) -> list[ExtractOutcome]:
    targets = operation_chunks(chunks)
    results: list[ExtractOutcome | None] = [None] * len(targets)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, max_concurrency)) as ex:
        futs = {ex.submit(extract_one, llm, c, chunks, job_id): i for i, c in enumerate(targets)}
        for fut, i in futs.items():
            results[i] = fut.result()
            done += 1
            if on_progress:
                on_progress(done, len(targets))
    return [r for r in results if r is not None]
