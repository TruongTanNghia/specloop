import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Input, Popconfirm } from "antd";
import { useState, type CSSProperties, type MouseEvent } from "react";
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

  // Thẻ là vùng bấm; bỏ qua khi bấm vào link con hoặc hộp xác nhận xóa (render qua portal nhưng sự kiện vẫn nổi lên).
  const openCard = (e: MouseEvent<HTMLElement>, id: number) => {
    if ((e.target as HTMLElement).closest("a, button, .ant-popover")) return;
    nav(`/projects/${id}`);
  };

  return (
    <>
      <PageHead eyebrow="Dự án" title="Dự án"
        lede="Mỗi dự án là một API: tài liệu nguồn, các phiên bản đặc tả, lượt kiểm thử và đề xuất sửa."
        actions={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>Tạo dự án</Button>} />
      <ErrorAlert error={q.error} />
      <div className="toolbar reveal" style={{ "--i": 1 } as CSSProperties}>
        <Input allowClear prefix={<SearchOutlined style={{ color: "#5b6672" }} />} placeholder="Tìm theo tên hoặc base URL"
          value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 360 }} />
        <Chip>{list.length} / {q.data?.length ?? 0} dự án</Chip>
      </div>
      {!q.isLoading && !list.length && (
        <div className="empty reveal">{q.data?.length ? "Không có dự án nào khớp bộ lọc." : "Chưa có dự án. Bấm “Tạo dự án” để bắt đầu."}</div>
      )}
      <div className="proj-grid">
        {list.map((p, i) => <ProjectCard key={p.id} p={p} index={i} onOpen={openCard} onDelete={() => remove.mutate(p.id)} />)}
      </div>
      <ProjectForm open={open} onCancel={() => setOpen(false)} onSubmit={(v) => create.mutate(v)} loading={create.isPending} />
    </>
  );
}

function ProjectCard({ p, index, onOpen, onDelete }: {
  p: Project; index: number; onOpen: (e: MouseEvent<HTMLElement>, id: number) => void; onDelete: () => void;
}) {
  const s = p.stats;
  return (
    <article className="proj-card reveal" style={{ "--i": Math.min(index, 8) + 2 } as CSSProperties} onClick={(e) => onOpen(e, p.id)}>
      <div className="top">
        <div style={{ minWidth: 0 }}>
          <div className="id">DỰ ÁN #{p.id}</div>
          <h3><Link to={`/projects/${p.id}`} style={{ color: "inherit" }}>{p.name}</Link></h3>
        </div>
        {s?.latest_version_label && <Chip tone="lime">{s.latest_version_label}</Chip>}
      </div>
      <div className="url" title={p.base_url ?? undefined}>{p.base_url ?? "chưa có base URL"}</div>
      {p.description && <p className="desc">{p.description}</p>}
      <div className="nums">
        <div>Tài liệu<b>{s?.documents ?? 0}</b></div>
        <div>Phiên bản<b>{s?.versions ?? 0}</b></div>
        <div>Sai lệch<b className={s?.open_findings ? "hot" : ""}>{s?.open_findings ?? 0}</b></div>
        <div>Đề xuất<b className={s?.pending_proposals ? "go" : ""}>{s?.pending_proposals ?? 0}</b></div>
      </div>
      <div className="foot">
        <span>{p.mode} · {p.policy}</span>
        <span>{fmtDate(p.created_at)}</span>
        <Popconfirm title="Xóa dự án và toàn bộ dữ liệu?" okText="Xóa" cancelText="Hủy" onConfirm={onDelete}>
          <Button size="small" danger type="text" className="del">Xóa</Button>
        </Popconfirm>
      </div>
    </article>
  );
}
