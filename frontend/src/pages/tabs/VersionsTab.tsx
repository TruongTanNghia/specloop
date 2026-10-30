// SC-09: dòng thời gian phiên bản, DiffEditor, diff ngữ nghĩa theo operation, xuất đặc tả.
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Checkbox, Col, Collapse, Empty, Radio, Row, Select, Space, Table, Tag, Timeline, Typography } from "antd";
import { useState } from "react";
import { api } from "../../api/client";
import { ErrorAlert, fmtDate, JsonBlock } from "../../components/common";
import { DiffView } from "../../components/editors";
import { C } from "../../theme";
import type { TabProps } from "./types";

const LABEL_COLOR: Record<string, string> = { generated: "blue", repaired: "cyan", manual: "orange", imported: "default" };

export default function VersionsTab({ specs, specId, selectSpec }: TabProps) {
  const current = specs.find((s) => s.id === specId);
  const [against, setAgainst] = useState<number | undefined>();
  const [format, setFormat] = useState<"yaml" | "json">("yaml");
  const [strip, setStrip] = useState(false);
  const [withEvidence, setWithEvidence] = useState(false);
  const other = against ?? current?.parent_id ?? undefined;
  const diff = useQuery({ queryKey: ["diff", specId, other], queryFn: () => api.diff(specId!, other), enabled: !!specId && !!other });
  const full = useQuery({ queryKey: ["spec", specId], queryFn: () => api.spec(specId!), enabled: !!specId });
  const applied = useQuery({ queryKey: ["proposals", other, "applied"], queryFn: () => api.proposals(other!, "applied,verified"), enabled: !!other });

  if (!specs.length) return <Empty description="Chưa có phiên bản" />;
  return (
    <Row gutter={16}>
      <Col xs={24} xl={6}>
        <Card size="small" title="Dòng thời gian phiên bản">
          <Timeline items={specs.map((s) => ({
            color: s.id === specId ? C.primary : C.faint,
            children: (
              <div style={{ cursor: "pointer" }} onClick={() => { selectSpec(s.id); setAgainst(undefined); }}>
                <Space size={4}><b>v{s.version_no}</b><Tag color={s.label.startsWith("refined") ? "green" : LABEL_COLOR[s.label]}>{s.label}</Tag>
                  {s.id === specId && <Tag color="blue">đang xem</Tag>}</Space>
                <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>#{s.id} · {fmtDate(s.created_at)} · {s.created_by}</Typography.Text></div>
                {s.note && <div style={{ fontSize: 12 }}>{s.note}</div>}
              </div>
            ),
          }))} />
        </Card>
      </Col>
      <Col xs={24} xl={18}>
        <Card size="small" title="Xuất đặc tả" style={{ marginBottom: 12 }}>
          <Space wrap>
            <Radio.Group value={format} onChange={(e) => setFormat(e.target.value)} optionType="button"
              options={[{ value: "yaml", label: "YAML" }, { value: "json", label: "JSON" }]} />
            <Checkbox checked={strip} onChange={(e) => setStrip(e.target.checked)}>Bỏ phần mở rộng x-*</Checkbox>
            <Checkbox checked={withEvidence} onChange={(e) => setWithEvidence(e.target.checked)}>Kèm x-evidence</Checkbox>
            <Button type="primary" href={specId ? api.exportUrl(specId, format, strip, withEvidence) : undefined}>Tải xuống</Button>
          </Space>
        </Card>
        <Card size="small" title={<Space>So sánh
          <Select style={{ width: 260 }} value={other} placeholder="Chọn phiên bản gốc" onChange={setAgainst}
            options={specs.filter((s) => s.id !== specId).map((s) => ({ value: s.id, label: `v${s.version_no} · ${s.label}` }))} />
          → {current ? `v${current.version_no} · ${current.label}` : ""}</Space>}>
          {!other ? <Empty description="Phiên bản gốc – chọn một phiên bản khác để so sánh" /> : (
            <>
              <ErrorAlert error={diff.error} />
              {diff.data && (
                <Space direction="vertical" style={{ width: "100%" }}>
                  <div data-testid="diff-view"><DiffView original={diff.data.from.yaml} modified={diff.data.to.yaml} height={460} /></div>
                  <Typography.Title level={5}>Diff ngữ nghĩa ({diff.data.semantic.changes} thay đổi)</Typography.Title>
                  <Collapse size="small" items={Object.entries(diff.data.semantic.by_operation).map(([op, ch]) => ({
                    key: op, label: <Space><code>{op}</code><Tag>{ch.length}</Tag></Space>,
                    children: <Table size="small" rowKey={(r) => r.path + r.type} pagination={false} dataSource={ch} columns={[
                      { title: "Loại", dataIndex: "type", render: (t: string) => <Tag>{t.replace(/_/g, " ")}</Tag> },
                      { title: "Đường dẫn", dataIndex: "path", render: (p: string) => <code style={{ fontSize: 11 }}>{p}</code> },
                      { title: "Cũ", dataIndex: "old", render: (v) => v === undefined ? "" : <code>{JSON.stringify(v)}</code> },
                      { title: "Mới", dataIndex: "new", render: (v) => v === undefined ? "" : <code>{JSON.stringify(v)}</code> },
                    ]} />,
                  }))} />
                  {!!applied.data?.length && (
                    <>
                      <Typography.Title level={5}>Đề xuất đã áp dụng ({applied.data.filter((p) => p.applied_version_id === specId).length})</Typography.Title>
                      <Table size="small" rowKey="id" pagination={false}
                        dataSource={applied.data.filter((p) => p.applied_version_id === specId)} columns={[
                          { title: "#", dataIndex: "id" }, { title: "Mã", dataIndex: "code" },
                          { title: "Tóm tắt", render: (_, p) => p.finding?.summary },
                          { title: "Độ tin cậy", dataIndex: "confidence", render: (v: number) => v.toFixed(2) },
                          { title: "Trạng thái", dataIndex: "status", render: (s) => <Tag color={s === "verified" ? "purple" : "blue"}>{s === "verified" ? "đã xác minh (hồi quy)" : "đã áp dụng"}</Tag> },
                        ]} />
                    </>
                  )}
                  {full.data?.patch_from_parent && <details><summary>JSON Patch so với phiên bản cha</summary><JsonBlock value={full.data.patch_from_parent} /></details>}
                </Space>
              )}
            </>
          )}
        </Card>
      </Col>
    </Row>
  );
}
