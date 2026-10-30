// SC-03: nạp tài liệu (tệp / URL / dán) và quản lý phân đoạn (gộp, tách, sửa, đánh dấu chung).
import { InboxOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App, Button, Card, Checkbox, Col, Empty, Input, InputNumber, List, Modal, Popconfirm, Row, Segmented, Select, Space, Switch,
  Tag, Typography, Upload,
} from "antd";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, errorText } from "../../api/client";
import type { Chunk } from "../../api/types";
import { ErrorAlert, fmtDate, Section } from "../../components/common";
import type { TabProps } from "./types";

export default function DocumentsTab({ project, goTab }: TabProps) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [mode, setMode] = useState<"text" | "url" | "file">("text");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [docId, setDocId] = useState<number | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [editing, setEditing] = useState<Chunk | null>(null);
  const [splitting, setSplitting] = useState<{ chunk: Chunk; offset: number } | null>(null);
  const [view, setView] = useState<"chunks" | "markdown">("chunks");

  const docs = useQuery({ queryKey: ["documents", project.id], queryFn: () => api.documents(project.id) });
  const currentDoc = docId ?? docs.data?.[0]?.id ?? null;
  const doc = useQuery({ queryKey: ["document", currentDoc], queryFn: () => api.document(currentDoc!), enabled: !!currentDoc });
  const chunks = useQuery({ queryKey: ["chunks", currentDoc], queryFn: () => api.chunks(currentDoc!), enabled: !!currentDoc });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["documents", project.id] });
    qc.invalidateQueries({ queryKey: ["chunks", currentDoc] });
    qc.invalidateQueries({ queryKey: ["project", project.id] });
  };
  const onErr = (e: unknown) => message.error(errorText(e));
  const add = useMutation({
    mutationFn: async (file?: File) => {
      if (file) return api.addDocumentFile(project.id, file);
      if (mode === "url") return api.addDocumentJson(project.id, { url });
      return api.addDocumentJson(project.id, { text, format: "markdown" });
    },
    onSuccess: (d) => {
      message.success(`Đã nạp tài liệu #${d.id} (${d.chunk_count} phân đoạn)`);
      setDocId(d.id);
      setText("");
      setUrl("");
      refresh();
    },
    onError: onErr,
  });
  const merge = useMutation({
    mutationFn: () => api.mergeChunks(currentDoc!, selected),
    onSuccess: () => { setSelected([]); refresh(); }, onError: onErr,
  });
  const split = useMutation({
    mutationFn: (v: { id: number; offset: number }) => api.splitChunk(v.id, v.offset),
    onSuccess: () => { setSplitting(null); refresh(); }, onError: onErr,
  });
  const update = useMutation({
    mutationFn: (c: Chunk) => api.updateChunk(c.id, { title: c.title, text: c.text, is_global: c.is_global }),
    onSuccess: () => { setEditing(null); refresh(); }, onError: onErr,
  });
  const removeChunk = useMutation({ mutationFn: api.deleteChunk, onSuccess: refresh, onError: onErr });
  const resegment = useMutation({ mutationFn: () => api.resegment(currentDoc!), onSuccess: refresh, onError: onErr });
  const removeDoc = useMutation({
    mutationFn: api.deleteDocument, onSuccess: () => { setDocId(null); refresh(); }, onError: onErr,
  });

  const ops = (chunks.data ?? []).filter((c) => c.operation_hint).length;
  return (
    <Row gutter={16}>
      <Col xs={24} xl={9}>
        <Card title="Nạp tài liệu" size="small">
          <Segmented value={mode} onChange={(v) => setMode(v as typeof mode)} style={{ marginBottom: 12 }}
            options={[{ value: "text", label: "Dán văn bản" }, { value: "url", label: "URL" }, { value: "file", label: "Tải tệp" }]} />
          {mode === "text" && (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Input.TextArea data-testid="doc-text" rows={12} value={text} onChange={(e) => setText(e.target.value)}
                placeholder="Dán tài liệu REST API (Markdown, HTML hoặc văn bản)…" />
              <Button type="primary" data-testid="doc-submit" disabled={!text.trim()} loading={add.isPending}
                onClick={() => add.mutate(undefined)}>Nạp tài liệu</Button>
            </Space>
          )}
          {mode === "url" && (
            <Space.Compact style={{ width: "100%" }}>
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/docs" />
              <Button type="primary" disabled={!url} loading={add.isPending} onClick={() => add.mutate(undefined)}>Tải</Button>
            </Space.Compact>
          )}
          {mode === "file" && (
            <Upload.Dragger multiple={false} showUploadList={false} accept=".md,.markdown,.html,.htm,.pdf,.txt"
              beforeUpload={(f) => { add.mutate(f); return false; }}>
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p>Kéo thả hoặc chọn tệp HTML / Markdown / PDF / TXT (≤ 10 MB)</p>
            </Upload.Dragger>
          )}
        </Card>
        <Card title="Tài liệu của dự án" size="small" style={{ marginTop: 16 }}>
          <List dataSource={docs.data ?? []} locale={{ emptyText: "Chưa có tài liệu" }} renderItem={(d) => (
            <List.Item style={{ cursor: "pointer", background: d.id === currentDoc ? "#e6f4ff" : undefined, paddingLeft: 8 }}
              onClick={() => setDocId(d.id)} actions={[
                <Popconfirm key="x" title="Xóa tài liệu?" onConfirm={() => removeDoc.mutate(d.id)} okText="Xóa" cancelText="Hủy">
                  <Button size="small" danger type="link">Xóa</Button>
                </Popconfirm>,
              ]}>
              <List.Item.Meta title={`#${d.id} · ${d.filename ?? d.source_uri ?? d.source_type}`}
                description={`${d.source_type} · ${d.chunk_count} phân đoạn · ${fmtDate(d.created_at)}`} />
            </List.Item>
          )} />
        </Card>
      </Col>
      <Col xs={24} xl={15}>
        <ErrorAlert error={chunks.error} />
        {!currentDoc ? <Empty description="Hãy nạp tài liệu để bắt đầu" /> : (
          <Section title={<>Phân đoạn ({chunks.data?.length ?? 0}, {ops} operation)</>} extra={
            <Space wrap>
              <Segmented value={view} onChange={(v) => setView(v as typeof view)}
                options={[{ value: "chunks", label: "Phân đoạn" }, { value: "markdown", label: "Xem trước Markdown" }]} />
              <Button disabled={selected.length < 2} loading={merge.isPending} onClick={() => merge.mutate()}>
                Gộp {selected.length || ""} phân đoạn
              </Button>
              <Popconfirm title="Phân đoạn lại sẽ xóa mọi chỉnh sửa phân đoạn" onConfirm={() => resegment.mutate()} okText="Đồng ý" cancelText="Hủy">
                <Button>Phân đoạn lại</Button>
              </Popconfirm>
              <Button type="primary" onClick={() => goTab("spec")}>Sang bước sinh đặc tả →</Button>
            </Space>
          }>
            {view === "markdown" ? (
              <div className="md-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{doc.data?.markdown ?? ""}</ReactMarkdown></div>
            ) : (
              <List dataSource={chunks.data ?? []} loading={chunks.isLoading} renderItem={(c) => (
                <Card size="small" style={{ marginBottom: 8 }}
                  className={`chunk-card ${c.is_global ? "global" : c.operation_hint ? "op" : ""}`}
                  title={
                    <Space>
                      <Checkbox checked={selected.includes(c.id)} onChange={(e) => setSelected(e.target.checked
                        ? [...selected, c.id] : selected.filter((x) => x !== c.id))} />
                      <span>#{c.order} {c.title}</span>
                      {c.operation_hint && <Tag color="green">{c.operation_hint.method} {c.operation_hint.path}</Tag>}
                      {c.is_global && <Tag color="blue">ngữ cảnh chung</Tag>}
                    </Space>
                  }
                  extra={
                    <Space size={4}>
                      <Typography.Text type="secondary">{c.token_count} token · [{c.span_start}–{c.span_end}]</Typography.Text>
                      <Button size="small" type="link" onClick={() => setEditing({ ...c })}>Sửa</Button>
                      <Button size="small" type="link" onClick={() => setSplitting({ chunk: c, offset: Math.floor(c.text.length / 2) })}>Tách</Button>
                      <Popconfirm title="Xóa phân đoạn?" onConfirm={() => removeChunk.mutate(c.id)} okText="Xóa" cancelText="Hủy">
                        <Button size="small" type="link" danger>Xóa</Button>
                      </Popconfirm>
                    </Space>
                  }>
                  <Typography.Paragraph ellipsis={{ rows: 3, expandable: true, symbol: "thêm" }} style={{ whiteSpace: "pre-wrap", fontSize: 12, margin: 0 }}>
                    {c.text}
                  </Typography.Paragraph>
                </Card>
              )} />
            )}
          </Section>
        )}
      </Col>
      <Modal open={!!editing} title="Sửa phân đoạn" width={760} onCancel={() => setEditing(null)} okText="Lưu" cancelText="Hủy"
        onOk={() => editing && update.mutate(editing)} confirmLoading={update.isPending}>
        {editing && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Input value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
            <Space><Switch checked={editing.is_global} onChange={(v) => setEditing({ ...editing, is_global: v })} />
              Ngữ cảnh chung (chèn vào prompt mọi phân đoạn)</Space>
            <Input.TextArea rows={16} value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} />
          </Space>
        )}
      </Modal>
      <Modal open={!!splitting} title="Tách phân đoạn" width={760} onCancel={() => setSplitting(null)} okText="Tách" cancelText="Hủy"
        onOk={() => splitting && split.mutate({ id: splitting.chunk.id, offset: splitting.offset })} confirmLoading={split.isPending}>
        {splitting && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>Vị trí ký tự: <InputNumber min={1} max={splitting.chunk.text.length - 1} value={splitting.offset}
              onChange={(v) => setSplitting({ ...splitting, offset: Number(v) || 1 })} />
              <Select style={{ width: 260 }} placeholder="hoặc chọn đầu dòng tiêu đề" onChange={(v) => setSplitting({ ...splitting, offset: v })}
                options={[...splitting.chunk.text.matchAll(/\n(#+ .*|`(GET|POST|PUT|PATCH|DELETE)[^`]*`)/g)].map((m) => ({
                  value: (m.index ?? 0) + 1, label: m[1].slice(0, 40) }))} />
            </Space>
            <pre className="ev-doc" style={{ maxHeight: 360 }}>
              {splitting.chunk.text.slice(0, splitting.offset)}
              <span style={{ background: "#ff4d4f", color: "#fff" }}>⟂</span>
              {splitting.chunk.text.slice(splitting.offset)}
            </pre>
          </Space>
        )}
      </Modal>
    </Row>
  );
}
