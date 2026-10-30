// SC-08: sai lệch & đề xuất – bằng chứng tài liệu + runtime, JSON Patch, YAML trước/sau, duyệt, áp dụng, vòng lặp tự động.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, App, Button, Card, Checkbox, Col, Descriptions, Empty, Input, InputNumber, Modal, Row, Select, Slider, Space, Table, Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";
import { api, errorText } from "../../api/client";
import type { Finding, JsonPatchOp, Observation, Proposal } from "../../api/types";
import { Chip, CODE_INFO, CodeTag, ConfidenceBar, ErrorAlert, JsonBlock, TIER_TEXT } from "../../components/common";
import { DiffView } from "../../components/editors";
import JobRunner from "../../components/JobRunner";
import { applyPatch, patchScope, subtree, toYaml } from "../../lib/patch";
import { ObservationDrawer, ObservationTable } from "./TestingTab";
import type { TabProps } from "./types";

const STATUS_TEXT: Record<string, { text: string; color: string }> = {
  pending: { text: "Chờ duyệt", color: "default" }, accepted: { text: "Đã chấp nhận", color: "green" },
  rejected: { text: "Đã từ chối", color: "red" }, edited: { text: "Đã sửa", color: "cyan" },
  applied: { text: "Đã áp dụng", color: "blue" }, verified: { text: "Đã xác minh", color: "purple" },
};

interface Row {
  key: string;
  finding: Finding;
  proposal: Proposal | null;
}

