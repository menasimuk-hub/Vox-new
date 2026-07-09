import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-hotel-gradient",
  ink: "#f5efe0",
  sub: "rgba(245,239,224,0.62)",
  card: "rgba(255,255,255,0.08)",
  border: "rgba(245,239,224,0.18)",
  accent: "#d4af37", // gold
  accent2: "#e9d38a",
  cool: "#0e3a4c",
  gradientButton: "linear-gradient(135deg,#d4af37,#e9d38a)",
  gradientProgress: "linear-gradient(90deg,#d4af37,#e9d38a,#f5efe0)",
  selectedShadow: "0 8px 24px -8px rgba(212,175,55,0.55)",
  ringA: "rgba(212,175,55,0.5)",
  ringB: "rgba(233,211,138,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-20 -top-16 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(212,175,55,0.18)" }} />
      <div className="animate-float-blob-2 absolute -right-20 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(233,211,138,0.10)" }} />
      {/* Gold arch */}
      <svg className="absolute -right-8 top-16 h-56 w-56 opacity-25" viewBox="0 0 100 100" fill="none" stroke="#d4af37" strokeWidth="1">
        {Array.from({ length: 8 }).map((_, i) => (
          <path key={i} d={`M 10 90 A ${30 + i * 4} ${30 + i * 4} 0 0 1 90 90`} />
        ))}
      </svg>
      {/* Bell */}
      <svg className="animate-bob absolute right-6 top-24 h-14 w-14 opacity-70" viewBox="0 0 40 40" fill="#d4af37" stroke="#0e3a4c" strokeWidth="1.5">
        <path d="M20 6a10 10 0 0 0-10 10v10h20V16A10 10 0 0 0 20 6z" />
        <rect x="8" y="26" width="24" height="3" rx="1.5" />
        <circle cx="20" cy="32" r="2" />
      </svg>
      {/* Stars */}
      {[
        { top: "20%", left: "22%", d: "0s" },
        { top: "68%", left: "12%", d: "0.8s" },
        { top: "82%", right: "22%", d: "1.4s" },
        { top: "38%", left: "48%", d: "2.2s" },
      ].map((p, i) => (
        <span key={i} className="animate-twinkle absolute text-xs" style={{ ...p, animationDelay: p.d, color: "#e9d38a" }}>✦</span>
      ))}
    </div>
  );
}
