// SC-05: báo cáo đánh giá – upload ground truth, chạy L1–L5, thẻ chỉ số, biểu đồ P/R/F1 theo nhóm fact.
import { UploadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App, Button, Card, Col, Collapse, Empty, Input, List, Modal, Radio, Row, Select, Space, Statistic, Table, Tag, Typography, Upload,
} from "antd";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorText } from "../../api/client";
import type { Evaluation, PRF } from "../../api/types";
import { chartAxis, chartTooltip, ErrorAlert, fmt, fmtDate } from "../../components/common";
import JobRunner from "../../components/JobRunner";
import { C, CHART, FONT_MONO } from "../../theme";
import type { TabProps } from "./types";

const CAT_VI: Record<string, string> = {
  endpoint: "Endpoint", parameter: "Tham số", request_body: "Body yêu cầu", request_field: "Trường yêu cầu",
  response: "Phản hồi", response_field: "Trường phản hồi", constraint: "Ràng buộc",
};

export default function EvaluationTab({ project, specId }: TabProps) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [gtOpen, setGtOpen] = useState(false);
  const [gtKind, setGtKind] = useState<"doc" | "behavior">("doc");
  const [gtText, setGtText] = useState("");
  const [gtId, setGtId] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [evalId, setEvalId] = useState<number | null>(null);
  const gts = useQuery({ queryKey: ["gts", project.id], queryFn: () => api.groundTruths(project.id) });
  const evals = useQuery({ queryKey: ["evaluations", specId], queryFn: () => api.evaluations(specId!), enabled: !!specId });
  const addGt = useMutation({
    mutationFn: () => api.addGroundTruth(project.id, gtKind, gtText),
    onSuccess: (g) => { setGtOpen(false); setGtText(""); setGtId(g.id); qc.invalidateQueries({ queryKey: ["gts", project.id] }); },
    onError: (e) => message.error(errorText(e)),
  });
  const run = useMutation({
    mutationFn: () => api.evaluate(specId!, gtId ?? gts.data?.[0]?.id ?? null),
    onSuccess: (r) => { setJobId(r.job_id); setEvalId(r.resource_id); },
    onError: (e) => message.error(errorText(e)),
  });
  if (!specId) return <Empty description="Chưa có phiên bản đặc tả" />;
  const shown = evalId ?? evals.data?.[0]?.id ?? null;
  const ev = (evals.data ?? []).find((e) => e.id === shown);
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Card size="small">
        <Space wrap>
          <Typography.Text>Ground truth:</Typography.Text>
          <Select style={{ width: 300 }} placeholder="(không – chỉ L1–L4)" allowClear value={gtId ?? gts.data?.[0]?.id}
            onChange={(v) => setGtId(v ?? null)}
            options={(gts.data ?? []).map((g) => ({ value: g.id, label: `#${g.id} · ${g.kind === "doc" ? "GT tài liệu" : "GT hành vi"}${g.note ? ` · ${g.note}` : ""}` }))} />
          <Button icon={<UploadOutlined />} onClick={() => setGtOpen(true)}>Tải lên ground truth</Button>
          <Button type="primary" loading={run.isPending} onClick={() => run.mutate()}>Đánh giá phiên bản này</Button>
          <Select style={{ width: 280 }} placeholder="Lần đánh giá" value={shown ?? undefined} onChange={setEvalId}
            options={(evals.data ?? []).map((e) => ({ value: e.id, label: `#${e.id} · ${e.metrics?.ground_truth_kind ?? "không GT"} · ${fmtDate(e.created_at)}` }))} />
        </Space>
      </Card>
      <JobRunner jobId={jobId} title="Đánh giá" invalidate={[["evaluations", specId]]} onClose={() => setJobId(null)} />
      <ErrorAlert error={evals.error} />
      {ev ? <Report ev={ev} /> : <Empty description="Chưa có kết quả đánh giá cho phiên bản này" />}
      <Modal open={gtOpen} title="Tải lên ground truth (OpenAPI YAML/JSON)" width={760} onCancel={() => setGtOpen(false)}
        onOk={() => addGt.mutate()} okText="Lưu" cancelText="Hủy" confirmLoading={addGt.isPending}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Radio.Group value={gtKind} onChange={(e) => setGtKind(e.target.value)} optionType="button"
            options={[{ value: "doc", label: "GT theo tài liệu" }, { value: "behavior", label: "GT theo hành vi" }]} />
          <Upload showUploadList={false} accept=".yaml,.yml,.json" beforeUpload={(f) => { f.text().then(setGtText); return false; }}>
            <Button icon={<UploadOutlined />}>Chọn tệp</Button>
          </Upload>
          <Input.TextArea rows={16} value={gtText} onChange={(e) => setGtText(e.target.value)} placeholder="openapi: 3.0.3 …" />
        </Space>
      </Modal>
    </Space>
  );
}

