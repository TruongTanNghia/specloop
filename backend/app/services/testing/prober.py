"""Gửi request kiểm thử an toàn (TECH_SPEC 5.4.3–5.4.4)."""
from __future__ import annotations

import copy
import ipaddress
import json
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx

from ...security import redact_headers, redact_query
from ..analysis.msg_miner import extract_message

MISSING = object()
MAX_STORED_BODY = 60_000


class SafetyError(Exception):
    pass


class BudgetExhausted(Exception):
    pass


def classify(status: int | None) -> str:
    if status is None:
        return "OTHER"
    if 200 <= status < 300:
        return "ACCEPT"
    if status in (400, 422):
        return "REJECT"
    if status in (401, 403):
        return "AUTH"
    if status == 404:
        return "NOT_FOUND"
    if status == 429:
        return "RATE"
    if status >= 500:
        return "SERVER_ERR"
    return "OTHER"


@dataclass
class ProbeRequest:
    path_params: dict = field(default_factory=dict)
    query: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    body: Any = MISSING

    def copy(self) -> ProbeRequest:
        return ProbeRequest(copy.deepcopy(self.path_params), copy.deepcopy(self.query), copy.deepcopy(self.headers),
                            self.body if self.body is MISSING else copy.deepcopy(self.body))


@dataclass
class Obs:
    id: int | None
    op: str
    strategy: str
    status: int | None
    outcome: str
    body: Any
    message: str | None
    latency_ms: float
    probe: dict | None = None


def _is_internal(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_unspecified or a.is_multicast


def check_target(base_url: str, allowed_hosts: list[str], allowed_networks: list[str]) -> bool:
    """Kiểm tra host trong allowlist và IP (chống SSRF). Trả về True nếu là sandbox (mạng nội bộ được cho phép)."""
    u = urlparse(base_url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise SafetyError(f"base_url không hợp lệ: {base_url}")
    host = u.hostname.lower()
    hosts = {h.lower().split(":")[0] for h in allowed_hosts if h}
    if hosts and host not in hosts:
        raise SafetyError(f"Host '{host}' không nằm trong danh sách được phép {sorted(hosts)}")
    try:
        infos = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80))
    except socket.gaierror as e:
        raise SafetyError(f"Không phân giải được host {host}: {e}") from e
    sandbox = False
    for info in infos:
        ip = info[4][0]
        if _is_internal(ip):
            if not any(ipaddress.ip_address(ip) in ipaddress.ip_network(n, strict=False) for n in allowed_networks):
                raise SafetyError(f"{host} ({ip}) thuộc dải IP nội bộ không được phép (TEST_ALLOWED_NETWORKS)")
            sandbox = True
    return sandbox


