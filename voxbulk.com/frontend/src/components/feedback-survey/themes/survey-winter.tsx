import * as React from "react";
import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-winter-gradient",
  ink: "#0f2540",
  sub: "rgba(15,37,64,0.60)",
  card: "rgba(255,255,255,0.85)",
  border: "rgba(15,37,64,0.10)",
  accent: "#3b82f6",
  accent2: "#8ec5ff",
  cool: "#0f2540",
  gradientButton: "linear-gradient(135deg,#3b82f6,#8ec5ff)",
  gradientProgress: "linear-gradient(90deg,#3b82f6,#8ec5ff,#0f2540)",
  selectedShadow: "0 8px 24px -8px rgba(59,130,246,0.45)",
  ringA: "rgba(59,130,246,0.55)",
  ringB: "rgba(142,197,255,0.4)",
};

function Snowflake({ style }: { style: React.CSSProperties }) {
  return (
    <span aria-hidden className="animate-snowfall absolute top-0 select-none" style={style}>
      ❄
    </span>
  );
}

export function Art() {
  const flakes = React.useMemo(
    () =>
      Array.from({ length: 22 }).map((_, i) => ({
        left: `${(i * 37) % 100}%`,
        delay: `${(i * 0.7) % 12}s`,
        duration: `${8 + (i % 6)}s`,
        size: `${10 + (i % 5) * 3}px`,
        opacity: 0.25 + (i % 4) * 0.15,
      })),
    [],
  );
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="animate-float-blob absolute -left-20 -top-10 h-72 w-72 rounded-full blur-3xl"
        style={{ background: "rgba(142,197,255,0.55)" }}
      />
      <div
        className="animate-float-blob-2 absolute -right-16 bottom-0 h-80 w-80 rounded-full blur-3xl"
        style={{ background: "rgba(59,130,246,0.35)" }}
      />
      <svg
        className="animate-orbit-slow absolute -right-10 top-20 h-48 w-48 opacity-30"
        viewBox="0 0 100 100"
        fill="none"
        stroke="#3b82f6"
        strokeWidth="1.5"
        strokeLinecap="round"
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <g key={i} transform={`rotate(${i * 60} 50 50)`}>
            <line x1="50" y1="50" x2="50" y2="10" />
            <line x1="50" y1="25" x2="42" y2="18" />
            <line x1="50" y1="25" x2="58" y2="18" />
            <line x1="50" y1="35" x2="44" y2="30" />
            <line x1="50" y1="35" x2="56" y2="30" />
          </g>
        ))}
      </svg>
      <svg className="absolute -left-4 bottom-0 h-40 w-40 opacity-30" viewBox="0 0 100 120" fill="#0f2540">
        <path d="M50 5 L30 40 L40 40 L20 70 L35 70 L10 105 L90 105 L65 70 L80 70 L60 40 L70 40 Z" />
        <rect x="45" y="105" width="10" height="12" />
      </svg>
      {flakes.map((f, i) => (
        <Snowflake
          key={i}
          style={{
            left: f.left,
            fontSize: f.size,
            opacity: f.opacity,
            color: "#e0f2fe",
            animationDuration: f.duration,
            animationDelay: f.delay,
          }}
        />
      ))}
    </div>
  );
}
