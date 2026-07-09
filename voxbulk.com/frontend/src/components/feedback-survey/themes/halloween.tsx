import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-halloween-gradient",
  ink: "#fff1e0",
  sub: "rgba(255,241,224,0.62)",
  card: "rgba(255,255,255,0.06)",
  border: "rgba(255,241,224,0.16)",
  accent: "#f97316",
  accent2: "#a855f7",
  cool: "#22c55e",
  gradientButton: "linear-gradient(135deg,#f97316,#a855f7)",
  gradientProgress: "linear-gradient(90deg,#a855f7,#f97316)",
  selectedShadow: "0 8px 24px -6px rgba(249,115,22,0.6)",
  ringA: "rgba(249,115,22,0.55)",
  ringB: "rgba(168,85,247,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(249,115,22,0.28)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(168,85,247,0.24)" }} />
      {/* Pumpkin */}
      <svg className="animate-bob absolute left-6 bottom-24 h-20 w-24 opacity-90" viewBox="0 0 80 70">
        <ellipse cx="40" cy="42" rx="34" ry="26" fill="#f97316" />
        <ellipse cx="20" cy="42" rx="10" ry="26" fill="#ea580c" opacity="0.7" />
        <ellipse cx="60" cy="42" rx="10" ry="26" fill="#ea580c" opacity="0.7" />
        <rect x="37" y="8" width="6" height="10" fill="#22c55e" />
        <polygon points="24,36 34,36 29,44" fill="#fff1e0" />
        <polygon points="46,36 56,36 51,44" fill="#fff1e0" />
        <path d="M22 54 l6 -3 l4 3 l4 -3 l4 3 l4 -3 l4 3 l6 -3" stroke="#fff1e0" strokeWidth="2" fill="none" />
      </svg>
      {/* Ghost */}
      <svg className="animate-drift-slow absolute right-6 top-16 h-24 w-20 opacity-80" viewBox="0 0 60 80">
        <path d="M10 30 a20 20 0 0 1 40 0 v40 l-6 -6 l-6 6 l-8 -6 l-8 6 l-6 -6 l-6 6 z" fill="#fff1e0" />
        <circle cx="22" cy="34" r="3" fill="#0f0a1a" />
        <circle cx="38" cy="34" r="3" fill="#0f0a1a" />
      </svg>
      {/* Bats */}
      {[
        { l: "22%", t: "20%", d: "0s" },
        { l: "62%", t: "48%", d: "1.2s" },
      ].map((b, i) => (
        <svg key={i} className="animate-sway absolute h-6 w-10 opacity-80" style={{ left: b.l, top: b.t, animationDelay: b.d, color: "#0f0a1a" }} viewBox="0 0 40 20" fill="currentColor">
          <path d="M20 4 l-6 6 l-8 -4 l4 8 l-4 4 l14 -4 l14 4 l-4 -4 l4 -8 l-8 4 z" />
        </svg>
      ))}
      {/* Moon */}
      <div className="animate-glow-pulse absolute right-8 top-4 h-12 w-12 rounded-full" style={{ background: "radial-gradient(circle,#fef08a,#f97316)" }} />
    </div>
  );
}
