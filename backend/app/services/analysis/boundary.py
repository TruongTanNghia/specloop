"""Thuật toán dò biên (TECH_SPEC 5.5.2): tìm kiếm mũ để gặp giá trị bị từ chối đầu tiên, rồi tìm kiếm nhị phân,
cuối cùng xác nhận (ok phải ACCEPT, ok±1 phải REJECT). Áp dụng cho số, độ dài chuỗi và số phần tử mảng.

`probe(v)` trả về một nhãn: ACCEPT | REJECT | INFO (từ chối không phải ràng buộc miền giá trị, vd. id không tồn tại)
| UNKNOWN (5xx/404/401/429...: không đủ bằng chứng).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ACCEPT, REJECT, INFO, UNKNOWN = "ACCEPT", "REJECT", "INFO", "UNKNOWN"

ProbeFn = Callable[[float | int], str]


class Stop(Exception):
    """Hết ngân sách / bị hủy – dừng dò."""


@dataclass
class BoundResult:
    status: str                    # bound | none | unknown | info
    value: float | int | None = None
    exclusive: bool = False
    verified_declared: bool = False
    accepted: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    reason: str = ""

    @property
    def n_support(self) -> int:
        return len(self.accepted) + len(self.rejected)


def _run(probe: ProbeFn, v, res: BoundResult) -> str:
    out = probe(v)
    if out == ACCEPT:
        res.accepted.append(v)
    elif out == REJECT:
        res.rejected.append(v)
    return out


def verify_declared(probe: ProbeFn, bound, *, upper: bool, exclusive: bool, integer: bool,
                    delta: float = 0.01) -> BoundResult:
    """Kiểm chứng nhanh biên đã khai báo bằng 2 probe."""
    res = BoundResult("unknown")
    d = 1 if integer else delta
    sign = 1 if upper else -1
    if exclusive:
        inside, outside = bound - sign * d, bound
    else:
        inside, outside = bound, bound + sign * d
    if integer:
        inside, outside = int(inside), int(outside)
    a = _run(probe, inside, res)
    b = _run(probe, outside, res)
    if a == ACCEPT and b == REJECT:
        res.status, res.value, res.exclusive, res.verified_declared = "bound", bound, exclusive, True
    elif INFO in (a, b):
        res.status, res.reason = "info", "từ chối không phải ràng buộc miền giá trị"
    elif UNKNOWN in (a, b):
        res.reason = "phản hồi không đủ bằng chứng"
    else:
        res.status = "mismatch"
    return res


def search(probe: ProbeFn, ok, *, upper: bool, integer: bool = True, cap: float = 10 ** 9,
           floor: float | None = None, confirm: bool = True) -> BoundResult:
    """ok: giá trị đã biết được ACCEPT. Trả về biên (bao gồm) theo hướng upper/lower.

    floor: giới hạn tự nhiên (vd. 0 cho độ dài) – nếu giá trị ở floor vẫn ACCEPT thì không có biên.
    """
    res = BoundResult("unknown")
    sign = 1 if upper else -1
    step = max(1, abs(ok)) if integer else max(1.0, abs(ok))
    bad = None
    # 1) tìm kiếm mũ
    while True:
        cand = ok + sign * step
        if floor is not None and not upper and cand < floor:
            cand = floor
        if abs(cand) > cap:
            res.status, res.reason = "none", f"không có biên trong phạm vi ±{cap:g}"
            return res
        out = _run(probe, int(cand) if integer else cand, res)
        if out == ACCEPT:
            ok = cand
            if floor is not None and not upper and cand <= floor:
                res.status, res.reason = "none", "giá trị nhỏ nhất tự nhiên vẫn được chấp nhận"
                return res
            step *= 2
        elif out == REJECT:
            bad = cand
            break
        elif out == INFO:
            res.status, res.reason = "info", "từ chối không phải ràng buộc miền giá trị"
            return res
        else:
            res.reason = "phản hồi không đủ bằng chứng (5xx/404/401...)"
            return res
    # 2) tìm kiếm nhị phân trong (ok, bad)
    while abs(bad - ok) > 1:
        mid = (ok + bad) // 2 if integer else int((ok + bad) / 2)
        if mid in (ok, bad):
            break
        out = _run(probe, mid, res)
        if out == ACCEPT:
            ok = mid
        elif out == REJECT:
            bad = mid
        elif out == INFO:
            res.status, res.reason = "info", "từ chối không phải ràng buộc miền giá trị"
            return res
        else:
            res.reason = "phản hồi không đủ bằng chứng"
            return res
    ok, bad = (int(ok), int(bad)) if integer or float(ok).is_integer() and float(bad).is_integer() else (ok, bad)
    exclusive = False
    value = ok
    if not integer:
        # biên số thực: thử nửa khoảng để phân biệt bao gồm / loại trừ
        half = ok + sign * 0.5
        out = _run(probe, half, res)
        if out == ACCEPT:
            value, exclusive = bad, True
        elif out not in (REJECT,):
            res.reason = "không xác định được tính bao gồm"
            return res
    # 3) xác nhận
    if confirm:
        a = _run(probe, ok, res)
        b = _run(probe, bad, res)
        if not (a == ACCEPT and b == REJECT):
            res.reason = "xác nhận thất bại (miền chấp nhận không phải một khoảng / không ổn định)"
            return res
    res.status, res.value, res.exclusive = "bound", value, exclusive
    return res
