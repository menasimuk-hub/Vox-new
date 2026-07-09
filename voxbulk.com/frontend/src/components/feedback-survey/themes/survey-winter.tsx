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

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {Array.from({ length: 18 }).map((_, i) => (
        <span
          key={i}
          className="animate-snowfall absolute top-0 text-white/80"
          style={{
            left: `${(i * 11 + 3) % 100}%`,
            fontSize: `${8 + (i % 4) * 3}px`,
            animationDelay: `${i * 0.7}s`,
            animationDuration: `${12 + (i % 6) * 2}s`,
          }}
        >
          ❄
        </span>
      ))}
      <div
        className="animate-float-blob absolute -left-20 top-10 h-72 w-72 rounded-full blur-3xl"
        style={{ background: "rgba(142,197,255,0.35)" }}
      />
      <div
        className="animate-float-blob-2 absolute -right-16 bottom-0 h-80 w-80 rounded-full blur-3xl"
        style={{ background: "rgba(59,130,246,0.25)" }}
      />
    </div>
  );
}
