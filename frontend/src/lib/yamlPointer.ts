// Tính JSON Pointer của phần tử tại một dòng YAML dạng block (do PyYAML/js-yaml sinh ra).

const esc = (s: string) => s.replace(/~/g, "~0").replace(/\//g, "~1");

function unquote(k: string): string {
  const t = k.trim();
  if ((t.startsWith("'") && t.endsWith("'")) || (t.startsWith('"') && t.endsWith('"'))) return t.slice(1, -1);
  return t;
}

const KEY_RE = /^((?:'[^']*'|"[^"]*"|[^:#'"][^:#]*?)):(?:\s|$)/;

interface Entry {
  indent: number;
  seg: string;
  list: boolean;
}

export function pointerAtLine(text: string, lineNumber: number): string {
  const lines = text.split("\n");
  const stack: Entry[] = [];
  const counters = new Map<string, number>();
  const path = () => stack.map((e) => e.seg).join("/");
  for (let i = 0; i < Math.min(lineNumber, lines.length); i++) {
    const raw = lines[i];
    if (!raw.trim() || raw.trim().startsWith("#")) continue;
    const indent = raw.length - raw.trimStart().length;
    let content = raw.trimStart();
    if (content.startsWith("- ") || content === "-") {
      while (stack.length && (stack[stack.length - 1].indent > indent ||
        (stack[stack.length - 1].indent === indent && stack[stack.length - 1].list))) stack.pop();
      // phần tử danh sách có thể không thụt lề so với khóa cha
      const key = path();
      const idx = counters.get(key) ?? 0;
      counters.set(key, idx + 1);
      stack.push({ indent, seg: String(idx), list: true });
      content = content.slice(2);
      const m = KEY_RE.exec(content);
      if (m) stack.push({ indent: indent + 2, seg: unquote(m[1]), list: false });
      continue;
    }
    const m = KEY_RE.exec(content);
    if (!m) continue;
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    const seg = unquote(m[1]);
    stack.push({ indent, seg, list: false });
    counters.delete(path());
  }
  return stack.length ? "/" + stack.map((e) => esc(e.seg)).join("/") : "";
}

/** Dòng (1-based) đầu tiên ứng với pointer – dùng để nhảy từ đề xuất tới YAML. */
export function lineOfPointer(text: string, pointer: string): number | null {
  const lines = text.split("\n");
  for (let i = 1; i <= lines.length; i++) {
    if (pointerAtLine(text, i) === pointer) return i;
  }
  return null;
}
