import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-restaurant-gradient",
  ink: "#3a1f0f",
  sub: "rgba(58,31,15,0.65)",
  card: "rgba(255,251,244,0.85)",
  border: "rgba(58,31,15,0.12)",
  accent: "#c2410c",
  accent2: "#f59e0b",
  cool: "#65a30d",
  gradientButton: "linear-gradient(135deg,#c2410c,#f59e0b)",
  gradientProgress: "linear-gradient(90deg,#c2410c,#f59e0b,#65a30d)",
  selectedShadow: "0 8px 24px -8px rgba(194,65,12,0.55)",
  ringA: "rgba(245,158,11,0.55)",
  ringB: "rgba(194,65,12,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-16 -top-10 h-72 w-72 rounded-full blur-3xl" style={{ background: "rgba(245,158,11,0.35)" }} />
      <div className="animate-float-blob-2 absolute -right-16 bottom-0 h-72 w-72 rounded-full blur-3xl" style={{ background: "rgba(101,163,13,0.25)" }} />
      {/* Coffee cup + steam */}
      <div className="absolute right-6 top-24 opacity-70">
        <div className="relative">
          <span className="animate-steam absolute -top-2 left-3 block h-6 w-1.5 rounded-full bg-white/70" style={{ animationDelay: "0s" }} />
          <span className="animate-steam absolute -top-2 left-6 block h-6 w-1.5 rounded-full bg-white/70" style={{ animationDelay: "1s" }} />
          <span className="animate-steam absolute -top-2 left-9 block h-6 w-1.5 rounded-full bg-white/70" style={{ animationDelay: "2s" }} />
          <svg viewBox="0 0 40 40" className="h-14 w-14" fill="none" stroke="#3a1f0f" strokeWidth="2" strokeLinecap="round">
            <path d="M6 14h22v10a8 8 0 0 1-8 8h-6a8 8 0 0 1-8-8V14z" fill="#c2410c" fillOpacity="0.85" />
            <path d="M28 18h4a4 4 0 0 1 0 8h-4" />
          </svg>
        </div>
      </div>
      {/* Croissant */}
      <svg className="animate-bob absolute left-4 bottom-24 h-16 w-16 opacity-60" viewBox="0 0 40 40" fill="#f59e0b" stroke="#3a1f0f" strokeWidth="1.5">
        <path d="M6 28c4-14 24-14 28 0-4-2-8-2-14 0-6-2-10-2-14 0z" />
      </svg>
      {/* Fork */}
      <svg className="animate-drift-c absolute left-1/3 top-1/2 h-10 w-10 opacity-40" viewBox="0 0 24 24" fill="none" stroke="#c2410c" strokeWidth="2" strokeLinecap="round">
        <path d="M8 2v8a4 4 0 0 0 8 0V2M12 10v12" />
      </svg>
    </div>
  );
}