function Report({ ev }: { ev: Evaluation }) {
  const m = ev.metrics;
  const st = m?.static;
  const l5 = m?.L5;
  const chart = l5 ? Object.entries(l5.by_category).map(([k, v]) => ({ name: CAT_VI[k] ?? k, P: v.precision, R: v.recall, F1: v.f1 }))
    .concat([{ name: "Ràng buộc (bỏ type)", P: l5.constraint_no_type.precision, R: l5.constraint_no_type.recall, F1: l5.constraint_no_type.f1 }]) : [];
  return (
    <Space direction="vertical" style={{ width: "100%" }} data-testid="evaluation-report">
      <Row gutter={[12, 12]}>
        <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="OAS hợp lệ (L2)" value={st?.L2_valid?.ok ? "Có" : "Không"} /></Card></Col>
        <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="Lint / operation" value={m?.lint_density ?? 0} /></Card></Col>
        <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="Grounding" value={st?.L4_grounding?.applicable ? fmt(st.L4_grounding.grounded_rate, 2) : "n/a"} /></Card></Col>
        {l5 && <>
          <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="Precision" value={fmt(l5.micro.precision)} /></Card></Col>
          <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="Recall" value={fmt(l5.micro.recall)} /></Card></Col>
          <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="F1 (micro)" value={fmt(l5.micro.f1)} /></Card></Col>
          <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="F1 ràng buộc (bỏ type)" value={fmt(l5.constraint_no_type.f1)} valueStyle={{ color: C.lime }} /></Card></Col>
          <Col xs={12} md={6} xl={3}><Card size="small"><Statistic title="Hallucination / Omission" value={`${fmt(l5.hallucination_rate, 2)} / ${fmt(l5.omission_rate, 2)}`} /></Card></Col>
        </>}
      </Row>
      {l5 && (
        <Card size="small" title={`P/R/F1 theo nhóm fact – so với ${m?.ground_truth_kind === "behavior" ? "GT hành vi" : "GT tài liệu"} (${l5.n_pred_facts} fact sinh / ${l5.n_gt_facts} fact GT)`}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chart}>
              <CartesianGrid stroke={C.lineSoft} vertical={false} />
              <XAxis dataKey="name" interval={0} {...chartAxis} />
              <YAxis domain={[0, 1]} {...chartAxis} width={36} />
              <Tooltip formatter={(v: number) => v.toFixed(3)} {...chartTooltip} />
              <Legend wrapperStyle={{ fontSize: 12, fontFamily: FONT_MONO }} />
              <Bar dataKey="P" fill={CHART[1]} radius={[3, 3, 0, 0]} />
              <Bar dataKey="R" fill={CHART[4]} radius={[3, 3, 0, 0]} />
              <Bar dataKey="F1" fill={CHART[0]} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <PrfTable title="Theo nhóm fact" data={l5.by_category} names={CAT_VI} />
          <PrfTable title="Ràng buộc theo từ khóa" data={l5.constraint_by_keyword} />
        </Card>
      )}
      <Collapse size="small" items={[
        ...(ev.facts ? [
          { key: "fp", label: `Fact thừa – FP (${ev.facts.fp.length})`, children: <FactList items={ev.facts.fp} /> },
          { key: "fn", label: `Fact thiếu – FN (${ev.facts.fn.length})`, children: <FactList items={ev.facts.fn} /> },
          { key: "wv", label: `Đúng vị trí, sai giá trị (${ev.facts.wrong_value.length})`, children: (
            <Table size="small" rowKey="key" pagination={false} dataSource={ev.facts.wrong_value} columns={[
              { title: "Fact", dataIndex: "key", render: (k: string) => <code style={{ fontSize: 11 }}>{k}</code> },
              { title: "GT", dataIndex: "gt", render: (v) => <code>{JSON.stringify(v)}</code> },
              { title: "Sinh ra", dataIndex: "pred", render: (v) => <code>{JSON.stringify(v)}</code> },
            ]} />) },
        ] : []),
        { key: "lint", label: `Lỗi lint (${ev.lint_issues?.length ?? 0})`, children: (
          <List size="small" dataSource={ev.lint_issues ?? []} renderItem={(i) => (
            <List.Item><Tag color={i.severity === "error" ? "red" : "orange"}>{i.rule}</Tag>{i.message} <code>{i.pointer}</code></List.Item>)} />) },
        ...(st?.L2_valid?.errors?.length ? [{ key: "l2", label: `Lỗi validate (${st.L2_valid.errors.length})`, children: (
          <List size="small" dataSource={st.L2_valid.errors as { message: string }[]} renderItem={(e) => <List.Item>{e.message}</List.Item>} />) }] : []),
      ]} />
    </Space>
  );
}

function PrfTable({ title, data, names }: { title: string; data: Record<string, PRF>; names?: Record<string, string> }) {
  return (
    <>
      <Typography.Text strong>{title}</Typography.Text>
      <Table size="small" pagination={false} rowKey="k" dataSource={Object.entries(data).map(([k, v]) => ({ k, ...v }))} columns={[
        { title: "Nhóm", dataIndex: "k", render: (k: string) => names?.[k] ?? k },
        { title: "GT", dataIndex: "gt" }, { title: "Sinh", dataIndex: "pred" },
        { title: "TP", dataIndex: "tp" }, { title: "FP", dataIndex: "fp" }, { title: "FN", dataIndex: "fn" },
        { title: "P", dataIndex: "precision", render: (v) => fmt(v) }, { title: "R", dataIndex: "recall", render: (v) => fmt(v) },
        { title: "F1", dataIndex: "f1", render: (v) => <b>{fmt(v)}</b> },
      ]} />
    </>
  );
}

function FactList({ items }: { items: string[] }) {
  return <List size="small" dataSource={items} pagination={items.length > 30 ? { pageSize: 30 } : false}
    renderItem={(k) => <List.Item><code style={{ fontSize: 11 }}>{k}</code></List.Item>} />;
}
