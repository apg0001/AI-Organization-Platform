import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

const relative = new Intl.RelativeTimeFormat("ko", { numeric: "auto" });

/** "3분 전" 같은 상대 시각. 1주를 넘으면 날짜. */
export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "방금";
  if (abs < 3600) return relative.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return relative.format(Math.round(diff / 3600), "hour");
  if (abs < 604800) return relative.format(Math.round(diff / 86400), "day");
  return new Date(iso).toLocaleDateString("ko");
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
