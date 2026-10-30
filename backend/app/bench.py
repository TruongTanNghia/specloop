"""Cầu nối tới mã có sẵn trong SpecLoop-Bench/tools (tái sử dụng bằng import, không viết lại)."""
from __future__ import annotations

import sys
from pathlib import Path

from .config import get_settings

BENCH_DIR = Path(get_settings().BENCH_DIR)
_TOOLS = BENCH_DIR / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import evaluate as bench_evaluate  # noqa: E402
import extract_facts as bench_facts  # noqa: E402
import oas_utils  # noqa: E402

__all__ = ["BENCH_DIR", "bench_evaluate", "bench_facts", "oas_utils", "api_dir"]


def api_dir(api_id: str) -> Path:
    return BENCH_DIR / "apis" / api_id
