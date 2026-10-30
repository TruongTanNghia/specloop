import { useQuery } from "@tanstack/react-query";
import { Card, Col, List, Row, Space, Statistic, Typography } from "antd";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorAlert, fmtDate } from "../components/common";

export default function DashboardPage() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 10000 });
  const d = q.data;
  const codes = Object.entries(d?.findings_by_code ?? {}).map(([code, n]) => ({ code, n })).sort((a, b) =>
    a.code.localeCompare(b.code));
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Typography.Title level={3} style={{ margin: 0 }}>Tổng quan</Typography.Title>
      <ErrorAlert error={q.error} />
      <Row gutter={[16, 16]}>
        {[
          ["Dự án", d?.projects], ["Phiên bản đặc tả", d?.versions], ["Lượt kiểm thử", d?.test_runs],
          ["Sai lệch đang mở", d?.open_findings], ["Đề xuất chờ duyệt", d?.pending_proposals],
          ["Lời gọi LLM", d?.llm.calls],
        ].map(([t, v]) => (
          <Col key={String(t)} xs={12} md={8} xl={4}>
            <Card><Statistic title={t} value={(v as number | undefined) ?? 0} loading={q.isLoading} /></Card>
          </Col>
        ))}
      </Row>
      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card title="Sai lệch theo mã (mọi lượt kiểm thử)">
            {codes.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={codes}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="code" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="n" name="Số finding" fill="#1f6feb" />
                </BarChart>
              </ResponsiveContainer>
            ) : <Typography.Text type="secondary">Chưa có lượt kiểm thử nào.</Typography.Text>}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="Dự án gần đây" extra={<Link to="/projects">Tất cả</Link>}>
            <List dataSource={d?.recent_projects ?? []} renderItem={(p) => (
              <List.Item><Link to={`/projects/${p.id}`}>{p.name}</Link><Typography.Text type="secondary">{fmtDate(p.created_at)}</Typography.Text></List.Item>
            )} />
            <Typography.Text type="secondary">
              Token LLM: {d?.llm.input_tokens ?? 0} vào / {d?.llm.output_tokens ?? 0} ra
            </Typography.Text>
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
