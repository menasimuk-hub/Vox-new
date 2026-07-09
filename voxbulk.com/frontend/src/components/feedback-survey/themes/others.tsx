import type { Theme, Copy } from "../types";

export const theme: Theme = {
  bgClass: "bg-others-gradient",
  ink: "#0f172a",
  sub: "rgba(15,23,42,0.62)",
  card: "rgba(255,255,255,0.80)",
  border: "rgba(15,23,42,0.10)",
  accent: "#0ea5e9",
  accent2: "#14b8a6",
  cool: "#0f172a",
  gradientButton: "linear-gradient(135deg,#0ea5e9,#14b8a6)",
  gradientProgress: "linear-gradient(90deg,#0ea5e9,#14b8a6)",
  selectedShadow: "0 8px 24px -8px rgba(14,165,233,0.45)",
  ringA: "rgba(14,165,233,0.45)",
  ringB: "rgba(20,184,166,0.35)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-20 -top-16 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(14,165,233,0.18)" }} />
      <div className="animate-float-blob-2 absolute -right-20 bottom-0 h-80 w-80 rounded-full blur-3xl" style={{ background: "rgba(20,184,166,0.18)" }} />
      {/* Dotted grid */}
      <svg className="absolute inset-0 h-full w-full opacity-[0.15]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="dots" x="0" y="0" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="1.5" cy="1.5" r="1.2" fill="#0f172a" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#dots)" />
      </svg>
      {/* Floating shapes */}
      <div className="animate-drift-a absolute left-8 top-1/3 h-3 w-3 rounded-full" style={{ background: "#0ea5e9" }} />
      <div className="animate-drift-b absolute right-10 top-1/4 h-4 w-4 rotate-12 rounded-sm" style={{ background: "#14b8a6" }} />
      <div className="animate-drift-c absolute left-1/3 bottom-24 h-3 w-3 rounded-full" style={{ background: "#0f172a", opacity: 0.4 }} />
      {/* Ring */}
      <svg className="animate-orbit-slow absolute -right-6 top-24 h-36 w-36 opacity-30" viewBox="0 0 100 100" fill="none" stroke="#0ea5e9" strokeWidth="1" strokeDasharray="4 4">
        <circle cx="50" cy="50" r="40" />
      </svg>
    </div>
  );
}
