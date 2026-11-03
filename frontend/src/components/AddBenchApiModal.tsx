// Trình 3 bước để người dùng tự thêm API vào SpecLoop-Bench: đặc tả → thông tin → xác nhận.
import { CheckCircleFilled, InboxOutlined, LinkOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import {
  Alert, Button, Col, Collapse, Descriptions, Form, Input, InputNumber, Modal, Radio, Result, Row, Segmented, Select,
  Space, Steps, Switch, Upload,
} from "antd";
import { useState } from "react";
import { api, errorText } from "../api/client";
import type { BenchApiCreate, BenchAuth, BenchCreateResult, BenchPreview, BenchSourceInput } from "../api/types";
import { Chip, fmtInt } from "./common";

type SourceMode = "url" | "file" | "text";

interface InfoValues extends Omit<BenchApiCreate, "auth" | keyof BenchSourceInput> {
  auth_type: BenchAuth["type"];
  auth_in?: BenchAuth["in"];
  auth_name?: string;
  auth_env_var?: string;
}

const GROUP_DEFAULTS = {
  A: { env: "local-docker", scope: "full" },
  B: { env: "public", scope: "read-only" },
} as const;

export default function AddBenchApiModal({ open, onClose, onCreated }: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<SourceMode>("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [doc, setDoc] = useState<{ name: string; text: string } | null>(null);
  const [info, setInfo] = useState<InfoValues | null>(null);
  const [form] = Form.useForm<InfoValues>();

  const source = (): BenchSourceInput => mode === "url" ? { spec_url: url.trim() }
    : mode === "file" ? { spec_text: file?.text ?? "", filename: file?.name } : { spec_text: text, filename: "dan-truc-tiep.yaml" };

  const preview = useMutation({ mutationFn: () => api.benchPreview(source()) });
  const create = useMutation({
    mutationFn: (v: InfoValues) => {
      const auth: BenchAuth = { type: v.auth_type };
      if (v.auth_type === "apiKey") Object.assign(auth, { in: v.auth_in ?? "header", name: v.auth_name || null });
      if (v.auth_type !== "none") auth.env_var = v.auth_env_var || null;
      return api.benchCreate({
        id: v.id, name: v.name, group: v.group, env: v.env, scope: v.scope, base_url: v.base_url || null,
        description: v.description || null, license: v.license || null, homepage: v.homepage || null,
        docs_url: v.docs_url || null, rate_limit_rps: v.rate_limit_rps ?? null, probe_path: v.probe_path || null,
        make_ablated: !!v.make_ablated, added_by: v.added_by || null, auth, ...source(),
        doc_original_text: doc?.text ?? null, doc_original_filename: doc?.name ?? null,
      });
    },
  });

  const reset = () => {
    setStep(0); setUrl(""); setText(""); setFile(null); setDoc(null); setInfo(null);
    preview.reset(); create.reset(); form.resetFields();
  };
  const close = () => { reset(); onClose(); };

  const p = preview.data;
  const hasSource = mode === "url" ? /^https?:\/\//.test(url.trim()) : mode === "file" ? !!file : text.trim().length > 20;

  const goInfo = (pv: BenchPreview) => {
    const s = pv.suggested;
    form.setFieldsValue({
      id: s.exists ? `${s.id}-2` : s.id, name: s.name, description: s.description, group: s.group, env: s.env,
      scope: s.scope, base_url: s.base_url || undefined, license: s.license || undefined,
      homepage: s.homepage || undefined, docs_url: s.docs_url || undefined,
      probe_path: s.probe_path || undefined, make_ablated: s.group === "A",
      auth_type: s.auth.type, auth_in: s.auth.in ?? "header", auth_name: s.auth.name ?? undefined,
      auth_env_var: s.auth.env_var ?? undefined, rate_limit_rps: s.env === "public" ? 1 : 5,
    });
    setStep(1);
  };

  const done: BenchCreateResult | undefined = create.data;
  return (
    <Modal open={open} onCancel={close} width={920} title="Thêm API vào bộ dữ liệu" destroyOnClose maskClosable={false}
      footer={null}>
      <Steps size="small" current={done ? 3 : step} style={{ margin: "8px 0 22px" }} items={[
        { title: "Đặc tả OpenAPI", description: "URL, tệp hoặc dán" },
        { title: "Thông tin API", description: "môi trường, xác thực, nguồn" },
        { title: "Xác nhận", description: "dựng & kiểm tra" },
      ]} />

      {step === 0 && (
        <>
          <Segmented value={mode} onChange={(v) => { setMode(v as SourceMode); preview.reset(); }} style={{ marginBottom: 14 }}
            options={[{ value: "url", label: "Từ URL", icon: <LinkOutlined /> },
              { value: "file", label: "Tải tệp lên", icon: <UploadOutlined /> },
              { value: "text", label: "Dán nội dung" }]} />
          {mode === "url" && (
            <Input size="large" value={url} onChange={(e) => { setUrl(e.target.value); preview.reset(); }}
              placeholder="https://…/openapi.yaml  hoặc  …/openapi.json" data-testid="bench-spec-url" />
          )}
          {mode === "file" && (
            <Upload.Dragger accept=".yaml,.yml,.json" showUploadList={false} multiple={false}
              beforeUpload={(f) => { f.text().then((t) => { setFile({ name: f.name, text: t }); preview.reset(); }); return false; }}>
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p>{file ? <b>{file.name}</b> : "Kéo thả hoặc bấm để chọn tệp OpenAPI / Swagger"}</p>
              <p className="ant-upload-hint">YAML hoặc JSON · OpenAPI 3.0, 3.1 hoặc Swagger 2.0 · tối đa 20 MB</p>
            </Upload.Dragger>
          )}
          {mode === "text" && (
            <Input.TextArea rows={12} value={text} onChange={(e) => { setText(e.target.value); preview.reset(); }}
              placeholder={"openapi: 3.0.3\ninfo:\n  title: …"} className="patch-op" />
          )}
          <p className="page-lede" style={{ marginTop: 10 }}>
            Hệ thống tự chuẩn hóa về OpenAPI 3.0.3 (chuyển Swagger 2.0, hạ cấp 3.1, sửa các lỗi hay gặp) và ghi lại
            mọi thay đổi. Đặc tả này là <b>ground truth</b> để chấm điểm, nên hãy dùng bản chính thức của nhà cung cấp.
          </p>
          {preview.error && <Alert type="error" showIcon message="Không đọc được đặc tả" description={errorText(preview.error)} />}
          {p && <PreviewCard p={p} />}
          <div className="modal-actions">
            <Button onClick={close}>Hủy</Button>
            {p?.valid ? <Button type="primary" onClick={() => goInfo(p)}>Tiếp tục →</Button>
              : <Button type="primary" disabled={!hasSource} loading={preview.isPending} onClick={() => preview.mutate()}
                data-testid="bench-preview-btn">Kiểm tra đặc tả</Button>}
          </div>
        </>
      )}

      {step === 1 && !done && (
        <Form form={form} layout="vertical"
          onFinish={(v) => { setInfo(v); setStep(2); }}
          onValuesChange={(ch) => {
            if (ch.group) form.setFieldsValue({ ...GROUP_DEFAULTS[ch.group as "A" | "B"], make_ablated: ch.group === "A" });
          }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="Tên API" rules={[{ required: true, message: "Nhập tên API" }]}>
                <Input placeholder="Swagger Petstore v3" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="id" label="Mã (tên thư mục)" extra="Chữ thường, số, gạch nối"
                rules={[{ required: true, message: "Nhập mã" },
                  { pattern: /^[a-z0-9][a-z0-9-]{1,40}$/, message: "Chỉ gồm a–z, 0–9, dấu gạch nối (2–41 ký tự)" }]}>
                <Input placeholder="petstore3" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="Mô tả" extra="Lĩnh vực, số endpoint, điểm đáng chú ý về ràng buộc">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="group" label="Nhóm">
            <Radio.Group optionType="button" options={[
              { value: "A", label: "A · Tự chạy (Docker), kiểm thử đầy đủ" },
              { value: "B", label: "B · API công khai, chỉ đọc" }]} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="env" label="Môi trường">
                <Select options={[{ value: "local-docker", label: "Docker cục bộ" }, { value: "public", label: "Công khai" },
                  { value: "offline", label: "Ngoại tuyến (không gọi được)" }]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="scope" label="Phạm vi kiểm thử">
                <Select options={[{ value: "full", label: "Đầy đủ (mọi phương thức)" },
                  { value: "read-only", label: "Chỉ đọc (GET)" }, { value: "none", label: "Không kiểm thử (chỉ RQ1)" }]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="rate_limit_rps" label="Tốc độ tối đa (req/s)">
                <InputNumber min={0.1} max={100} step={0.5} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item name="base_url" label="Base URL để kiểm thử" extra="Ghi đè servers[0].url của đặc tả">
                <Input placeholder="http://localhost:8080/api/v3" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="probe_path" label="Đường dẫn thử kết nối (GET)">
                <Input placeholder="/health" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={6}>
              <Form.Item name="auth_type" label="Xác thực">
                <Select options={[{ value: "none", label: "Không" }, { value: "apiKey", label: "API key" },
                  { value: "bearer", label: "Bearer token" }, { value: "oauth2", label: "OAuth2" }]} />
              </Form.Item>
            </Col>
            <Form.Item noStyle shouldUpdate={(a, b) => a.auth_type !== b.auth_type}>
              {({ getFieldValue }) => getFieldValue("auth_type") !== "none" && (
                <>
                  {getFieldValue("auth_type") === "apiKey" && (
                    <>
                      <Col span={5}><Form.Item name="auth_in" label="Gửi trong">
                        <Select options={[{ value: "header", label: "header" }, { value: "query", label: "query" },
                          { value: "cookie", label: "cookie" }]} />
                      </Form.Item></Col>
                      <Col span={6}><Form.Item name="auth_name" label="Tên header/query"><Input placeholder="X-API-Key" /></Form.Item></Col>
                    </>
                  )}
                  <Col span={7}><Form.Item name="auth_env_var" label="Biến môi trường chứa khóa"
                    extra="Khóa không lưu vào bộ dữ liệu" rules={[{ required: true, message: "Nhập tên biến" }]}>
                    <Input placeholder="MY_API_KEY" />
                  </Form.Item></Col>
                </>
              )}
            </Form.Item>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="license" label="Giấy phép / điều khoản" rules={[{ required: true, message: "Ghi giấy phép" }]}>
              <Input placeholder="Apache-2.0" /></Form.Item></Col>
            <Col span={8}><Form.Item name="homepage" label="Trang chủ"><Input placeholder="https://…" /></Form.Item></Col>
            <Col span={8}><Form.Item name="docs_url" label="Trang tài liệu"><Input placeholder="https://…/docs" /></Form.Item></Col>
          </Row>
          <Row gutter={16} align="middle">
            <Col span={12}>
              <Form.Item label="Tài liệu gốc cho người đọc" extra="Markdown / HTML / TXT – đầu vào thực tế hơn bản render từ đặc tả">
                <Upload accept=".md,.markdown,.txt,.html,.htm" showUploadList={false}
                  beforeUpload={(f) => { f.text().then((t) => setDoc({ name: f.name, text: t })); return false; }}>
                  <Button icon={<UploadOutlined />}>{doc ? doc.name : "Chọn tệp tài liệu"}</Button>
                </Upload>
                {doc && <Button type="link" danger onClick={() => setDoc(null)}>Bỏ</Button>}
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="make_ablated" label="Sinh bản lược ràng buộc" valuePropName="checked"
                extra="Ẩn ~40% ràng buộc để đo khả năng phục hồi">
                <Switch />
              </Form.Item>
            </Col>
            <Col span={6}><Form.Item name="added_by" label="Người thêm"><Input placeholder="Họ tên" /></Form.Item></Col>
          </Row>
          <div className="modal-actions">
            <Button onClick={() => setStep(0)}>← Quay lại</Button>
            <Button type="primary" htmlType="submit">Tiếp tục →</Button>
          </div>
        </Form>
      )}

      {step === 2 && info && !done && (
        <>
          <Descriptions bordered size="small" column={2} items={[
            { key: "n", label: "API", children: <><b>{info.name}</b> <Chip mono>{info.id}</Chip></> },
            { key: "s", label: "Đặc tả", children: p ? `${p.source_version} · ${p.operations} operation` : "–" },
            { key: "g", label: "Nhóm / môi trường", children: `${info.group} · ${info.env} · ${info.scope}` },
            { key: "b", label: "Base URL", children: info.base_url ? <code>{info.base_url}</code> : "theo đặc tả" },
            { key: "a", label: "Xác thực", children: info.auth_type === "none" ? "không" : `${info.auth_type} · biến ${info.auth_env_var}` },
            { key: "l", label: "Giấy phép", children: info.license },
            { key: "d", label: "Tài liệu gốc", children: doc ? doc.name : "không (dùng bản render từ đặc tả)" },
            { key: "x", label: "Bản lược ràng buộc", children: info.make_ablated ? "có" : "không" },
          ]} />
          <p className="page-lede" style={{ marginTop: 12 }}>
            Hệ thống sẽ ghi <code>apis/{info.id}/</code> (đặc tả gốc, ground truth 3.0.3, meta.yaml), sinh atomic facts và
            tài liệu render, cập nhật <code>manifest.json</code>, <code>stats.csv</code> rồi chạy kiểm tra toàn vẹn.
          </p>
          {create.error && <Alert type="error" showIcon message="Không thêm được API" description={errorText(create.error)} style={{ marginTop: 12 }} />}
          <div className="modal-actions">
            <Button onClick={() => setStep(1)} disabled={create.isPending}>← Sửa thông tin</Button>
            <Button type="primary" loading={create.isPending} onClick={() => create.mutate(info)} data-testid="bench-create-btn">
              Thêm vào bộ dữ liệu
            </Button>
          </div>
        </>
      )}

      {done && (
        <Result status="success" icon={<CheckCircleFilled />} title={`Đã thêm “${info?.name}” vào bộ dữ liệu`}
          subTitle={<>
            <b>{fmtInt(done.stats.operations)}</b> operation · <b>{fmtInt(done.stats.constraints_no_type)}</b> ràng buộc ·{" "}
            <b>{fmtInt(done.stats.facts_total)}</b> atomic facts · kiểm tra toàn vẹn: {done.validation.ok ? "ĐẠT" : "CÓ LỖI"}
          </>}
          extra={<Space>
            <Button onClick={() => { reset(); }}>Thêm API khác</Button>
            <Button type="primary" onClick={() => { const id = done.id; close(); onCreated(id); }}>Xem API vừa thêm</Button>
          </Space>}>
          {(done.validation.warnings.length > 0 || done.normalization.length > 0) && (
            <Collapse size="small" items={[
              ...(done.normalization.length ? [{ key: "n", label: `Đã chuẩn hóa ${done.normalization.length} mục`,
                children: <ul className="note-list">{done.normalization.map((n) => <li key={n}>{n}</li>)}</ul> }] : []),
              ...(done.validation.warnings.length ? [{ key: "w", label: `Lưu ý (${done.validation.warnings.length})`,
                children: <ul className="note-list">{done.validation.warnings.map((n) => <li key={n}>{n}</li>)}</ul> }] : []),
            ]} />
          )}
        </Result>
      )}
    </Modal>
  );
}

function PreviewCard({ p }: { p: BenchPreview }) {
  return (
    <div style={{ marginTop: 14 }} data-testid="bench-preview">
      {p.valid
        ? <Alert type="success" showIcon message={`Đặc tả hợp lệ – “${p.title ?? "API"}” (${p.source_version} → OpenAPI 3.0.3)`} />
        : <Alert type="error" showIcon message="Đặc tả vẫn chưa hợp lệ sau khi tự sửa"
          description={<ul className="note-list">{p.errors.map((e) => <li key={e}>{e}</li>)}</ul>} />}
      <Descriptions size="small" column={3} style={{ marginTop: 12 }} items={[
        { key: "o", label: "Operation", children: <b>{p.operations}</b> },
        { key: "p", label: "Đường dẫn", children: p.paths },
        { key: "v", label: "Phiên bản API", children: p.version ?? "–" },
        { key: "s", label: "Servers", span: 2, children: p.servers.length ? p.servers.map((s) => <Chip key={s} mono>{s}</Chip>) : "–" },
        { key: "a", label: "Xác thực", children: p.security_schemes.length ? p.security_schemes.join(", ") : "không" },
      ]} />
      {p.normalization.length > 0 && (
        <Collapse size="small" style={{ marginTop: 8 }} items={[{ key: "n", label: `Tự động chuẩn hóa / sửa ${p.normalization.length} mục`,
          children: <ul className="note-list">{p.normalization.map((n) => <li key={n}>{n}</li>)}</ul> }]} />
      )}
      {p.suggested.exists && (
        <Alert style={{ marginTop: 8 }} type="warning" showIcon
          message={`Bộ dữ liệu đã có API mã “${p.suggested.id}” – bước sau hãy đặt mã khác.`} />
      )}
    </div>
  );
}
