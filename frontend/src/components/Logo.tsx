// Biểu tượng SpecLoop: vòng lặp có mũi tên (tài liệu → đặc tả → kiểm thử → tinh chỉnh) ôm dấu kiểm (đã kiểm chứng).
// Cùng hình với public/favicon.svg – sửa một nơi thì sửa cả hai.
import { useId } from "react";

export function LogoMark({ size = 34, className }: { size?: number; className?: string }) {
  const gid = useId();
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} className={className} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2473ec" />
          <stop offset="1" stopColor="#0a3f9e" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="10" fill={`url(#${gid})`} />
      <path d="M28.66 15 A10 10 0 1 1 17.4 10.3" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      <path d="M20.72 9.72 L16.36 13.74 L15.24 7.44 Z" fill="#fff" stroke="#fff" strokeWidth="1" strokeLinejoin="round" />
      <path d="M14.8 20.6 L18.6 24.3 L25.4 17.4" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
