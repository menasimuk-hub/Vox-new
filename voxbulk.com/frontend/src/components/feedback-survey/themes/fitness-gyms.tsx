import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-fitness-gradient",
  ink: "#ecfccb",
  sub: "rgba(236,252,203,0.60)",
  card: "rgba(255,255,255,0.06)",
  border: "rgba(236,252,203,0.15)",
  accent: "#a3e635", // lime
  accent2: "#fb923c", // orange
  cool: "#111827",
  gradientButton: "linear-gradient(135deg,#a3e635,#fb923c)",
  gradientProgress: "linear-gradient(90deg,#a3e635,#fb923c)",
  selectedShadow: "0 8px 24px -6px rgba(163,230,53,0.55)",
  ringA: "rgba(163,230,53,0.55)",
  ringB: "rgba(251,146,60,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-20 -top-16 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(163,230,53,0.22)" }} />
      <div className="animate-float-blob-2 absolute -right-20 bottom-0 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(251,146,60,0.22)" }} />
      {/* Diagonal stripes */}
      <div className="absolute inset-0 opacity-[0.06]" style={{
        backgroundImage: "repeating-linear-gradient(45deg, #a3e635 0 2px, transparent 2px 22px)",
      }} />
      {/* Dumbbell */}
      <svg className="animate-bob absolute right-6 top-24 h-16 w-16 opacity-80" viewBox="0 0 40 40" fill="none" stroke="#a3e635" strokeWidth="2.5" strokeLinecap="round">
        <rect x="4" y="14" width="4" height="12" rx="1.5" fill="#a3e635" />
        <rect x="32" y="14" width="4" height="12" rx="1.5" fill="#a3e635" />
        <rect x="8" y="17" width="2.5" height="6" fill="#fb923c" />
        <rect x="29.5" y="17" width="2.5" height="6" fill="#fb923c" />
        <line x1="11" y1="20" x2="29" y2="20" />
      </svg>
      {/* Bolt */}
      <svg className="animate-pulse-fast absolute left-6 bottom-28 h-14 w-14 opacity-80" viewBox="0 0 24 24" fill="#fb923c">
        <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />
      </svg>
      {/* Heartbeat line */}
      <svg className="animate-squiggle absolute left-1/4 top-1/2 h-8 w-40 opacity-40" viewBox="0 0 200 40" fill="none" stroke="#a3e635" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M0 20 H40 L50 5 L60 35 L70 20 H110 L120 8 L130 32 L140 20 H200" />
      </svg>
    </div>
  );
}
