// SC-06 + SC-07: cấu hình & chạy kiểm thử (SSE) và trình xem vết observation.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App, Button, Card, Checkbox, Col, Collapse, Descriptions, Drawer, Empty, Form, Input, InputNumber, Radio, Row, Select, Space,
  Statistic, Switch, Table, Tag, Typography,
} from "antd";
import { useState } from "react";
import { api, errorText } from "../../api/client";
import type { Observation, TestRun, TestRunConfig } from "../../api/types";
import { CodeTag, ErrorAlert, fmtDate, JsonBlock, OutcomeTag } from "../../components/common";
import JobRunner from "../../components/JobRunner";
import type { TabProps } from "./types";

const STRATEGIES: { value: string; label: string }[] = [
  { value: "S2", label: "S2 – dữ liệu cực trị (phát hiện 5xx)" },
  { value: "S3", label: "S3 – bỏ tham số bắt buộc" },
  { value: "S4", label: "S4 – sai kiểu" },
  { value: "S5", label: "S5 – enum" },
  { value: "S6", label: "S6 – dò biên (mũ + nhị phân)" },
  { value: "S7", label: "S7 – định dạng / pattern" },
  { value: "S8", label: "S8 – phụ thuộc giữa tham số" },
  { value: "S9", label: "S9 – lấy mẫu phản hồi" },
];

interface FormValues {
  base_url?: string;
  mode: "auto" | "safe" | "full";
  budget_per_operation?: number;
  max_rps?: number;
  timeout_s?: number;
  repeats: number;
  strategies: string[];
  reset: boolean;
  operations?: string[];
}

export default function TestingTab({ project, specId, goTab }: TabProps) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const [jobId, setJobId] = useState<string | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const runs = useQuery({ queryKey: ["test-runs", project.id], queryFn: () => api.projectTestRuns(project.id) });
  const spec = useQuery({ queryKey: ["spec", specId], queryFn: () => api.spec(specId!), enabled: !!specId });
  const opOptions = Object.entries(spec.data?.content?.paths ?? {}).flatMap(([p, item]) =>
    Object.keys(item as object).filter((m) => ["get", "post", "put", "patch", "delete", "head", "options"].includes(m))
      .map((m) => ({ value: `${m.toUpperCase()} ${p}`, label: `${m.toUpperCase()} ${p}` })));

  const start = useMutation({
    mutationFn: (v: FormValues) => {
      const cfg: TestRunConfig = {
        base_url: v.base_url || null, mode: v.mode === "auto" ? null : v.mode, strategies: v.strategies,
        budget_per_operation: v.budget_per_operation ?? null, max_rps: v.max_rps ?? null, timeout_s: v.timeout_s ?? null,
        repeats: v.repeats, reset: v.reset, operations: v.operations?.length ? v.operations : null,
      };
      return api.startTestRun(specId!, cfg);
    },
    onSuccess: (r) => { setJobId(r.job_id); setRunId(r.resource_id); qc.invalidateQueries({ queryKey: ["test-runs", project.id] }); },
    onError: (e) => message.error(errorText(e)),
  });

  const selectedRun = runId ?? runs.data?.[0]?.id ?? null;
  if (!specId) return <Empty description="Cần một phiên bản đặc tả để kiểm thử" />;
  return (
    <Row gutter={16}>
      <Col xs={24} xl={8}>
        <Card size="small" title="Cấu hình lượt kiểm thử">
          <Form form={form} layout="vertical" onFinish={(v) => start.mutate(v)} initialValues={{
            base_url: project.base_url ?? "", mode: "auto", repeats: 3, strategies: STRATEGIES.map((s) => s.value), reset: true,
          }}>
            <Form.Item name="base_url" label="Base URL" extra="Để trống = base URL của dự án hoặc servers trong đặc tả">
              <Input data-testid="test-base-url" placeholder="http://localhost:8000/v1" />
            </Form.Item>
            <Form.Item name="mode" label="Chế độ">
              <Radio.Group optionType="button" options={[
                { value: "auto", label: "Tự động" }, { value: "safe", label: "Safe (GET/HEAD/OPTIONS)" }, { value: "full", label: "Full" }]} />
            </Form.Item>
            <Space wrap>
              <Form.Item name="budget_per_operation" label="Ngân sách / operation"><InputNumber min={5} max={1000} placeholder="150" /></Form.Item>
              <Form.Item name="max_rps" label="Tốc độ (req/s)"><InputNumber min={0.1} max={100} step={0.5} placeholder="5" /></Form.Item>
              <Form.Item name="timeout_s" label="Timeout (s)"><InputNumber min={1} max={60} placeholder="10" /></Form.Item>
              <Form.Item name="repeats" label="Số lần lặp probe"><InputNumber min={1} max={10} /></Form.Item>
            </Space>
            <Form.Item name="strategies" label="Chiến lược"><Checkbox.Group options={STRATEGIES} style={{ display: "grid" }} /></Form.Item>
            <Form.Item name="operations" label="Chỉ kiểm thử các operation (để trống = tất cả)">
              <Select mode="multiple" options={opOptions} allowClear />
            </Form.Item>
            <Form.Item name="reset" label="Reset dữ liệu SUT trước khi chạy" valuePropName="checked"><Switch /></Form.Item>
            <Button type="primary" htmlType="submit" loading={start.isPending} data-testid="start-test">Chạy kiểm thử</Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} xl={16}>
        <JobRunner jobId={jobId} title="Kiểm thử" onClose={() => setJobId(null)}
          invalidate={[["test-runs", project.id], ["test-run", runId], ["proposals", specId], ["project", project.id]]}
          onFinished={(f) => {
            if (f.status === "succeeded") {
              const n = f.result?.proposals ?? 0;
              message.success(`Kiểm thử xong: ${f.result?.requests ?? 0} request, ${n} đề xuất`);
            }
          }} />
        <Card size="small" title="Các lượt kiểm thử" style={{ marginBottom: 12 }}>
          <Table<TestRun> size="small" rowKey="id" dataSource={runs.data ?? []} pagination={{ pageSize: 5 }}
            rowClassName={(r) => (r.id === selectedRun ? "ant-table-row-selected" : "")}
            onRow={(r) => ({ onClick: () => setRunId(r.id), style: { cursor: "pointer" } })}
            columns={[
              { title: "#", dataIndex: "id", width: 60 },
              { title: "Phiên bản", dataIndex: "spec_version_id", width: 90, render: (v) => `#${v}` },
              { title: "Trạng thái", dataIndex: "status", render: (s) => <Tag color={s === "succeeded" ? "green" : s === "failed" ? "red" : "blue"}>{s}</Tag> },
              { title: "Request", render: (_, r) => r.stats?.requests ?? "–" },
              { title: "Sai lệch", render: (_, r) => <Space size={2} wrap>{Object.entries(r.stats?.findings_by_code ?? {}).map(([c, n]) => <span key={c}><CodeTag code={c} />{n}</span>)}</Space> },
              { title: "Đề xuất", render: (_, r) => r.stats?.proposals ?? "–" },
              { title: "Bắt đầu", dataIndex: "started_at", render: fmtDate },
            ]} />
        </Card>
        {selectedRun && <RunDetail runId={selectedRun} onFindings={() => goTab("proposals")} />}
      </Col>
    </Row>
  );
}

