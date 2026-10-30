// Thành phần dùng lại: ConfidenceBar, nhãn mã sai lệch, tiến trình job, khung JSON.
import { Alert, Progress, Space, Tag, Tooltip, Typography } from "antd";
import type { ReactNode } from "react";
import { errorText } from "../api/client";
import type { JobProgress } from "../hooks/useJobEvents";

export const CODE_INFO: Record<string, { label: string; color: string }> = {
  D0: { label: "Lỗi máy chủ", color: "red" },
  D1: { label: "Thiếu ràng buộc", color: "blue" },
  D2: { label: "Ràng buộc quá chặt", color: "orange" },
  D3: { label: "Sai giá trị biên", color: "gold" },
  D4: { label: "Sai tính bắt buộc", color: "volcano" },
  D5: { label: "Sai/thiếu enum", color: "purple" },
  D6: { label: "Sai kiểu/định dạng", color: "magenta" },
  D7: { label: "Mã trạng thái chưa khai báo", color: "cyan" },
  D8: { label: "Lệch schema phản hồi", color: "geekblue" },
  D9: { label: "Phụ thuộc giữa tham số", color: "lime" },
  INFO: { label: "Thông tin", color: "default" },
};

export function CodeTag({ code }: { code: string }) {
  const c = CODE_INFO[code] ?? { label: code, color: "default" };
  return (
    <Tooltip title={c.label}>
      <Tag color={c.color}>{code}</Tag>
    </Tooltip>
  );
}

export const TIER_TEXT: Record<string, { text: string; color: string }> = {
  auto: { text: "Tin cậy cao", color: "green" },
  review: { text: "Cần duyệt", color: "orange" },
  suggestion: { text: "Gợi ý", color: "default" },
};

export function ConfidenceBar({ value, width = 120 }: { value: number; width?: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "#52c41a" : value >= 0.5 ? "#faad14" : "#bfbfbf";
  return (
    <Tooltip title={`Độ tin cậy ${value.toFixed(2)}`}>
      <div style={{ width }}>
        <Progress percent={pct} size="small" strokeColor={color} format={() => value.toFixed(2)} />
      </div>
    </Tooltip>
  );
}

export const OUTCOME_COLOR: Record<string, string> = {
  ACCEPT: "green", REJECT: "orange", NOT_FOUND: "default", SERVER_ERR: "red", AUTH: "purple", RATE: "magenta",
  OTHER: "default",
};

export function OutcomeTag({ outcome }: { outcome: string }) {
  return <Tag color={OUTCOME_COLOR[outcome] ?? "default"}>{outcome}</Tag>;
}

const STAGE_TEXT: Record<string, string> = {
  extract: "Trích xuất IR", assemble: "Lắp ráp OAS", repair: "Vòng sửa lỗi", testing: "Kiểm thử", analysis: "Phân tích",
  done: "Hoàn tất", evaluate: "Đánh giá", refine: "Vòng lặp tinh chỉnh", experiment: "Thực nghiệm",
};

export function JobStatus({ progress, finished, title }: {
  progress: JobProgress | null;
  finished: { status: string; error: string | null } | null;
  title?: string;
}) {
  if (finished) {
    if (finished.status === "succeeded") return <Alert type="success" showIcon message={`${title ?? "Tác vụ"} hoàn tất`} />;
    return <Alert type={finished.status === "cancelled" ? "warning" : "error"} showIcon
      message={`${title ?? "Tác vụ"} ${finished.status === "cancelled" ? "đã hủy" : "thất bại"}`}
      description={finished.error ?? undefined} />;
  }
  if (!progress) return <Alert type="info" showIcon message={`${title ?? "Tác vụ"} đang chờ…`} />;
  const pct = progress.total ? Math.round(((progress.done ?? 0) / progress.total) * 100) : undefined;
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text>
        {title ?? "Tác vụ"}: <b>{STAGE_TEXT[progress.stage ?? ""] ?? progress.stage ?? progress.status}</b>
        {progress.operation ? <> · <code>{progress.operation}</code></> : null}
        {progress.iteration ? <> · vòng {String(progress.iteration)}/{String(progress.max_iter)}</> : null}
        {progress.requests !== undefined ? <> · {progress.requests} request</> : null}
      </Typography.Text>
      {pct !== undefined && <Progress percent={pct} status="active" />}
      {progress.outcomes && (
        <Space wrap>
          {Object.entries(progress.outcomes).map(([k, v]) => (
            <Tag key={k} color={OUTCOME_COLOR[k]}>{k}: {v}</Tag>
          ))}
        </Space>
      )}
    </Space>
  );
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  return <Alert type="error" showIcon message={errorText(error)} style={{ marginBottom: 12 }} />;
}

export function JsonBlock({ value, maxHeight = 360 }: { value: unknown; maxHeight?: number }) {
  return (
    <pre style={{ background: "#f6f8fa", padding: 8, borderRadius: 6, maxHeight, overflow: "auto", fontSize: 12, margin: 0 }}>
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Section({ title, extra, children }: { title: ReactNode; extra?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Typography.Title level={5} style={{ margin: 0 }}>{title}</Typography.Title>
        <div>{extra}</div>
      </div>
      {children}
    </div>
  );
}

export const fmt = (v: number | null | undefined, nd = 3) => (v === null || v === undefined ? "–" : v.toFixed(nd));
export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleString("vi-VN") : "–");
