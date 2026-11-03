// Trang “Bộ dữ liệu”: các API trong SpecLoop-Bench + người dùng tự thêm API mới (đặc tả OpenAPI làm ground truth).
import {
  ApiOutlined, CloudOutlined, ContainerOutlined, DatabaseOutlined, NodeIndexOutlined, PlusOutlined, ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Input, Segmented, Space, Table, Tooltip } from "antd";
import { useState, type CSSProperties, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { BenchApiRow } from "../api/types";
import AddBenchApiModal from "../components/AddBenchApiModal";
import BenchApiDrawer from "../components/BenchApiDrawer";
import { Chip, ErrorAlert, fmtInt, PageHead } from "../components/common";

type Filter = "all" | "A" | "B" | "web";
const ENV_TEXT: Record<string, string> = { "local-docker": "Docker", public: "Công khai", offline: "Ngoại tuyến" };
const SCOPE_TEXT: Record<string, string> = { full: "đầy đủ", "read-only": "chỉ đọc", none: "không" };
const BEH: Record<string, { text: string; tone: "green" | "amber" | "gray" }> = {
  exact: { text: "chính xác", tone: "green" }, partial: { text: "một phần", tone: "amber" }, pending: { text: "chờ", tone: "gray" },
};
const delay = (i: number) => ({ "--i": i } as CSSProperties);
const sum = (rows: BenchApiRow[], k: keyof BenchApiRow) => rows.reduce((s, r) => s + (Number(r[k]) || 0), 0);

export default function DatasetPage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const q = useQuery({ queryKey: ["bench-apis"], queryFn: api.benchList });
  const rows = q.data ?? [];
  const open = params.get("api");
  const setOpen = (id: string | null) => {
    const p = new URLSearchParams(params);
    if (id) p.set("api", id);
    else p.delete("api");
    setParams(p);
  };
  const s = search.trim().toLowerCase();
  const shown = rows.filter((r) => (filter === "all" || (filter === "web" ? r.added_via === "web" : r.group === filter))
    && (!s || r.id.includes(s) || r.name.toLowerCase().includes(s) || (r.description ?? "").toLowerCase().includes(s)));
  const nA = rows.filter((r) => r.group === "A").length;
  const nWeb = rows.filter((r) => r.added_via === "web").length;
  const stats: { k: string; v: number; icon: ReactNode; tone?: string; sub?: string }[] = [
    { k: "API trong bộ dữ liệu", v: rows.length, icon: <DatabaseOutlined />, sub: nWeb ? `${nWeb} API do người dùng thêm` : undefined },
    { k: "Nhóm A · chạy Docker", v: nA, icon: <ContainerOutlined />, tone: "teal" },
    { k: "Nhóm B · công khai", v: rows.length - nA, icon: <CloudOutlined />, tone: "purple" },
    { k: "Operation", v: sum(rows, "operations"), icon: <ApiOutlined />, tone: "ok" },
    { k: "Ràng buộc (bỏ type)", v: sum(rows, "constraints"), icon: <NodeIndexOutlined />, tone: "go" },
    { k: "Atomic facts", v: sum(rows, "facts"), icon: <DatabaseOutlined /> },
  ];

  return (
    <>
      <PageHead title="Bộ dữ liệu"
        lede="SpecLoop-Bench: mỗi API gồm đặc tả OpenAPI chính thức (ground truth), tài liệu đầu vào cho LLM và môi trường để kiểm thử. Thêm API mới bằng URL hoặc tệp đặc tả – hệ thống tự chuẩn hóa, sinh facts và kiểm tra."
        actions={<>
          <Button icon={<ReloadOutlined />} onClick={() => qc.invalidateQueries({ queryKey: ["bench-apis"] })}>Tải lại</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)} data-testid="bench-add-btn">Thêm API</Button>
        </>} />
      <ErrorAlert error={q.error} />
      <div className="stat-strip reveal" style={delay(1)}>
        {stats.map((x) => (
          <div key={x.k} className={`stat ${x.tone ?? ""}`}>
            <div className="k">{x.k}</div>
            <div className="ico">{x.icon}</div>
            <div className="v">{q.isLoading ? "–" : fmtInt(x.v)}</div>
            {x.sub && <div className="sub">{x.sub}</div>}
          </div>
        ))}
      </div>
      <section className="panel reveal" style={{ ...delay(2), marginTop: 16 }}>
        <div className="panel-head">
          <div className="toolbar" style={{ margin: 0 }}>
            <Input allowClear prefix={<SearchOutlined style={{ color: "#9aa3af" }} />} placeholder="Tìm theo tên, mã, mô tả"
              value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 300 }} />
            <Segmented value={filter} onChange={(v) => setFilter(v as Filter)} options={[
              { value: "all", label: `Tất cả (${rows.length})` }, { value: "A", label: `Nhóm A (${nA})` },
              { value: "B", label: `Nhóm B (${rows.length - nA})` }, { value: "web", label: `Người dùng thêm (${nWeb})` }]} />
          </div>
        </div>
        <Table<BenchApiRow> rowKey="id" loading={q.isLoading} dataSource={shown} pagination={{ pageSize: 25, hideOnSinglePage: true }}
          rowClassName="row-click" data-testid="bench-table"
          onRow={(r) => ({ onClick: (e) => { if (!(e.target as HTMLElement).closest("a, button")) setOpen(r.id); } })}
          locale={{ emptyText: rows.length ? "Không có API nào khớp bộ lọc." : "Bộ dữ liệu trống." }}
          columns={[
            { title: "API", dataIndex: "name", render: (v, r) => (
              <>
                <a className="cell-title" onClick={() => setOpen(r.id)}>{v}</a>{" "}
                {r.added_via === "web" && <Chip tone="purple">mới thêm</Chip>}
                <div className="cell-sub" style={{ maxWidth: 330 }}><span className="mono">{r.id}</span>{r.description ? ` · ${r.description}` : ""}</div>
              </>) },
            { title: "Nhóm", dataIndex: "group", width: 80, align: "center",
              render: (g) => <Chip tone={g === "A" ? "blue" : "teal"}>{g}</Chip> },
            { title: "Môi trường", width: 170, render: (_, r) => (
              <span>{ENV_TEXT[r.environment ?? ""] ?? r.environment}<div className="cell-sub">kiểm thử {SCOPE_TEXT[r.test_scope ?? ""] ?? r.test_scope}{r.auth !== "none" ? ` · ${r.auth}` : ""}</div></span>) },
            { title: "Op", dataIndex: "operations", width: 70, align: "right", sorter: (a, b) => (a.operations ?? 0) - (b.operations ?? 0), render: fmtInt },
            { title: "Ràng buộc", dataIndex: "constraints", width: 100, align: "right", sorter: (a, b) => (a.constraints ?? 0) - (b.constraints ?? 0), render: fmtInt },
            { title: "Facts", dataIndex: "facts", width: 90, align: "right", sorter: (a, b) => (a.facts ?? 0) - (b.facts ?? 0), render: fmtInt },
            { title: "Tài liệu", width: 110, render: (_, r) => <Space size={4}>
              <Tooltip title="Tài liệu gốc viết cho người đọc"><Chip tone={r.has_original_doc ? "green" : "gray"}>gốc</Chip></Tooltip>
              {r.has_ablated_doc && <Tooltip title="Bản lược ràng buộc"><Chip tone="amber">lược</Chip></Tooltip>}
            </Space> },
            { title: "GT hành vi", dataIndex: "behavior_gt", width: 100, render: (b) => <Chip tone={BEH[b]?.tone ?? "gray"}>{BEH[b]?.text ?? b}</Chip> },
            { title: "Kết nối", dataIndex: "connectivity_checked", width: 85, align: "center", render: (c, r) => r.test_scope === "none" ? "–"
              : <Tooltip title={c ? "Đã thử kết nối thành công" : "Chưa kiểm tra / chưa kết nối được"}><span className={`dot ${c ? "on" : ""}`} style={{ display: "inline-block" }} /></Tooltip> },
          ]} />
      </section>
      <AddBenchApiModal open={adding} onClose={() => setAdding(false)}
        onCreated={(id) => { qc.invalidateQueries({ queryKey: ["bench-apis"] }); qc.invalidateQueries({ queryKey: ["bench-apis-exp"] }); setOpen(id); }} />
      <BenchApiDrawer apiId={open} onClose={() => setOpen(null)} />
    </>
  );
}
