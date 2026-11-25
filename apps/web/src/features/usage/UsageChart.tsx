/**
 * 사용량 이력 꺾은선(단일 계열). 데이터 시각화 지침: 한 축(0~100%), 2px 선, 연한 격자, 십자선+툴팁, 표 대체 보기.
 * 계열이 하나라 범례 대신 제목이 이름이다. 색은 정체성(계열)용 주색 하나, 글자는 글자 토큰.
 */

import { useMemo, useRef, useState } from "react";

const W = 640;
const H = 168;
const PAD = { top: 8, right: 12, bottom: 22, left: 36 };

export function UsageChart({ points, title }: { points: { at: string; percent: number }[]; title: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const data = useMemo(() => points.map((p) => ({ t: new Date(p.at).getTime(), v: p.percent })), [points]);
  if (data.length < 2) {
    return <p className="text-xs text-faint">이력이 쌓이면 그래프가 나타납니다(관측 {data.length}개).</p>;
  }
  const t0 = data[0]!.t;
  const t1 = data[data.length - 1]!.t;
  const span = Math.max(1, t1 - t0);
  const x = (t: number) => PAD.left + ((t - t0) / span) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - v / 100) * (H - PAD.top - PAD.bottom);
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(d.t).toFixed(1)},${y(d.v).toFixed(1)}`).join("");
  const fmt = (t: number) =>
    new Date(t).toLocaleString("ko", span > 2 * 86_400_000 ? { month: "numeric", day: "numeric" } : { hour: "2-digit", minute: "2-digit" });
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const t = t0 + ((((e.clientX - rect.left) / rect.width) * W - PAD.left) / (W - PAD.left - PAD.right)) * span;
    let best = 0;
    data.forEach((d, i) => {
      if (Math.abs(d.t - t) < Math.abs(data[best]!.t - t)) best = i;
    });
    setHover(best);
  };
  const h = hover !== null ? data[hover] : null;
  return (
    <figure className="flex flex-col gap-1">
      <figcaption className="text-xs font-medium text-muted">{title}</figcaption>
      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="w-full touch-none"
          role="img"
          aria-label={`${title}: ${data.length}개 관측, 최근 ${data[data.length - 1]!.v.toFixed(0)}%`}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          {[0, 50, 100].map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeWidth={1} />
              <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--text-faint)" className="tabular">
                {v}%
              </text>
            </g>
          ))}
          <text x={PAD.left} y={H - 4} fontSize={11} fill="var(--text-faint)">
            {fmt(t0)}
          </text>
          <text x={W - PAD.right} y={H - 4} textAnchor="end" fontSize={11} fill="var(--text-faint)">
            {fmt(t1)}
          </text>
          <path d={path} fill="none" stroke="var(--chart-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {h ? (
            <g>
              <line x1={x(h.t)} x2={x(h.t)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--border-strong)" strokeWidth={1} />
              <circle cx={x(h.t)} cy={y(h.v)} r={4} fill="var(--chart-1)" stroke="var(--surface-1)" strokeWidth={2} />
            </g>
          ) : null}
        </svg>
        {h ? (
          <div
            className="pointer-events-none absolute top-1 rounded-md border border-border-strong bg-surface-2 px-2 py-1 text-xs shadow-overlay"
            style={{ left: `calc(${(x(h.t) / W) * 100}% + 8px)`, transform: x(h.t) > W * 0.7 ? "translateX(calc(-100% - 16px))" : undefined }}
          >
            <span className="tabular font-medium text-fg">{h.v.toFixed(1)}%</span>
            <span className="ml-2 text-faint">{new Date(h.t).toLocaleString("ko")}</span>
          </div>
        ) : null}
      </div>
      <details className="text-xs text-faint">
        <summary className="cursor-pointer">표로 보기</summary>
        <table className="mt-1 tabular">
          <tbody>
            {data.slice(-20).map((d) => (
              <tr key={d.t}>
                <td className="pr-4">{new Date(d.t).toLocaleString("ko")}</td>
                <td>{d.v.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
