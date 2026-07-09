import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-retail-gradient",
  ink: "#3b0764",
  sub: "rgba(59,7,100,0.65)",
  card: "rgba(255,255,255,0.82)",
  border: "rgba(59,7,100,0.12)",
  accent: "#d946ef",
  accent2: "#22d3ee",
  cool: "#7c3aed",
  gradientButton: "linear-gradient(135deg,#d946ef,#7c3aed)",
  gradientProgress: "linear-gradient(90deg,#d946ef,#7c3aed,#22d3ee)",
  selectedShadow: "0 8px 24px -8px rgba(217,70,239,0.55)",
  ringA: "rgba(217,70,239,0.5)",
  ringB: "rgba(124,58,237,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-20 -top-16 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(217,70,239,0.28)" }} />
      <div className="animate-float-blob-2 absolute -right-20 bottom-0 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(34,211,238,0.25)" }} />
      {/* Shopping bag */}
      <svg className="animate-bob absolute right-6 top-24 h-16 w-16 opacity-60" viewBox="0 0 40 40" fill="none" stroke="#7c3aed" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M8 14h24l-2 22H10z" fill="#d946ef" fillOpacity="0.6" />
        <path d="M14 14a6 6 0 0 1 12 0" />
      </svg>
      {/* Tag */}
      <svg className="animate-drift-a absolute left-6 top-40 h-12 w-12 opacity-55" viewBox="0 0 40 40" fill="none" stroke="#7c3aed" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 6h14l14 14-14 14L6 20z" fill="#22d3ee" fillOpacity="0.4" />
        <circle cx="13" cy="13" r="2" fill="#7c3aed" />
      </svg>
      {/* Sparkles */}
      {[
        { top: "18%", left: "40%", d: "0s" },
        { top: "60%", left: "12%", d: "0.6s" },
        { top: "75%", right: "18%", d: "1.2s" },
        { top: "35%", right: "25%", d: "1.8s" },
      ].map((p, i) => (
        <span key={i} className="animate-twinkle absolute text-lg" style={{ ...p, animationDelay: p.d, color: "#d946ef" }}>✦</span>
      ))}
    </div>
  );
}
