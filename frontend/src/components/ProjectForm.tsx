// Form cấu hình dự án (tạo mới / sửa): base URL, xác thực, host được phép, chế độ, chính sách, reset SUT.
import { Form, Input, Modal, Radio, Select, Space } from "antd";
import { useEffect } from "react";
import type { Project, ProjectInput } from "../api/types";

interface Values {
  name: string;
  description?: string;
  base_url?: string;
  auth_type: "none" | "bearer" | "header" | "query";
  auth_name?: string;
  auth_secret?: string;
  allowed_hosts?: string[];
  mode: "auto" | "safe" | "full";
  policy: "descriptive" | "prescriptive";
  reset_method?: string;
  reset_url?: string;
  reset_header_name?: string;
  reset_header_value?: string;
}

export default function ProjectForm({ open, initial, onCancel, onSubmit, loading }: {
  open: boolean;
  initial?: Project | null;
  onCancel: () => void;
  onSubmit: (v: ProjectInput) => void;
  loading?: boolean;
}) {
  const [form] = Form.useForm<Values>();
  useEffect(() => {
    if (!open) return;
    form.resetFields();
    if (initial) {
      form.setFieldsValue({
        name: initial.name, description: initial.description ?? undefined, base_url: initial.base_url ?? undefined,
        auth_type: initial.auth_config?.type ?? "none", auth_name: initial.auth_config?.name ?? undefined,
        allowed_hosts: initial.allowed_hosts, mode: initial.mode, policy: initial.policy,
        reset_method: initial.reset_config?.method ?? "POST", reset_url: initial.reset_config?.url,
      });
    }
  }, [open, initial, form]);

  const finish = (v: Values) => {
    const out: ProjectInput = {
      name: v.name, description: v.description || null, base_url: v.base_url || null,
      auth: { type: v.auth_type, name: v.auth_name || null }, allowed_hosts: v.allowed_hosts ?? [], mode: v.mode,
      policy: v.policy, reset: v.reset_url ? { method: v.reset_method || "POST", url: v.reset_url } : null,
    };
    if (v.auth_secret) out.auth_secret = v.auth_secret;
    if (v.reset_header_name && v.reset_header_value) out.reset_headers = { [v.reset_header_name]: v.reset_header_value };
    onSubmit(out);
  };

  return (
    <Modal open={open} title={initial ? "Cấu hình dự án" : "Tạo dự án"} onCancel={onCancel} onOk={() => form.submit()}
      okText={initial ? "Lưu" : "Tạo"} cancelText="Hủy" confirmLoading={loading} width={640} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={finish}
        initialValues={{ auth_type: "none", mode: "auto", policy: "descriptive", reset_method: "POST" }}>
        <Form.Item name="name" label="Tên dự án" rules={[{ required: true, message: "Nhập tên dự án" }]}>
          <Input placeholder="Bookstore-Lab" />
        </Form.Item>
        <Form.Item name="description" label="Mô tả"><Input.TextArea rows={2} /></Form.Item>
        <Form.Item name="base_url" label="Base URL của API cần kiểm thử">
          <Input placeholder="http://localhost:8000/v1" />
        </Form.Item>
        <Space style={{ width: "100%" }} align="start" wrap>
          <Form.Item name="auth_type" label="Xác thực">
            <Select style={{ width: 150 }} options={[
              { value: "none", label: "Không" }, { value: "bearer", label: "Bearer token" },
              { value: "header", label: "Header" }, { value: "query", label: "Query" },
            ]} />
          </Form.Item>
          <Form.Item name="auth_name" label="Tên header/query"><Input placeholder="X-API-Key" /></Form.Item>
          <Form.Item name="auth_secret" label="Token / khóa API" extra={initial?.has_secret ? "Đã lưu (mã hóa) – để trống nếu giữ nguyên" : "Được mã hóa, không bao giờ hiển thị lại"}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Space>
        <Form.Item name="allowed_hosts" label="Host được phép (để trống = host của base URL)">
          <Select mode="tags" placeholder="localhost, bookstore-lab" />
        </Form.Item>
        <Space wrap>
          <Form.Item name="mode" label="Chế độ kiểm thử">
            <Radio.Group options={[
              { value: "auto", label: "Tự động" }, { value: "safe", label: "Safe (chỉ đọc)" }, { value: "full", label: "Full" },
            ]} optionType="button" />
          </Form.Item>
          <Form.Item name="policy" label="Chính sách khi mâu thuẫn tài liệu">
            <Radio.Group options={[
              { value: "descriptive", label: "Descriptive" }, { value: "prescriptive", label: "Prescriptive" },
            ]} optionType="button" />
          </Form.Item>
        </Space>
        <Space wrap align="start">
          <Form.Item name="reset_method" label="Reset SUT"><Select style={{ width: 90 }} options={["POST", "GET", "PUT", "DELETE"].map((m) => ({ value: m, label: m }))} /></Form.Item>
          <Form.Item name="reset_url" label="URL reset"><Input placeholder="/__admin/reset" /></Form.Item>
          <Form.Item name="reset_header_name" label="Header reset"><Input placeholder="X-Admin-Token" /></Form.Item>
          <Form.Item name="reset_header_value" label="Giá trị"><Input.Password autoComplete="new-password" placeholder="reset-me" /></Form.Item>
        </Space>
      </Form>
    </Modal>
  );
}
