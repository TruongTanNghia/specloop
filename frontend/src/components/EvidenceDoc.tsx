// Khung tài liệu: tô sáng mọi trích dẫn (span_start/span_end), làm nổi bật & cuộn tới trích dẫn đang chọn.
import { useEffect, useMemo, useRef } from "react";
import type { EvidenceItem } from "../api/types";

interface Seg {
  start: number;
  end: number;
  ids: number[];
}

export default function EvidenceDoc({ text, evidence, activeIds, height = 600 }: {
  text: string;
  evidence: EvidenceItem[];
  activeIds: number[];
  height?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const segs = useMemo(() => {
    const cuts = new Set<number>([0, text.length]);
    const spans = evidence.filter((e) => e.span_start !== null && e.span_end !== null && e.span_end! > e.span_start!);
    for (const e of spans) {
      cuts.add(Math.max(0, e.span_start!));
      cuts.add(Math.min(text.length, e.span_end!));
    }
    const points = [...cuts].sort((a, b) => a - b);
    const out: Seg[] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const s = points[i];
      const en = points[i + 1];
      out.push({ start: s, end: en, ids: spans.filter((e) => e.span_start! <= s && e.span_end! >= en).map((e) => e.id) });
    }
    return out;
  }, [text, evidence]);

  useEffect(() => {
    const el = box.current?.querySelector(".ev-mark.active");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeIds]);

  return (
    <div ref={box} className="ev-doc" style={{ height }} data-testid="evidence-doc">
      {segs.map((s) => {
        const t = text.slice(s.start, s.end);
        if (!s.ids.length) return <span key={s.start}>{t}</span>;
        const active = s.ids.some((id) => activeIds.includes(id));
        return <mark key={s.start} className={`ev-mark${active ? " active" : ""}`} title={`${s.ids.length} trích dẫn`}>{t}</mark>;
      })}
    </div>
  );
}
