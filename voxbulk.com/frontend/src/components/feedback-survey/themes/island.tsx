import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-island-gradient",
  ink: "#0c3b4a",
  sub: "rgba(12,59,74,0.65)",
  card: "rgba(255,255,255,0.78)",
  border: "rgba(12,59,74,0.10)",
  accent: "#06b6d4",
  accent2: "#f59e0b",
  cool: "#14b8a6",
  gradientButton: "linear-gradient(135deg,#06b6d4,#14b8a6,#f59e0b)",
  gradientProgress: "linear-gradient(90deg,#f59e0b,#14b8a6,#06b6d4)",
  selectedShadow: "0 8px 24px -6px rgba(6,182,212,0.5)",
  ringA: "rgba(6,182,212,0.5)",
  ringB: "rgba(245,158,11,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(6,182,212,0.35)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(245,158,11,0.25)" }} />
      {/* Sun */}
      <div className="animate-sun-spin absolute -right-8 -top-8 h-40 w-40 opacity-70" style={{ background: "conic-gradient(from 0deg,#fde68a,#f59e0b,#fde68a)", borderRadius: "9999px", filter: "blur(2px)" }} />
      {/* Waves */}
      <svg className="animate-squiggle absolute bottom-24 left-0 w-full opacity-40" viewBox="0 0 400 40" fill="none" stroke="#06b6d4" strokeWidth="2">
        <path d="M0 20 Q 25 5 50 20 T 100 20 T 150 20 T 200 20 T 250 20 T 300 20 T 350 20 T 400 20" />
      </svg>
      <svg className="animate-squiggle absolute bottom-16 left-0 w-full opacity-30" viewBox="0 0 400 40" fill="none" stroke="#14b8a6" strokeWidth="2" style={{ animationDelay: "0.6s" }}>
        <path d="M0 20 Q 30 30 60 20 T 120 20 T 180 20 T 240 20 T 300 20 T 360 20 T 400 20" />
      </svg>
      {/* Palm tree */}
      <svg className="animate-sway absolute -left-2 bottom-20 h-44 w-40 opacity-70" viewBox="0 0 120 160" style={{ transformOrigin: "50% 100%" }}>
        <path d="M60 160 Q 55 100 50 60 Q 46 30 40 20" stroke="#78350f" strokeWidth="5" fill="none" strokeLinecap="round" />
        {Array.from({ length: 7 }).map((_, i) => (
          <ellipse key={i} cx="42" cy="20" rx="8" ry="30" fill="#14b8a6" opacity="0.8"
            transform={`rotate(${(i - 3) * 28} 42 20) translate(0 -22)`} />
        ))}
        <circle cx="52" cy="24" r="4" fill="#a16207" />
        <circle cx="34" cy="30" r="4" fill="#a16207" />
      </svg>
      {/* Hibiscus */}
      <svg className="animate-twinkle absolute right-6 top-20 h-14 w-14 opacity-85" viewBox="0 0 40 40">
        {Array.from({ length: 5 }).map((_, i) => (
          <ellipse key={i} cx="20" cy="10" rx="6" ry="10" fill="#ec4899" transform={`rotate(${i * 72} 20 20)`} />
        ))}
        <circle cx="20" cy="20" r="3" fill="#facc15" />
      </svg>
      {/* Seagulls */}
      <svg className="animate-drift-slow absolute left-1/3 top-16 h-4 w-10 opacity-70" viewBox="0 0 40 10" fill="none" stroke="#0c3b4a" strokeWidth="1.5">
        <path d="M2 8 Q 10 0 20 8 Q 30 0 38 8" />
      </svg>
    </div>
  );
}
