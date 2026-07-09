import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-diwali-gradient",
  ink: "#fff7ed",
  sub: "rgba(255,247,237,0.65)",
  card: "rgba(255,255,255,0.07)",
  border: "rgba(255,247,237,0.17)",
  accent: "#f59e0b",
  accent2: "#ec4899",
  cool: "#a855f7",
  gradientButton: "linear-gradient(135deg,#f59e0b,#ec4899,#a855f7)",
  gradientProgress: "linear-gradient(90deg,#a855f7,#ec4899,#f59e0b)",
  selectedShadow: "0 8px 24px -6px rgba(245,158,11,0.55)",
  ringA: "rgba(245,158,11,0.55)",
  ringB: "rgba(236,72,153,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(245,158,11,0.30)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(168,85,247,0.25)" }} />
      {/* Diya lamps glowing */}
      {[
        { l: "12%", b: "18%", d: "0s" },
        { l: "40%", b: "10%", d: "0.7s" },
        { l: "70%", b: "22%", d: "1.3s" },
      ].map((p, i) => (
        <div key={i} className="animate-glow-pulse absolute" style={{ left: p.l, bottom: p.b, animationDelay: p.d }}>
          <div className="h-6 w-10 rounded-b-full" style={{ background: "#78350f" }} />
          <div className="mx-auto -mt-5 h-8 w-3 rounded-full" style={{ background: "radial-gradient(circle,#fef08a,#f59e0b)" }} />
        </div>
      ))}
      {/* Rangoli */}
      <svg className="animate-orbit-slow absolute -right-8 top-20 h-36 w-36 opacity-45" viewBox="0 0 100 100">
        {Array.from({ length: 12 }).map((_, i) => (
          <ellipse key={i} cx="50" cy="20" rx="6" ry="14" fill={i % 2 === 0 ? "#f59e0b" : "#ec4899"} transform={`rotate(${i * 30} 50 50)`} />
        ))}
        <circle cx="50" cy="50" r="5" fill="#fef08a" />
      </svg>
      {/* Sparkles */}
      {[
        { l: "22%", t: "30%", d: "0s" },
        { l: "58%", t: "18%", d: "0.5s" },
        { l: "80%", t: "50%", d: "1.1s" },
      ].map((s, i) => (
        <span key={i} className="animate-twinkle absolute text-lg" style={{ left: s.l, top: s.t, color: "#fef08a", animationDelay: s.d }}>✧</span>
      ))}
    </div>
  );
}
