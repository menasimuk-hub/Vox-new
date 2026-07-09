import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-eidadha-gradient",
  ink: "#f0fdf4",
  sub: "rgba(240,253,244,0.65)",
  card: "rgba(255,255,255,0.07)",
  border: "rgba(240,253,244,0.16)",
  accent: "#eab308",
  accent2: "#4ade80",
  cool: "#065f46",
  gradientButton: "linear-gradient(135deg,#eab308,#4ade80)",
  gradientProgress: "linear-gradient(90deg,#4ade80,#eab308)",
  selectedShadow: "0 8px 24px -6px rgba(234,179,8,0.5)",
  ringA: "rgba(234,179,8,0.5)",
  ringB: "rgba(74,222,128,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(74,222,128,0.28)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(234,179,8,0.22)" }} />
      {/* Geometric star pattern */}
      <svg className="animate-orbit-slow absolute -right-8 top-16 h-40 w-40 opacity-35" viewBox="0 0 100 100" fill="none" stroke="#eab308" strokeWidth="0.8">
        <polygon points="50,8 62,42 96,42 68,62 78,96 50,74 22,96 32,62 4,42 38,42" />
        <polygon points="50,20 58,44 82,44 62,58 70,82 50,68 30,82 38,58 18,44 42,44" />
      </svg>
      {/* Crescent */}
      <svg className="animate-bob absolute left-6 top-14 h-20 w-20 opacity-90" viewBox="0 0 100 100">
        <defs><mask id="cr2"><rect width="100" height="100" fill="white" /><circle cx="60" cy="45" r="30" fill="black" /></mask></defs>
        <circle cx="50" cy="50" r="30" fill="#eab308" mask="url(#cr2)" />
      </svg>
      {/* Palm */}
      <svg className="animate-sway absolute right-0 bottom-16 h-40 w-32 opacity-45" viewBox="0 0 120 160" style={{ transformOrigin: "50% 100%" }}>
        <rect x="56" y="80" width="8" height="80" fill="#78350f" />
        {Array.from({ length: 7 }).map((_, i) => (
          <ellipse key={i} cx="60" cy="80" rx="10" ry="40" fill="#4ade80" opacity="0.75"
            transform={`rotate(${(i - 3) * 25} 60 80) translate(0 -30)`} />
        ))}
      </svg>
      {/* Stars */}
      {[
        { l: "22%", t: "30%", d: "0s" },
        { l: "60%", t: "22%", d: "0.6s" },
        { l: "40%", t: "55%", d: "1.2s" },
      ].map((s, i) => (
        <span key={i} className="animate-twinkle absolute" style={{ left: s.l, top: s.t, color: "#eab308", animationDelay: s.d }}>✧</span>
      ))}
    </div>
  );
}
