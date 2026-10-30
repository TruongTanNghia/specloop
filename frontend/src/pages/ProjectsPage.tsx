import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Input, Popconfirm, Space, Table } from "antd";
import { useState, type CSSProperties } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorText } from "../api/client";
import type { Project } from "../api/types";
import { Chip, ErrorAlert, fmtDate, PageHead } from "../components/common";
import ProjectForm from "../components/ProjectForm";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const q = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const create = useMutation({
    mutationFn: api.createProject,
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      nav(`/projects/${p.id}`);
    },
    onError: (e) => message.error(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
    onError: (e) => message.error(errorText(e)),
  });
  const f = filter.trim().toLowerCase();
  const list = (q.data ?? []).filter((p) => !f || p.name.toLowerCase().includes(f) || (p.base_url ?? "").toLowerCase().includes(f));

  return (
    <>
      <PageHead title="Dự án"
        lede="Mỗi dự án là một API: tài liệu nguồn, các phiên bản đặc tả, lượt kiểm thử và đề xuất sửa."
        actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>Tạo dự án</Button>} />
      <ErrorAlert error={q.error} />
      <section className="panel reveal" style={{ "--i": 1 } as CSSProperties}>
        <div className="panel-head">
          <div className="toolbar" style={{ margin: 0 }}>
            <Input allowClear prefix={<SearchOutlined style={{ color: "#9aa3af" }} />} placeholder="Tìm theo tên hoặc base URL"
              value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 320 }} />
            <Chip>{list.length} / {q.data?.length ?? 0} dự án</Chip>
          </div>
        </div>
        <Table<Project> rowKey="id" loading={q.isLoading} dataSource={list} pagination={{ pageSize: 20, hideOnSinglePage: true }}
          rowClassName="row-click"
          onRow={(r) => ({ onClick: (e) => { if (!(e.target as HTMLElement).closest("a, button, .ant-popover")) nav(`/projects/${r.id}`); } })}
          locale={{ emptyText: q.data?.length ? "Không có dự án nào khớp bộ lọc." : "Chưa có dự án. Bấm “Tạo dự án” để bắt đầu." }}
          columns={[
            { title: "Dự án", dataIndex: "name", render: (v, r) => (
              <>
                <Link to={`/projects/${r.id}`} className="cell-title">{v}</Link>
                <div className="cell-sub">{r.description || `#${r.id}`}</div>
              </>) },
            { title: "Base URL", dataIndex: "base_url", render: (v) => v ? <code>{v}</code> : <span style={{ color: "#9aa3af" }}>–</span> },
            { title: "Phiên bản", width: 170, render: (_, r) => (
              <Space size={6}>
                <span>{r.stats?.versions ?? 0}</span>
                {r.stats?.latest_version_label && <Chip tone="blue" mono>{r.stats.latest_version_label}</Chip>}
              </Space>) },
            { title: "Sai lệch", width: 100, align: "center", render: (_, r) => r.stats?.open_findings
              ? <Chip tone="red">{r.stats.open_findings}</Chip> : <span style={{ color: "#9aa3af" }}>0</span> },
            { title: "Đề xuất", width: 100, align: "center", render: (_, r) => r.stats?.pending_proposals
              ? <Chip tone="amber">{r.stats.pending_proposals}</Chip> : <span style={{ color: "#9aa3af" }}>0</span> },
            { title: "Chế độ", width: 180, render: (_, r) => <Space size={4}><Chip>{r.mode}</Chip><Chip>{r.policy}</Chip></Space> },
            { title: "Tạo lúc", dataIndex: "created_at", width: 160, render: fmtDate },
            { title: "", width: 110, align: "right", render: (_, r) => (
              <Space size={4}>
                <Button size="small" type="link" onClick={() => nav(`/projects/${r.id}`)}>Mở</Button>
                <Popconfirm title="Xóa dự án và toàn bộ dữ liệu?" okText="Xóa" cancelText="Hủy" onConfirm={() => remove.mutate(r.id)}>
                  <Button size="small" type="link" danger>Xóa</Button>
                </Popconfirm>
              </Space>) },
          ]} />
      </section>
      <ProjectForm open={open} onCancel={() => setOpen(false)} onSubmit={(v) => create.mutate(v)} loading={create.isPending} />
    </>
  );
}
