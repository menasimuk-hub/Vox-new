import type { Theme } from "../types";

/** Throwaway demo theme for الانتخابات التشريعية 2026 — Palestine flag motif. */
export const theme: Theme = {
  bgClass: "bg-elections-gradient",
  ink: "#f7f4ef",
  sub: "rgba(247,244,239,0.68)",
  card: "rgba(255,255,255,0.08)",
  border: "rgba(247,244,239,0.18)",
  accent: "#ce1126",
  accent2: "#007a3d",
  cool: "#000000",
  gradientButton: "linear-gradient(135deg,#ce1126,#007a3d)",
  gradientProgress: "linear-gradient(90deg,#000000,#ffffff,#007a3d,#ce1126)",
  selectedShadow: "0 8px 24px -6px rgba(206,17,38,0.55)",
  ringA: "rgba(206,17,38,0.5)",
  ringB: "rgba(0,122,61,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(0,122,61,0.28)" }}
      />
      <div
        className="animate-float-blob-2 absolute -right-20 bottom-0 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(206,17,38,0.22)" }}
      />
      <svg className="absolute inset-0 h-full w-full opacity-[0.18]" viewBox="0 0 120 80" preserveAspectRatio="none">
        <rect width="120" height="26.67" fill="#000" />
        <rect y="26.67" width="120" height="26.67" fill="#fff" />
        <rect y="53.33" width="120" height="26.67" fill="#007a3d" />
        <polygon points="0,0 52,40 0,80" fill="#ce1126" />
      </svg>
    </div>
  );
}
