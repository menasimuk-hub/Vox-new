import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-christmas-gradient",
  ink: "#fff8ee",
  sub: "rgba(255,248,238,0.65)",
  card: "rgba(255,255,255,0.07)",
  border: "rgba(255,248,238,0.16)",
  accent: "#ef4444",
  accent2: "#22c55e",
  cool: "#fbbf24",
  gradientButton: "linear-gradient(135deg,#ef4444,#22c55e)",
  gradientProgress: "linear-gradient(90deg,#22c55e,#fbbf24,#ef4444)",
  selectedShadow: "0 8px 24px -6px rgba(239,68,68,0.55)",
  ringA: "rgba(239,68,68,0.5)",
  ringB: "rgba(34,197,94,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(34,197,94,0.28)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(239,68,68,0.25)" }} />
      {/* Snowflakes */}
      {Array.from({ length: 14 }).map((_, i) => (
        <span key={i} className="animate-snowfall absolute top-0 text-white/70" style={{
          left: `${(i * 13 + 4) % 100}%`, fontSize: `${10 + (i % 3) * 4}px`,
          animationDelay: `${i * 0.8}s`, animationDuration: `${10 + (i % 5) * 2}s`,
        }}>❄</span>
      ))}
      {/* Pine tree */}
      <svg className="animate-sway absolute -left-4 bottom-24 h-40 w-32 opacity-40" viewBox="0 0 100 140" fill="#22c55e" style={{ transformOrigin: "50% 100%" }}>
        <polygon points="50,10 20,55 40,55 15,95 42,95 10,135 90,135 58,95 85,95 60,55 80,55" />
        <rect x="44" y="130" width="12" height="10" fill="#78350f" />
      </svg>
      {/* Ornament */}
      <svg className="animate-bob absolute right-6 top-20 h-14 w-14 opacity-75" viewBox="0 0 40 40">
        <circle cx="20" cy="24" r="12" fill="#ef4444" />
        <rect x="17" y="8" width="6" height="6" fill="#fbbf24" />
      </svg>
    </div>
  );
}
