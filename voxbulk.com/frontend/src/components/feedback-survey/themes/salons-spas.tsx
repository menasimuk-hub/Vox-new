import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-salon-gradient",
  ink: "#5b1a2b",
  sub: "rgba(91,26,43,0.62)",
  card: "rgba(255,251,250,0.82)",
  border: "rgba(91,26,43,0.10)",
  accent: "#e11d74",
  accent2: "#f7c6cf",
  cool: "#b76e79", // rose gold
  gradientButton: "linear-gradient(135deg,#e11d74,#b76e79)",
  gradientProgress: "linear-gradient(90deg,#f7c6cf,#e11d74,#b76e79)",
  selectedShadow: "0 8px 24px -8px rgba(225,29,116,0.45)",
  ringA: "rgba(247,198,207,0.7)",
  ringB: "rgba(225,29,116,0.35)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-16 -top-10 h-72 w-72 rounded-full blur-3xl" style={{ background: "rgba(247,198,207,0.6)" }} />
      <div className="animate-float-blob-2 absolute -right-16 bottom-0 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(225,29,116,0.18)" }} />
      {/* Flower */}
      <svg className="animate-orbit-slow absolute -right-6 top-20 h-40 w-40 opacity-45" viewBox="0 0 100 100" fill="none">
        {Array.from({ length: 8 }).map((_, i) => (
          <ellipse key={i} cx="50" cy="30" rx="8" ry="16" fill="#f7c6cf" transform={`rotate(${i * 45} 50 50)`} />
        ))}
        <circle cx="50" cy="50" r="6" fill="#e11d74" />
      </svg>
      {/* Petals falling */}
      {[
        { left: "10%", d: "0s", dur: "9s" },
        { left: "35%", d: "3s", dur: "11s" },
        { left: "70%", d: "1s", dur: "10s" },
        { left: "88%", d: "5s", dur: "12s" },
      ].map((p, i) => (
        <span key={i} className="animate-confetti-fall absolute top-0 text-lg opacity-60" style={{ left: p.left, animationDelay: p.d, animationDuration: p.dur, color: "#e11d74" }}>❀</span>
      ))}
      {/* Droplet */}
      <svg className="animate-bob absolute left-8 bottom-28 h-12 w-12 opacity-50" viewBox="0 0 40 40" fill="#b76e79">
        <path d="M20 4 C 10 18 6 26 6 30 a 14 14 0 0 0 28 0 c 0-4-4-12-14-26z" />
      </svg>
    </div>
  );
}
