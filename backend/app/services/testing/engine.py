"""Bộ máy kiểm thử M4 + phát hiện M5 (TECH_SPEC 5.4–5.5).

Mỗi operation: request cơ sở → các chiến lược một-biến (S3 bắt buộc, S8 phụ thuộc, S5 enum, S4 kiểu, S7 định dạng,
S6 dò biên, S2 dữ liệu cực trị, S9 lấy mẫu phản hồi). Sau cùng phân tích toàn cục: mã trạng thái (D7),
lệch schema phản hồi (D8/D5), lỗi máy chủ (D0). Kết quả là các FindingDraft kèm JSON Patch và kênh bằng chứng.
"""
from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..analysis import boundary as bd
from ..analysis.confidence import R_MESSAGE_REGEX, noisy_or, wilson_lower
from ..analysis.msg_miner import hints_for, is_referential, mine
from ..analysis.schema_check import check, get_pointer, json_type
from ..versioning.core import has_value
from .opmodel import (
    SAFE_METHODS,
    OperationModel,
    Target,
    array_of_length,
    build_models,
    esc,
    gen_value,
    parent_collection,
    string_of_length,
)
from .prober import MISSING, BudgetExhausted, Obs, Prober, ProbeRequest

ROBUST_INTS = (-1, 0, 2 ** 31, -(2 ** 31))
IDL_IF_RE = re.compile(r"^\s*IF\s+([\w.\-\[\]]+)\s+THEN\s+([\w.\-\[\]]+)\s*;?\s*$", re.I)
STATUS_TEXT = {"200": "OK", "201": "Created", "202": "Accepted", "204": "No Content", "400": "Bad Request",
               "401": "Unauthorized", "403": "Forbidden", "404": "Not Found", "405": "Method Not Allowed",
               "409": "Conflict", "415": "Unsupported Media Type", "422": "Unprocessable Entity"}


@dataclass
class FindingDraft:
    code: str
    op: str
    location: str
    keyword: str | None
    pointer: str | None
    summary: str
    details: dict = field(default_factory=dict)
    support: list[int] = field(default_factory=list)
    contradict: list[int] = field(default_factory=list)
    channels: dict = field(default_factory=dict)
    doc_conflict: bool = False
    patch: list[dict] | None = None
    message: str | None = None

    @property
    def confidence(self) -> float:
        return noisy_or(self.channels)


@dataclass
class EngineConfig:
    strategies: set[str] = field(default_factory=lambda: {"S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"})
    repeats: int = 3
    mode: str = "full"
    operations: list[str] | None = None
    sample_size: int = 20
    int_cap: float = 10 ** 9
    len_cap: int = 4096
    items_cap: int = 256


def _ids(obs_list) -> list[int]:
    return [o.id for o in obs_list if o is not None and o.id is not None]


def _probe_channel(support: int, contradict: int = 0) -> float:
    return round(wilson_lower(support, support + contradict), 4)


def _norm_data_path(p: str) -> str:
    return re.sub(r"\[\d+\]", "[]", p)


def _infer(values: list) -> dict:
    types = {json_type(v) for v in values if v is not None}
    s: dict = {}
    if len(types) == 1:
        t = types.pop()
        s["type"] = "number" if t == "number" else t
        if t == "array":
            s["items"] = {}
    if any(v is None for v in values):
        s["nullable"] = True
    return s


