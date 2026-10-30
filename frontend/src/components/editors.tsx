// Monaco (đóng gói cục bộ, không tải từ CDN) – YamlEditor và DiffView, theme sáng "specloop" cùng bảng màu giao diện.
import Editor, { DiffEditor, loader, type OnMount } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { FONT_MONO } from "../theme";

(self as any).MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

monaco.editor.defineTheme("specloop", {
  base: "vs",
  inherit: true,
  rules: [
    { token: "type", foreground: "0b5cd6" }, // khóa YAML
    { token: "string", foreground: "1f2937" },
    { token: "number", foreground: "b45309" },
    { token: "keyword", foreground: "6d28d9" },
    { token: "comment", foreground: "6b7280", fontStyle: "italic" },
    { token: "operators", foreground: "6b7280" },
  ],
  colors: {
    "editor.background": "#ffffff",
    "editor.foreground": "#111827",
    "editorLineNumber.foreground": "#b4bcc8",
    "editorLineNumber.activeForeground": "#6b7280",
    "editor.lineHighlightBackground": "#f3f7fd",
    "editor.selectionBackground": "#cfe0fb",
    "editorCursor.foreground": "#0b5cd6",
    "editorIndentGuide.background1": "#eef1f5",
    "editorIndentGuide.activeBackground1": "#d5dbe4",
    "diffEditor.insertedTextBackground": "#1e9e4a33",
    "diffEditor.removedTextBackground": "#d32f2f2e",
    "diffEditor.insertedLineBackground": "#1e9e4a14",
    "diffEditor.removedLineBackground": "#d32f2f12",
  },
});
// Font mono tự đóng gói nạp sau khi Monaco đo chữ → đo lại để con trỏ khớp cột.
document.fonts?.ready.then(() => monaco.editor.remeasureFonts());

const BASE = { minimap: { enabled: false }, fontSize: 12.5, fontFamily: FONT_MONO, scrollBeyondLastLine: false, padding: { top: 10 },
  renderLineHighlight: "line" as const, smoothScrolling: true };

export function YamlEditor({ value, onChange, readOnly, height = 560, onMount, language = "yaml" }: {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  height?: number | string;
  onMount?: OnMount;
  language?: string;
}) {
  return (
    <div className="monaco-frame">
      <Editor
        height={height}
        language={language}
        theme="specloop"
        value={value}
        onChange={(v) => onChange?.(v ?? "")}
        onMount={onMount}
        options={{ ...BASE, readOnly, wordWrap: "on" }}
      />
    </div>
  );
}

export function DiffView({ original, modified, height = 520, language = "yaml" }: {
  original: string;
  modified: string;
  height?: number | string;
  language?: string;
}) {
  return (
    <div className="monaco-frame">
      <DiffEditor
        height={height}
        language={language}
        theme="specloop"
        original={original}
        modified={modified}
        options={{ ...BASE, readOnly: true, renderSideBySide: true }}
      />
    </div>
  );
}

export type { OnMount };
