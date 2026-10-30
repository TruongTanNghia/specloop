import { SettingOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Breadcrumb, Button, Descriptions, Select, Space, Tabs, Tag, Typography } from "antd";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, errorText } from "../api/client";
import { ErrorAlert } from "../components/common";
import ProjectForm from "../components/ProjectForm";
import DocumentsTab from "./tabs/DocumentsTab";
import EvaluationTab from "./tabs/EvaluationTab";
import ProposalsTab from "./tabs/ProposalsTab";
import SpecTab from "./tabs/SpecTab";
import TestingTab from "./tabs/TestingTab";
import VersionsTab from "./tabs/VersionsTab";

export default function ProjectDetailPage() {
  const projectId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [editing, setEditing] = useState(false);
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api.project(projectId) });
  const specs = useQuery({ queryKey: ["specs", projectId], queryFn: () => api.specs(projectId) });
  const update = useMutation({
    mutationFn: (v: Parameters<typeof api.updateProject>[1]) => api.updateProject(projectId, v),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      setEditing(false);
      message.success("Đã lưu cấu hình dự án");
    },
    onError: (e) => message.error(errorText(e)),
  });

  const tab = params.get("tab") ?? "documents";
  const vParam = params.get("v");
  const specId = vParam ? Number(vParam) : specs.data?.[0]?.id ?? null;
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v === null) p.delete(k);
    else p.set(k, v);
    setParams(p, { replace: false });
  };
  const selectSpec = (id: number) => set("v", String(id));
  const goTab = (t: string, specIdNext?: number) => {
    const p = new URLSearchParams(params);
    p.set("tab", t);
    if (specIdNext) p.set("v", String(specIdNext));
    setParams(p);
  };

  const p = project.data;
  if (!p) return <ErrorAlert error={project.error} />;
  const ctx = { project: p, specs: specs.data ?? [], specId, selectSpec, goTab };
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Breadcrumb items={[{ title: <Link to="/projects">Dự án</Link> }, { title: p.name }]} />
      <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }} data-testid="project-title">{p.name}</Typography.Title>
        <Space wrap>
          <Typography.Text>Phiên bản đặc tả:</Typography.Text>
          <Select style={{ minWidth: 260 }} value={specId ?? undefined} placeholder="Chưa có phiên bản"
            data-testid="version-select" onChange={(v) => selectSpec(v)}
            options={(specs.data ?? []).map((s) => ({ value: s.id, label: `v${s.version_no} · ${s.label} (#${s.id})` }))} />
          <Button icon={<SettingOutlined />} onClick={() => setEditing(true)}>Cấu hình</Button>
        </Space>
      </Space>
      <Descriptions size="small" column={{ xs: 1, md: 3 }} items={[
        { key: "b", label: "Base URL", children: p.base_url ? <code>{p.base_url}</code> : "–" },
        { key: "m", label: "Chế độ", children: <Tag>{p.mode}</Tag> },
        { key: "po", label: "Chính sách", children: <Tag>{p.policy}</Tag> },
        { key: "a", label: "Xác thực", children: `${p.auth_config?.type ?? "none"}${p.has_secret ? " (đã lưu khóa)" : ""}` },
        { key: "r", label: "Reset SUT", children: p.reset_config ? `${p.reset_config.method} ${p.reset_config.url}` : "–" },
        { key: "s", label: "Thống kê", children: `${p.stats?.documents ?? 0} tài liệu · ${p.stats?.versions ?? 0} phiên bản · ${p.stats?.pending_proposals ?? 0} đề xuất chờ` },
      ]} />
      <Tabs activeKey={tab} onChange={(k) => goTab(k)} destroyInactiveTabPane items={[
        { key: "documents", label: "Tài liệu", children: <DocumentsTab {...ctx} /> },
        { key: "spec", label: "Đặc tả", children: <SpecTab {...ctx} /> },
        { key: "evaluation", label: "Đánh giá", children: <EvaluationTab {...ctx} /> },
        { key: "testing", label: "Kiểm thử", children: <TestingTab {...ctx} /> },
        { key: "proposals", label: "Sai lệch & đề xuất", children: <ProposalsTab {...ctx} /> },
        { key: "versions", label: "Phiên bản", children: <VersionsTab {...ctx} /> },
      ]} />
      <ProjectForm open={editing} initial={p} onCancel={() => setEditing(false)} onSubmit={(v) => update.mutate(v)}
        loading={update.isPending} />
    </Space>
  );
}
