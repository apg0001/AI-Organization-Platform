import { type ReactElement, memo } from "react";

import { SHIRT_COLORS, pixelColor, spriteRows } from "@/features/office/sprites";
import { mixHash } from "@/features/office/presence";
import { cn } from "@/lib/utils";

/**
 * 에이전트 아바타 — 사무실 캐릭터와 같은 픽셀 그림(sprites.ts)을 SVG로 그린다.
 * 제품의 '하나의 개성 있는 요소'다(docs/DESIGN_SYSTEM.md §시그니처). 이름 이니셜 대신 사무실 속 그 사람이 보인다.
 * 옷 색은 ID 해시로 고정되어 화면마다 같다. 장식이므로 접근성 트리에서는 이름만 읽힌다.
 */
export const AgentAvatar = memo(function AgentAvatar({
  id,
  lead = false,
  size = 28,
  className,
  dim = false,
}: {
  id: string;
  lead?: boolean;
  size?: number;
  className?: string;
  dim?: boolean;
}) {
  const shirt = mixHash(id) % SHIRT_COLORS.length;
  // 머리와 상체만 잘라 보여 준다(얼굴이 잘 보이도록).
  const rows = spriteRows(lead ? "lead" : "member", 0).slice(0, 13);
  const width = rows[0]?.length ?? 12;
  const rects: ReactElement[] = [];
  rows.forEach((row, y) =>
    Array.from(row).forEach((code, x) => {
      const color = pixelColor(code, shirt);
      if (color !== null) {
        rects.push(
          <rect key={`${x}-${y}`} x={x} y={y} width={1.02} height={1.02} fill={`#${color.toString(16).padStart(6, "0")}`} />,
        );
      }
    }),
  );
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-end justify-center overflow-hidden rounded-md border border-border bg-surface-3",
        dim && "opacity-50 grayscale",
        className,
      )}
      style={{ width: size, height: size }}
    >
      <svg viewBox={`-1 -1 ${width + 2} ${rows.length + 1}`} width={size - 4} height={size - 2} shapeRendering="crispEdges">
        {rects}
      </svg>
    </span>
  );
});

