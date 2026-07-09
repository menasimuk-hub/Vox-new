import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-valentines-gradient",
  ink: "#5b0f26",
  sub: "rgba(91,15,38,0.62)",
  card: "rgba(255,251,252,0.82)",
  border: "rgba(91,15,38,0.10)",
  accent: "#e11d48",
  accent2: "#f472b6",
  cool: "#be185d",
  gradientButton: "linear-gradient(135deg,#e11d48,#f472b6)",
  gradientProgress: "linear-gradient(90deg,#f472b6,#e11d48)",
  selectedShadow: "0 8px 24px -6px rgba(225,29,72,0.5)",
  ringA: "rgba(244,114,182,0.55)",
  ringB: "rgba(225,29,72,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(244,114,182,0.45)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(225,29,72,0.20)" }} />
      {/* Floating hearts */}
      {[
        { l: "10%", d: "0s", dur: "10s", s: "18px" },
        { l: "28%", d: "2s", dur: "12s", s: "14px" },
        { l: "52%", d: "1s", dur: "11s", s: "22px" },
        { l: "74%", d: "3s", dur: "13s", s: "16px" },
        { l: "90%", d: "4s", dur: "10s", s: "12px" },
      ].map((h, i) => (
        <span key={i} className="animate-confetti-fall absolute top-0" style={{
          left: h.l, color: "#e11d48", fontSize: h.s,
          animationDelay: h.d, animationDuration: h.dur, transform: "rotate(0deg)",
        }}>♥</span>
      ))}
      {/* Big heart */}
      <svg className="animate-glow-pulse absolute -right-4 top-16 h-32 w-32 opacity-40" viewBox="0 0 32 29" fill="#e11d48">
        <path d="M23.6 0c-2.6 0-5 1.4-6.6 3.5C15.4 1.4 13 0 10.4 0 4.7 0 0 4.7 0 10.4c0 10.4 16 18.6 16 18.6s16-8.2 16-18.6C32 4.7 27.3 0 23.6 0z" />
      </svg>
      {/* Petals */}
      {["18%", "48%", "82%"].map((l, i) => (
        <span key={i} className="animate-twinkle absolute" style={{ left: l, top: `${55 + i * 5}%`, color: "#f472b6", animationDelay: `${i * 0.5}s` }}>❀</span>
      ))}
    </div>
  );
}
