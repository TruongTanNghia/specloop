"""Biểu diễn trung gian (IR) do LLM trích xuất cho từng operation (TECH_SPEC Phụ lục B)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Kind = Literal["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "pattern",
               "enum", "format", "minItems", "maxItems", "uniqueItems", "default", "nullable"]
JsonType = Literal["integer", "number", "string", "boolean", "array", "object"]


def _clip(v: Any, n: int = 300) -> Any:
    return v[:n] if isinstance(v, str) else v


class ConstraintIR(BaseModel):
    kind: Kind
    value: Any = None
    evidence: str = Field(max_length=300)

    _clip_ev = field_validator("evidence", mode="before")(lambda v: _clip(v or ""))


class ParamIR(BaseModel):
    name: str
    location: Literal["query", "path", "header", "cookie"]
    type: JsonType | None = None
    required: bool | None = None
    description: str | None = None
    constraints: list[ConstraintIR] = []
    evidence: str

    _clip_ev = field_validator("evidence", mode="before")(lambda v: _clip(v or ""))


class FieldIR(BaseModel):
    path: str  # "items[].isbn"
    type: str | None = None
    required: bool | None = None
    constraints: list[ConstraintIR] = []
    evidence: str | None = None

    _clip_ev = field_validator("evidence", mode="before")(lambda v: _clip(v))


class BodyIR(BaseModel):
    media_type: str = "application/json"
    fields: list[FieldIR] = []
    example: Any | None = None
    evidence: str

    _clip_ev = field_validator("evidence", mode="before")(lambda v: _clip(v or ""))


class ResponseIR(BaseModel):
    status: str
    description: str | None = None
    fields: list[FieldIR] = []
    example: Any | None = None
    evidence: str

    _clip_ev = field_validator("evidence", mode="before")(lambda v: _clip(v or ""))
    _status = field_validator("status", mode="before")(lambda v: str(v))


class DependencyIR(BaseModel):
    idl: str
    evidence: str

    _clip_ev = field_validator("evidence", mode="before")(lambda v: _clip(v or ""))


class OperationIR(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    path: str
    summary: str | None = None
    parameters: list[ParamIR] = []
    request_body: BodyIR | None = None
    responses: list[ResponseIR] = []
    dependencies: list[DependencyIR] = []
    security: list[str] = []

    _method = field_validator("method", mode="before")(lambda v: str(v).upper())


class ExtractionResult(BaseModel):
    """Đầu ra của LLM: một OperationIR hoặc {"operation": null}."""

    operation: OperationIR | None = None


def parse_extraction(data: Any) -> OperationIR | None:
    """Chấp nhận cả {"operation": {...}} lẫn đối tượng OperationIR trực tiếp."""
    if isinstance(data, dict) and "operation" in data and set(data) <= {"operation"}:
        return ExtractionResult.model_validate(data).operation
    if isinstance(data, dict) and data.get("operation") is None and "method" not in data:
        return None
    return OperationIR.model_validate(data)


def ir_json_schema() -> dict:
    return OperationIR.model_json_schema()
