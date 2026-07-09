import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-events-gradient",
  ink: "#f5f3ff",
  sub: "rgba(245,243,255,0.60)",
  card: "rgba(255,255,255,0.06)",
  border: "rgba(245,243,255,0.15)",
  accent: "#ec4899",
  accent2: "#22d3ee",
  cool: "#7c3aed",
  gradientButton: "linear-gradient(135deg,#ec4899,#7c3aed,#22d3ee)",
  gradientProgress: "linear-gradient(90deg,#22d3ee,#7c3aed,#ec4899)",
  selectedShadow: "0 8px 24px -6px rgba(236,72,153,0.6)",
  ringA: "rgba(236,72,153,0.5)",
  ringB: "rgba(34,211,238,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-20 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(236,72,153,0.30)" }} />
      <div className="animate-float-blob-2 absolute -right-20 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(34,211,238,0.25)" }} />
      {/* Disco ball */}
      <svg className="animate-orbit-slow absolute right-6 top-20 h-24 w-24 opacity-70" viewBox="0 0 100 100">
        <defs>
          <radialGradient id="disco" cx="35%" cy="35%">
            <stop offset="0%" stopColor="#f5f3ff" />
            <stop offset="60%" stopColor="#7c3aed" />
            <stop offset="100%" stopColor="#1e0b3d" />
          </radialGradient>
        </defs>
        <circle cx="50" cy="55" r="30" fill="url(#disco)" />
        {Array.from({ length: 6 }).map((_, i) => (
          <line key={i} x1="50" y1="25" x2="50" y2="85" stroke="rgba(255,255,255,0.25)" strokeWidth="0.6" transform={`rotate(${i * 30} 50 55)`} />
        ))}
      </svg>
      {/* Confetti */}
      {["#ec4899", "#22d3ee", "#a78bfa", "#f5f3ff", "#f59e0b"].map((c, i) => (
        <span key={i} className="animate-confetti-fall absolute top-0 text-sm" style={{
          left: `${(i * 21 + 5) % 100}%`,
          color: c,
          animationDelay: `${i * 1.3}s`,
          animationDuration: `${8 + i}s`,
        }}>■</span>
      ))}
      {/* Bolt */}
      <svg className="animate-pulse-fast absolute left-6 bottom-28 h-14 w-14 opacity-70" viewBox="0 0 24 24" fill="#22d3ee">
        <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />
      </svg>
    </div>
  );
}
