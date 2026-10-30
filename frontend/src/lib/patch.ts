// Áp dụng JSON Patch phía client (cùng quy tắc "không chặt" với backend) để xem trước YAML trước/sau.
import yaml from "js-yaml";
import type { JsonPatchOp } from "../api/types";

function parts(pointer: string): string[] {
  if (pointer === "" || pointer === "/") return [];
  return pointer.slice(1).split("/").map((p) => p.replace(/~1/g, "/").replace(/~0/g, "~"));
}

function getAt(doc: any, pointer: string): { ok: boolean; value?: any } {
  let node = doc;
  for (const p of parts(pointer)) {
    if (node === null || typeof node !== "object" || !(p in node)) return { ok: false };
    node = Array.isArray(node) ? node[Number(p)] : node[p];
  }
  return { ok: true, value: node };
}

function parentOf(doc: any, pointer: string, create: boolean): [any, string] | null {
  const ps = parts(pointer);
  if (!ps.length) return null;
  let node = doc;
  for (const p of ps.slice(0, -1)) {
    if (Array.isArray(node)) node = node[Number(p)];
    else if (node && typeof node === "object") {
      if (!(p in node)) {
        if (!create) return null;
        node[p] = {};
      }
      node = node[p];
    } else return null;
  }
  return [node, ps[ps.length - 1]];
}

export function applyPatch(doc: any, ops: JsonPatchOp[]): { result: any; warnings: string[] } {
  const out = structuredClone(doc);
  const warnings: string[] = [];
  for (const op of ops) {
    const clone = (v: any) => (v === undefined ? v : structuredClone(v));
    if (op.op === "add" || op.op === "replace") {
      const pr = parentOf(out, op.path, true);
      if (!pr) { warnings.push(`bỏ qua ${op.op} ${op.path}`); continue; }
      const [parent, key] = pr;
      if (Array.isArray(parent)) {
        const idx = key === "-" ? parent.length : Number(key);
        if (op.op === "add") parent.splice(idx, 0, clone(op.value));
        else parent[idx] = clone(op.value);
      } else parent[key] = clone(op.value);
    } else if (op.op === "remove") {
      if (!getAt(out, op.path).ok) { warnings.push(`bỏ qua remove ${op.path} (không tồn tại)`); continue; }
      const [parent, key] = parentOf(out, op.path, false)!;
      if (Array.isArray(parent)) parent.splice(Number(key), 1);
      else delete parent[key];
    } else if (op.op === "move" || op.op === "copy") {
      const src = getAt(out, op.from ?? "");
      if (!src.ok) { warnings.push(`bỏ qua ${op.op} từ ${op.from}`); continue; }
      const val = structuredClone(src.value);
      if (op.op === "move") {
        const [sp, sk] = parentOf(out, op.from ?? "", false)!;
        if (Array.isArray(sp)) sp.splice(Number(sk), 1);
        else delete sp[sk];
      }
      const pr = parentOf(out, op.path, true);
      if (pr) {
        const [parent, key] = pr;
        if (Array.isArray(parent)) parent.splice(key === "-" ? parent.length : Number(key), 0, val);
        else parent[key] = val;
      }
    }
  }
  return { result: out, warnings };
}

export function toYaml(doc: any): string {
  return yaml.dump(doc, { noRefs: true, lineWidth: 110, sortKeys: false });
}

/** Lấy nút con nhỏ nhất bao phủ mọi đường dẫn trong patch – để xem trước gọn. */
export function patchScope(ops: JsonPatchOp[]): string {
  const all = ops.flatMap((o) => [o.path, ...(o.from ? [o.from] : [])]).map(parts);
  if (!all.length) return "";
  const common: string[] = [];
  for (let i = 0; ; i++) {
    const seg = all[0][i];
    if (seg === undefined || !all.every((p) => p[i] === seg)) break;
    common.push(seg);
  }
  // lùi về cấp operation/schema để có ngữ cảnh
  const keep = common.slice(0, Math.max(0, common.length - 1));
  return keep.length ? "/" + keep.map((s) => s.replace(/~/g, "~0").replace(/\//g, "~1")).join("/") : "";
}

export function subtree(doc: any, pointer: string): any {
  const r = getAt(doc, pointer);
  return r.ok ? r.value : undefined;
}
