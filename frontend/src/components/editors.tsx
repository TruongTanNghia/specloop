// Monaco (đóng gói cục bộ, không tải từ CDN) – YamlEditor và DiffView.
import Editor, { DiffEditor, loader, type OnMount } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

(self as any).MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

export function YamlEditor({ value, onChange, readOnly, height = 560, onMount, language = "yaml" }: {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  height?: number | string;
  onMount?: OnMount;
  language?: string;
}) {
  return (
    <Editor
      height={height}
      language={language}
      value={value}
      onChange={(v) => onChange?.(v ?? "")}
      onMount={onMount}
      options={{ readOnly, minimap: { enabled: false }, fontSize: 12, wordWrap: "on", scrollBeyondLastLine: false }}
    />
  );
}

export function DiffView({ original, modified, height = 520, language = "yaml" }: {
  original: string;
  modified: string;
  height?: number | string;
  language?: string;
}) {
  return (
    <DiffEditor
      height={height}
      language={language}
      original={original}
      modified={modified}
      options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false }, fontSize: 12 }}
    />
  );
}

export type { OnMount };
