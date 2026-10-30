import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Popconfirm, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorText } from "../api/client";
import type { Project } from "../api/types";
import { ErrorAlert, fmtDate } from "../components/common";
import ProjectForm from "../components/ProjectForm";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
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
  });
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Dự án</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>Tạo dự án</Button>
      </Space>
      <ErrorAlert error={q.error} />
      <Table<Project> rowKey="id" loading={q.isLoading} dataSource={q.data ?? []} pagination={{ pageSize: 20 }}
        columns={[
          { title: "Tên", dataIndex: "name", render: (v, r) => <Link to={`/projects/${r.id}`}>{v}</Link> },
          { title: "Base URL", dataIndex: "base_url", render: (v) => v ? <code>{v}</code> : "–" },
          { title: "Phiên bản", render: (_, r) => r.stats?.versions ?? 0 },
          { title: "Mới nhất", render: (_, r) => r.stats?.latest_version_label ? <Tag>{r.stats.latest_version_label}</Tag> : "–" },
          { title: "Sai lệch mở", render: (_, r) => r.stats?.open_findings ?? 0 },
          { title: "Đề xuất chờ", render: (_, r) => r.stats?.pending_proposals ?? 0 },
          { title: "Tạo lúc", dataIndex: "created_at", render: fmtDate },
          {
            title: "", width: 80, render: (_, r) => (
              <Popconfirm title="Xóa dự án và toàn bộ dữ liệu?" okText="Xóa" cancelText="Hủy" onConfirm={() => remove.mutate(r.id)}>
                <Button danger size="small">Xóa</Button>
              </Popconfirm>
            ),
          },
        ]} />
      <ProjectForm open={open} onCancel={() => setOpen(false)} onSubmit={(v) => create.mutate(v)} loading={create.isPending} />
    </Space>
  );
}
