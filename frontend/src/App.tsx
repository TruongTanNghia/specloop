import {
  DashboardOutlined, DatabaseOutlined, ExperimentOutlined, FolderOpenOutlined, RobotOutlined, SettingOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useMatch } from "react-router-dom";
import { api } from "./api/client";
import { LogoMark } from "./components/Logo";
import DashboardPage from "./pages/DashboardPage";
import DatasetPage from "./pages/DatasetPage";
import ExperimentsPage from "./pages/ExperimentsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import ProjectsPage from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";

const NAV = [
  { group: "Làm việc", items: [
    { to: "/dashboard", label: "Tổng quan", icon: <DashboardOutlined /> },
    { to: "/projects", label: "Dự án", icon: <FolderOpenOutlined /> },
    { to: "/experiments", label: "Thực nghiệm", icon: <ExperimentOutlined /> },
    { to: "/dataset", label: "Bộ dữ liệu", icon: <DatabaseOutlined /> },
  ] },
  { group: "Hệ thống", items: [
    { to: "/settings", label: "Cài đặt LLM", icon: <SettingOutlined /> },
  ] },
];

const ROOT_TITLE: Record<string, string> = {
  dashboard: "Tổng quan", projects: "Dự án", experiments: "Thực nghiệm", dataset: "Bộ dữ liệu", settings: "Cài đặt LLM",
};

function Crumbs() {
  const loc = useLocation();
  const m = useMatch("/projects/:id");
  const id = m ? Number(m.params.id) : null;
  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.project(id!), enabled: !!id });
  const root = loc.pathname.split("/")[1] || "dashboard";
  return (
    <nav className="crumbs" aria-label="Đường dẫn">
      <Link to="/dashboard">SpecLoop</Link>
      <span className="sep">/</span>
      {id ? (
        <>
          <Link to="/projects">Dự án</Link>
          <span className="sep">/</span>
          <span className="cur">{project.data?.name ?? `#${id}`}</span>
        </>
      ) : <span className="cur">{ROOT_TITLE[root] ?? root}</span>}
    </nav>
  );
}

function StatusPills() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000, retry: 0 });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, staleTime: 60000 });
  const model = providers.data?.find((p) => p.default)?.models[0];
  const apiOk = health.data?.status === "ok";
  return (
    <div className="topbar-right">
      <span className="pill" title="Kết nối tới backend">
        <span className={`dot ${health.isLoading ? "" : apiOk ? "on" : "off"}`} />
        API <b>{health.isLoading ? "…" : apiOk ? "sẵn sàng" : "mất kết nối"}</b>
      </span>
      <span className="pill" title="Mô hình LLM mặc định (.env)">
        <RobotOutlined /> LLM <b>{model ?? (health.data ? "chưa cấu hình" : "…")}</b>
      </span>
    </div>
  );
}

export default function App() {
  return (
    <div className="shell">
      <aside className="rail">
        <Link to="/dashboard" className="brand">
          <LogoMark size={34} className="brand-mark" />
          <span>
            <span className="brand-name">Spec<em>Loop</em></span>
            <span className="brand-sub">Tài liệu → OpenAPI → kiểm thử</span>
          </span>
        </Link>
        <nav className="nav" aria-label="Điều hướng chính">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="nav-label">{g.group}</div>
              {g.items.map((n) => (
                <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? "active" : "")}>
                  {n.icon}{n.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="rail-foot">
          <b>SpecLoop 1.0</b><br />OpenAPI 3.0.3 · SpecLoop-Bench v0.1
        </div>
      </aside>
      <header className="topbar">
        <Crumbs />
        <StatusPills />
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/experiments" element={<ExperimentsPage />} />
          <Route path="/dataset" element={<DatasetPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<p className="page-lede">Không tìm thấy trang.</p>} />
        </Routes>
      </main>
    </div>
  );
}
