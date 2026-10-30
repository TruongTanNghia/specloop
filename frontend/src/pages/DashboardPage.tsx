import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { chartAxis, chartTooltip, CODE_INFO, ErrorAlert, fmtDate, fmtInt, PageHead, Panel } from "../components/common";
import { C } from "../theme";

const LOOP = [
  { t: "Nạp tài liệu", d: "Markdown, HTML, PDF hoặc URL → chuẩn hóa, phân đoạn theo từng operation." },
  { t: "Sinh OAS", d: "LLM trích xuất IR kèm trích dẫn → lắp ráp OpenAPI 3.0.3 → vòng sửa lỗi." },
  { t: "Đánh giá", d: "L1 parse · L2 validate · L3 lint · L4 grounding · L5 so với ground truth." },
  { t: "Kiểm thử API thật", d: "Dò biên, sai kiểu, enum, bỏ tham số… trong ngân sách và tốc độ giới hạn." },
  { t: "Đề xuất & phiên bản", d: "JSON Patch kèm độ tin cậy → duyệt → phiên bản mới bất biến, có diff." },
];

const delay = (i: number) => ({ "--i": i } as CSSProperties);

export default function DashboardPage() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 10000 });
  const d = q.data;
  const codes = Object.entries(d?.findings_by_code ?? {}).map(([code, n]) => ({ code, n })).sort((a, b) =>
    a.code.localeCompare(b.code));
  const stats: { k: string; v: number | undefined; tone?: string; sub?: string }[] = [
    { k: "Dự án", v: d?.projects },
    { k: "Phiên bản đặc tả", v: d?.versions },
    { k: "Lượt kiểm thử", v: d?.test_runs },
    { k: "Sai lệch đang mở", v: d?.open_findings, tone: d?.open_findings ? "hot" : "" },
    { k: "Đề xuất chờ duyệt", v: d?.pending_proposals, tone: d?.pending_proposals ? "go" : "" },
    { k: "Lời gọi LLM", v: d?.llm.calls, sub: `${fmtInt(d?.llm.input_tokens ?? 0)} token vào · ${fmtInt(d?.llm.output_tokens ?? 0)} ra` },
  ];
  return (
    <>
      <PageHead eyebrow="Tổng quan"
        title={<>Tài liệu vào, <span className="hl">đặc tả đã kiểm chứng</span> ra.</>}
        lede="SpecLoop đọc tài liệu REST API, sinh OpenAPI 3.0.3 có trích dẫn, rồi tự kiểm thử API thật để tìm chỗ tài liệu nói sai và đề xuất sửa." />
      <ErrorAlert error={q.error} />
      <div className="stat-strip reveal" style={delay(1)}>
        {stats.map((s) => (
          <div key={s.k} className={`stat ${s.tone ?? ""}`}>
            <div className="k">{s.k}</div>
            <div className="v">{q.isLoading ? "–" : fmtInt(s.v ?? 0)}</div>
            {s.sub && <div className="sub">{s.sub}</div>}
          </div>
        ))}
      </div>
      <div className="loop reveal" style={delay(2)}>
        {LOOP.map((s, i) => (
          <div key={s.t} className="loop-step">
            <div className="n">BƯỚC 0{i + 1}</div>
            <div className="t">{s.t}</div>
            <div className="d">{s.d}</div>
          </div>
        ))}
      </div>
      <div className="grid-2">
        <Panel title="Sai lệch theo mã · mọi lượt kiểm thử" className="reveal" style={delay(3)}>
          {codes.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={codes} barCategoryGap="28%">
                <CartesianGrid stroke={C.lineSoft} vertical={false} />
                <XAxis dataKey="code" {...chartAxis} />
                <YAxis allowDecimals={false} {...chartAxis} width={32} />
                <Tooltip {...chartTooltip} formatter={(v: number, _n, item) => [v, CODE_INFO[item.payload.code]?.label ?? item.payload.code]} />
                <Bar dataKey="n" name="Số finding" radius={[3, 3, 0, 0]}>
                  {codes.map((c) => <Cell key={c.code} fill={CODE_INFO[c.code]?.color ?? C.lime} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="empty">Chưa có lượt kiểm thử nào. Tạo dự án, sinh đặc tả rồi chạy kiểm thử để thấy số liệu ở đây.</div>}
        </Panel>
        <Panel title="Dự án gần đây" extra={<Link to="/projects">Tất cả →</Link>} bodyStyle={{ padding: 0 }} className="reveal" style={delay(4)}>
          {d?.recent_projects.length ? d.recent_projects.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="row-link">
              <span className="nm">{p.name}</span>
              <span className="meta">#{p.id} · {fmtDate(p.created_at)}</span>
              <span className="arrow">→</span>
            </Link>
          )) : <div className="empty" style={{ border: 0 }}>Chưa có dự án.</div>}
        </Panel>
      </div>
    </>
  );
}
