"""CLI thực nghiệm: python -m app.experiments --config experiments.yaml [--out data/experiments/<tên>]

Ví dụ experiments.yaml:
    name: rq-bookstore
    apis: [bookstore-lab]          # hoặc [all]
    models: [fake]                 # "fake" = FakeLLM; tên khác dùng LLM_BASE_URL/LLM_API_KEY trong .env
    configs: [C0, C1, C2]
    repeats: 3
    doc_variant: original          # original | rendered | ablated
    base_url_overrides: {bookstore-lab: http://localhost:8000/v1}
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

from .config import get_settings
from .db import init_db
from .services.experiments import run_matrix


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8")) or {}
    name = cfg.get("name", "experiment")
    out = Path(a.out) if a.out else Path(get_settings().DATA_DIR) / "experiments" / (
        f"{name}-{datetime.now():%Y%m%d-%H%M%S}")
    init_db()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    res = run_matrix(cfg, out)
    print(f"\nĐã ghi: {out / 'results.csv'} và {out / 'summary.md'}")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return 0 if res["summary"]["ok_rows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
