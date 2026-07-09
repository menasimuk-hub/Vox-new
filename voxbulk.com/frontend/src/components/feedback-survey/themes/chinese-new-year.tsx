import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-cny-gradient",
  ink: "#fff2d6",
  sub: "rgba(255,242,214,0.68)",
  card: "rgba(255,255,255,0.08)",
  border: "rgba(255,242,214,0.18)",
  accent: "#fbbf24",
  accent2: "#facc15",
  cool: "#dc2626",
  gradientButton: "linear-gradient(135deg,#fbbf24,#dc2626)",
  gradientProgress: "linear-gradient(90deg,#dc2626,#fbbf24)",
  selectedShadow: "0 8px 24px -6px rgba(251,191,36,0.6)",
  ringA: "rgba(251,191,36,0.55)",
  ringB: "rgba(220,38,38,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(251,191,36,0.30)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(220,38,38,0.35)" }} />
      {/* Lanterns */}
      {[
        { l: "12%", t: "12%", d: "0s" },
        { l: "72%", t: "18%", d: "0.7s" },
        { l: "44%", t: "6%", d: "1.3s" },
      ].map((p, i) => (
        <div key={i} className="animate-bob absolute" style={{ left: p.l, top: p.t, animationDelay: p.d }}>
          <div className="mx-auto h-1 w-6 bg-yellow-300/70" />
          <div className="h-12 w-10 rounded-full" style={{ background: "radial-gradient(ellipse at center, #fca5a5, #dc2626)", boxShadow: "0 0 24px rgba(251,191,36,0.5)" }} />
          <div className="mx-auto h-3 w-1 bg-yellow-300/80" />
        </div>
      ))}
      {/* Coin */}
      <svg className="animate-orbit-slow absolute -right-6 bottom-24 h-24 w-24 opacity-70" viewBox="0 0 60 60">
        <circle cx="30" cy="30" r="26" fill="#fbbf24" stroke="#dc2626" strokeWidth="2" />
        <rect x="26" y="10" width="8" height="40" fill="#dc2626" />
        <rect x="10" y="26" width="40" height="8" fill="#dc2626" />
      </svg>
      {/* Sparks */}
      {["18%", "38%", "62%", "84%"].map((l, i) => (
        <span key={i} className="animate-twinkle absolute text-xl" style={{ left: l, top: `${40 + (i % 2) * 10}%`, color: "#fbbf24", animationDelay: `${i * 0.4}s` }}>✦</span>
      ))}
    </div>
  );
}