function RunDetail({ runId, onFindings }: { runId: number; onFindings: () => void }) {
  const run = useQuery({ queryKey: ["test-run", runId], queryFn: () => api.testRun(runId),
    refetchInterval: (q) => (q.state.data?.status === "running" || q.state.data?.status === "queued" ? 2000 : false) });
  const [filters, setFilters] = useState<{ operation?: string; strategy?: string; outcome?: string }>({});
  const [page, setPage] = useState(1);
  const [obs, setObs] = useState<Observation | null>(null);
  const list = useQuery({ queryKey: ["observations", runId, filters, page],
    queryFn: () => api.observations(runId, { ...filters, page, size: 20 }) });
  const r = run.data;
  const st = r?.stats;
  return (
    <Card size="small" title={`Lượt kiểm thử #${runId}`} extra={
      <Space>
        {r && (r.status === "running" || r.status === "queued") && <Button danger size="small" onClick={() => api.cancelTestRun(runId)}>Hủy</Button>}
        <Button size="small" type="primary" onClick={onFindings}>Xem sai lệch & đề xuất →</Button>
      </Space>}>
      <ErrorAlert error={run.error} />
      {r?.error && <Typography.Text type="danger">{r.error}</Typography.Text>}
      {st && (
        <>
          <Row gutter={12} style={{ marginBottom: 8 }}>
            <Col span={4}><Statistic title="Request" value={st.requests ?? 0} /></Col>
            <Col span={4}><Statistic title="Thời gian (s)" value={st.duration_s ?? 0} /></Col>
            <Col span={4}><Statistic title="Sai lệch" value={st.findings ?? 0} /></Col>
            <Col span={4}><Statistic title="Đề xuất" value={st.proposals ?? 0} /></Col>
            <Col span={8}><Space wrap>{Object.entries(st.outcomes ?? {}).map(([k, v]) => <span key={k}><OutcomeTag outcome={k} />{v}</span>)}</Space></Col>
          </Row>
          <Collapse size="small" items={[
            { key: "op", label: "Theo operation", children: (
              <Descriptions size="small" column={1} items={Object.entries(st.operations ?? {}).map(([op, s]) => ({
                key: op, label: <code>{op}</code>, children: `${s} · ${st.requests_by_operation?.[op] ?? 0} request` }))} />) },
            { key: "cfg", label: "Cấu hình hiệu lực", children: <JsonBlock value={st.effective_config} /> },
            { key: "v", label: `Ràng buộc đã kiểm chứng (${st.verified?.length ?? 0})`, children: (
              <Table size="small" rowKey={(x) => `${x.operation}${x.location}${x.check}`} pagination={false} dataSource={st.verified ?? []}
                columns={[{ title: "Operation", dataIndex: "operation" }, { title: "Vị trí", dataIndex: "location" },
                  { title: "Kiểm tra", dataIndex: "check" }, { title: "Số quan sát", dataIndex: "observations" }]} />) },
            { key: "u", label: `Chưa xác minh (${st.unverified?.length ?? 0})`, children: (
              <Table size="small" rowKey={(x) => `${x.operation}${x.location}${x.check}`} pagination={false} dataSource={st.unverified ?? []}
                columns={[{ title: "Operation", dataIndex: "operation" }, { title: "Vị trí", dataIndex: "location" },
                  { title: "Kiểm tra", dataIndex: "check" }, { title: "Lý do", dataIndex: "reason" }]} />) },
          ]} />
        </>
      )}
      <Typography.Title level={5} style={{ marginTop: 12 }}>Vết request/response</Typography.Title>
      <Space wrap style={{ marginBottom: 8 }}>
        <Select allowClear placeholder="Operation" style={{ width: 240 }} value={filters.operation}
          options={(list.data?.facets.operations ?? []).map((o) => ({ value: o, label: o }))}
          onChange={(v) => { setFilters({ ...filters, operation: v }); setPage(1); }} />
        <Select allowClear placeholder="Chiến lược" style={{ width: 140 }} value={filters.strategy}
          options={(list.data?.facets.strategies ?? []).map((o) => ({ value: o, label: o }))}
          onChange={(v) => { setFilters({ ...filters, strategy: v }); setPage(1); }} />
        <Select allowClear placeholder="Kết quả" style={{ width: 140 }} value={filters.outcome}
          options={["ACCEPT", "REJECT", "NOT_FOUND", "SERVER_ERR", "AUTH", "RATE", "OTHER"].map((o) => ({ value: o, label: o }))}
          onChange={(v) => { setFilters({ ...filters, outcome: v }); setPage(1); }} />
      </Space>
      <ObservationTable data={list.data?.items ?? []} loading={list.isLoading} onOpen={setObs}
        pagination={{ current: page, pageSize: 20, total: list.data?.total ?? 0, onChange: setPage, showSizeChanger: false }} />
      <ObservationDrawer obs={obs} onClose={() => setObs(null)} />
    </Card>
  );
}

