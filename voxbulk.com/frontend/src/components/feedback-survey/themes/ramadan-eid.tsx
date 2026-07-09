import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-ramadan-gradient",
  ink: "#f5f3ff",
  sub: "rgba(245,243,255,0.62)",
  card: "rgba(255,255,255,0.06)",
  border: "rgba(245,243,255,0.15)",
  accent: "#fbbf24",
  accent2: "#10b981",
  cool: "#6366f1",
  gradientButton: "linear-gradient(135deg,#fbbf24,#10b981)",
  gradientProgress: "linear-gradient(90deg,#10b981,#fbbf24)",
  selectedShadow: "0 8px 24px -6px rgba(251,191,36,0.5)",
  ringA: "rgba(251,191,36,0.5)",
  ringB: "rgba(16,185,129,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(99,102,241,0.30)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(16,185,129,0.20)" }} />
      {/* Crescent moon */}
      <svg className="animate-bob absolute right-6 top-16 h-24 w-24 opacity-90" viewBox="0 0 100 100">
        <defs>
          <mask id="crescent">
            <rect width="100" height="100" fill="white" />
            <circle cx="60" cy="45" r="30" fill="black" />
          </mask>
        </defs>
        <circle cx="50" cy="50" r="30" fill="#fbbf24" mask="url(#crescent)" />
      </svg>
      {/* Stars twinkling */}
      {[
        { l: "12%", t: "22%", d: "0s" },
        { l: "34%", t: "14%", d: "0.6s" },
        { l: "78%", t: "40%", d: "1.1s" },
        { l: "20%", t: "58%", d: "1.8s" },
        { l: "62%", t: "68%", d: "0.3s" },
      ].map((s, i) => (
        <span key={i} className="animate-twinkle absolute text-white/80" style={{ left: s.l, top: s.t, animationDelay: s.d }}>✦</span>
      ))}
      {/* Lantern */}
      <svg className="animate-glow-pulse absolute left-6 bottom-32 h-20 w-14 opacity-80" viewBox="0 0 40 60">
        <rect x="16" y="2" width="8" height="4" fill="#fbbf24" />
        <path d="M8 12 h24 v32 a12 12 0 0 1 -24 0 z" fill="#fbbf24" opacity="0.9" />
        <line x1="14" y1="18" x2="14" y2="42" stroke="#78350f" strokeWidth="1" />
        <line x1="26" y1="18" x2="26" y2="42" stroke="#78350f" strokeWidth="1" />
        <rect x="6" y="44" width="28" height="4" fill="#78350f" />
      </svg>
      {/* Mosque silhouette */}
      <svg className="absolute -right-4 bottom-16 h-28 w-40 opacity-30" viewBox="0 0 200 120" fill="#f5f3ff">
        <path d="M20 110 h160 v-40 c0-15-25-25-40-25v-15c0-8-6-14-14-14h-52c-8 0-14 6-14 14v15c-15 0-40 10-40 25z" />
        <circle cx="100" cy="45" r="14" />
      </svg>
    </div>
  );
}
