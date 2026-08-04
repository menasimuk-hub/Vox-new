import * as React from "react";

import { cn } from "@/lib/utils";

export function spark(seed: number, n = 16): number[] {
  const out: number[] = [];
  let x = seed * 9301 + 49297;
  for (let i = 0; i < n; i++) {
    x = (x * 9301 + 49297) % 233280;
    out.push(30 + (x / 233280) * 70);
  }
  return out;
}

interface SparklineProps {
  data: number[];
  className?: string;
  filled?: boolean;
}

export function Sparkline({ data, className, filled = true }: SparklineProps) {
  const w = 100;
  const h = 28;
  if (!data?.length) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const pts = data.map((v, i) => {
    const x = data.length === 1 ? 0 : (i / (data.length - 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * (h - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn("h-7 w-full", className)} preserveAspectRatio="none">
      {filled ? (
        <polygon
          points={`0,${h} ${pts.join(" ")} ${w},${h}`}
          fill="currentColor"
          className="opacity-10"
        />
      ) : null}
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="opacity-80"
      />
    </svg>
  );
}

export type StatusTone = "ok" | "warn" | "bad";

export function StatusDot({ tone }: { tone: StatusTone }) {
  return (
    <span className="relative flex h-2 w-2">
      <span
        className={cn(
          "absolute inline-flex h-full w-full animate-ping rounded-full opacity-60",
          tone === "ok" && "bg-success",
          tone === "warn" && "bg-warning",
          tone === "bad" && "bg-destructive",
        )}
      />
      <span
        className={cn(
          "relative inline-flex h-2 w-2 rounded-full",
          tone === "ok" && "bg-success",
          tone === "warn" && "bg-warning",
          tone === "bad" && "bg-destructive",
        )}
      />
    </span>
  );
}
