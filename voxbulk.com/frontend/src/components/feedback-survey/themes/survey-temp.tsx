import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-warm-gradient",
  ink: "#2d2926",
  sub: "rgba(45,41,38,0.65)",
  card: "#ffffff",
  border: "rgba(45,41,38,0.12)",
  accent: "#b8954a",
  accent2: "#d4b86a",
  cool: "#2d2926",
  gradientButton: "linear-gradient(135deg,#2d2926,#b8954a)",
  gradientProgress: "linear-gradient(90deg,#2d2926,#b8954a,#d4b86a)",
  selectedShadow: "0 8px 24px -8px rgba(45,41,38,0.35)",
  ringA: "rgba(184,149,74,0.55)",
  ringB: "rgba(45,41,38,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -right-20 top-0 h-64 w-64 rounded-full bg-gold/10 blur-3xl" />
      <div className="animate-float-blob-2 absolute -left-20 bottom-20 h-72 w-72 rounded-full bg-accent/25 blur-3xl" />
      <svg className="animate-orbit-slow absolute -left-16 top-16 h-56 w-56 text-foreground/10" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="80" stroke="currentColor" strokeDasharray="2 8" />
        <circle cx="100" cy="20" r="4" fill="currentColor" />
      </svg>
      <svg className="animate-orbit-rev absolute -right-24 bottom-8 h-72 w-72 text-gold/20" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="90" stroke="currentColor" strokeDasharray="1 10" />
        <circle cx="190" cy="100" r="5" fill="currentColor" />
      </svg>
      <div className="animate-drift-a absolute left-6 top-1/3 h-3 w-3 rounded-full bg-gold/60" />
      <div className="animate-drift-b absolute right-8 top-1/4 h-4 w-4 rotate-12 rounded-sm bg-foreground/40" />
      <div className="animate-drift-c absolute left-1/2 bottom-24 h-2.5 w-2.5 rounded-full bg-foreground/25" />
      <svg className="animate-squiggle absolute -left-10 top-1/2 h-10 w-40 text-foreground/10" viewBox="0 0 200 40" fill="none">
        <path d="M0 20 Q 20 0 40 20 T 80 20 T 120 20 T 160 20 T 200 20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <svg className="animate-squiggle absolute -right-10 bottom-40 h-10 w-40 text-gold/25" viewBox="0 0 200 40" fill="none" style={{ animationDelay: "1.5s" }}>
        <path d="M0 20 Q 20 40 40 20 T 80 20 T 120 20 T 160 20 T 200 20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}
