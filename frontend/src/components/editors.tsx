// Monaco (đóng gói cục bộ, không tải từ CDN) – YamlEditor và DiffView, theme tối "specloop".
import Editor, { DiffEditor, loader, type OnMount } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { FONT_MONO } from "../theme";

(self as any).MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

monaco.editor.defineTheme("specloop", {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "type", foreground: "d4ff3a" }, // khóa YAML
    { token: "string", foreground: "e7ecef" },
    { token: "number", foreground: "ffb547" },
    { token: "keyword", foreground: "5ce1e6" },
    { token: "comment", foreground: "5b6672", fontStyle: "italic" },
    { token: "operators", foreground: "8a96a3" },
  ],
  colors: {
    "editor.background": "#0d1013",
    "editor.foreground": "#e7ecef",
    "editorGutter.background": "#0d1013",
    "editorLineNumber.foreground": "#3b4650",
    "editorLineNumber.activeForeground": "#8a96a3",
    "editor.lineHighlightBackground": "#141920",
    "editor.selectionBackground": "#2b3a14",
    "editor.inactiveSelectionBackground": "#1d2616",
    "editorCursor.foreground": "#d4ff3a",
    "editorIndentGuide.background1": "#1b2229",
    "editorIndentGuide.activeBackground1": "#2a333d",
    "editorWidget.background": "#161b21",
    "editorWidget.border": "#232b34",
    "scrollbarSlider.background": "#262f3980",
    "scrollbarSlider.hoverBackground": "#36414dcc",
    "diffEditor.insertedTextBackground": "#d4ff3a22",
    "diffEditor.removedTextBackground": "#ff6b4a2a",
    "diffEditor.insertedLineBackground": "#d4ff3a10",
    "diffEditor.removedLineBackground": "#ff6b4a14",
    "diffEditorGutter.insertedLineBackground": "#d4ff3a18",
    "diffEditorGutter.removedLineBackground": "#ff6b4a1c",
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
