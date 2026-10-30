// SC-11: cài đặt LLM – nhà cung cấp khả dụng, thử kết nối (khóa tạm thời, không lưu), thống kê sử dụng.
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Form, Input, Table } from "antd";
import type { CSSProperties } from "react";
import { api } from "../api/client";
import { Chip, ErrorAlert, fmtInt, JsonBlock, PageHead, Panel } from "../components/common";

const delay = (i: number) => ({ "--i": i } as CSSProperties);

export default function SettingsPage() {
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const usage = useQuery({ queryKey: ["llm-usage"], queryFn: api.llmUsage });
  const test = useMutation({ mutationFn: api.llmTest });
  return (
    <>
      <PageHead eyebrow="Cài đặt" title={<>Mô hình <span className="hl">ngôn ngữ</span></>}
        lede="Cấu hình mặc định đọc từ tệp .env của backend. Mọi máy chủ tương thích OpenAI đều dùng được: OpenAI, Gemini, Ollama, LM Studio." />
      <div className="grid-2 reveal" style={{ ...delay(1), marginTop: 0 }}>
        <Panel title="Nhà cung cấp khả dụng" bodyStyle={{ padding: 0 }}>
          <ErrorAlert error={providers.error} />
          <Table size="small" rowKey="id" pagination={false} dataSource={providers.data ?? []} columns={[
            { title: "Nhà cung cấp", dataIndex: "name" },
            { title: "Base URL", dataIndex: "base_url", render: (v) => v ? <code>{v}</code> : "–" },
            { title: "Mô hình", dataIndex: "models", render: (m: string[]) => m.map((x) => <Chip key={x} tone="lime">{x}</Chip>) },
            { title: "Trạng thái", dataIndex: "available", render: (a) => <Chip tone={a ? "lime" : "muted"}>{a ? "sẵn sàng" : "chưa cấu hình"}</Chip> },
          ]} />
        </Panel>
        <Panel title="Biến môi trường (.env)">
          <div className="env-hint">
            <span className="k">LLM_BASE_URL</span><span>OpenAI <code>https://api.openai.com/v1</code> · Ollama <code>http://localhost:11434/v1</code> · LM Studio <code>http://localhost:1234/v1</code></span>
            <span className="k">LLM_MODEL</span><span>tên mô hình; <code>fake</code> luôn có sẵn để chạy thử không cần mạng</span>
            <span className="k">LLM_API_KEY</span><span>khóa API (Ollama để <code>ollama</code>)</span>
            <span className="k">LLM_REASONING_EFFORT</span><span><code>none</code> để tắt chế độ suy nghĩ của Qwen3 / o-series</span>
            <span className="k">LLM_STRUCTURED_OUTPUT</span><span><code>true</code> ép JSON đúng khuôn (json_schema)</span>
          </div>
        </Panel>
      </div>
      <Panel title="Thử kết nối" className="reveal" style={{ ...delay(2), marginTop: 18 }}>
        <Form layout="inline" onFinish={(v) => test.mutate(v)} style={{ gap: 8 }}>
          <Form.Item name="base_url"><Input placeholder="Base URL (để trống = .env)" style={{ width: 300 }} /></Form.Item>
          <Form.Item name="model"><Input placeholder="Mô hình (vd. gpt-4o-mini, fake)" style={{ width: 240 }} /></Form.Item>
          <Form.Item name="api_key"><Input.Password placeholder="API key (không lưu)" style={{ width: 220 }} autoComplete="new-password" /></Form.Item>
          <Button type="primary" htmlType="submit" loading={test.isPending}>Thử kết nối</Button>
        </Form>
        {test.data && (
          <div style={{ marginTop: 14 }}>
            {test.data.ok ? <Alert type="success" showIcon message={`Kết nối thành công: ${test.data.model} (${test.data.provider}) – ${test.data.latency_ms} ms`} />
              : <Alert type="error" showIcon message="Kết nối thất bại" description={test.data.error} />}
            {test.data.ok && <div style={{ marginTop: 10 }}><JsonBlock value={test.data.response} /></div>}
          </div>
        )}
        <ErrorAlert error={test.error} />
      </Panel>
      <Panel title="Sử dụng LLM · bảng llm_call" bodyStyle={{ padding: 0 }} className="reveal" style={{ ...delay(3), marginTop: 18 }}>
        <Table size="small" rowKey="model" pagination={false} dataSource={usage.data ?? []} columns={[
          { title: "Mô hình", dataIndex: "model", render: (m) => <code>{m}</code> }, { title: "Lời gọi", dataIndex: "calls", render: fmtInt },
          { title: "Cache hit", dataIndex: "cached", render: fmtInt }, { title: "Token vào", dataIndex: "input_tokens", render: fmtInt },
          { title: "Token ra", dataIndex: "output_tokens", render: fmtInt },
        ]} />
      </Panel>
    </>
  );
}
