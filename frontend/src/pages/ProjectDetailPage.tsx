import {
  AuditOutlined, BranchesOutlined, CheckCircleOutlined, CodeOutlined, ExperimentOutlined, FileTextOutlined, SettingOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Select, Tabs } from "antd";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, errorText } from "../api/client";
import { Chip, ErrorAlert } from "../components/common";
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
  const current = specs.data?.find((s) => s.id === specId);
  return (
    <>
      <header className="proj-head reveal">
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow">Dự án #{p.id}</div>
          <h1 className="page-title" data-testid="project-title">{p.name}</h1>
          {p.description && <p className="page-lede">{p.description}</p>}
          <div className="meta-line">
            <Chip tone={p.base_url ? "blue" : "gray"} mono title="Base URL của API cần kiểm thử">{p.base_url ?? "chưa có base URL"}</Chip>
            <Chip title="Chế độ kiểm thử">chế độ {p.mode}</Chip>
            <Chip title="Chính sách khi mâu thuẫn tài liệu">{p.policy}</Chip>
            <Chip title="Xác thực">xác thực {p.auth_config?.type ?? "none"}{p.has_secret ? " · đã lưu khóa" : ""}</Chip>
            {p.reset_config && <Chip title="Reset SUT trước khi kiểm thử">reset {p.reset_config.method} {p.reset_config.url}</Chip>}
            <Chip tone="gray">{p.stats?.documents ?? 0} tài liệu · {p.stats?.versions ?? 0} phiên bản · {p.stats?.pending_proposals ?? 0} đề xuất chờ</Chip>
          </div>
        </div>
        <div className="proj-actions">
          <span className="lbl">Phiên bản đặc tả</span>
          <Select style={{ minWidth: 280 }} value={specId ?? undefined} placeholder="Chưa có phiên bản"
            data-testid="version-select" onChange={(v) => selectSpec(v)}
            options={(specs.data ?? []).map((s) => ({ value: s.id, label: `v${s.version_no} · ${s.label} (#${s.id})` }))} />
          {current?.model && <Chip tone="gray" mono title="Mô hình đã sinh phiên bản này">{current.model}</Chip>}
          <Button icon={<SettingOutlined />} onClick={() => setEditing(true)}>Cấu hình</Button>
        </div>
      </header>
      <Tabs className="pipeline" activeKey={tab} onChange={(k) => goTab(k)} destroyInactiveTabPane items={[
        { key: "documents", label: "Tài liệu", icon: <FileTextOutlined />, children: <DocumentsTab {...ctx} /> },
        { key: "spec", label: "Đặc tả", icon: <CodeOutlined />, children: <SpecTab {...ctx} /> },
        { key: "evaluation", label: "Đánh giá", icon: <CheckCircleOutlined />, children: <EvaluationTab {...ctx} /> },
        { key: "testing", label: "Kiểm thử", icon: <ExperimentOutlined />, children: <TestingTab {...ctx} /> },
        { key: "proposals", label: "Sai lệch & đề xuất", icon: <AuditOutlined />, children: <ProposalsTab {...ctx} /> },
        { key: "versions", label: "Phiên bản", icon: <BranchesOutlined />, children: <VersionsTab {...ctx} /> },
      ]} />
      <ProjectForm open={editing} initial={p} onCancel={() => setEditing(false)} onSubmit={(v) => update.mutate(v)}
        loading={update.isPending} />
    </>
  );
}
