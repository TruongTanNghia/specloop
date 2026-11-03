// SC-10: thực nghiệm – ma trận API × mô hình × cấu hình × lần lặp, theo dõi, biểu đồ, xuất CSV / summary.md.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App, Button, Card, Checkbox, Col, Form, Input, InputNumber, Modal, Radio, Row, Select, Space, Table, Tag,
} from "antd";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorText } from "../api/client";
import type { ExperimentRequest, ExperimentRow } from "../api/types";
import { chartAxis, chartTooltip, ErrorAlert, fmt, fmtDate, PageHead } from "../components/common";
import JobRunner from "../components/JobRunner";
import { C, CHART, FONT_MONO } from "../theme";

interface FormValues {
  name: string;
  apis: string[];
  models: string[];
  configs: ("C0" | "C1" | "C2")[];
  repeats: number;
  doc_variant: "original" | "rendered" | "ablated";
  max_iter: number;
  max_rps?: number;
  overrides?: string;
}

export default function ExperimentsPage() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [jobId, setJobId] = useState<string | null>(null);
  const [expId, setExpId] = useState<number | null>(null);
  const [md, setMd] = useState<string | null>(null);
  const apis = useQuery({ queryKey: ["bench-apis-exp"], queryFn: api.benchApis });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const list = useQuery({ queryKey: ["experiments"], queryFn: api.experiments });
  const shown = expId ?? list.data?.[0]?.id ?? null;
  const results = useQuery({ queryKey: ["experiment", shown], queryFn: () => api.experimentResults(shown!), enabled: !!shown });
  const start = useMutation({
    mutationFn: (v: FormValues) => {
      const overrides: Record<string, string> = {};
      for (const line of (v.overrides ?? "").split("\n")) {
        const [k, ...rest] = line.split("=");
        if (k?.trim() && rest.length) overrides[k.trim()] = rest.join("=").trim();
      }
      const body: ExperimentRequest = { name: v.name, apis: v.apis, models: v.models, configs: v.configs, repeats: v.repeats,
        doc_variant: v.doc_variant, base_url_overrides: overrides, max_iter: v.max_iter, max_rps: v.max_rps ?? null };
      return api.startExperiment(body);
    },
    onSuccess: (r) => { setJobId(r.job_id); setExpId(r.resource_id); qc.invalidateQueries({ queryKey: ["experiments"] }); },
    onError: (e) => message.error(errorText(e)),
  });
  const modelOptions = (providers.data ?? []).flatMap((p) => p.models.map((m) => ({ value: m, label: m, disabled: !p.available })));
  const sum = results.data?.summary;
  const chart = Object.entries(sum?.macro ?? {}).map(([c, m]) => ({
    config: c, "F1 (GT tài liệu)": m.f1, "F1 ràng buộc – tài liệu": m.constraint_f1_doc, "F1 ràng buộc – hành vi": m.constraint_f1_behavior,
  }));
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <PageHead title="Thực nghiệm"
        lede="Ma trận API × mô hình × cấu hình trên SpecLoop-Bench: C0 chỉ LLM · C1 thêm vòng sửa lỗi · C2 thêm tinh chỉnh từ kiểm thử. Kiểm định Wilcoxon, hiệu chỉnh Holm, khoảng tin cậy bootstrap." />
      <Row gutter={16}>
        <Col xs={24} xl={9}>
          <Card size="small" title="Cấu hình ma trận">
            <Form layout="vertical" onFinish={(v: FormValues) => start.mutate(v)} initialValues={{
              name: "thuc-nghiem", apis: ["bookstore-lab"], models: ["fake"], configs: ["C0", "C1", "C2"], repeats: 3,
              doc_variant: "original", max_iter: 3, overrides: "bookstore-lab=http://localhost:8000/v1",
            }}>
              <Form.Item name="name" label="Tên" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="apis" label="API (SpecLoop-Bench)" rules={[{ required: true }]}>
                <Select mode="multiple" options={(apis.data ?? []).map((a) => ({ value: a.id,
                  label: `${a.id} · nhóm ${a.group} · kiểm thử: ${a.test_scope}${a.has_behavior_gt ? " · có GT hành vi" : ""}` }))} />
              </Form.Item>
              <Form.Item name="models" label="Mô hình" rules={[{ required: true }]}>
                <Select mode="tags" options={modelOptions} />
              </Form.Item>
              <Form.Item name="configs" label="Cấu hình">
                <Checkbox.Group options={[{ value: "C0", label: "C0 – chỉ LLM" }, { value: "C1", label: "C1 – + sửa lỗi" },
                  { value: "C2", label: "C2 – + tinh chỉnh từ kiểm thử" }]} />
              </Form.Item>
              <Space wrap>
                <Form.Item name="repeats" label="Số lần lặp"><InputNumber min={1} max={10} /></Form.Item>
                <Form.Item name="max_iter" label="K vòng (C2)"><InputNumber min={1} max={10} /></Form.Item>
                <Form.Item name="max_rps" label="Tốc độ (req/s)"><InputNumber min={0.1} max={100} placeholder="mặc định" /></Form.Item>
              </Space>
              <Form.Item name="doc_variant" label="Biến thể tài liệu">
                <Radio.Group optionType="button" options={[{ value: "original", label: "Gốc" }, { value: "rendered", label: "Render từ GT" },
                  { value: "ablated", label: "Lược ràng buộc" }]} />
              </Form.Item>
              <Form.Item name="overrides" label="Ghi đè base URL (mỗi dòng api=url)"><Input.TextArea rows={2} /></Form.Item>
              <Button type="primary" htmlType="submit" loading={start.isPending}>Chạy thực nghiệm</Button>
            </Form>
          </Card>
          <Card size="small" title="Các lần chạy" style={{ marginTop: 12 }}>
            <Table size="small" rowKey="id" dataSource={list.data ?? []} pagination={{ pageSize: 8 }}
              onRow={(r) => ({ onClick: () => setExpId(r.id), style: { cursor: "pointer" } })}
              rowClassName={(r) => (r.id === shown ? "ant-table-row-selected" : "")}
              columns={[{ title: "#", dataIndex: "id" }, { title: "Tên", dataIndex: "name" },
                { title: "Trạng thái", dataIndex: "status", render: (s) => <Tag color={s === "succeeded" ? "green" : s === "failed" ? "red" : "blue"}>{s}</Tag> },
                { title: "Dòng", dataIndex: "rows" }, { title: "Lúc", dataIndex: "created_at", render: fmtDate }]} />
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <JobRunner jobId={jobId} title="Thực nghiệm" onClose={() => setJobId(null)}
            invalidate={[["experiments"], ["experiment", expId]]} />
          <ErrorAlert error={results.error} />
          {!results.data && !jobId && !results.isLoading && (
            <div className="empty">
              Chưa có kết quả để hiển thị. Chạy một ma trận ở bên trái, hoặc chọn một lần chạy trong bảng “Các lần chạy”.
              Thực nghiệm chạy bằng CLI (<code>python -m app.experiments</code>) ghi ra <code>data/experiments/</code>, không hiện ở đây.
            </div>
          )}
          {results.data && (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Card size="small" title={`Kết quả #${results.data.id} – ${results.data.name}`} extra={
                <Space>
                  <Button href={api.experimentCsvUrl(results.data.id)} disabled={!results.data.rows.length}>Tải CSV</Button>
                  <Button disabled={!sum} onClick={async () => setMd(await api.experimentMarkdown(results.data!.id))}>summary.md</Button>
                </Space>}>
                {chart.length > 0 && (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={chart}>
                      <CartesianGrid stroke={C.lineSoft} vertical={false} />
                      <XAxis dataKey="config" {...chartAxis} />
                      <YAxis domain={[0, 1]} {...chartAxis} width={36} />
                      <Tooltip formatter={(v: number) => (v === null ? "–" : v.toFixed(3))} {...chartTooltip} />
                      <Legend wrapperStyle={{ fontSize: 12, fontFamily: FONT_MONO }} />
                      <Bar dataKey="F1 (GT tài liệu)" fill={CHART[1]} radius={[3, 3, 0, 0]} />
                      <Bar dataKey="F1 ràng buộc – tài liệu" fill={CHART[0]} radius={[3, 3, 0, 0]} />
                      <Bar dataKey="F1 ràng buộc – hành vi" fill={CHART[2]} radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
                {sum && (
                  <Table size="small" pagination={false} rowKey={(r) => r[0]} dataSource={Object.entries(sum.tests)} columns={[
                    { title: "Kiểm định Wilcoxon", render: (_, r) => r[0].replace("_vs_", " vs ") },
                    { title: "n", render: (_, r) => r[1].n }, { title: "ΔF1 TB", render: (_, r) => fmt(r[1].mean_diff) },
                    { title: "KTC 95%", render: (_, r) => (r[1].ci95 ? `[${r[1].ci95[0]}, ${r[1].ci95[1]}]` : "–") },
                    { title: "p", render: (_, r) => fmt(r[1].p_value, 4) }, { title: "p Holm", render: (_, r) => fmt(r[1].p_holm, 4) },
                    { title: "Ghi chú", render: (_, r) => r[1].note ?? "" },
                  ]} />
                )}
              </Card>
              <Table<ExperimentRow> size="small" rowKey={(r) => `${r.api}${r.model}${r.config}${r.rep}`} dataSource={results.data.rows}
                scroll={{ x: 1100 }} pagination={{ pageSize: 15 }} columns={[
                  { title: "API", dataIndex: "api" }, { title: "Mô hình", dataIndex: "model" }, { title: "Cấu hình", dataIndex: "config" },
                  { title: "Lần", dataIndex: "rep" },
                  { title: "Trạng thái", dataIndex: "status", render: (s, r) => <Tag color={s === "ok" ? "green" : "orange"} title={r.note}>{s}</Tag> },
                  { title: "Hợp lệ", dataIndex: "valid" }, { title: "Op", dataIndex: "operations" },
                  { title: "F1", dataIndex: "f1", render: (v) => fmt(v) },
                  { title: "F1 RB (tài liệu)", dataIndex: "constraint_f1_doc", render: (v) => fmt(v) },
                  { title: "F1 RB (hành vi)", dataIndex: "constraint_f1_behavior", render: (v) => fmt(v) },
                  { title: "Request", dataIndex: "requests" }, { title: "Token vào", dataIndex: "input_tokens" },
                  { title: "Token ra", dataIndex: "output_tokens" }, { title: "Thời gian (s)", dataIndex: "duration_s" },
                  { title: "Vòng", dataIndex: "iterations" },
                  { title: "Ghi chú", dataIndex: "note", ellipsis: true },
                ]} />
            </Space>
          )}
        </Col>
      </Row>
      <Modal open={md !== null} onCancel={() => setMd(null)} footer={null} width={1000} title="summary.md">
        <div className="md-preview"><ReactMarkdown remarkPlugins={[remarkGfm]}>{md ?? ""}</ReactMarkdown></div>
      </Modal>
    </Space>
  );
}
