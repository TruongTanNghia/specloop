// SC-04: trình xem đặc tả 3 khung – tài liệu (trích dẫn) | YAML (Monaco) | Swagger UI.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, App, Badge, Button, Card, Checkbox, Col, Collapse, Empty, Input, List, Modal, Row, Select, Space, Spin, Tag, Typography,
} from "antd";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import yaml from "js-yaml";
import { api, errorText } from "../../api/client";
import type { EvidenceItem, ValidationReport } from "../../api/types";
import { ErrorAlert } from "../../components/common";
import EvidenceDoc from "../../components/EvidenceDoc";
import JobRunner from "../../components/JobRunner";
import { YamlEditor, type OnMount } from "../../components/editors";
import { pointerAtLine } from "../../lib/yamlPointer";
import type { TabProps } from "./types";

const SwaggerView = lazy(() => import("../../components/SwaggerView"));

export default function SpecTab({ project, specs, specId, selectSpec }: TabProps) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [model, setModel] = useState<string>("fake");
  const [repair, setRepair] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [draft, setDraft] = useState<string | null>(null);
  const [pointer, setPointer] = useState<string>("");
  const [active, setActive] = useState<EvidenceItem[]>([]);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [showSwagger, setShowSwagger] = useState(true);

  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const modelOptions = (providers.data ?? []).flatMap((p) => p.models.map((m) => ({
    value: m, label: `${m} – ${p.name}`, disabled: !p.available })));
  const docs = useQuery({ queryKey: ["documents", project.id], queryFn: () => api.documents(project.id) });
  const docId = docs.data?.[0]?.id;
  const doc = useQuery({ queryKey: ["document", docId], queryFn: () => api.document(docId!), enabled: !!docId });
  const yamlQ = useQuery({ queryKey: ["spec-yaml", specId], queryFn: () => api.specYaml(specId!), enabled: !!specId });
  const spec = useQuery({ queryKey: ["spec", specId], queryFn: () => api.spec(specId!), enabled: !!specId });
  const evidence = useQuery({ queryKey: ["evidence", specId], queryFn: () => api.evidence(specId!), enabled: !!specId });

  useEffect(() => { setDraft(null); setReport(null); setActive([]); setPointer(""); }, [specId]);
  const text = draft ?? yamlQ.data ?? "";
  const dirty = draft !== null && draft !== yamlQ.data;
  const parsedDraft = useMemo(() => {
    try { return { spec: yaml.load(text) as object, error: null as string | null }; } catch (e) { return { spec: null, error: String(e) }; }
  }, [text]);

  const gen = useMutation({
    mutationFn: () => api.generate(project.id, { model, repair, document_id: docId }),
    onSuccess: (r) => setJobId(r.job_id),
    onError: (e) => message.error(errorText(e)),
  });
  const imp = useMutation({
    mutationFn: () => api.importSpec(project.id, importText, "Nhập từ giao diện"),
    onSuccess: (v) => {
      setImportOpen(false); setImportText("");
      qc.invalidateQueries({ queryKey: ["specs", project.id] });
      selectSpec(v.id);
      message.success(`Đã nhập phiên bản v${v.version_no}`);
    },
    onError: (e) => message.error(errorText(e)),
  });
  const save = useMutation({
    mutationFn: () => api.manualVersion(specId!, text, "Sửa tay trên trình soạn YAML"),
    onSuccess: (v) => {
      qc.invalidateQueries({ queryKey: ["specs", project.id] });
      selectSpec(v.id);
      message.success(`Đã lưu phiên bản v${v.version_no} (manual)`);
    },
    onError: (e) => message.error(errorText(e)),
  });
  const validate = useMutation({
    mutationFn: () => api.validate(specId!),
    onSuccess: setReport,
    onError: (e) => message.error(errorText(e)),
  });

  const onMount: OnMount = (editor) => {
    editor.onMouseDown(async (e) => {
      const line = e.target.position?.lineNumber;
      if (!line) return;
      const p = pointerAtLine(editor.getValue(), line);
      setPointer(p);
      if (!p || !specId) return;
      try {
        setActive(await api.evidence(specId, p));
      } catch {
        setActive([]);
      }
    });
  };

  const current = specs.find((s) => s.id === specId);
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Card size="small">
        <Space wrap>
          <Typography.Text strong>Sinh đặc tả từ tài liệu:</Typography.Text>
          <Select style={{ width: 300 }} value={model} onChange={setModel} options={modelOptions} data-testid="model-select" />
          <Checkbox checked={repair} onChange={(e) => setRepair(e.target.checked)}>Vòng sửa lỗi (C1)</Checkbox>
          <Button type="primary" data-testid="generate-btn" disabled={!docId} loading={gen.isPending} onClick={() => gen.mutate()}>
            Sinh OAS
          </Button>
          <Button onClick={() => setImportOpen(true)}>Nhập OAS có sẵn</Button>
          <Button disabled={!specId} loading={validate.isPending} onClick={() => validate.mutate()}>Kiểm tra L1–L4</Button>
          <Button disabled={!dirty || !!parsedDraft.error} loading={save.isPending} onClick={() => save.mutate()}>
            Lưu phiên bản sửa tay
          </Button>
          <Checkbox checked={showSwagger} onChange={(e) => setShowSwagger(e.target.checked)}>Swagger UI</Checkbox>
        </Space>
        {!docId && <Alert style={{ marginTop: 8 }} type="info" showIcon message="Chưa có tài liệu – hãy nạp ở tab Tài liệu, hoặc nhập OAS có sẵn." />}
      </Card>
      <JobRunner jobId={jobId} title="Sinh đặc tả" invalidate={[["specs", project.id], ["project", project.id]]}
        onClose={() => setJobId(null)}
        onFinished={(f) => {
          const vid = f.result?.version_id;
          if (f.status === "succeeded" && vid) {
            const st = f.result?.stats ?? {};
            message.success(`Đã sinh ${st.operations ?? "?"} operation (${st.input_tokens ?? 0}/${st.output_tokens ?? 0} token)`);
            selectSpec(vid);
          }
        }} />
      {report && <ValidationPanel report={report} onClose={() => setReport(null)} />}
      {!specId ? <Empty description="Chưa có phiên bản đặc tả" /> : (
        <>
          <Space wrap>
            {current && <Tag color="blue">v{current.version_no} · {current.label}</Tag>}
            {current?.model && <Tag>mô hình: {current.model}</Tag>}
            {current?.note && <Typography.Text type="secondary">{current.note}</Typography.Text>}
            {pointer && <Typography.Text>Phần tử: <code data-testid="pointer">{pointer}</code></Typography.Text>}
            {pointer && <Badge count={active.length} showZero color={active.length ? "#52c41a" : "#bfbfbf"} title="Số trích dẫn" />}
            {dirty && <Tag color="orange">Có thay đổi chưa lưu</Tag>}
            {parsedDraft.error && <Tag color="red">YAML lỗi</Tag>}
          </Space>
          <Row gutter={12}>
            <Col xs={24} xl={showSwagger ? 7 : 10}>
              <Card size="small" title={`Tài liệu (${evidence.data?.length ?? 0} trích dẫn)`} bodyStyle={{ padding: 6 }}>
                {doc.data?.markdown ? (
                  <EvidenceDoc text={doc.data.markdown} evidence={evidence.data ?? []} activeIds={active.map((a) => a.id)} />
                ) : <Empty description="Không có tài liệu" />}
                {active.length > 0 && (
                  <List size="small" style={{ marginTop: 6 }} dataSource={active} renderItem={(e) => (
                    <List.Item><Typography.Text style={{ fontSize: 12 }}><code>{e.json_pointer}</code> · khớp {e.match_score ?? "–"} · “{e.quote}”</Typography.Text></List.Item>
                  )} />
                )}
                {pointer && active.length === 0 && <Typography.Text type="secondary">Phần tử này không có trích dẫn tài liệu.</Typography.Text>}
              </Card>
            </Col>
            <Col xs={24} xl={showSwagger ? 9 : 14}>
              <Card size="small" title="YAML (bấm vào một dòng để xem trích dẫn)" bodyStyle={{ padding: 0 }}>
                <ErrorAlert error={yamlQ.error} />
                {yamlQ.isLoading ? <Spin /> : <YamlEditor value={text} onChange={setDraft} onMount={onMount} height={620} />}
              </Card>
            </Col>
            {showSwagger && (
              <Col xs={24} xl={8}>
                <Card size="small" title="Swagger UI" bodyStyle={{ padding: 0 }}>
                  <Suspense fallback={<Spin />}>
                    {parsedDraft.spec ? <SwaggerView spec={parsedDraft.spec} /> : spec.data?.content ? <SwaggerView spec={spec.data.content} /> : null}
                  </Suspense>
                </Card>
              </Col>
            )}
          </Row>
        </>
      )}
      <Modal open={importOpen} title="Nhập đặc tả OpenAPI (YAML/JSON, 3.0.x hoặc 3.1 – tự chuẩn hóa về 3.0.3)" width={800}
        onCancel={() => setImportOpen(false)} onOk={() => imp.mutate()} okText="Nhập" cancelText="Hủy" confirmLoading={imp.isPending}>
        <Input.TextArea rows={20} value={importText} onChange={(e) => setImportText(e.target.value)} placeholder="openapi: 3.0.3 …" />
      </Modal>
    </Space>
  );
}

