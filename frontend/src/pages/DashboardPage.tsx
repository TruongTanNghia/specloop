import {
  AuditOutlined, ExperimentOutlined, FileTextOutlined, FolderOpenOutlined, RobotOutlined, WarningOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Steps, Table } from "antd";
import type { CSSProperties, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { chartAxis, chartTooltip, CODE_INFO, ErrorAlert, fmtDate, fmtInt, PageHead, Panel } from "../components/common";
import { C } from "../theme";

const LOOP = [
  { t: "Nạp tài liệu", d: "Markdown, HTML, PDF, URL → phân đoạn theo operation" },
  { t: "Sinh OpenAPI", d: "LLM trích xuất kèm trích dẫn → OAS 3.0.3 → sửa lỗi" },
  { t: "Đánh giá", d: "L1 parse · L2 validate · L3 lint · L4 grounding · L5 GT" },
  { t: "Kiểm thử API thật", d: "Dò biên, sai kiểu, enum, bỏ tham số… có giới hạn" },
  { t: "Đề xuất & phiên bản", d: "JSON Patch + độ tin cậy → duyệt → phiên bản mới" },
];

const delay = (i: number) => ({ "--i": i } as CSSProperties);

export default function DashboardPage() {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 10000 });
  const d = q.data;
  const codes = Object.entries(d?.findings_by_code ?? {}).map(([code, n]) => ({ code, n })).sort((a, b) =>
    a.code.localeCompare(b.code));
  const stats: { k: string; v: number | undefined; icon: ReactNode; tone?: string; sub?: string }[] = [
    { k: "Dự án", v: d?.projects, icon: <FolderOpenOutlined /> },
    { k: "Phiên bản đặc tả", v: d?.versions, icon: <FileTextOutlined />, tone: "teal" },
    { k: "Lượt kiểm thử", v: d?.test_runs, icon: <ExperimentOutlined />, tone: "purple" },
    { k: "Sai lệch đang mở", v: d?.open_findings, icon: <WarningOutlined />, tone: d?.open_findings ? "hot" : "" },
    { k: "Đề xuất chờ duyệt", v: d?.pending_proposals, icon: <AuditOutlined />, tone: d?.pending_proposals ? "go" : "" },
    { k: "Lời gọi LLM", v: d?.llm.calls, icon: <RobotOutlined />, tone: "ok",
      sub: `${fmtInt(d?.llm.input_tokens ?? 0)} token vào · ${fmtInt(d?.llm.output_tokens ?? 0)} ra` },
  ];
  return (
    <>
      <PageHead title="Tổng quan"
        lede="Tình hình chung của các dự án: tài liệu đã nạp, đặc tả đã sinh, kết quả kiểm thử API thật và các đề xuất đang chờ duyệt." />
      <ErrorAlert error={q.error} />
      <div className="stat-strip reveal" style={delay(1)}>
        {stats.map((s) => (
          <div key={s.k} className={`stat ${s.tone ?? ""}`}>
            <div className="k">{s.k}</div>
            <div className="ico">{s.icon}</div>
            <div className="v">{q.isLoading ? "–" : fmtInt(s.v ?? 0)}</div>
            {s.sub && <div className="sub">{s.sub}</div>}
          </div>
        ))}
      </div>
      <section className="panel steps-card reveal" style={delay(2)} aria-label="Quy trình">
        <Steps size="small" labelPlacement="vertical"
          items={LOOP.map((s) => ({ title: s.t, description: s.d, status: "process" as const }))} />
      </section>
      <div className="grid-2">
        <Panel title="Sai lệch theo mã · mọi lượt kiểm thử" className="reveal" style={delay(3)}>
          {codes.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={codes} barCategoryGap="30%">
                <CartesianGrid stroke={C.lineSoft} vertical={false} />
                <XAxis dataKey="code" {...chartAxis} />
                <YAxis allowDecimals={false} {...chartAxis} width={32} />
                <Tooltip {...chartTooltip} formatter={(v: number, _n, item) => [v, CODE_INFO[item.payload.code]?.label ?? item.payload.code]} />
                <Bar dataKey="n" name="Số finding" radius={[4, 4, 0, 0]}>
                  {codes.map((c) => <Cell key={c.code} fill={CODE_INFO[c.code]?.color ?? C.primary} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="empty" style={{ border: 0, padding: 24 }}>Chưa có lượt kiểm thử nào. Tạo dự án, sinh đặc tả rồi chạy kiểm thử để thấy số liệu ở đây.</div>}
        </Panel>
        <Panel title="Dự án gần đây" extra={<Link to="/projects">Xem tất cả</Link>} bodyStyle={{ padding: 0 }} className="reveal" style={delay(4)}>
          <Table size="small" rowKey="id" pagination={false} dataSource={d?.recent_projects ?? []} loading={q.isLoading}
            rowClassName="row-click" onRow={(p) => ({ onClick: () => nav(`/projects/${p.id}`) })}
            locale={{ emptyText: "Chưa có dự án" }}
            columns={[
              { title: "Dự án", dataIndex: "name", render: (v, p) => <Link to={`/projects/${p.id}`} className="cell-title">{v}</Link> },
              { title: "ID", dataIndex: "id", width: 70, render: (v) => <span className="mono">#{v}</span> },
              { title: "Tạo lúc", dataIndex: "created_at", width: 170, render: fmtDate },
            ]} />
        </Panel>
      </div>
    </>
  );
}