class Prober:
    def __init__(self, base_url: str, *, max_rps: float, budget: int, timeout: float,
                 auth: dict | None = None, secret: str | None = None, extra_redact: set[str] | None = None,
                 recorder: Callable[[dict], int | None] | None = None, cancel_check: Callable[[], None] | None = None,
                 on_obs: Callable[[Obs], None] | None = None):
        self.base_url = base_url.rstrip("/")
        self.min_interval = 1.0 / max_rps if max_rps and max_rps > 0 else 0.0
        self.budget = budget
        self.timeout = timeout
        self.auth = auth or {"type": "none"}
        self.secret = secret
        self.redact = set(extra_redact or set())
        if self.auth.get("type") in ("header", "query") and self.auth.get("name"):
            self.redact.add(self.auth["name"])
        self.recorder = recorder
        self.cancel_check = cancel_check
        self.on_obs = on_obs
        self.used: dict[str, int] = {}
        self.total = 0
        self.outcomes: dict[str, int] = {}
        self._last = 0.0
        self._lock = threading.Lock()
        self.client = httpx.Client(timeout=timeout, follow_redirects=False,
                                   headers={"User-Agent": "SpecLoop-Prober/1.0"})

    def close(self) -> None:
        self.client.close()

    def remaining(self, op_key: str) -> int:
        return self.budget - self.used.get(op_key, 0)

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def _auth_apply(self, headers: dict, query: dict) -> None:
        t = self.auth.get("type")
        if not self.secret or t in (None, "none"):
            return
        if t == "bearer":
            headers["Authorization"] = f"Bearer {self.secret}"
        elif t == "header":
            headers[self.auth.get("name") or "X-API-Key"] = self.secret
        elif t == "query":
            query[self.auth.get("name") or "api_key"] = self.secret

    def url_for(self, path: str, path_params: dict) -> str:
        p = path
        for k, v in path_params.items():
            p = p.replace("{" + k + "}", quote(_to_str(v), safe=""))
        return self.base_url + p

    def send(self, op_key: str, method: str, path: str, req: ProbeRequest, strategy: str,
             probe: dict | None = None, repeat_index: int = 0) -> Obs:
        if self.used.get(op_key, 0) >= self.budget:
            raise BudgetExhausted(op_key)
        if self.cancel_check and self.total % 5 == 0:
            self.cancel_check()
        self.used[op_key] = self.used.get(op_key, 0) + 1
        self.total += 1
        url = self.url_for(path, req.path_params)
        headers = {k: _to_str(v) for k, v in req.headers.items()}
        query = {k: _query_val(v) for k, v in req.query.items()}
        self._auth_apply(headers, query)
        kwargs: dict = {"headers": headers, "params": query}
        if req.body is not MISSING:
            kwargs["json"] = req.body
        self._throttle()
        t0 = time.perf_counter()
        status, body, resp_headers, err = None, None, {}, None
        try:
            r = self.client.request(method, url, **kwargs)
            status = r.status_code
            resp_headers = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "location",
                                                                                  "retry-after", "allow")}
            try:
                body = r.json() if r.content else None
            except (json.JSONDecodeError, ValueError):
                body = r.text[:4000]
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}: {e}"
        latency = (time.perf_counter() - t0) * 1000
        outcome = classify(status) if err is None else "OTHER"
        message = extract_message(body) if outcome != "ACCEPT" else None
        stored_body = body
        try:
            if body is not None and len(json.dumps(body, default=str)) > MAX_STORED_BODY:
                stored_body = {"_truncated": json.dumps(body, default=str)[:MAX_STORED_BODY]}
        except (TypeError, ValueError):
            stored_body = str(body)[:MAX_STORED_BODY]
        record = {
            "operation_id": op_key, "strategy": strategy, "probe": probe, "repeat_index": repeat_index,
            "request": {"method": method, "url": url, "path_params": req.path_params,
                        "query": redact_query(query, self.redact), "headers": redact_headers(headers, self.redact),
                        "body": None if req.body is MISSING else req.body},
            "status_code": status,
            "response": {"headers": resp_headers, "body": stored_body, "error": err},
            "outcome": outcome, "latency_ms": round(latency, 2),
        }
        oid = self.recorder(record) if self.recorder else None
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1
        obs = Obs(oid, op_key, strategy, status, outcome, body, message, latency, probe)
        if self.on_obs:
            self.on_obs(obs)
        return obs

    def reset(self, reset_cfg: dict | None, headers: dict | None = None) -> dict:
        if not reset_cfg or not reset_cfg.get("url"):
            return {"done": False}
        url = reset_cfg["url"]
        if not url.startswith(("http://", "https://")):
            u = urlparse(self.base_url)
            url = urljoin(f"{u.scheme}://{u.netloc}", url)
        try:
            r = self.client.request(reset_cfg.get("method", "POST"), url, headers=headers or {})
            return {"done": r.status_code < 300, "status": r.status_code}
        except httpx.HTTPError as e:
            return {"done": False, "error": str(e)}


def _to_str(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)


def _query_val(v: Any):
    if isinstance(v, list):
        return [_to_str(x) for x in v]
    return _to_str(v)
