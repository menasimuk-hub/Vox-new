import type { Theme } from "../types";

export const theme: Theme = {
  bgClass: "bg-easter-gradient",
  ink: "#3f2b52",
  sub: "rgba(63,43,82,0.62)",
  card: "rgba(255,255,255,0.78)",
  border: "rgba(63,43,82,0.10)",
  accent: "#f472b6",
  accent2: "#86efac",
  cool: "#facc15",
  gradientButton: "linear-gradient(135deg,#f472b6,#facc15,#86efac)",
  gradientProgress: "linear-gradient(90deg,#86efac,#facc15,#f472b6)",
  selectedShadow: "0 8px 24px -6px rgba(244,114,182,0.45)",
  ringA: "rgba(244,114,182,0.5)",
  ringB: "rgba(134,239,172,0.45)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-24 -top-16 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(244,114,182,0.35)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(134,239,172,0.30)" }} />
      {/* Easter eggs */}
      {[
        { l: "10%", b: "18%", c1: "#f472b6", c2: "#86efac", d: "0s" },
        { l: "42%", b: "10%", c1: "#facc15", c2: "#f472b6", d: "0.6s" },
        { l: "72%", b: "22%", c1: "#86efac", c2: "#facc15", d: "1.2s" },
      ].map((e, i) => (
        <svg key={i} className="animate-bob absolute h-14 w-11 opacity-85" viewBox="0 0 40 55" style={{ left: e.l, bottom: e.b, animationDelay: e.d }}>
          <ellipse cx="20" cy="30" rx="18" ry="24" fill={e.c1} />
          <path d="M2 30 q9 -6 18 0 t18 0" stroke={e.c2} strokeWidth="3" fill="none" />
          <circle cx="14" cy="18" r="3" fill={e.c2} />
          <circle cx="26" cy="42" r="3" fill={e.c2} />
        </svg>
      ))}
      {/* Bunny */}
      <svg className="animate-sway absolute right-4 top-16 h-24 w-20 opacity-70" viewBox="0 0 60 80" fill="#fff" stroke="#3f2b52" strokeWidth="1.2" style={{ transformOrigin: "50% 100%" }}>
        <ellipse cx="20" cy="20" rx="6" ry="16" />
        <ellipse cx="40" cy="20" rx="6" ry="16" />
        <circle cx="30" cy="50" r="18" />
        <circle cx="24" cy="46" r="2" fill="#3f2b52" />
        <circle cx="36" cy="46" r="2" fill="#3f2b52" />
        <path d="M28 54 q2 3 4 0" fill="none" />
      </svg>
      {/* Flowers */}
      {["18%", "50%", "82%"].map((l, i) => (
        <svg key={i} className="animate-twinkle absolute" style={{ left: l, top: `${25 + i * 8}%`, animationDelay: `${i * 0.5}s` }} viewBox="0 0 20 20" width="18" height="18">
          {Array.from({ length: 5 }).map((_, k) => (
            <circle key={k} cx={10 + Math.cos(k * 1.256) * 5} cy={10 + Math.sin(k * 1.256) * 5} r="3" fill="#f472b6" opacity="0.7" />
          ))}
          <circle cx="10" cy="10" r="2" fill="#facc15" />
        </svg>
      ))}
    </div>
  );
}
