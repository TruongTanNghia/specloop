"""Prompt trích xuất IR (giữ tiếng Anh – TECH_SPEC Phụ lục A)."""
from __future__ import annotations

import json

from ...schemas.ir import ir_json_schema

SYSTEM_EXTRACT = (
    "You are an API specification extractor. Read ONE documentation section and return ONLY a JSON object that "
    "validates against the provided JSON Schema (OperationIR). Rules: 1) Extract only facts explicitly stated in "
    "SECTION or GLOBAL CONTEXT; never guess or use prior knowledge about this API. 2) For every parameter, body "
    "field, response and constraint, copy a verbatim quote (<= 200 chars) into \"evidence\". 3) If a property is not "
    "stated, omit it; do not invent defaults. 4) Use JSON Schema types. 5) Write path variables as {name}; remove "
    "the server base URL from paths. 6) Express inter-parameter dependencies in IDL form, e.g. \"IF order THEN "
    "sort;\". 7) If SECTION does not describe an API operation, return {\"operation\": null}."
)

USER_EXTRACT = """GLOBAL CONTEXT (authentication, pagination, common errors):
{global_context}

SECTION:
{chunk_text}

JSON Schema (OperationIR):
{schema}"""

SYSTEM_REPAIR = (
    "You fix ONE OpenAPI 3.0.3 operation object so that it passes validation. Return ONLY a JSON object of the form "
    "{\"operation_object\": {...}} containing the corrected operation object. Do not add facts that are not "
    "already present; only fix structural problems reported in ERRORS."
)

USER_REPAIR = """PATH: {path}
METHOD: {method}
ERRORS:
{errors}

OPERATION OBJECT:
{operation}"""

SYSTEM_MESSAGE = (
    "You read ONE error message returned by a REST API and extract the input constraint it states. Return ONLY JSON: "
    "{\"param\": string|null, \"kind\": one of [minimum, maximum, minLength, maxLength, enum, pattern, format, "
    "required, minItems, maxItems, dependency, none], \"value\": any, \"confidence\": number 0..1}."
)

_SCHEMA_TEXT: str | None = None


def schema_text() -> str:
    global _SCHEMA_TEXT
    if _SCHEMA_TEXT is None:
        _SCHEMA_TEXT = json.dumps(ir_json_schema(), separators=(",", ":"))
    return _SCHEMA_TEXT


def build_extract_prompt(global_context: str, chunk_text: str) -> tuple[str, str]:
    user = USER_EXTRACT.format(global_context=global_context or "(none)", chunk_text=chunk_text,
                               schema=schema_text())
    return SYSTEM_EXTRACT, user
