import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-newyear-gradient",
  ink: "#faf5ff",
  sub: "rgba(250,245,255,0.65)",
  card: "rgba(255,255,255,0.07)",
  border: "rgba(250,245,255,0.16)",
  accent: "#fbbf24",
  accent2: "#a78bfa",
  cool: "#f472b6",
  gradientButton: "linear-gradient(135deg,#fbbf24,#f472b6,#a78bfa)",
  gradientProgress: "linear-gradient(90deg,#a78bfa,#f472b6,#fbbf24)",
  selectedShadow: "0 8px 24px -6px rgba(251,191,36,0.55)",
  ringA: "rgba(251,191,36,0.5)",
  ringB: "rgba(167,139,250,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(167,139,250,0.28)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(251,191,36,0.22)" }} />
      {/* Fireworks */}
      {[
        { left: "18%", top: "18%", color: "#fbbf24", d: "0s" },
        { left: "72%", top: "12%", color: "#f472b6", d: "0.9s" },
        { left: "40%", top: "30%", color: "#a78bfa", d: "1.6s" },
      ].map((f, i) => (
        <span key={i} className="animate-firework absolute h-24 w-24 rounded-full" style={{
          left: f.left, top: f.top, background: `radial-gradient(circle, ${f.color} 0%, transparent 60%)`, animationDelay: f.d,
        }} />
      ))}
      {/* Confetti */}
      {["#fbbf24", "#f472b6", "#a78bfa", "#22d3ee"].map((c, i) => (
        <span key={i} className="animate-confetti-fall absolute top-0" style={{
          left: `${(i * 27 + 8) % 100}%`, color: c, animationDelay: `${i * 1.4}s`, animationDuration: `${9 + i}s`,
        }}>✦</span>
      ))}
      {/* Big countdown clock */}
      <svg className="animate-orbit-slow absolute -right-8 top-24 h-32 w-32 opacity-25" viewBox="0 0 100 100" fill="none" stroke="#fbbf24" strokeWidth="1.5">
        <circle cx="50" cy="50" r="42" />
        {Array.from({ length: 12 }).map((_, i) => (
          <line key={i} x1="50" y1="10" x2="50" y2="16" transform={`rotate(${i * 30} 50 50)`} />
        ))}
      </svg>
    </div>
  );
}
