// Thành phần dùng lại: tiêu đề trang, khối panel, nhãn mã sai lệch, chip, thanh độ tin cậy, tiến trình job, khung JSON.
import { Alert, Progress, Space, Tooltip } from "antd";
import { forwardRef, type CSSProperties, type HTMLAttributes, type ReactNode } from "react";
import { errorText } from "../api/client";
import type { JobProgress } from "../hooks/useJobEvents";
import { C, FONT_MONO } from "../theme";

export const CODE_INFO: Record<string, { label: string; color: string }> = {
  D0: { label: "Lỗi máy chủ", color: C.danger },
  D1: { label: "Thiếu ràng buộc", color: C.primary },
  D2: { label: "Ràng buộc quá chặt", color: C.warning },
  D3: { label: "Sai giá trị biên", color: "#8a6d00" },
  D4: { label: "Sai tính bắt buộc", color: "#c2410c" },
  D5: { label: "Sai/thiếu enum", color: C.purple },
  D6: { label: "Sai kiểu/định dạng", color: C.pink },
  D7: { label: "Mã trạng thái chưa khai báo", color: C.teal },
  D8: { label: "Lệch schema phản hồi", color: "#1d4ed8" },
  D9: { label: "Phụ thuộc giữa tham số", color: C.success },
  INFO: { label: "Thông tin", color: C.muted },
};

export function CodeTag({ code }: { code: string }) {
  const c = CODE_INFO[code] ?? { label: code, color: C.muted };
  return (
    <Tooltip title={c.label}>
      <span className="code-tag" style={{ color: c.color, borderColor: `${c.color}55`, background: `${c.color}12` }}>{code}</span>
    </Tooltip>
  );
}

export type Tone = "blue" | "green" | "amber" | "red" | "teal" | "purple" | "gray";

// forwardRef + truyền tiếp props để dùng được làm con trực tiếp của Tooltip/Popover (tránh findDOMNode).
export const Chip = forwardRef<HTMLSpanElement, { tone?: Tone; mono?: boolean; children: ReactNode; title?: string }
  & HTMLAttributes<HTMLSpanElement>>(function Chip({ tone, mono, children, className, ...rest }, ref) {
  return <span ref={ref} className={`chip ${tone ?? ""}${mono ? " mono" : ""} ${className ?? ""}`} {...rest}>{children}</span>;
});

export const TIER_TEXT: Record<string, { text: string; tone: Tone }> = {
  auto: { text: "Tin cậy cao", tone: "green" },
  review: { text: "Cần duyệt", tone: "amber" },
  suggestion: { text: "Gợi ý", tone: "gray" },
};

export function ConfidenceBar({ value, width = 120 }: { value: number; width?: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "#1e9e4a" : value >= 0.5 ? "#e8a317" : C.faint;
  return (
    <Tooltip title={`Độ tin cậy ${value.toFixed(2)}`}>
      <div className="conf" style={{ width }}>
        <div className="conf-track"><div className="conf-fill" style={{ width: `${pct}%`, background: color }} /></div>
        <span className="conf-val" style={{ color: value >= 0.5 ? C.text2 : C.muted }}>{value.toFixed(2)}</span>
      </div>
    </Tooltip>
  );
}

export const OUTCOME_COLOR: Record<string, string> = {
  ACCEPT: C.success, REJECT: C.warning, NOT_FOUND: C.muted, SERVER_ERR: C.danger, AUTH: C.purple, RATE: C.pink, OTHER: C.muted,
};

export function OutcomeTag({ outcome }: { outcome: string }) {
  const color = OUTCOME_COLOR[outcome] ?? C.muted;
  return <span className="code-tag" style={{ color, borderColor: `${color}55`, background: `${color}12` }}>{outcome}</span>;
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
    <div className="job">
      <div className="job-line">
        <span className="job-title">{title ?? "Tác vụ"}</span>
        <span className="job-stage">{STAGE_TEXT[progress.stage ?? ""] ?? progress.stage ?? progress.status}</span>
        {progress.operation ? <code>{progress.operation}</code> : null}
        {progress.iteration ? <span className="job-meta">vòng {String(progress.iteration)}/{String(progress.max_iter)}</span> : null}
        {progress.requests !== undefined ? <span className="job-meta">{progress.requests} request</span> : null}
      </div>
      {pct !== undefined && <Progress percent={pct} status="active" size="small" />}
      {progress.outcomes && (
        <Space wrap size={6} style={{ marginTop: 8 }}>
          {Object.entries(progress.outcomes).map(([k, v]) => (
            <span key={k} className="job-meta"><OutcomeTag outcome={k} /> {v}</span>
          ))}
        </Space>
      )}
    </div>
  );
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  return <Alert type="error" showIcon message={errorText(error)} style={{ marginBottom: 12 }} />;
}

export function JsonBlock({ value, maxHeight = 360 }: { value: unknown; maxHeight?: number }) {
  return (
    <pre className="json-block" style={{ maxHeight }}>
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Section({ title, extra, children }: { title: ReactNode; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="sec">
      <div className="sec-head">
        <h5 className="sec-title">{title}</h5>
        <div>{extra}</div>
      </div>
      {children}
    </section>
  );
}

export function PageHead({ eyebrow, title, lede, actions }: {
  eyebrow?: ReactNode; title: ReactNode; lede?: ReactNode; actions?: ReactNode;
}) {
  return (
    <header className="page-head reveal">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {lede && <p className="page-lede">{lede}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Panel({ title, extra, children, bodyStyle, className, ...rest }: {
  title?: ReactNode; extra?: ReactNode; children: ReactNode; bodyStyle?: CSSProperties;
} & HTMLAttributes<HTMLElement>) {
  return (
    <section className={`panel ${className ?? ""}`} {...rest}>
      {(title || extra) && (
        <div className="panel-head">
          <h3 className="panel-title">{title}</h3>
          <div>{extra}</div>
        </div>
      )}
      <div className="panel-body" style={bodyStyle}>{children}</div>
    </section>
  );
}

// Thuộc tính dùng chung cho biểu đồ Recharts.
export const chartAxis = {
  tick: { fill: C.muted, fontSize: 12, fontFamily: FONT_MONO },
  axisLine: { stroke: C.line },
  tickLine: false as const,
};
export const chartTooltip = {
  contentStyle: { background: C.surface, border: `1px solid ${C.line}`, borderRadius: 6, fontSize: 12.5, boxShadow: "0 4px 12px rgba(16,24,40,.1)" },
  labelStyle: { color: C.text, fontWeight: 600 },
  itemStyle: { color: C.text2 },
  cursor: { fill: "rgba(11,92,214,.06)" },
};

export const fmt = (v: number | null | undefined, nd = 3) => (v === null || v === undefined ? "–" : v.toFixed(nd));
export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleString("vi-VN") : "–");
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? "–" : v.toLocaleString("vi-VN"));
