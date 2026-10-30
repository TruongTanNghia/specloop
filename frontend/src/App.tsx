import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import DashboardPage from "./pages/DashboardPage";
import ExperimentsPage from "./pages/ExperimentsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import ProjectsPage from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";

const NAV = [
  { to: "/dashboard", label: "Tổng quan" },
  { to: "/projects", label: "Dự án" },
  { to: "/experiments", label: "Thực nghiệm" },
  { to: "/settings", label: "Cài đặt LLM" },
];

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <circle cx="20" cy="20" r="15" stroke="#232b34" strokeWidth="2" />
      <path d="M20 5a15 15 0 0 1 15 15" stroke="#d4ff3a" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M20 35a15 15 0 0 1-15-15" stroke="#5ce1e6" strokeWidth="2.5" strokeLinecap="round" />
      <g className="orbit">
        <circle cx="35" cy="20" r="3" fill="#d4ff3a" />
      </g>
      <rect x="15" y="15" width="10" height="10" rx="1.5" fill="#e7ecef" />
    </svg>
  );
}

function RailFoot() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000, retry: 0 });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, staleTime: 60000 });
  const model = providers.data?.find((p) => p.default)?.models[0];
  const apiOk = health.data?.status === "ok";
  return (
    <div className="rail-foot">
      <div className="sig" title="Kết nối tới backend">
        <span className={`dot ${health.isLoading ? "" : apiOk ? "on" : "off"}`} />
        API <b>{health.isLoading ? "…" : apiOk ? "sẵn sàng" : "mất kết nối"}</b>
      </div>
      <div className="sig" title="Mô hình LLM mặc định (.env)">
        <span className={`dot ${health.data?.llm_configured ? "on" : ""}`} />
        LLM <b>{model ?? (health.data ? "chưa cấu hình" : "…")}</b>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="shell">
      <aside className="rail">
        <Link to="/dashboard" className="brand">
          <BrandMark />
          <span>
            <span className="brand-name">Spec<em>Loop</em></span>
            <span className="brand-sub">tài liệu → OAS → kiểm thử</span>
          </span>
        </Link>
        <nav className="nav" aria-label="Điều hướng chính">
          <div className="nav-label">Khu vực</div>
          {NAV.map((n, i) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? "active" : "")}>
              <span className="idx">0{i + 1}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <RailFoot />
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/experiments" element={<ExperimentsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<p className="page-lede">Không tìm thấy trang.</p>} />
        </Routes>
      </main>
    </div>
  );
}