export default function ProposalsTab({ project, specId, selectSpec, goTab }: TabProps) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [code, setCode] = useState<string | undefined>();
  const [threshold, setThreshold] = useState(0.8);
  const [includeConflicts, setIncludeConflicts] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [loopOpen, setLoopOpen] = useState(false);
  const [loopJob, setLoopJob] = useState<string | null>(null);
  const [loopCfg, setLoopCfg] = useState({ max_iter: 3, auto_accept_threshold: 0.8, min_confidence: 0.5, base_url: project.base_url ?? "" });

  const proposals = useQuery({ queryKey: ["proposals", specId], queryFn: () => api.proposals(specId!), enabled: !!specId });
  const runs = useQuery({ queryKey: ["test-runs", project.id], queryFn: () => api.projectTestRuns(project.id) });
  const lastRun = (runs.data ?? []).find((r) => r.spec_version_id === specId && r.status === "succeeded");
  const findings = useQuery({ queryKey: ["findings", lastRun?.id], queryFn: () => api.findings(lastRun!.id), enabled: !!lastRun });
  const spec = useQuery({ queryKey: ["spec", specId], queryFn: () => api.spec(specId!), enabled: !!specId });

  const rows: Row[] = useMemo(() => {
    const byFinding = new Map<number, Proposal>();
    for (const p of proposals.data ?? []) byFinding.set(p.finding_id, p);
    const out: Row[] = [];
    const seen = new Set<number>();
    for (const p of proposals.data ?? []) {
      if (p.finding) { out.push({ key: `p${p.id}`, finding: p.finding, proposal: p }); seen.add(p.finding_id); }
    }
    for (const f of findings.data ?? []) if (!seen.has(f.id)) out.push({ key: `f${f.id}`, finding: f, proposal: byFinding.get(f.id) ?? null });
    return out.filter((r) => !code || r.finding.code === code)
      .sort((a, b) => (b.proposal ? 1 : 0) - (a.proposal ? 1 : 0) || b.finding.confidence - a.finding.confidence);
  }, [proposals.data, findings.data, code]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["proposals", specId] });
    qc.invalidateQueries({ queryKey: ["project", project.id] });
  };
  const onErr = (e: unknown) => message.error(errorText(e));
  const review = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "accept" | "reject" }) => (action === "accept" ? api.accept(id) : api.reject(id)),
    onSuccess: invalidate, onError: onErr,
  });
  const bulk = useMutation({
    mutationFn: () => api.acceptThreshold(specId!, threshold, includeConflicts),
    onSuccess: (r) => { message.success(`Đã chấp nhận ${r.length} đề xuất`); invalidate(); }, onError: onErr,
  });
  const apply = useMutation({
    mutationFn: () => api.apply(specId!),
    onSuccess: (v) => {
      message.success(`Đã tạo phiên bản v${v.version_no} (${v.label})`);
      (v.stats?.warnings ?? []).forEach((w) => message.warning(w));
      qc.invalidateQueries({ queryKey: ["specs", project.id] });
      invalidate();
      selectSpec(v.id);
      goTab("versions", v.id);
    },
    onError: onErr,
  });
  const loop = useMutation({
    mutationFn: () => api.refineLoop(specId!, { max_iter: loopCfg.max_iter, auto_accept_threshold: loopCfg.auto_accept_threshold,
      min_confidence: loopCfg.min_confidence, test_config: { base_url: loopCfg.base_url || null } }),
    onSuccess: (r) => { setLoopJob(r.job_id); setLoopOpen(false); }, onError: onErr,
  });

  if (!specId) return <Empty description="Chưa có phiên bản đặc tả" />;
  const props = proposals.data ?? [];
  const accepted = props.filter((p) => p.status === "accepted" || p.status === "edited").length;
  const pending = props.filter((p) => p.status === "pending").length;
  const current = rows.find((r) => r.key === selected) ?? null;
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Card size="small">
        <Space wrap>
          <Select allowClear placeholder="Lọc theo mã" style={{ width: 220 }} value={code} onChange={setCode}
            options={Object.entries(CODE_INFO).map(([k, v]) => ({ value: k, label: `${k} – ${v.label}` }))} />
          <Typography.Text>Ngưỡng:</Typography.Text>
          <Slider style={{ width: 140 }} min={0.5} max={1} step={0.05} value={threshold} onChange={setThreshold} />
          <Typography.Text>{threshold.toFixed(2)}</Typography.Text>
          <Checkbox checked={includeConflicts} onChange={(e) => setIncludeConflicts(e.target.checked)}>Gồm mâu thuẫn tài liệu</Checkbox>
          <Button disabled={!pending} loading={bulk.isPending} onClick={() => bulk.mutate()}>Chấp nhận hàng loạt ≥ ngưỡng</Button>
          <Button type="primary" data-testid="apply-btn" disabled={!accepted} loading={apply.isPending} onClick={() => apply.mutate()}>
            Áp dụng {accepted} đề xuất → phiên bản mới
          </Button>
          <Button onClick={() => setLoopOpen(true)}>Vòng lặp tự động…</Button>
        </Space>
        <div style={{ marginTop: 6 }}>
          <Typography.Text type="secondary">
            {props.length} đề xuất ({pending} chờ, {accepted} đã chấp nhận) · lượt kiểm thử gần nhất trên phiên bản này: {lastRun ? `#${lastRun.id}` : "chưa có"}
          </Typography.Text>
        </div>
      </Card>
      <JobRunner jobId={loopJob} title="Vòng lặp tinh chỉnh" onClose={() => setLoopJob(null)}
        invalidate={[["specs", project.id], ["proposals", specId], ["test-runs", project.id], ["project", project.id]]}
        onFinished={(f) => {
          if (f.status === "succeeded" && f.result) {
            message.info(`Dừng: ${f.result.stop_reason}`);
            if (f.result.final_spec_id && f.result.final_spec_id !== specId) selectSpec(f.result.final_spec_id);
          }
        }} />
      <ErrorAlert error={proposals.error || findings.error} />
      <Row gutter={12}>
        <Col xs={24} xxl={13}>
          <Table<Row> size="small" rowKey="key" dataSource={rows} loading={proposals.isLoading} pagination={{ pageSize: 15 }}
            data-testid="proposals-table"
            rowClassName={(r) => (r.key === selected ? "ant-table-row-selected" : "")}
            onRow={(r) => ({ onClick: () => setSelected(r.key), style: { cursor: "pointer" } })}
            columns={[
              { title: "Mã", width: 60, render: (_, r) => <CodeTag code={r.finding.code} /> },
              { title: "Operation / vị trí", render: (_, r) => <><code>{r.finding.operation_id}</code><br />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.finding.location}</Typography.Text></> },
              { title: "Độ tin cậy", width: 116, render: (_, r) => <ConfidenceBar value={r.proposal?.confidence ?? r.finding.confidence} width={100} /> },
              { title: "Nhãn / trạng thái", render: (_, r) => <Space direction="vertical" size={3}>
                {r.proposal ? <Chip tone={TIER_TEXT[r.proposal.tier].tone}>{TIER_TEXT[r.proposal.tier].text}</Chip> : <Chip tone="muted">Chỉ báo cáo</Chip>}
                {r.finding.doc_conflict && <Chip tone="coral">Mâu thuẫn tài liệu</Chip>}
                {r.proposal ? <Tag color={STATUS_TEXT[r.proposal.status]?.color}>{STATUS_TEXT[r.proposal.status]?.text ?? r.proposal.status}</Tag> : <Tag>{r.finding.status}</Tag>}
              </Space> },
              { title: "", render: (_, r) => r.proposal && ["pending", "rejected", "accepted", "edited"].includes(r.proposal.status) ? (
                <Space size={4} wrap onClick={(e) => e.stopPropagation()}>
                  <Button size="small" type="primary" data-testid={`accept-${r.proposal.id}`} disabled={r.proposal.status === "accepted"}
                    onClick={() => review.mutate({ id: r.proposal!.id, action: "accept" })}>Chấp nhận</Button>
                  <Button size="small" danger disabled={r.proposal.status === "rejected"}
                    onClick={() => review.mutate({ id: r.proposal!.id, action: "reject" })}>Từ chối</Button>
                </Space>) : null },
            ]} />
        </Col>
        <Col xs={24} xxl={11}>
          {current ? <Detail row={current} content={spec.data?.content} onChanged={invalidate} /> :
            <Empty description="Chọn một sai lệch để xem bằng chứng và JSON Patch" />}
        </Col>
      </Row>
      <Modal open={loopOpen} title="Vòng lặp tinh chỉnh tự động" onCancel={() => setLoopOpen(false)} onOk={() => loop.mutate()}
        okText="Chạy" cancelText="Hủy" confirmLoading={loop.isPending}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Alert type="info" showIcon message="Mỗi vòng: kiểm thử → tự chấp nhận đề xuất có độ tin cậy ≥ ngưỡng và không mâu thuẫn tài liệu → phiên bản mới. Dừng khi không còn đề xuất ≥ độ tin cậy tối thiểu." />
          <Space wrap>
            <span>Số vòng tối đa K <InputNumber min={1} max={10} value={loopCfg.max_iter} onChange={(v) => setLoopCfg({ ...loopCfg, max_iter: Number(v) || 3 })} /></span>
            <span>Ngưỡng tự chấp nhận <InputNumber min={0.5} max={1} step={0.05} value={loopCfg.auto_accept_threshold} onChange={(v) => setLoopCfg({ ...loopCfg, auto_accept_threshold: Number(v) || 0.8 })} /></span>
            <span>Độ tin cậy tối thiểu τ <InputNumber min={0} max={1} step={0.05} value={loopCfg.min_confidence} onChange={(v) => setLoopCfg({ ...loopCfg, min_confidence: Number(v) || 0.5 })} /></span>
          </Space>
          <Input addonBefore="Base URL" value={loopCfg.base_url} onChange={(e) => setLoopCfg({ ...loopCfg, base_url: e.target.value })} />
        </Space>
      </Modal>
    </Space>
  );
}