class Engine:
    def __init__(self, spec: dict, prober: Prober, cfg: EngineConfig,
                 progress: Callable[..., None] | None = None):
        self.spec = spec
        self.prober = prober
        self.cfg = cfg
        self.progress = progress or (lambda **_: None)
        self.models = build_models(spec)
        self.by_key = {m.key: m for m in self.models}
        self.findings: list[FindingDraft] = []
        self.verified: list[dict] = []
        self.unverified: list[dict] = []
        self.resp_obs: list[tuple[OperationModel, Obs]] = []
        self.statuses: dict[str, dict[str, list[Obs]]] = {}
        self.server_errors: dict[tuple[str, str], list[Obs]] = {}
        self.op_status: dict[str, str] = {}
        self.current_label: str = "-"

    # ------------------------------------------------------------------ ghi nhận
    def record(self, om: OperationModel, obs: Obs) -> None:
        if obs.status is not None:
            self.statuses.setdefault(om.key, {}).setdefault(str(obs.status), []).append(obs)
        if obs.outcome == "SERVER_ERR":
            label = (obs.probe or {}).get("param", "-")
            self.server_errors.setdefault((om.key, label), []).append(obs)
        if obs.status is not None and obs.outcome not in ("SERVER_ERR", "RATE") and obs.body is not None:
            self.resp_obs.append((om, obs))

    def verify(self, om: OperationModel, label: str, what: str, n: int, **extra) -> None:
        self.verified.append({"operation": om.key, "location": label, "check": what, "observations": n, **extra})

    def unverify(self, om: OperationModel, label: str, what: str, reason: str) -> None:
        self.unverified.append({"operation": om.key, "location": label, "check": what, "reason": reason})

    def add(self, f: FindingDraft) -> None:
        self.findings.append(f)

    # ------------------------------------------------------------------ chạy
    def ordered(self) -> list[OperationModel]:
        def rank(m: OperationModel):
            has_param = "{" in m.path
            order = {"GET": 0 if not has_param else 2, "POST": 1, "PUT": 3, "PATCH": 3, "HEAD": 4, "OPTIONS": 4,
                     "DELETE": 5}.get(m.method, 6)
            return (order, m.path)
        ops = sorted(self.models, key=rank)
        if self.cfg.operations:
            want = {o.strip() for o in self.cfg.operations}
            ops = [m for m in ops if m.key in want]
        return ops

    def run(self) -> None:
        ops = self.ordered()
        for i, om in enumerate(ops):
            self.progress(stage="testing", operation=om.key, done=i, total=len(ops), outcomes=dict(self.prober.outcomes),
                          requests=self.prober.total)
            if self.cfg.mode == "safe" and om.method not in SAFE_METHODS:
                self.op_status[om.key] = "skipped (safe mode)"
                self.unverify(om, "-", "toàn bộ operation", "chế độ safe chỉ cho phép GET/HEAD/OPTIONS")
                continue
            runner = OpRunner(self, om)
            try:
                runner.run()
                self.op_status.setdefault(om.key, "done")
            except BudgetExhausted:
                self.op_status[om.key] = "budget_exhausted"
                self.unverify(om, "-", "một phần chiến lược", "hết ngân sách request của operation")
        self.progress(stage="analysis", operation=None, done=len(ops), total=len(ops),
                      outcomes=dict(self.prober.outcomes), requests=self.prober.total)
        self.analyse_statuses()
        self.analyse_responses()
        self.analyse_server_errors()
        self.merge_list_patches()

    # ------------------------------------------------------------------ phân tích toàn cục
    def analyse_statuses(self) -> None:
        for key, by_status in self.statuses.items():
            om = self.by_key[key]
            declared = set(om.responses)
            if "default" in declared:
                continue
            ranges = {d[0] for d in declared if re.fullmatch(r"[1-5]XX", d, re.I)}
            observed = {s: obs for s, obs in by_status.items()
                        if not s.startswith("5") and s not in ("429", "401", "403") and s[0] not in ranges}
            obs2 = {s for s in observed if s.startswith("2")}
            dec2 = {s for s in declared if s.startswith("2")}
            for s, obs in sorted(observed.items()):
                if s in declared:
                    continue
                sample = next((o.body for o in obs if o.body is not None), None)
                resp_obj: dict = {"description": STATUS_TEXT.get(s, f"Response {s}")}
                schema = self.schema_for_body(sample)
                if schema is not None:
                    resp_obj["content"] = {"application/json": {"schema": schema}}
                base = om.responses_ptr
                unseen2 = sorted(d for d in dec2 if d not in obs2)
                if s.startswith("2") and dec2 and len(unseen2) == len(dec2):
                    src = unseen2[0]
                    patch = [{"op": "move", "from": f"{base}/{esc(src)}", "path": f"{base}/{esc(s)}"}]
                    summary = (f"{key}: phản hồi thành công thực tế là {s} (khai báo {src} nhưng không bao giờ "
                               f"quan sát được trong {len(obs)} phản hồi 2xx)")
                    conflict = True
                    det = {"declared": src, "observed": s}
                else:
                    patch = [{"op": "add", "path": f"{base}/{esc(s)}", "value": resp_obj}]
                    summary = f"{key}: mã trạng thái {s} xuất hiện nhưng chưa được khai báo ({len(obs)} lần)"
                    conflict = False
                    det = {"observed": s, "sample_message": next((o.message for o in obs if o.message), None)}
                self.add(FindingDraft("D7", key, "responses", s, f"{base}/{esc(s)}", summary, det, _ids(obs), [],
                                      {"probe": _probe_channel(len(obs))}, conflict, patch,
                                      next((o.message for o in obs if o.message), None)))

    def schema_for_body(self, body: Any) -> dict | None:
        if body is None or isinstance(body, str):
            return None
        comps = (self.spec.get("components") or {}).get("schemas") or {}
        if isinstance(body, dict):
            keys = set(body)
            for name, comp in comps.items():
                if isinstance(comp, dict) and set((comp.get("properties") or {})) == keys and keys:
                    if not check(body, comp, f"/components/schemas/{esc(name)}", self.spec, report_additional=True):
                        return {"$ref": f"#/components/schemas/{name}"}
            return {"type": "object", "properties": {k: _infer([v]) for k, v in body.items()}}
        if isinstance(body, list):
            return {"type": "array", "items": _infer(body[:1]) if body else {}}
        return _infer([body])

    def analyse_responses(self) -> None:
        groups: dict[tuple, dict] = {}
        for om, obs in self.resp_obs:
            st = str(obs.status)
            entry = om.responses.get(st)
            if entry is None:
                entry = om.responses.get(st[0] + "XX") or om.responses.get("default")
            if not entry or entry[0] is None:
                continue
            schema, sptr = entry
            seen_in_obs = set()
            for v in check(obs.body, schema, sptr, self.spec):
                gk = (v.schema_ptr, v.kind, v.prop if v.kind in ("required", "additional") else None)
                g = groups.setdefault(gk, {"obs": [], "ops": set(), "values": [], "paths": set(),
                                           "status": st, "v": v, "op": om.key})
                if (gk, obs.id) not in seen_in_obs:
                    seen_in_obs.add((gk, obs.id))
                    g["obs"].append(obs)
                g["ops"].add(om.key)
                g["values"].append(v.actual)
                g["paths"].add(_norm_data_path(v.data_path) if v.kind not in ("required", "additional")
                               else (_norm_data_path(v.data_path) + "." if v.data_path else "") + (v.prop or ""))
        for (sptr, kind, prop), g in groups.items():
            v = g["v"]
            node = get_pointer(self.spec, sptr) if has_value(self.spec, sptr) else {}
            ops = sorted(g["ops"])
            loc = f"resp{g['status']}:{sorted(g['paths'])[0]}"
            n = len(g["obs"])
            channels = {"sampling": _probe_channel(n)}
            where = f"{loc} ({', '.join(ops)})"
            if kind == "null":
                f = FindingDraft("D8", ops[0], loc, "nullable", sptr,
                                 f"Phản hồi có giá trị null tại {where} nhưng schema không cho phép null ({n} phản hồi)",
                                 {"operations": ops}, _ids(g["obs"]), [], channels, False,
                                 [{"op": "add", "path": f"{sptr}/nullable", "value": True}])
            elif kind == "enum":
                declared = list(node.get("enum") or [])
                extra = []
                for x in g["values"]:
                    if x not in declared and x not in extra:
                        extra.append(x)
                f = FindingDraft("D5", ops[0], loc, "enum", sptr,
                                 f"Phản hồi chứa giá trị ngoài enum tại {where}: {extra}",
                                 {"operations": ops, "declared": declared, "observed_extra": extra}, _ids(g["obs"]), [],
                                 channels, True, [{"op": "replace", "path": f"{sptr}/enum", "value": declared + extra}])
            elif kind == "type":
                types = {json_type(x) for x in g["values"]}
                new = types.pop() if len(types) == 1 else None
                if new == "integer" and node.get("type") == "number":
                    continue
                f = FindingDraft("D8", ops[0], loc, "type", sptr,
                                 f"Kiểu trong phản hồi khác khai báo tại {where}: khai báo {v.expected}, quan sát "
                                 f"{sorted({json_type(x) for x in g['values']})}",
                                 {"operations": ops, "declared": v.expected}, _ids(g["obs"]), [], channels, True,
                                 [{"op": "replace", "path": f"{sptr}/type", "value": new}] if new else None)
            elif kind == "required":
                req = [r for r in (node.get("required") or []) if r != prop]
                patch = ([{"op": "replace", "path": f"{sptr}/required", "value": req}] if req
                         else [{"op": "remove", "path": f"{sptr}/required"}])
                f = FindingDraft("D8", ops[0], loc, "required", sptr,
                                 f"Thuộc tính bắt buộc '{prop}' vắng mặt trong phản hồi ({where}, {n} lần)",
                                 {"operations": ops, "property": prop}, _ids(g["obs"]), [], channels, True, patch)
            elif kind == "additional":
                f = FindingDraft("D8", ops[0], loc, "properties", sptr,
                                 f"Phản hồi có thuộc tính '{prop}' chưa khai báo ({where}, {n} lần)",
                                 {"operations": ops, "property": prop}, _ids(g["obs"]), [],
                                 {"sampling": round(_probe_channel(n) * 0.8, 4)}, False,
                                 [{"op": "add", "path": f"{sptr}/properties/{esc(prop)}", "value": _infer(g["values"])}])
            elif kind in ("minimum", "maximum", "minLength", "maxLength", "pattern", "format", "minItems",
                          "maxItems"):
                f = FindingDraft("D8", ops[0], loc, kind, sptr,
                                 f"Giá trị trong phản hồi vi phạm {kind}={v.expected!r} tại {where}",
                                 {"operations": ops, "values": g["values"][:10]}, _ids(g["obs"]), [], channels, True,
                                 [{"op": "remove", "path": f"{sptr}/{kind}"}])
            else:
                continue
            self.add(f)

    def analyse_server_errors(self) -> None:
        for (key, label), obs in self.server_errors.items():
            vals = []
            for o in obs:
                v = (o.probe or {}).get("value")
                if v is not None and v not in vals:
                    vals.append(v)
            self.add(FindingDraft(
                "D0", key, label if label != "-" else "operation", None,
                self.by_key[key].op_ptr if key in self.by_key else None,
                f"{key}: lỗi máy chủ {sorted({o.status for o in obs})} khi {label}"
                + (f" = {vals[:5]}" if vals else "") + f" ({len(obs)} lần) – chỉ báo cáo, không sửa đặc tả",
                {"values": vals[:20], "statuses": sorted({o.status for o in obs})}, _ids(obs), [],
                {"probe": _probe_channel(len(obs))}, False, None))

    def merge_list_patches(self) -> None:
        """Gộp các đề xuất cùng sửa một danh sách (required, x-dependencies) để áp dụng theo thứ tự nào cũng đúng."""
        by_path: dict[str, list[FindingDraft]] = {}
        for f in self.findings:
            if f.patch and len(f.patch) >= 1 and f.details.get("list_edit"):
                by_path.setdefault(f.details["list_edit"]["path"], []).append(f)
        for path, fs in by_path.items():
            base = list(fs[0].details["list_edit"]["base"])
            removes = {json_key(x) for f in fs for x in f.details["list_edit"].get("remove", [])}
            adds = [x for f in fs for x in f.details["list_edit"].get("add", [])]
            final = [x for x in base if json_key(x) not in removes]
            for x in adds:
                if json_key(x) not in {json_key(y) for y in final}:
                    final.append(x)
            for f in fs:
                extra = [p for p in f.patch if p.get("path") != path]
                if final:
                    op = "replace" if has_value(self.spec, path) else "add"
                    f.patch = [{"op": op, "path": path, "value": final}] + extra
                else:
                    f.patch = [{"op": "remove", "path": path}] + extra