export function ObservationTable({ data, loading, onOpen, pagination }: {
  data: Observation[];
  loading?: boolean;
  onOpen: (o: Observation) => void;
  pagination?: false | object;
}) {
  return (
    <Table<Observation> size="small" rowKey="id" loading={loading} dataSource={data} pagination={pagination ?? false}
      onRow={(o) => ({ onClick: () => onOpen(o), style: { cursor: "pointer" } })}
      columns={[
        { title: "#", dataIndex: "id", width: 70 },
        ...(data.some((o) => o.role) ? [{ title: "Vai trò", dataIndex: "role", width: 90, render: (v: string) => <Tag color={v === "support" ? "green" : "red"}>{v === "support" ? "ủng hộ" : "mâu thuẫn"}</Tag> }] : []),
        { title: "Operation", dataIndex: "operation_id" },
        { title: "Chiến lược", dataIndex: "strategy" },
        { title: "Probe", dataIndex: "probe", render: (p) => p ? <code style={{ fontSize: 11 }}>{JSON.stringify(p).slice(0, 70)}</code> : "–" },
        { title: "HTTP", dataIndex: "status_code", width: 60 },
        { title: "Kết quả", dataIndex: "outcome", render: (o) => <OutcomeTag outcome={o} /> },
        { title: "ms", dataIndex: "latency_ms", width: 60, render: (v) => v?.toFixed(0) },
      ]} />
  );
}

export function ObservationDrawer({ obs, onClose }: { obs: Observation | null; onClose: () => void }) {
  return (
    <Drawer open={!!obs} onClose={onClose} width={640} title={obs ? `Observation #${obs.id} – ${obs.operation_id}` : ""}>
      {obs && (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Space wrap><Tag>{obs.strategy}</Tag><OutcomeTag outcome={obs.outcome} /><Tag>HTTP {obs.status_code ?? "–"}</Tag>
            <Tag>{obs.latency_ms?.toFixed(1)} ms</Tag><Tag>lần {obs.repeat_index}</Tag></Space>
          <Typography.Text strong>Probe</Typography.Text>
          <JsonBlock value={obs.probe} />
          <Typography.Text strong>Request</Typography.Text>
          <Typography.Text code>{obs.request.method} {obs.request.url}</Typography.Text>
          <JsonBlock value={{ query: obs.request.query, headers: obs.request.headers, body: obs.request.body }} />
          <Typography.Text strong>Response</Typography.Text>
          <JsonBlock value={obs.response} maxHeight={480} />
        </Space>
      )}
    </Drawer>
  );
}