function Detail({ row, content, onChanged }: { row: Row; content: any; onChanged: () => void }) {
  const { message } = App.useApp();
  const { finding: f, proposal: p } = row;
  const [editing, setEditing] = useState<string | null>(null);
  const [obs, setObs] = useState<Observation | null>(null);
  const runtime = useQuery({ queryKey: ["finding", f.id], queryFn: () => api.finding(f.id) });
  const edit = useMutation({
    mutationFn: (ops: JsonPatchOp[]) => api.editProposal(p!.id, ops),
    onSuccess: () => { setEditing(null); onChanged(); message.success("Đã lưu JSON Patch đã sửa"); },
    onError: (e) => message.error(errorText(e)),
  });
  const preview = useMemo(() => {
    if (!p || !content) return null;
    const { result, warnings } = applyPatch(content, p.json_patch);
    const scope = patchScope(p.json_patch);
    const before = subtree(content, scope);
    const after = subtree(result, scope);
    return { before: before === undefined ? "" : toYaml(before), after: after === undefined ? "" : toYaml(after), scope, warnings };
  }, [p, content]);

  return (
    <Card size="small" title={<Space><CodeTag code={f.code} />{CODE_INFO[f.code]?.label}</Space>} data-testid="finding-detail">
      <Typography.Paragraph>{f.summary}</Typography.Paragraph>
      <Descriptions size="small" column={2} items={[
        { key: "o", label: "Operation", children: <code>{f.operation_id}</code> },
        { key: "l", label: "Vị trí", children: f.location },
        { key: "p", label: "JSON Pointer", children: <code style={{ fontSize: 11 }}>{f.json_pointer}</code> },
        { key: "c", label: "Độ tin cậy", children: <ConfidenceBar value={p?.confidence ?? f.confidence} width={160} /> },
        ...(p?.channels ? [{ key: "ch", label: "Kênh bằng chứng", children: <Space wrap>{Object.entries(p.channels).map(([k, v]) => <Tag key={k}>{k}: {v.toFixed(2)}</Tag>)}</Space> }] : []),
        ...(f.doc_conflict ? [{ key: "dc", label: "Ghi chú", children: <Tag color="red">Mâu thuẫn tài liệu – cài đặt (không tự động chấp nhận)</Tag> }] : []),
      ]} />
      <Typography.Title level={5}>Bằng chứng tài liệu</Typography.Title>
      {p?.evidence?.doc?.length ? p.evidence.doc.map((d, i) => (
        <Alert key={i} type="info" style={{ marginBottom: 4 }} message={<>“{d.quote}” <Typography.Text type="secondary">({d.pointer})</Typography.Text></>} />
      )) : <Typography.Text type="secondary">Không có trích dẫn tài liệu cho phần tử này (đặc tả nhập sẵn hoặc tài liệu không nêu).</Typography.Text>}
      {(p?.evidence?.message || f.details?.message) && (
        <Alert type="warning" style={{ marginTop: 6 }} message={<>Thông báo lỗi từ API: <code>{p?.evidence?.message ?? f.details?.message}</code></>} />
      )}
      <Typography.Title level={5} style={{ marginTop: 12 }}>Bằng chứng runtime ({runtime.data?.observations.length ?? 0} observation)</Typography.Title>
      <ObservationTable data={runtime.data?.observations ?? []} loading={runtime.isLoading} onOpen={setObs} pagination={{ pageSize: 5 }} />
      <ObservationDrawer obs={obs} onClose={() => setObs(null)} />
      {f.details && <details style={{ marginTop: 6 }}><summary>Chi tiết phân tích</summary><JsonBlock value={f.details} /></details>}
      {p ? (
        <>
          <Space style={{ marginTop: 12, justifyContent: "space-between", width: "100%" }}>
            <Typography.Title level={5} style={{ margin: 0 }}>JSON Patch (RFC 6902)</Typography.Title>
            {["pending", "accepted", "edited", "rejected"].includes(p.status) && (
              editing === null ? <Button size="small" onClick={() => setEditing(JSON.stringify(p.json_patch, null, 2))}>Sửa</Button> :
                <Space><Button size="small" onClick={() => setEditing(null)}>Hủy</Button>
                  <Button size="small" type="primary" loading={edit.isPending} onClick={() => {
                    try { edit.mutate(JSON.parse(editing)); } catch (e) { message.error(`JSON không hợp lệ: ${e}`); }
                  }}>Lưu</Button></Space>
            )}
          </Space>
          {editing !== null ? <Input.TextArea rows={8} value={editing} onChange={(e) => setEditing(e.target.value)} className="patch-op" />
            : <JsonBlock value={p.json_patch} maxHeight={200} />}
          {preview && (
            <>
              <Typography.Title level={5} style={{ marginTop: 12 }}>YAML trước / sau <Typography.Text type="secondary" style={{ fontSize: 12 }}>{preview.scope || "/"}</Typography.Text></Typography.Title>
              {preview.warnings.map((w) => <Alert key={w} type="warning" message={w} />)}
              <DiffView original={preview.before} modified={preview.after} height={300} />
            </>
          )}
        </>
      ) : <Alert style={{ marginTop: 12 }} type="info" message={f.code === "D0" ? "Lỗi máy chủ – chỉ báo cáo, không sửa đặc tả tự động." : "Chỉ báo cáo, không có đề xuất sửa đặc tả."} />}
    </Card>
  );
}
