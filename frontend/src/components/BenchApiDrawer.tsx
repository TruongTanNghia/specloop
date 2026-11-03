// Chi tiết một API trong SpecLoop-Bench: nguồn, môi trường, thống kê, tài liệu, ground truth, kiểm tra kết nối, xóa.
import { ApiOutlined, DeleteOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Descriptions, Drawer, Empty, Popconfirm, Space, Spin, Table, Tabs } from "antd";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, errorText } from "../api/client";
import type { BenchApiDetail } from "../api/types";
import { Chip, ErrorAlert, fmtInt } from "./common";
import { YamlEditor } from "./editors";

const ENV_TEXT: Record<string, string> = { "local-docker": "Docker cục bộ", public: "Công khai", offline: "Ngoại tuyến" };
const SCOPE_TEXT: Record<string, string> = { full: "đầy đủ", "read-only": "chỉ đọc", none: "không kiểm thử" };

export default function BenchApiDrawer({ apiId, onClose }: { apiId: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const q = useQuery({ queryKey: ["bench-api", apiId], queryFn: () => api.benchDetail(apiId!), enabled: !!apiId });
  const conn = useMutation({
    mutationFn: () => api.benchConnectivity(apiId!),
    onSuccess: (r) => {
      if (r.ok) message.success(`Kết nối được: HTTP ${r.status} · ${r.latency_ms} ms`);
      qc.invalidateQueries({ queryKey: ["bench-apis"] });
      qc.invalidateQueries({ queryKey: ["bench-api", apiId] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.benchDelete(apiId!),
    onSuccess: () => {
      message.success(`Đã xóa ${apiId} khỏi bộ dữ liệu`);
      qc.invalidateQueries({ queryKey: ["bench-apis"] });
      qc.invalidateQueries({ queryKey: ["bench-apis-exp"] });
      onClose();
    },
    onError: (e) => message.error(errorText(e)),
  });
  const d = q.data;
  return (
    <Drawer open={!!apiId} onClose={() => { conn.reset(); onClose(); }} width={880} destroyOnClose
      title={d ? <Space><span>{d.meta.name}</span><Chip mono>{d.id}</Chip></Space> : apiId}
      extra={d && <Space>
        <Button icon={<ApiOutlined />} loading={conn.isPending} onClick={() => conn.mutate()}
          disabled={d.meta.environment.test_scope === "none"}>Kiểm tra kết nối</Button>
        {d.deletable && (
          <Popconfirm title="Xóa API này khỏi bộ dữ liệu?" description="Xóa thư mục apis/ và gỡ khỏi manifest." okText="Xóa"
            okButtonProps={{ danger: true }} cancelText="Hủy" onConfirm={() => remove.mutate()}>
            <Button danger icon={<DeleteOutlined />} loading={remove.isPending}>Xóa</Button>
          </Popconfirm>
        )}
      </Space>}>
      <ErrorAlert error={q.error} />
      {q.isLoading && <Spin />}
      {conn.data && (
        <Alert style={{ marginBottom: 14 }} showIcon type={conn.data.ok ? "success" : "warning"}
          message={conn.data.ok ? `Kết nối được: HTTP ${conn.data.status} · ${conn.data.latency_ms} ms`
            : `Chưa kết nối được: ${conn.data.status}`}
          description={conn.data.ok ? conn.data.url : (conn.data.reason ?? conn.data.error ?? conn.data.url)} />
      )}
      {conn.error && <ErrorAlert error={conn.error} />}
      {d && <Body d={d} />}
    </Drawer>
  );
}

function Body({ d }: { d: BenchApiDetail }) {
  const m = d.meta;
  const st = d.stats;
  const env = m.environment;
  const auth = env.auth;
  return (
    <>
      {m.description && <p className="page-lede" style={{ marginTop: 0, maxWidth: "none" }}>{m.description}</p>}
      <div className="mini-stats">
        {[["Operation", st?.operations], ["Tham số", st?.parameters], ["Ràng buộc*", st?.constraints_no_type],
          ["Atomic facts", st?.facts_total], ["Từ tài liệu render", st?.doc_rendered_words]].map(([k, v]) => (
          <div key={String(k)}><span>{k}</span><b>{fmtInt(v as number | undefined)}</b></div>
        ))}
      </div>
      <Tabs items={[
        { key: "info", label: "Thông tin", children: (
          <>
            <Descriptions bordered size="small" column={1} items={[
              { key: "g", label: "Nhóm", children: <Space><Chip tone={m.group === "A" ? "blue" : "teal"}>Nhóm {m.group}</Chip>
                {m.added_via === "web" && <Chip tone="purple">thêm từ web</Chip>}</Space> },
              { key: "e", label: "Môi trường", children: `${ENV_TEXT[env.type] ?? env.type} · kiểm thử ${SCOPE_TEXT[env.test_scope] ?? env.test_scope} · ≤ ${env.rate_limit_rps} req/s` },
              { key: "b", label: "Base URL", children: <code>{env.base_url}</code> },
              { key: "a", label: "Xác thực", children: auth.type === "none" ? "không"
                : <>{auth.type}{auth.in ? ` trong ${auth.in}` : ""}{auth.name ? <> <code>{auth.name}</code></> : null} · khóa lấy từ biến <code>{auth.env_var}</code></> },
              { key: "p", label: "Thử kết nối", children: <>{env.probe.method} <code>{env.probe.path ?? "–"}</code> ·{" "}
                {env.connectivity_checked ? <Chip tone="green">đã kết nối được</Chip> : <Chip>chưa kiểm tra</Chip>}</> },
              { key: "s", label: "Nguồn đặc tả", children: /^https?:/.test(m.source.spec_url)
                ? <a href={m.source.spec_url} target="_blank" rel="noreferrer">{m.source.spec_url}</a> : m.source.spec_url },
              { key: "l", label: "Giấy phép", children: m.source.license },
              { key: "h", label: "Trang chủ / tài liệu", children: <Space direction="vertical" size={0}>
                {[m.source.homepage, m.source.docs_url].filter((u) => u && u !== "TODO").map((u) => (
                  /^https?:/.test(u) ? <a key={u} href={u} target="_blank" rel="noreferrer">{u}</a> : <span key={u}>{u}</span>))}
              </Space> },
              { key: "r", label: "Ngày lấy", children: m.source.retrieved_at },
              { key: "t", label: "GT hành vi", children: m.ground_truth.behavior_status },
              { key: "by", label: "Người thêm", children: m.added_by ?? "–" },
            ]} />
            {m.source.normalization?.length > 0 && (
              <>
                <h5 className="sec-title" style={{ margin: "16px 0 6px" }}>Chuẩn hóa so với đặc tả gốc</h5>
                <ul className="note-list">{m.source.normalization.map((n) => <li key={n}>{n}</li>)}</ul>
              </>
            )}
            {st && (
              <>
                <h5 className="sec-title" style={{ margin: "16px 0 6px" }}>Ràng buộc theo từ khóa</h5>
                <Space wrap size={6}>
                  {Object.entries(st.constraint_by_keyword).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <Chip key={k} tone={k === "type" ? "gray" : "blue"} mono>{k}: {v}</Chip>
                  ))}
                </Space>
              </>
            )}
            <p className="page-lede" style={{ fontSize: 12.5 }}>* Không tính từ khóa <code>type</code>.</p>
          </>
        ) },
        { key: "doc", label: "Tài liệu đầu vào", children: <DocView d={d} /> },
        { key: "gt", label: "Ground truth (OpenAPI)", children: <FileView id={d.id} path="ground_truth/openapi.yaml" yaml /> },
        { key: "files", label: `Tệp (${d.files.length})`, children: (
          <Table size="small" rowKey="path" pagination={false} dataSource={d.files} columns={[
            { title: "Đường dẫn", dataIndex: "path", render: (p) => <code>{p}</code> },
            { title: "Kích thước", dataIndex: "size", align: "right", width: 120,
              render: (s: number) => s > 1024 * 1024 ? `${(s / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(s / 1024))} KB` },
          ]} />
        ) },
      ]} />
    </>
  );
}

function DocView({ d }: { d: BenchApiDetail }) {
  const kinds = [
    ...(d.meta.docs.original ? [{ key: d.meta.docs.original, label: "Tài liệu gốc" }] : []),
    { key: d.meta.docs.rendered, label: "Bản render từ đặc tả" },
    ...(d.meta.docs.ablated ? [{ key: d.meta.docs.ablated, label: "Bản lược ràng buộc" }] : []),
  ];
  return <Tabs size="small" type="card" items={kinds.map((k) => ({
    key: k.key, label: k.label, children: <FileView id={d.id} path={k.key} />,
  }))} />;
}

function FileView({ id, path, yaml }: { id: string; path: string; yaml?: boolean }) {
  const q = useQuery({ queryKey: ["bench-file", id, path], queryFn: () => api.benchFile(id, path) });
  if (q.isLoading) return <Spin />;
  if (q.error) return <ErrorAlert error={q.error} />;
  if (!q.data) return <Empty />;
  if (yaml) return <YamlEditor value={q.data} readOnly height={560} />;
  if (path.endsWith(".md")) {
    return <div className="md-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{q.data}</ReactMarkdown></div>;
  }
  return <pre className="json-block" style={{ maxHeight: 600 }}>{q.data}</pre>;
}
