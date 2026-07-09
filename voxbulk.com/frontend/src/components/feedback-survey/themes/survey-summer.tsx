import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-summer-gradient",
  ink: "#0b3a4a",
  sub: "rgba(11,58,74,0.65)",
  card: "rgba(255,255,255,0.75)",
  border: "rgba(11,58,74,0.12)",
  accent: "#ff7a59",
  accent2: "#ffd166",
  cool: "#2ec4b6",
  gradientButton: "linear-gradient(135deg,#ff7a59,#ffd166)",
  gradientProgress: "linear-gradient(90deg,#ff7a59,#ffd166,#2ec4b6)",
  selectedShadow: "0 8px 24px -8px rgba(255,122,89,0.45)",
  ringA: "rgba(255,122,89,0.55)",
  ringB: "rgba(255,209,102,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute -right-16 -top-16 h-64 w-64 rounded-full opacity-70"
        style={{ background: "radial-gradient(circle, #ffd166 0%, #ff7a59 55%, transparent 70%)" }}
      />
      <svg className="animate-sun-spin absolute -right-16 -top-16 h-64 w-64 opacity-40" viewBox="0 0 200 200" fill="none">
        {Array.from({ length: 12 }).map((_, i) => (
          <line
            key={i}
            x1="100"
            y1="20"
            x2="100"
            y2="0"
            stroke="#ff7a59"
            strokeWidth="3"
            strokeLinecap="round"
            transform={`rotate(${i * 30} 100 100)`}
          />
        ))}
      </svg>
      <div
        className="animate-float-blob-2 absolute -left-20 bottom-0 h-72 w-72 rounded-full blur-3xl"
        style={{ background: "rgba(46,196,182,0.35)" }}
      />
      <svg className="animate-sway absolute -left-6 top-24 h-28 w-28 origin-bottom opacity-60" viewBox="0 0 100 100" fill="none">
        <path
          d="M50 100 C 45 60 40 30 20 15 M50 100 C 55 60 60 30 80 15 M50 100 C 30 70 15 55 5 55 M50 100 C 70 70 85 55 95 55"
          stroke="#2a7f62"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      <div className="animate-drift-a absolute left-8 top-1/2 h-3 w-3 rounded-full" style={{ background: theme.accent }} />
      <div className="animate-drift-b absolute right-10 top-1/3 h-4 w-4 rotate-12 rounded-sm" style={{ background: theme.cool }} />
      <div className="animate-drift-c absolute left-1/3 bottom-28 h-2.5 w-2.5 rounded-full" style={{ background: theme.accent2 }} />
      <svg className="animate-squiggle absolute -right-10 bottom-32 h-10 w-48 opacity-40" viewBox="0 0 200 40" fill="none">
        <path d="M0 20 Q 20 0 40 20 T 80 20 T 120 20 T 160 20 T 200 20" stroke={theme.cool} strokeWidth="2.5" strokeLinecap="round" />
      </svg>
    </div>
  );
}
