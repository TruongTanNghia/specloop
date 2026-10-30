// Theo dõi job nền qua SSE (/api/v1/jobs/{id}/events). Tự kết nối lại; khi `finished` thì làm mới cache.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api/client";

export interface JobProgress {
  job_id: string;
  status: string;
  stage?: string;
  operation?: string | null;
  done?: number;
  total?: number;
  outcomes?: Record<string, number>;
  requests?: number;
  [k: string]: unknown;
}

export interface JobFinished {
  job_id: string;
  status: "succeeded" | "failed" | "cancelled";
  result: Record<string, any> | null;
  error: string | null;
}

export function useJobEvents(jobId: string | null | undefined, opts?: {
  invalidate?: unknown[][];
  onFinished?: (f: JobFinished) => void;
}) {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [finished, setFinished] = useState<JobFinished | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    setProgress(null);
    setFinished(null);
    if (!jobId) return;
    let closed = false;
    let es: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      es = new EventSource(`${API_BASE}/jobs/${jobId}/events`);
      es.addEventListener("progress", (e) => setProgress(JSON.parse((e as MessageEvent).data)));
      es.addEventListener("finished", (e) => {
        const f = JSON.parse((e as MessageEvent).data) as JobFinished;
        closed = true;
        es?.close();
        setFinished(f);
        for (const key of optsRef.current?.invalidate ?? []) qc.invalidateQueries({ queryKey: key });
        optsRef.current?.onFinished?.(f);
      });
      es.onerror = () => {
        es?.close();
        if (!closed) retry = setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      closed = true;
      es?.close();
      if (retry) clearTimeout(retry);
    };
  }, [jobId, qc]);

  const running = !!jobId && !finished;
  return { progress, finished, running };
}