def json_key(x: Any) -> str:
    return repr(x)


class OpRunner:
    def __init__(self, eng: Engine, om: OperationModel):
        self.e = eng
        self.om = om
        self.cfg = eng.cfg
        self.base: ProbeRequest | None = None
        self.consuming = om.method == "DELETE"
        self.single: dict[str, tuple[str, Obs, Any]] = {}
        self.companions: dict[str, tuple[Target, Any]] = {}
        self.base_values: dict[str, Any] = {}

    # ------------------------------------------------------------------ tiện ích request
    def send(self, req: ProbeRequest, strategy: str, probe: dict | None = None, repeat: int = 0) -> Obs:
        obs = self.e.prober.send(self.om.key, self.om.method, self.om.path, req, strategy, probe, repeat)
        self.e.record(self.om, obs)
        return obs

    @staticmethod
    def put(req: ProbeRequest, t: Target, value: Any) -> ProbeRequest:
        r = req.copy()
        if t.location == "path":
            r.path_params[t.name] = value
        elif t.location == "query":
            r.query[t.name] = value
        elif t.location == "header":
            r.headers[t.name] = value
        elif t.location == "cookie":
            r.headers["Cookie"] = f"{t.name}={value}"
        else:
            if not isinstance(r.body, dict):
                r.body = {}
            r.body[t.name] = value
        return r

    @staticmethod
    def drop(req: ProbeRequest, t: Target) -> ProbeRequest:
        r = req.copy()
        if t.location == "query":
            r.query.pop(t.name, None)
        elif t.location == "header":
            r.headers.pop(t.name, None)
        elif t.location == "cookie":
            r.headers.pop("Cookie", None)
        elif t.location == "body" and isinstance(r.body, dict):
            r.body.pop(t.name, None)
        return r

    @staticmethod
    def present(req: ProbeRequest, t: Target) -> bool:
        if t.location == "path":
            return t.name in req.path_params
        if t.location == "query":
            return t.name in req.query
        if t.location == "header":
            return t.name in req.headers
        if t.location == "body":
            return isinstance(req.body, dict) and t.name in req.body
        return False

    @staticmethod
    def value_of(req: ProbeRequest, t: Target) -> Any:
        return {"path": req.path_params, "query": req.query, "header": req.headers}.get(
            t.location, req.body if isinstance(req.body, dict) else {}).get(t.name)

    def fresh(self) -> ProbeRequest:
        if self.consuming:
            produced = self.produce()
            if produced:
                r = self.base.copy()
                r.path_params.update(produced)
                return r
        return self.base.copy()

    def base_for(self, t: Target) -> ProbeRequest:
        """Request cơ sở cho thuộc tính t (kèm thuộc tính đồng hành nếu t phụ thuộc thuộc tính khác)."""
        r = self.fresh()
        comp = self.companions.get(t.label)
        if comp:
            r = self.put(r, comp[0], comp[1])
        return r

    def gen(self, t: Target) -> Any:
        v = gen_value(t.schema, self.e.spec)
        if t.location in ("query", "path", "header") and isinstance(v, (dict, list)) and t.type != "array":
            return "sample"
        return v

    # ------------------------------------------------------------------ cơ sở
    def initial_request(self) -> ProbeRequest:
        r = ProbeRequest()
        for t in self.om.params:
            if t.location == "path" or t.required:
                r = self.put(r, t, self.gen(t))
        if self.om.body_schema is not None:
            body = self.om.body_example if isinstance(self.om.body_example, dict) else None
            if body is None:
                body = gen_value(self.om.body_schema, self.e.spec)
            if body or self.om.body_required or self.om.method in ("POST", "PUT", "PATCH"):
                r.body = copy.deepcopy(body)
        return r

    def produce(self) -> dict | None:
        coll = parent_collection(self.om.path)
        if coll is None:
            return None
        prod = self.e.by_key.get(f"POST {coll}")
        if prod is None:
            return None
        pr = OpRunner(self.e, prod).initial_request()
        obs = self.e.prober.send(self.om.key, "POST", prod.path, pr, "producer", {"producer": prod.key})
        if obs.outcome != "ACCEPT" or not isinstance(obs.body, dict):
            return None
        out = {}
        for t in self.om.params:
            if t.location != "path":
                continue
            val = obs.body.get(t.name)
            if val is None:
                val = obs.body.get("id")
            if val is None:
                val = next((v for k, v in obs.body.items() if k.lower().endswith("id")), None)
            if val is not None:
                out[t.name] = val
        return out or None

    def establish_baseline(self) -> bool:
        req = self.initial_request()
        has_path = any(t.location == "path" for t in self.om.params)
        if self.consuming:
            produced = self.produce()
            if produced:
                req.path_params.update(produced)
        for attempt in range(3):
            obs = self.send(req, "S0.baseline", {"baseline": True})
            if obs.outcome == "ACCEPT":
                self.base = req
                if not self.consuming:
                    self.send(req, "S0.baseline", {"baseline": True}, repeat=1)
                for t in self.om.targets:
                    if self.present(req, t):
                        self.base_values[t.label] = self.value_of(req, t)
                return True
            if obs.outcome == "NOT_FOUND" and has_path and attempt == 0:
                produced = self.produce()
                if produced:
                    req.path_params.update(produced)
                    continue
            if obs.outcome == "REJECT":
                changed = False
                for h in mine(obs.message):
                    if h.kind != "required" or not h.param:
                        continue
                    t = next((x for x in self.om.targets if x.name == h.param and not self.present(req, x)), None)
                    if t is not None:
                        req = self.put(req, t, self.gen(t))
                        changed = True
                        self.e.add(FindingDraft(
                            "D4", self.om.key, t.label, "required", t.holder_ptr,
                            f"{self.om.key}: '{t.name}' được khai báo tùy chọn nhưng thiếu thì bị từ chối "
                            f"(\"{obs.message}\")", {"declared_required": False, "observed_required": True},
                            _ids([obs]), [], {"probe": _probe_channel(1), "error_message": R_MESSAGE_REGEX}, True,
                            self.required_patch(t, True), obs.message))
                if changed:
                    continue
            break
        self.e.op_status[self.om.key] = "no_baseline"
        self.e.unverify(self.om, "-", "request cơ sở", f"không tạo được request cơ sở 2xx (outcome {obs.outcome})")
        return False

    # ------------------------------------------------------------------ chạy các chiến lược
    def run(self) -> None:
        if not self.establish_baseline():
            if "S2" in self.cfg.strategies:
                self.robustness(only_path=True)
            return
        s = self.cfg.strategies
        if self.consuming:
            if "S4" in s:
                self.type_probes(only_path=True)
            if "S2" in s:
                self.robustness(only_path=True)
            return
        if "S3" in s:
            self.required_probes()
        if "S8" in s:
            self.declared_dependencies()
        self.single_probes()
        if "S8" in s:
            self.discover_dependencies()
        if "S5" in s:
            self.enum_probes()
        if "S4" in s:
            self.type_probes()
        if "S7" in s:
            self.format_probes()
        if "S6" in s:
            for t in self.om.targets:
                self.e.current_label = t.label
                self.boundary(t)
        if "S2" in s:
            self.robustness()
        if "S9" in s and self.om.method in SAFE_METHODS:
            self.sampling()

    def repeat(self, req: ProbeRequest, strategy: str, probe: dict, n: int | None = None) -> list[Obs]:
        out = []
        for i in range(n or self.cfg.repeats):
            o = self.send(req, strategy, probe, repeat=i)
            out.append(o)
            if len(out) >= 2 and out[-1].outcome != out[0].outcome:
                break
        return out

    def required_patch(self, t: Target, required: bool) -> list[dict]:
        if t.location != "body":
            return [{"op": "replace" if has_value(self.e.spec, t.holder_ptr + "/required") else "add",
                     "path": t.holder_ptr + "/required", "value": required}]
        holder = get_pointer(self.e.spec, t.holder_ptr)
        req = list(holder.get("required") or [])
        if required and t.name not in req:
            req.append(t.name)
        if not required:
            req = [r for r in req if r != t.name]
        return [{"op": "replace" if "required" in holder else "add", "path": t.holder_ptr + "/required",
                 "value": req}]

    def required_probes(self) -> None:
        for t in self.om.targets:
            if not t.required or t.location == "path":
                continue
            req = self.drop(self.fresh(), t)
            obs = self.repeat(req, "S3.required", {"param": t.label, "action": "omit"})
            outs = {o.outcome for o in obs}
            if outs == {"ACCEPT"}:
                patch = self.required_patch(t, False)
                details: dict = {"declared_required": True, "observed_required": False}
                if t.location == "body":
                    holder = get_pointer(self.e.spec, t.holder_ptr)
                    details["list_edit"] = {"path": t.holder_ptr + "/required",
                                            "base": list(holder.get("required") or []), "remove": [t.name]}
                default = self.infer_default(t, obs[0])
                if default is not None and "default" not in t.schema:
                    patch = patch + [{"op": "add", "path": t.schema_ptr + "/default", "value": default[0]}]
                    details["inferred_default"] = default[0]
                support = obs + (default[1] if default else [])
                self.e.add(FindingDraft(
                    "D4", self.om.key, t.label, "required", t.holder_ptr,
                    f"{self.om.key}: '{t.name}' khai báo bắt buộc nhưng bỏ đi vẫn được chấp nhận "
                    f"({len(obs)}/{len(obs)} lần)" + (f"; mặc định quan sát được = {default[0]!r}" if default else ""),
                    details, _ids(support), [], {"probe": _probe_channel(len(obs))}, True, patch))
            elif outs == {"REJECT"}:
                hs = [h for h in hints_for(obs[0].message, t.name) if h.kind == "required"]
                self.e.verify(self.om, t.label, "required", len(obs), message=obs[0].message,
                              channels={"probe": _probe_channel(len(obs)),
                                        **({"error_message": R_MESSAGE_REGEX} if hs else {})})
            else:
                self.e.unverify(self.om, t.label, "required", f"kết quả không ổn định: {sorted(outs)}")

    def infer_default(self, t: Target, omitted: Obs) -> tuple[Any, list[Obs]] | None:
        """Bỏ tham số được chấp nhận → so phản hồi với từng giá trị enum để suy ra giá trị mặc định."""
        values = list(t.schema.get("enum") or [])
        if not values or omitted.body is None or len(values) > 10:
            return None
        matches, used = [], []
        for v in values:
            o = self.send(self.put(self.drop(self.fresh(), t), t, v), "S3.default", {"param": t.label, "value": v})
            used.append(o)
            if o.outcome == "ACCEPT" and o.body == omitted.body:
                matches.append(v)
        if len(matches) == 1:
            return matches[0], used
        return None

    def declared_dependencies(self) -> None:
        deps = self.om.dependencies
        for idl in deps:
            m = IDL_IF_RE.match(idl)
            if not m:
                self.e.unverify(self.om, "operation", f"x-dependencies: {idl}", "chỉ kiểm chứng được dạng IF a THEN b")
                continue
            ta = next((t for t in self.om.targets if t.name == m.group(1)), None)
            tb = next((t for t in self.om.targets if t.name == m.group(2)), None)
            if ta is None or tb is None:
                self.e.unverify(self.om, "operation", f"x-dependencies: {idl}", "tham số không có trong đặc tả")
                continue
            req = self.put(self.drop(self.fresh(), tb), ta, self.base_values.get(ta.label, self.gen(ta)))
            obs = self.repeat(req, "S8.dependency", {"param": ta.label, "without": tb.label, "idl": idl})
            outs = {o.outcome for o in obs}
            if outs == {"ACCEPT"}:
                self.e.add(FindingDraft(
                    "D2", self.om.key, "operation", "x-dependencies", self.om.op_ptr + "/x-dependencies",
                    f"{self.om.key}: phụ thuộc '{idl}' không được cài đặt kiểm tra – có {ta.name} mà thiếu "
                    f"{tb.name} vẫn được chấp nhận ({len(obs)}/{len(obs)} lần)",
                    {"idl": idl, "list_edit": {"path": self.om.op_ptr + "/x-dependencies", "base": deps,
                                               "remove": [idl]}},
                    _ids(obs), [], {"probe": _probe_channel(len(obs))}, True,
                    [{"op": "replace", "path": self.om.op_ptr + "/x-dependencies", "value": []}]))
            elif outs == {"REJECT"}:
                self.e.verify(self.om, "operation", f"x-dependencies: {idl}", len(obs), message=obs[0].message)
            else:
                self.e.unverify(self.om, "operation", f"x-dependencies: {idl}", f"không ổn định {sorted(outs)}")

    def single_probes(self) -> None:
        for t in self.om.targets:
            if t.location == "path" or self.present(self.base, t):
                continue
            v = self.gen(t)
            o = self.send(self.put(self.fresh(), t, v), "S8.single", {"param": t.label, "value": v})
            self.single[t.label] = (o.outcome, o, v)

    def discover_dependencies(self) -> None:
        optional = [t for t in self.om.targets if t.location != "path" and t.label in self.single]
        for t in optional:
            outcome, o1, v = self.single[t.label]
            if outcome != "REJECT":
                continue
            own = [h for h in hints_for(o1.message, t.name) if h.kind not in ("required", "dependency")]
            if own:
                continue  # chính giá trị của t bị từ chối – không phải phụ thuộc
            hinted = [h.param for h in mine(o1.message) if h.param and h.param != t.name]
            cands = sorted([q for q in optional if q is not t],
                           key=lambda q: (q.name not in hinted, q.name))[:6]
            for q in cands:
                qv = self.single[q.label][2]
                o2 = self.send(self.put(self.put(self.fresh(), t, v), q, qv), "S8.pair",
                               {"param": t.label, "with": q.label})
                if o2.outcome != "ACCEPT":
                    continue
                more_r = self.repeat(self.put(self.fresh(), t, v), "S8.pair", {"param": t.label, "without": q.label},
                                     max(1, self.cfg.repeats - 1))
                more_a = self.repeat(self.put(self.put(self.fresh(), t, v), q, qv), "S8.pair",
                                     {"param": t.label, "with": q.label}, max(1, self.cfg.repeats - 1))
                rej = [o1] + more_r
                acc = [o2] + more_a
                if {o.outcome for o in rej} != {"REJECT"} or {o.outcome for o in acc} != {"ACCEPT"}:
                    self.e.unverify(self.om, t.label, f"phụ thuộc {t.name}→{q.name}", "không ổn định")
                    break
                self.companions[t.label] = (q, qv)
                idl = f"IF {t.name} THEN {q.name};"
                declared = [" ".join(d.split()) for d in self.om.dependencies]
                dep_hint = [h for h in mine(o1.message) if h.kind == "dependency" and h.value == idl]
                channels = {"probe": _probe_channel(len(rej) + len(acc))}
                if dep_hint:
                    channels["error_message"] = R_MESSAGE_REGEX
                if idl in declared:
                    self.e.verify(self.om, "operation", f"x-dependencies: {idl}", len(rej) + len(acc))
                else:
                    self.e.add(FindingDraft(
                        "D9", self.om.key, "operation", "x-dependencies", self.om.op_ptr + "/x-dependencies",
                        f"{self.om.key}: có {t.name} mà thiếu {q.name} thì bị từ chối, có cả hai thì được chấp nhận "
                        f"→ {idl}", {"idl": idl, "list_edit": {"path": self.om.op_ptr + "/x-dependencies",
                                                               "base": list(self.om.dependencies), "add": [idl]}},
                        _ids(rej + acc), [], channels, False,
                        [{"op": "add", "path": self.om.op_ptr + "/x-dependencies", "value": [idl]}], o1.message))
                break

    def enum_probes(self) -> None:
        for t in self.om.targets:
            enum = t.schema.get("enum")
            if not enum or t.location == "path":
                continue
            ints = all(isinstance(x, int) and not isinstance(x, bool) for x in enum)
            invalid = (max(enum) + 1000) if ints else "zz_invalid_zz"
            base = self.base_for(t)
            obs = self.repeat(self.put(base, t, invalid), "S5.enum", {"param": t.label, "value": invalid})
            outs = {o.outcome for o in obs}
            if outs == {"ACCEPT"}:
                self.e.add(FindingDraft(
                    "D2", self.om.key, t.label, "enum", t.schema_ptr + "/enum",
                    f"{self.om.key}: giá trị ngoài enum {invalid!r} cho '{t.name}' vẫn được chấp nhận",
                    {"declared": enum}, _ids(obs), [], {"probe": _probe_channel(len(obs))}, True,
                    [{"op": "remove", "path": t.schema_ptr + "/enum"}]))
                continue
            if outs != {"REJECT"}:
                self.e.unverify(self.om, t.label, "enum", f"kết quả {sorted(outs)}")
                continue
            msg = obs[0].message
            msg_vals = None
            for h in hints_for(msg, t.name):
                if h.kind == "enum":
                    msg_vals = [int(x) if ints and re.fullmatch(r"-?\d+", str(x)) else x for x in h.value]
            removed, accepted, contra = [], [], []
            support = list(obs)
            cur = self.value_of(base, t)
            for v in enum:
                if v == cur:
                    continue
                o = self.send(self.put(base, t, v), "S5.enum", {"param": t.label, "value": v})
                if o.outcome == "REJECT":
                    more = self.repeat(self.put(base, t, v), "S5.enum", {"param": t.label, "value": v},
                                       max(1, self.cfg.repeats - 1))
                    if {m.outcome for m in more} == {"REJECT"}:
                        removed.append(v)
                        support += [o] + more
                elif o.outcome == "ACCEPT":
                    support.append(o)
            for v in (msg_vals or []):
                if v in enum:
                    continue
                more = self.repeat(self.put(base, t, v), "S5.enum", {"param": t.label, "value": v})
                if {m.outcome for m in more} == {"ACCEPT"}:
                    accepted.append(v)
                    support += more
                else:
                    contra += more
            if accepted or removed:
                new = [v for v in enum if v not in removed] + accepted
                channels = {"probe": _probe_channel(len(support), len(contra))}
                if msg_vals is not None and set(map(str, msg_vals)) == set(map(str, new)):
                    channels["error_message"] = R_MESSAGE_REGEX
                self.e.add(FindingDraft(
                    "D5", self.om.key, t.label, "enum", t.schema_ptr + "/enum",
                    f"{self.om.key}: enum của '{t.name}' khác thực tế – khai báo {enum}, thực tế {new}"
                    + (f" (thông báo lỗi: \"{msg}\")" if msg else ""),
                    {"declared": enum, "observed": new, "accepted_extra": accepted, "rejected_declared": removed},
                    _ids(support), _ids(contra), channels, True,
                    [{"op": "replace", "path": t.schema_ptr + "/enum", "value": new}], msg))
            else:
                ch = {"probe": _probe_channel(len(support))}
                if msg_vals is not None and set(map(str, msg_vals)) == set(map(str, enum)):
                    ch["error_message"] = R_MESSAGE_REGEX
                self.e.verify(self.om, t.label, "enum", len(support), message=msg, channels=ch)

    def wrong_type_values(self, t: Target) -> list[Any]:
        typ = t.type
        if t.location in ("query", "path", "header", "cookie"):
            return {"integer": ["abc", "1.5"], "number": ["abc"], "boolean": ["notabool"]}.get(typ, [])
        return {"integer": ["abc", 1.5], "number": ["abc"], "string": [12345], "boolean": ["notabool"],
                "array": ["notalist"], "object": ["notanobject"]}.get(typ, [])

    def type_probes(self, only_path: bool = False) -> None:
        for t in self.om.targets:
            if only_path and t.location != "path":
                continue
            if t.schema.get("enum") and t.location != "body":
                continue
            for wv in self.wrong_type_values(t):
                base = self.fresh() if t.location == "path" else self.base_for(t)
                obs = self.repeat(self.put(base, t, wv), "S4.type", {"param": t.label, "value": wv}, 1)
                if obs[0].outcome == "ACCEPT":
                    obs += self.repeat(self.put(self.fresh() if t.location == "path" else self.base_for(t), t, wv),
                                       "S4.type", {"param": t.label, "value": wv}, max(1, self.cfg.repeats - 1))
                    if {o.outcome for o in obs} == {"ACCEPT"} and t.location != "path":
                        new_t = "number" if (t.type == "integer" and isinstance(wv, float)) or wv == "1.5" else "string"
                        self.e.add(FindingDraft(
                            "D6", self.om.key, t.label, "type", t.schema_ptr + "/type",
                            f"{self.om.key}: '{t.name}' khai báo {t.type} nhưng giá trị {wv!r} vẫn được chấp nhận",
                            {"declared": t.type, "accepted_value": wv}, _ids(obs), [],
                            {"probe": _probe_channel(len(obs))}, True,
                            [{"op": "replace", "path": t.schema_ptr + "/type", "value": new_t}]))
                        break
                elif obs[0].outcome == "REJECT":
                    self.e.verify(self.om, t.label, f"type={t.type}", 1, message=obs[0].message)

    def format_probes(self) -> None:
        for t in self.om.targets:
            if t.type != "string" or t.schema.get("enum"):
                continue
            checks = []
            if t.schema.get("format") in ("date", "date-time", "email", "uuid", "uri", "ipv4"):
                checks.append(("format", "not-a-valid-value"))
            if t.schema.get("pattern"):
                bad = "!!~~"
                try:
                    if not re.search(t.schema["pattern"], bad):
                        checks.append(("pattern", bad))
                except re.error:
                    pass
            for kw, bad in checks:
                obs = self.repeat(self.put(self.base_for(t), t, bad), "S7.format", {"param": t.label, "value": bad},
                                  1)
                if obs[0].outcome == "ACCEPT":
                    obs += self.repeat(self.put(self.base_for(t), t, bad), "S7.format",
                                       {"param": t.label, "value": bad}, max(1, self.cfg.repeats - 1))
                    if {o.outcome for o in obs} == {"ACCEPT"}:
                        self.e.add(FindingDraft(
                            "D6" if kw == "format" else "D2", self.om.key, t.label, kw, t.schema_ptr + f"/{kw}",
                            f"{self.om.key}: '{t.name}' khai báo {kw}={t.schema[kw]!r} nhưng {bad!r} vẫn được chấp nhận",
                            {"declared": t.schema[kw]}, _ids(obs), [], {"probe": _probe_channel(len(obs))}, True,
                            [{"op": "remove", "path": t.schema_ptr + f"/{kw}"}]))
                elif obs[0].outcome == "REJECT":
                    self.e.verify(self.om, t.label, f"{kw}={t.schema[kw]}", 1, message=obs[0].message)

    # ------------------------------------------------------------------ S6 dò biên
    def ok_value(self, t: Target) -> tuple[bool, Any]:
        if t.label in self.base_values:
            return True, self.base_values[t.label]
        if t.label in self.single and self.single[t.label][0] == "ACCEPT":
            return True, self.single[t.label][2]
        if t.label in self.companions and t.label in self.single:
            return True, self.single[t.label][2]
        return False, None

    def boundary(self, t: Target) -> None:
        typ = t.type
        s = t.schema
        if s.get("enum") or typ not in ("integer", "number", "string", "array"):
            return
        if typ == "string" and (s.get("format") or s.get("pattern")):
            return
        if t.location in ("header", "cookie"):
            return
        ok, val = self.ok_value(t)
        if not ok:
            self.e.unverify(self.om, t.label, "biên", "không có giá trị cơ sở được chấp nhận")
            return
        if typ == "string":
            kind, lo_kw, hi_kw = "length", "minLength", "maxLength"
            try:
                okv = len(str(val))
            except TypeError:
                return
        elif typ == "array":
            kind, lo_kw, hi_kw = "items", "minItems", "maxItems"
            okv = len(val) if isinstance(val, list) else 1
        else:
            kind, lo_kw, hi_kw = "value", "minimum", "maximum"
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                try:
                    val = float(val) if typ == "number" else int(val)
                except (TypeError, ValueError):
                    return
            okv = val
        integer = typ != "number"
        msgs: list[str] = []
        obs_all: list[Obs] = []

        def make(v):
            if kind == "length":
                return string_of_length(int(v))
            if kind == "items":
                return array_of_length(int(v), s, self.e.spec)
            return int(v) if typ == "integer" else v

        def probe(v):
            if kind != "value" and v < 0:
                return bd.REJECT
            req = self.put(self.base_for(t) if t.location != "path" else self.fresh(), t, make(v))
            o = self.send(req, "S6.boundary", {"param": t.label, "kind": kind, "value": v})
            obs_all.append(o)
            if o.outcome == "ACCEPT":
                return bd.ACCEPT
            if o.outcome == "REJECT":
                if o.message:
                    msgs.append(o.message)
                if is_referential(o.message, t.name):
                    return bd.INFO
                return bd.REJECT
            return bd.UNKNOWN

        for upper in (False, True):
            kw = hi_kw if upper else lo_kw
            ex_kw = ("exclusiveMaximum" if upper else "exclusiveMinimum") if kind == "value" else None
            declared = s.get(kw)
            declared_ex = bool(ex_kw and s.get(ex_kw) is True)
            if t.location == "path" and upper and declared is None:
                continue
            res = None
            if declared is not None:
                res = bd.verify_declared(probe, declared, upper=upper, exclusive=declared_ex, integer=integer)
                if res.status == "bound":
                    hs = [h for m in msgs for h in hints_for(m, t.name)]
                    self.e.verify(self.om, t.label, f"{kw}={declared}" + (" (exclusive)" if declared_ex else ""),
                                  res.n_support, channels={"probe": _probe_channel(res.n_support),
                                                           **({"error_message": R_MESSAGE_REGEX} if hs else {})})
                    continue
                if res.status != "mismatch":
                    if res.status == "info":
                        self.info(t, msgs, obs_all)
                    else:
                        self.e.unverify(self.om, t.label, kw, res.reason or "không xác định")
                    continue
            if t.location == "path":
                continue
            floor = 0 if kind != "value" else None
            cap = self.cfg.len_cap if kind == "length" else self.cfg.items_cap if kind == "items" else self.cfg.int_cap
            full = bd.search(probe, okv, upper=upper, integer=integer, cap=cap, floor=floor)
            if full.status == "info":
                self.info(t, msgs, obs_all)
                break
            if full.status == "unknown":
                self.e.unverify(self.om, t.label, kw, full.reason)
                continue
            self.bound_finding(t, kind, kw, ex_kw, declared, declared_ex, full, msgs, obs_all, upper)

    def bound_finding(self, t, kind, kw, ex_kw, declared, declared_ex, res: bd.BoundResult, msgs, obs_all, upper):
        observed = res.value if res.status == "bound" else None
        if kind != "value" and not upper and observed == 0:
            observed = None  # minLength/minItems = 0 không phải ràng buộc
        obs_ex = bool(res.exclusive) if observed is not None else False
        if observed is None and declared is None:
            return
        if observed is not None and declared is not None and observed == declared and obs_ex == declared_ex:
            self.e.verify(self.om, t.label, f"{kw}={declared}", res.n_support)
            return
        sp = t.schema_ptr
        patch: list[dict] = []
        if observed is None:
            code = "D2"
            patch.append({"op": "remove", "path": f"{sp}/{kw}"})
            if ex_kw and declared_ex:
                patch.append({"op": "remove", "path": f"{sp}/{ex_kw}"})
            summary = (f"{self.om.key}: '{t.name}' khai báo {kw}={declared} nhưng không tìm thấy biên "
                       f"({res.reason})")
        else:
            patch.append({"op": "replace" if declared is not None else "add", "path": f"{sp}/{kw}", "value": observed})
            if ex_kw:
                if obs_ex and not declared_ex:
                    patch.append({"op": "add", "path": f"{sp}/{ex_kw}", "value": True})
                elif declared_ex and not obs_ex:
                    patch.append({"op": "remove", "path": f"{sp}/{ex_kw}"})
            if declared is None:
                code = "D1"
                summary = (f"{self.om.key}: '{t.name}' thiếu ràng buộc – quan sát được {kw}={observed}"
                           + (" (loại trừ)" if obs_ex else ""))
            elif observed == declared:
                code = "D2"
                patch = [p for p in patch if p["path"] != f"{sp}/{kw}"]
                summary = (f"{self.om.key}: '{t.name}' khai báo {kw}={declared}"
                           f"{' loại trừ' if declared_ex else ''} nhưng thực tế "
                           f"{'loại trừ' if obs_ex else 'bao gồm'} biên – ràng buộc khai báo quá chặt")
            else:
                code = "D3"
                summary = f"{self.om.key}: '{t.name}' khai báo {kw}={declared} nhưng biên quan sát được là {observed}"
        ids = [o for o in obs_all if o.outcome in ("ACCEPT", "REJECT")]
        channels = {"probe": _probe_channel(len(ids))}
        msg_used = None
        if observed is not None:
            want_kw = kw
            if ex_kw and obs_ex:
                want_kw = ex_kw
            for m in msgs:
                for h in hints_for(m, t.name):
                    if h.kind == want_kw and h.value == observed:
                        channels["error_message"] = R_MESSAGE_REGEX
                        msg_used = m
        doc_conflict = declared is not None
        self.e.add(FindingDraft(code, self.om.key, t.label, kw, f"{sp}/{kw}", summary,
                                {"declared": declared, "declared_exclusive": declared_ex, "observed": observed,
                                 "observed_exclusive": obs_ex, "kind": kind, "probes": len(obs_all)},
                                _ids(ids), [], channels, doc_conflict, patch, msg_used))

    def info(self, t: Target, msgs: list[str], obs_all: list[Obs]) -> None:
        if any(f.code == "INFO" and f.op == self.om.key and f.location == t.label for f in self.e.findings):
            return
        msg = next((m for m in msgs if is_referential(m, t.name)), msgs[-1] if msgs else None)
        rej = [o for o in obs_all if o.outcome == "REJECT"]
        self.e.add(FindingDraft(
            "INFO", self.om.key, t.label, None, t.schema_ptr,
            f"{self.om.key}: '{t.name}' bị từ chối vì lý do không phải ràng buộc miền giá trị "
            f"(\"{msg}\") – chỉ báo cáo, không sửa đặc tả", {"reason": "referential"}, _ids(rej), [],
            {"probe": _probe_channel(len(rej))}, False, None, msg))

    # ------------------------------------------------------------------ S2, S9
    def robustness(self, only_path: bool = False) -> None:
        base_ok = self.base is not None
        for t in self.om.targets:
            if only_path and t.location != "path":
                continue
            if t.type not in ("integer", "number") or t.schema.get("enum") or t.location in ("header", "cookie"):
                continue
            for v in ROBUST_INTS:
                if base_ok:
                    req = self.put(self.fresh() if t.location == "path" else self.base_for(t), t, v)
                else:
                    req = self.put(self.initial_request(), t, v)
                self.send(req, "S2.robustness", {"param": t.label, "value": v})
            if t.location == "path" and base_ok:
                # tài nguyên không tồn tại – lặp lại để có đủ bằng chứng cho mã trạng thái tương ứng
                for i in range(self.cfg.repeats):
                    self.send(self.put(self.fresh(), t, 987654321), "S2.notfound",
                              {"param": t.label, "value": 987654321}, repeat=i)

    def sampling(self) -> None:
        reqs: list[tuple[ProbeRequest, dict]] = []
        for t in self.om.params:
            if t.location != "query":
                continue
            for v in (t.schema.get("enum") or [])[:6]:
                reqs.append((self.put(self.fresh(), t, v), {"param": t.label, "value": v}))
            if t.type == "integer" and re.search(r"page|offset|skip", t.name, re.I):
                start = t.schema.get("minimum", 1)
                for v in (start + 1, start + 2):
                    reqs.append((self.put(self.fresh(), t, v), {"param": t.label, "value": v}))
        for req, probe in reqs[: self.cfg.sample_size]:
            self.send(req, "S9.sampling", probe)


def run_engine(spec: dict, prober: Prober, cfg: EngineConfig, progress=None) -> Engine:
    eng = Engine(spec, prober, cfg, progress)
    eng.run()
    return eng


__all__ = ["Engine", "EngineConfig", "FindingDraft", "run_engine", "MISSING"]