function ValidationPanel({ report, onClose }: { report: ValidationReport; onClose: () => void }) {
  const g = report.L4_grounding;
  return (
    <Card size="small" title="Kết quả kiểm tra L1–L4" extra={<Button size="small" onClick={onClose}>Đóng</Button>} data-testid="validation-panel">
      <Space wrap style={{ marginBottom: 8 }}>
        <Tag color={report.L1_parse.ok ? "green" : "red"}>L1 Parse: {report.L1_parse.ok ? "đạt" : "lỗi"}</Tag>
        <Tag color={report.L2_valid.ok ? "green" : "red"}>L2 OAS 3.0.3: {report.L2_valid.ok ? "hợp lệ" : `${report.L2_valid.errors.length} lỗi`}</Tag>
        <Tag color={report.L3_lint.count ? "orange" : "green"}>L3 Lint: {report.L3_lint.count} vấn đề ({report.L3_lint.density}/operation)</Tag>
        <Tag color={!g.applicable ? "default" : g.grounded_rate === 1 ? "green" : "orange"}>
          L4 Grounding: {g.applicable ? `${g.grounded}/${g.evidence} trích dẫn khớp (≥90), ${g.elements_without_evidence_count} phần tử thiếu căn cứ` : g.note}
        </Tag>
        <Tag>{report.operations} operation</Tag>
      </Space>
      <Collapse size="small" items={[
        ...(report.L2_valid.errors.length ? [{ key: "e", label: `Lỗi validate (${report.L2_valid.errors.length})`, children: (
          <List size="small" dataSource={report.L2_valid.errors} renderItem={(e) => <List.Item><code>{e.path.join("/")}</code> {e.message}</List.Item>} />) }] : []),
        ...(report.L3_lint.issues.length ? [{ key: "l", label: `Lint (${report.L3_lint.issues.length})`, children: (
          <List size="small" dataSource={report.L3_lint.issues} renderItem={(i) => (
            <List.Item><Tag color={i.severity === "error" ? "red" : "orange"}>{i.rule}</Tag>{i.message} <code>{i.pointer}</code></List.Item>)} />) }] : []),
        ...(g.suspected_hallucination?.length ? [{ key: "h", label: `Nghi hallucination (${g.suspected_hallucination.length})`, children: (
          <List size="small" dataSource={g.suspected_hallucination} renderItem={(h) => <List.Item><code>{h.pointer}</code> ({h.score}) “{h.quote}”</List.Item>} />) }] : []),
        ...(g.elements_without_evidence?.length ? [{ key: "w", label: `Phần tử không có trích dẫn (${g.elements_without_evidence_count})`, children: (
          <List size="small" dataSource={g.elements_without_evidence} renderItem={(p) => <List.Item><code>{p}</code></List.Item>} />) }] : []),
      ]} />
    </Card>
  );
}
