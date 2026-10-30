"""Tiện ích dùng chung cho router: lỗi RFC 7807, lấy bản ghi hoặc 404."""
from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

T = TypeVar("T")


class Problem(HTTPException):
    def __init__(self, status: int, title: str, detail: str | None = None, errors: list | None = None,
                 type_: str = "about:blank"):
        super().__init__(status_code=status, detail=detail or title)
        self.title = title
        self.errors = errors or []
        self.type = type_


def get_or_404(db: Session, model: type[T], id_: Any, what: str = "Tài nguyên") -> T:
    obj = db.get(model, id_)
    if obj is None:
        raise Problem(404, "Không tìm thấy", f"{what} #{id_} không tồn tại")
    return obj
