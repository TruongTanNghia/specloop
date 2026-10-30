// SC-11: cài đặt LLM – nhà cung cấp khả dụng, thử kết nối (khóa tạm thời, không lưu), thống kê sử dụng.
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Table, Tag, Typography } from "antd";
import { api } from "../api/client";
import { ErrorAlert, JsonBlock } from "../components/common";

export default function SettingsPage() {
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const usage = useQuery({ queryKey: ["llm-usage"], queryFn: api.llmUsage });
  const test = useMutation({ mutationFn: api.llmTest });
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Typography.Title level={3} style={{ margin: 0 }}>Cài đặt LLM</Typography.Title>
      <Alert type="info" showIcon message="Cấu hình mặc định đọc từ tệp .env của backend"
        description={<>Đặt <code>LLM_BASE_URL</code>, <code>LLM_API_KEY</code>, <code>LLM_MODEL</code>. Ví dụ OpenAI: <code>https://api.openai.com/v1</code>;
          Gemini: <code>https://generativelanguage.googleapis.com/v1beta/openai/</code>; Ollama: <code>http://localhost:11434/v1</code>;
          LM Studio: <code>http://localhost:1234/v1</code>. Mô hình <code>fake</code> luôn có sẵn để chạy thử không cần mạng.</>} />
      <Card title="Nhà cung cấp khả dụng" size="small">
        <ErrorAlert error={providers.error} />
        <Table size="small" rowKey="id" pagination={false} dataSource={providers.data ?? []} columns={[
          { title: "Nhà cung cấp", dataIndex: "name" },
          { title: "Base URL", dataIndex: "base_url", render: (v) => v ? <code>{v}</code> : "–" },
          { title: "Mô hình", dataIndex: "models", render: (m: string[]) => m.map((x) => <Tag key={x}>{x}</Tag>) },
          { title: "Trạng thái", dataIndex: "available", render: (a) => <Tag color={a ? "green" : "default"}>{a ? "sẵn sàng" : "chưa cấu hình"}</Tag> },
        ]} />
      </Card>
      <Card title="Thử kết nối" size="small">
        <Form layout="inline" onFinish={(v) => test.mutate(v)}>
          <Form.Item name="base_url"><Input placeholder="Base URL (để trống = .env)" style={{ width: 300 }} /></Form.Item>
          <Form.Item name="model"><Input placeholder="Mô hình (vd. gpt-4o-mini, fake)" style={{ width: 220 }} /></Form.Item>
          <Form.Item name="api_key"><Input.Password placeholder="API key (không lưu)" style={{ width: 220 }} autoComplete="new-password" /></Form.Item>
          <Button type="primary" htmlType="submit" loading={test.isPending}>Thử kết nối</Button>
        </Form>
        {test.data && (
          <div style={{ marginTop: 12 }}>
            {test.data.ok ? <Alert type="success" showIcon message={`Kết nối thành công: ${test.data.model} (${test.data.provider}) – ${test.data.latency_ms} ms`} />
              : <Alert type="error" showIcon message="Kết nối thất bại" description={test.data.error} />}
            {test.data.ok && <JsonBlock value={test.data.response} />}
          </div>
        )}
        <ErrorAlert error={test.error} />
      </Card>
      <Card title="Sử dụng LLM (bảng llm_call)" size="small">
        <Table size="small" rowKey="model" pagination={false} dataSource={usage.data ?? []} columns={[
          { title: "Mô hình", dataIndex: "model" }, { title: "Lời gọi", dataIndex: "calls" },
          { title: "Cache hit", dataIndex: "cached" }, { title: "Token vào", dataIndex: "input_tokens" },
          { title: "Token ra", dataIndex: "output_tokens" },
        ]} />
      </Card>
    </Space>
  );
}
