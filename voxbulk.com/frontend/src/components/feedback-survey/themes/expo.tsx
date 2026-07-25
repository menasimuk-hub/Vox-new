import type { Theme } from "../types";

/** Exact port of feedback-flow-main `/expo` theme tokens + Art. */
export const theme: Theme = {
  bgClass: "bg-expo-gradient",
  ink: "#eaf2ff",
  sub: "rgba(234,242,255,0.62)",
  card: "rgba(255,255,255,0.06)",
  border: "rgba(234,242,255,0.16)",
  accent: "#38bdf8",
  accent2: "#a78bfa",
  cool: "#0ea5e9",
  gradientButton: "linear-gradient(135deg,#38bdf8,#6366f1)",
  gradientProgress: "linear-gradient(90deg,#38bdf8,#6366f1,#a78bfa)",
  selectedShadow: "0 8px 24px -8px rgba(56,189,248,0.55)",
  ringA: "rgba(56,189,248,0.5)",
  ringB: "rgba(99,102,241,0.4)",
};

export function Art() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="animate-float-blob absolute -left-24 -top-20 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(56,189,248,0.20)" }}
      />
      <div
        className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl"
        style={{ background: "rgba(167,139,250,0.16)" }}
      />
      <svg className="absolute inset-0 h-full w-full opacity-[0.07]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="expo-grid" width="34" height="34" patternUnits="userSpaceOnUse">
            <path d="M 34 0 L 0 0 0 34" fill="none" stroke="#eaf2ff" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#expo-grid)" />
      </svg>
      <svg className="absolute right-4 top-16 h-40 w-40 opacity-60" viewBox="0 0 120 120" fill="none">
        <g stroke="#38bdf8" strokeWidth="0.6" opacity="0.7">
          <line x1="20" y1="30" x2="70" y2="20" />
          <line x1="70" y1="20" x2="100" y2="55" />
          <line x1="100" y1="55" x2="60" y2="85" />
          <line x1="60" y1="85" x2="20" y2="70" />
          <line x1="20" y1="70" x2="20" y2="30" />
          <line x1="70" y1="20" x2="60" y2="85" />
        </g>
        {[
          [20, 30],
          [70, 20],
          [100, 55],
          [60, 85],
          [20, 70],
        ].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="3" fill="#a78bfa">
            <animate attributeName="r" values="3;4.5;3" dur="3s" begin={`${i * 0.4}s`} repeatCount="indefinite" />
          </circle>
        ))}
      </svg>
      <svg className="absolute left-5 bottom-24 h-24 w-28 opacity-60" viewBox="0 0 100 80">
        {[40, 55, 30, 65, 48].map((h, i) => (
          <rect
            key={i}
            x={i * 18 + 4}
            y={80 - h}
            width="12"
            height={h}
            rx="2"
            fill="#38bdf8"
            opacity={0.55 + i * 0.08}
          >
            <animate
              attributeName="height"
              values={`${h};${h - 8};${h}`}
              dur="4s"
              begin={`${i * 0.3}s`}
              repeatCount="indefinite"
            />
            <animate
              attributeName="y"
              values={`${80 - h};${80 - h + 8};${80 - h}`}
              dur="4s"
              begin={`${i * 0.3}s`}
              repeatCount="indefinite"
            />
          </rect>
        ))}
      </svg>
      {[
        { top: "26%", left: "10%", d: "0s", c: "#38bdf8" },
        { top: "60%", right: "14%", d: "1.2s", c: "#a78bfa" },
        { top: "78%", left: "40%", d: "2.1s", c: "#6366f1" },
      ].map((p, i) => (
        <span
          key={i}
          className="animate-twinkle absolute text-[10px]"
          style={{ ...p, animationDelay: p.d, color: p.c }}
        >
          ◆
        </span>
      ))}
    </div>
  );
}
