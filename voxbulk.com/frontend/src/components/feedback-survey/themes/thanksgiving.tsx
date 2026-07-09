import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-thanksgiving-gradient",
  ink: "#fff7ed",
  sub: "rgba(255,247,237,0.7)",
  card: "rgba(255,255,255,0.08)",
  border: "rgba(255,247,237,0.18)",
  accent: "#d97706",
  accent2: "#b45309",
  cool: "#7c2d12",
  gradientButton: "linear-gradient(135deg,#d97706,#b45309)",
  gradientProgress: "linear-gradient(90deg,#b45309,#d97706)",
  selectedShadow: "0 8px 24px -6px rgba(217,119,6,0.55)",
  ringA: "rgba(217,119,6,0.55)",
  ringB: "rgba(180,83,9,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(217,119,6,0.30)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(180,83,9,0.30)" }} />
      {/* Falling leaves */}
      {[
        { l: "10%", d: "0s", c: "#d97706" },
        { l: "28%", d: "2s", c: "#b45309" },
        { l: "48%", d: "1s", c: "#dc2626" },
        { l: "68%", d: "3s", c: "#eab308" },
        { l: "86%", d: "4s", c: "#7c2d12" },
      ].map((p, i) => (
        <span key={i} className="animate-confetti-fall absolute top-0 text-xl" style={{
          left: p.l, color: p.c, animationDelay: p.d, animationDuration: `${10 + i}s`,
        }}>❦</span>
      ))}
      {/* Pumpkin */}
      <svg className="animate-bob absolute left-6 bottom-24 h-16 w-20 opacity-85" viewBox="0 0 80 60">
        <ellipse cx="40" cy="36" rx="30" ry="22" fill="#d97706" />
        <ellipse cx="22" cy="36" rx="8" ry="22" fill="#b45309" opacity="0.7" />
        <ellipse cx="58" cy="36" rx="8" ry="22" fill="#b45309" opacity="0.7" />
        <rect x="37" y="8" width="6" height="8" fill="#4d7c0f" />
      </svg>
      {/* Wheat */}
      <svg className="animate-sway absolute right-4 bottom-20 h-32 w-24 opacity-55" viewBox="0 0 60 100" style={{ transformOrigin: "50% 100%" }}>
        <line x1="30" y1="100" x2="30" y2="20" stroke="#eab308" strokeWidth="2" />
        {Array.from({ length: 6 }).map((_, i) => (
          <g key={i} transform={`translate(0 ${20 + i * 10})`}>
            <ellipse cx="24" cy="0" rx="6" ry="3" fill="#eab308" transform="rotate(-30 24 0)" />
            <ellipse cx="36" cy="0" rx="6" ry="3" fill="#eab308" transform="rotate(30 36 0)" />
          </g>
        ))}
      </svg>
      {/* Sun */}
      <div className="animate-glow-pulse absolute right-8 top-6 h-14 w-14 rounded-full" style={{ background: "radial-gradient(circle,#fde68a,#d97706)" }} />
    </div>
  );
}
