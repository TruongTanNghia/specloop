"""M6 – phiên bản bất biến, áp dụng JSON Patch (RFC 6902), diff văn bản/ngữ nghĩa, xuất đặc tả."""
from __future__ import annotations

import copy
import difflib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...bench import oas_utils
from ...models import Evidence, SpecVersion


class PatchError(Exception):
    pass


def _parts(pointer: str) -> list[str]:
    if pointer in ("", "/"):
        return []
    if not pointer.startswith("/"):
        raise PatchError(f"JSON Pointer không hợp lệ: {pointer}")
    return [p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/")]


def _parent(doc: Any, pointer: str, create: bool) -> tuple[Any, str]:
    parts = _parts(pointer)
    if not parts:
        raise PatchError("Không thao tác trên gốc tài liệu")
    node = doc
    for p in parts[:-1]:
        if isinstance(node, list):
            node = node[int(p)]
        elif isinstance(node, dict):
            if p not in node:
                if not create:
                    raise PatchError(f"Không tồn tại: {pointer}")
                node[p] = {}
            node = node[p]
        else:
            raise PatchError(f"Không đi tiếp được tại {p} ({pointer})")
    return node, parts[-1]


def get_value(doc: Any, pointer: str) -> Any:
    node = doc
    for p in _parts(pointer):
        node = node[int(p)] if isinstance(node, list) else node[p]
    return node


def has_value(doc: Any, pointer: str) -> bool:
    try:
        get_value(doc, pointer)
        return True
    except (KeyError, IndexError, ValueError, TypeError):
        return False


def apply_patch(doc: dict, ops: list[dict], strict: bool = False) -> tuple[dict, list[str]]:
    """Áp dụng JSON Patch. Chế độ không chặt: add vào khóa đã có = replace; replace khóa chưa có = add;
    remove khóa không tồn tại = bỏ qua (ghi cảnh báo). Trả về (tài_liệu_mới, cảnh_báo)."""
    out = copy.deepcopy(doc)
    warnings: list[str] = []
    for op in ops:
        kind, path = op.get("op"), op.get("path", "")
        try:
            if kind in ("add", "replace"):
                exists = has_value(out, path)
                if kind == "replace" and not exists and strict:
                    raise PatchError(f"replace: không tồn tại {path}")
                parent, key = _parent(out, path, create=not strict)
                if isinstance(parent, list):
                    idx = len(parent) if key == "-" else int(key)
                    if kind == "add":
                        parent.insert(idx, copy.deepcopy(op["value"]))
                    else:
                        parent[idx] = copy.deepcopy(op["value"])
                else:
                    parent[key] = copy.deepcopy(op["value"])
            elif kind == "remove":
                if not has_value(out, path):
                    if strict:
                        raise PatchError(f"remove: không tồn tại {path}")
                    warnings.append(f"bỏ qua remove {path} (không tồn tại)")
                    continue
                parent, key = _parent(out, path, create=False)
                if isinstance(parent, list):
                    parent.pop(int(key))
                else:
                    parent.pop(key)
            elif kind in ("move", "copy"):
                src = op.get("from", "")
                if not has_value(out, src):
                    if strict:
                        raise PatchError(f"{kind}: không tồn tại {src}")
                    warnings.append(f"bỏ qua {kind} từ {src} (không tồn tại)")
                    continue
                val = copy.deepcopy(get_value(out, src))
                if kind == "move":
                    sp, sk = _parent(out, src, create=False)
                    sp.pop(int(sk)) if isinstance(sp, list) else sp.pop(sk)
                parent, key = _parent(out, path, create=True)
                if isinstance(parent, list):
                    parent.insert(len(parent) if key == "-" else int(key), val)
                else:
                    parent[key] = val
            elif kind == "test":
                if get_value(out, path) != op.get("value"):
                    raise PatchError(f"test thất bại tại {path}")
            else:
                raise PatchError(f"op không hỗ trợ: {kind}")
        except PatchError:
            raise
        except (KeyError, IndexError, ValueError, TypeError) as e:
            if strict:
                raise PatchError(f"{kind} {path}: {e}") from e
            warnings.append(f"bỏ qua {kind} {path}: {e}")
    return out, warnings


def touched_pointers(ops: list[dict]) -> set[str]:
    out = set()
    for o in ops:
        out.add(o.get("path", ""))
        if "from" in o:
            out.add(o["from"])
    return out


# ------------------------------------------------------------------ phiên bản
def next_version_no(db: Session, project_id: int) -> int:
    n = db.scalar(select(func.max(SpecVersion.version_no)).where(SpecVersion.project_id == project_id))
    return (n or 0) + 1


def create_version(db: Session, project_id: int, content: dict, *, label: str, parent: SpecVersion | None = None,
                   patch: list | None = None, model: str | None = None, note: str | None = None,
                   created_by: str = "system", copy_evidence: bool = True) -> SpecVersion:
    v = SpecVersion(project_id=project_id, parent_id=parent.id if parent else None,
                    version_no=next_version_no(db, project_id), label=label, content=content,
                    patch_from_parent=patch, model=model or (parent.model if parent else None), note=note,
                    created_by=created_by)
    db.add(v)
    db.flush()
    if parent is not None and copy_evidence:
        for ev in db.scalars(select(Evidence).where(Evidence.spec_version_id == parent.id)):
            if has_value(content, ev.json_pointer) or ev.json_pointer == "/":
                db.add(Evidence(spec_version_id=v.id, json_pointer=ev.json_pointer, chunk_id=ev.chunk_id,
                                quote=ev.quote, match_score=ev.match_score, span_start=ev.span_start,
                                span_end=ev.span_end))
    return v


def refined_label(db: Session, parent: SpecVersion) -> str:
    k = 1
    node = parent
    while node is not None:
        if node.label.startswith("refined-"):
            try:
                k = int(node.label.split("-")[1]) + 1
            except ValueError:
                pass
            break
        node = db.get(SpecVersion, node.parent_id) if node.parent_id else None
    return f"refined-{k}"


def diff_patch(a: dict, b: dict, prefix: str = "") -> list[dict]:
    """Sinh JSON Patch tối giản a → b (dùng cho sửa tay)."""
    ops: list[dict] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            p = f"{prefix}/{str(k).replace('~', '~0').replace('/', '~1')}"
            if k not in b:
                ops.append({"op": "remove", "path": p})
            else:
                ops += diff_patch(a[k], b[k], p)
        for k in b:
            if k not in a:
                ops.append({"op": "add", "path": f"{prefix}/{str(k).replace('~', '~0').replace('/', '~1')}",
                            "value": b[k]})
        return ops
    if a != b:
        ops.append({"op": "replace", "path": prefix or "/", "value": b})
    return ops


# ------------------------------------------------------------------ diff và xuất
def to_yaml(content: dict) -> str:
    return oas_utils.dump_yaml(content)


def text_diff(a: dict, b: dict, a_name: str = "a", b_name: str = "b") -> str:
    return "".join(difflib.unified_diff(to_yaml(a).splitlines(True), to_yaml(b).splitlines(True),
                                        fromfile=a_name, tofile=b_name, n=3))


def semantic_diff(a: dict, b: dict) -> dict:
    from deepdiff import DeepDiff

    dd = DeepDiff(a, b, ignore_order=True, view="tree")
    by_op: dict[str, list[dict]] = {}
    for change_type, items in dd.items():
        for it in items:
            path = it.path(output_format="list")
            if len(path) >= 3 and path[0] == "paths":
                key = f"{str(path[2]).upper()} {path[1]}"
            elif path and path[0] == "components":
                key = "components/" + "/".join(str(x) for x in path[1:3])
            else:
                key = "(chung)"
            entry = {"type": change_type, "path": "/" + "/".join(str(x) for x in path)}
            if hasattr(it, "t1") and change_type != "dictionary_item_added":
                entry["old"] = _short(it.t1)
            if hasattr(it, "t2") and change_type != "dictionary_item_removed":
                entry["new"] = _short(it.t2)
            by_op.setdefault(key, []).append(entry)
    return {"changes": sum(len(v) for v in by_op.values()), "by_operation": by_op}


def _short(v: Any) -> Any:
    try:
        s = json.dumps(v, ensure_ascii=False, default=str)
    except TypeError:
        s = str(v)
    if len(s) > 300:
        return s[:300] + "…"
    return v if not isinstance(v, type) else str(v)


def strip_extensions(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: strip_extensions(v) for k, v in node.items() if not str(k).startswith("x-")}
    if isinstance(node, list):
        return [strip_extensions(x) for x in node]
    return node


def with_evidence(content: dict, evidence: list[Evidence]) -> dict:
    """Xuất kèm x-evidence tại nút cha của mỗi pointer."""
    out = copy.deepcopy(content)
    for ev in evidence:
        parts = _parts(ev.json_pointer)
        node = out
        try:
            for p in parts:
                nxt = node[int(p)] if isinstance(node, list) else node[p]
                if not isinstance(nxt, (dict, list)):
                    break
                node = nxt
        except (KeyError, IndexError, ValueError):
            continue
        if isinstance(node, dict):
            node.setdefault("x-evidence", [])
            if ev.quote not in node["x-evidence"]:
                node["x-evidence"].append(ev.quote)
    return out
