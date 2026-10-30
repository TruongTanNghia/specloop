"""Độ tin cậy đề xuất (TECH_SPEC 5.5.6): noisy-OR trên các kênh, kênh probe = cận dưới Wilson."""
from __future__ import annotations

import math

Z = 1.96
R_MESSAGE_REGEX = 0.8
R_MESSAGE_LLM = 0.6
R_DOC = 0.7
AUTO_THRESHOLD = 0.8
REVIEW_THRESHOLD = 0.5


def wilson_lower(s: int, n: int, z: float = Z) -> float:
    if n <= 0:
        return 0.0
    p = s / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def noisy_or(channels: dict[str, float]) -> float:
    prod = 1.0
    for r in channels.values():
        prod *= 1 - max(0.0, min(1.0, r))
    return round(1 - prod, 4)


def tier(confidence: float, doc_conflict: bool) -> str:
    """auto: được tự chấp nhận; review: cần duyệt; suggestion: chỉ gợi ý."""
    if confidence >= AUTO_THRESHOLD and not doc_conflict:
        return "auto"
    if confidence >= REVIEW_THRESHOLD:
        return "review"
    return "suggestion"
