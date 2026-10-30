import { ApiOutlined, DashboardOutlined, ExperimentOutlined, FolderOutlined, SettingOutlined } from "@ant-design/icons";
import { Layout, Menu, Typography } from "antd";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import ExperimentsPage from "./pages/ExperimentsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import ProjectsPage from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const loc = useLocation();
  const key = loc.pathname.startsWith("/projects") ? "projects" : loc.pathname.split("/")[1] || "dashboard";
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider width={210} theme="dark" breakpoint="lg" collapsedWidth={0}>
        <div style={{ padding: "16px 20px", color: "#fff", display: "flex", alignItems: "center", gap: 8 }}>
          <ApiOutlined style={{ fontSize: 22 }} />
          <Typography.Text style={{ color: "#fff", fontSize: 18, fontWeight: 600 }}>SpecLoop</Typography.Text>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[key]} items={[
          { key: "dashboard", icon: <DashboardOutlined />, label: <Link to="/dashboard">Tổng quan</Link> },
          { key: "projects", icon: <FolderOutlined />, label: <Link to="/projects">Dự án</Link> },
          { key: "experiments", icon: <ExperimentOutlined />, label: <Link to="/experiments">Thực nghiệm</Link> },
          { key: "settings", icon: <SettingOutlined />, label: <Link to="/settings">Cài đặt LLM</Link> },
        ]} />
      </Layout.Sider>
      <Layout>
        <Layout.Content style={{ padding: 20 }}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
            <Route path="/experiments" element={<ExperimentsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Typography.Text>Không tìm thấy trang.</Typography.Text>} />
          </Routes>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
