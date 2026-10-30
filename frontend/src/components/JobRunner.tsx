// Hiển thị một job đang chạy (SSE) kèm nút hủy.
import { Button, Card } from "antd";
import { api } from "../api/client";
import { useJobEvents, type JobFinished } from "../hooks/useJobEvents";
import { JobStatus } from "./common";

export default function JobRunner({ jobId, title, invalidate, onFinished, onClose }: {
  jobId: string | null;
  title: string;
  invalidate?: unknown[][];
  onFinished?: (f: JobFinished) => void;
  onClose?: () => void;
}) {
  const { progress, finished, running } = useJobEvents(jobId, { invalidate, onFinished });
  if (!jobId) return null;
  return (
    <Card size="small" className="job-card" style={{ marginBottom: 12 }} data-testid="job-card" data-status={finished?.status ?? "running"}
      extra={running ? <Button size="small" danger onClick={() => api.cancelJob(jobId)}>Hủy</Button>
        : onClose ? <Button size="small" onClick={onClose}>Đóng</Button> : null}>
      <JobStatus progress={progress} finished={finished} title={title} />
    </Card>
  );
}
