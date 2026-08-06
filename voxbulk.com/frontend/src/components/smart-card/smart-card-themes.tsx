import * as React from "react";

export type SmartCardThemeId =
  | "smartcard"
  | "smartcard1"
  | "smartcard2"
  | "smartcard3"
  | "smartcard4";

export const SMART_CARD_THEME_IDS: SmartCardThemeId[] = [
  "smartcard",
  "smartcard1",
  "smartcard2",
  "smartcard3",
  "smartcard4",
];

export type SmartCardThemeTokens = {
  id: SmartCardThemeId;
  label: string;
  emoji: string;
  bgClass: string;
  ink: string;
  sub: string;
  border: string;
  surface: string;
  accent: string;
  accent2: string;
  accent3: string;
  onAccent: string;
  radius: string;
  surveyNote: string;
};

const BASE: Record<SmartCardThemeId, Omit<SmartCardThemeTokens, "id">> = {
  smartcard: {
    label: "Sky Indigo",
    emoji: "🌌",
    bgClass: "bg-smartcard-gradient",
    ink: "#eaf2ff",
    sub: "rgba(234,242,255,0.62)",
    border: "rgba(234,242,255,0.14)",
    surface: "rgba(255,255,255,0.06)",
    accent: "#38bdf8",
    accent2: "#6366f1",
    accent3: "#7dd3fc",
    onAccent: "#06121f",
    radius: "28px",
    surveyNote: "60 seconds",
  },
  smartcard1: {
    label: "Emerald",
    emoji: "💚",
    bgClass: "bg-smartcard1-gradient",
    ink: "#ecfdf5",
    sub: "rgba(236,253,245,0.6)",
    border: "rgba(212,175,55,0.24)",
    surface: "rgba(255,255,255,0.06)",
    accent: "#34d399",
    accent2: "#d4af37",
    accent3: "#a3e635",
    onAccent: "#04231a",
    radius: "22px",
    surveyNote: "Under a minute",
  },
  smartcard2: {
    label: "Blush",
    emoji: "🌸",
    bgClass: "bg-smartcard2-gradient",
    ink: "#3b2135",
    sub: "rgba(59,33,53,0.6)",
    border: "rgba(59,33,53,0.12)",
    surface: "rgba(255,255,255,0.65)",
    accent: "#e0648f",
    accent2: "#a78bfa",
    accent3: "#f0a2b8",
    onAccent: "#ffffff",
    radius: "30px",
    surveyNote: "Takes 60 seconds",
  },
  smartcard3: {
    label: "Amber",
    emoji: "🧡",
    bgClass: "bg-smartcard3-gradient",
    ink: "#fdf3e3",
    sub: "rgba(253,243,227,0.62)",
    border: "rgba(253,243,227,0.16)",
    surface: "rgba(255,255,255,0.07)",
    accent: "#fbbf24",
    accent2: "#f97316",
    accent3: "#ef7c5a",
    onAccent: "#2a1405",
    radius: "20px",
    surveyNote: "Quick 1 min",
  },
  smartcard4: {
    label: "Neon",
    emoji: "⚡",
    bgClass: "bg-smartcard4-gradient",
    ink: "#eef0ff",
    sub: "rgba(238,240,255,0.6)",
    border: "rgba(238,240,255,0.14)",
    surface: "rgba(255,255,255,0.05)",
    accent: "#a3e635",
    accent2: "#c084fc",
    accent3: "#67e8f9",
    onAccent: "#12190a",
    radius: "16px",
    surveyNote: "60 second survey",
  },
};

export function normalizeSmartCardThemeId(raw: unknown): SmartCardThemeId {
  const v = String(raw || "").trim().toLowerCase();
  if ((SMART_CARD_THEME_IDS as string[]).includes(v)) return v as SmartCardThemeId;
  return "smartcard";
}

export function getSmartCardThemeTokens(id: unknown): SmartCardThemeTokens {
  const tid = normalizeSmartCardThemeId(id);
  return { id: tid, ...BASE[tid] };
}

export function smartCardThemeToFeedbackTheme(tokens: SmartCardThemeTokens) {
  return {
    bgClass: tokens.bgClass,
    ink: tokens.ink,
    sub: tokens.sub,
    card: tokens.surface,
    border: tokens.border,
    accent: tokens.accent,
    accent2: tokens.accent2,
    cool: tokens.accent3,
    onAccent: tokens.onAccent,
    gradientButton: `linear-gradient(135deg,${tokens.accent},${tokens.accent2})`,
    gradientProgress: `linear-gradient(90deg,${tokens.accent},${tokens.accent2})`,
    selectedShadow: `0 10px 28px -12px ${tokens.accent2}cc`,
    ringA: `${tokens.accent}73`,
    ringB: `${tokens.accent2}66`,
  };
}

export function SmartCardThemeArt({ themeId }: { themeId: SmartCardThemeId }) {
  if (themeId === "smartcard1") {
    return (
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-float-blob absolute -left-24 -top-24 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(16,185,129,0.14)" }} />
        <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(212,175,55,0.12)" }} />
        <svg className="animate-orbit-slow absolute -right-16 top-24 h-64 w-64 opacity-[0.15]" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="72" stroke="#d4af37" strokeWidth="0.7" strokeDasharray="2 10" />
          <circle cx="100" cy="28" r="3" fill="#34d399" />
        </svg>
        <svg className="animate-drift-slow absolute left-6 top-[20%] h-9 w-9 opacity-[0.14]" viewBox="0 0 24 24" fill="none" style={{ color: "#d4af37" }}>
          <path d="M12 3l2.4 5.2 5.6.7-4.1 3.9 1.1 5.6L12 15.7 6.9 18.4 8 12.8 3.9 8.9l5.6-.7L12 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
        <svg className="animate-drift-slower absolute right-10 bottom-[16%] h-8 w-8 opacity-[0.13]" viewBox="0 0 24 24" fill="none" style={{ color: "#34d399" }}>
          <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </div>
    );
  }
  if (themeId === "smartcard2") {
    return (
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-float-blob absolute -left-24 -top-28 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(244,114,182,0.22)" }} />
        <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(167,139,250,0.18)" }} />
        <svg className="animate-orbit-rev absolute -left-16 bottom-16 h-56 w-56 opacity-[0.22]" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="80" stroke="#f472b6" strokeWidth="0.8" strokeDasharray="3 9" />
          <circle cx="180" cy="100" r="3" fill="#a78bfa" />
        </svg>
        <svg className="animate-drift-slow absolute right-8 top-[18%] h-10 w-10 opacity-[0.2]" viewBox="0 0 24 24" fill="none" style={{ color: "#f472b6" }}>
          <path d="M12 20s-7-4.6-7-9.3A3.9 3.9 0 0112 8.6a3.9 3.9 0 017 2.1c0 4.7-7 9.3-7 9.3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
        <svg className="animate-drift-slower absolute left-8 top-[52%] h-8 w-8 opacity-[0.18]" viewBox="0 0 24 24" fill="none" style={{ color: "#a78bfa" }}>
          <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.3" />
          <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2 2M16.4 16.4l2 2M18.4 5.6l-2 2M7.6 16.4l-2 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </div>
    );
  }
  if (themeId === "smartcard3") {
    return (
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-float-blob absolute -left-24 -top-24 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(251,146,60,0.16)" }} />
        <div className="animate-float-blob-2 absolute -right-24 bottom-4 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(239,68,68,0.12)" }} />
        <svg className="absolute inset-0 h-full w-full opacity-[0.05]" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="sc3-grid" width="44" height="44" patternUnits="userSpaceOnUse">
              <path d="M 44 0 L 0 0 0 44" fill="none" stroke="#fde9c8" strokeWidth="0.6" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#sc3-grid)" />
        </svg>
        <svg className="animate-drift-slow absolute left-7 top-[22%] h-9 w-9 opacity-[0.15]" viewBox="0 0 24 24" fill="none" style={{ color: "#fbbf24" }}>
          <path d="M7 3v7a3 3 0 006 0V3M10 13v8M17 3c-1.6 1.4-2 3.2-2 5.5V13h3V3z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
        <svg className="animate-drift-slower absolute right-9 top-[45%] h-9 w-9 opacity-[0.14]" viewBox="0 0 24 24" fill="none" style={{ color: "#f97316" }}>
          <path d="M4 15h16a8 8 0 00-16 0zM3 18h18" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
        <svg className="animate-orbit-slow absolute -right-14 bottom-10 h-56 w-56 opacity-[0.14]" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="74" stroke="#fbbf24" strokeWidth="0.7" strokeDasharray="4 10" />
          <circle cx="100" cy="26" r="3" fill="#f97316" />
        </svg>
      </div>
    );
  }
  if (themeId === "smartcard4") {
    return (
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-float-blob absolute -right-24 -top-24 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(163,230,53,0.12)" }} />
        <div className="animate-float-blob-2 absolute -left-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(168,85,247,0.16)" }} />
        <svg className="absolute inset-0 h-full w-full opacity-[0.06]" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="sc4-dots" width="26" height="26" patternUnits="userSpaceOnUse">
              <circle cx="1.4" cy="1.4" r="1.1" fill="#e9e5ff" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#sc4-dots)" />
        </svg>
        <svg className="animate-drift-slow absolute left-6 top-[18%] h-9 w-9 opacity-[0.16]" viewBox="0 0 24 24" fill="none" style={{ color: "#a3e635" }}>
          <path d="M4 7h6v6H4zM14 11h6v6h-6zM10 10h4M7 13v4h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
        <svg className="animate-drift-slower absolute right-8 top-[40%] h-8 w-8 opacity-[0.15]" viewBox="0 0 24 24" fill="none" style={{ color: "#c084fc" }}>
          <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
        <svg className="animate-orbit-rev absolute -left-20 top-1/3 h-60 w-60 opacity-[0.14]" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="78" stroke="#a3e635" strokeWidth="0.7" strokeDasharray="2 12" />
          <circle cx="178" cy="100" r="3" fill="#c084fc" />
        </svg>
      </div>
    );
  }
  // default sky/indigo
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="animate-float-blob absolute -left-28 -top-24 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(99,102,241,0.16)" }} />
      <div className="animate-float-blob-2 absolute -right-24 bottom-0 h-96 w-96 rounded-full blur-3xl" style={{ background: "rgba(56,189,248,0.12)" }} />
      <svg className="absolute inset-0 h-full w-full opacity-[0.05]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="sc-grid" width="38" height="38" patternUnits="userSpaceOnUse">
            <path d="M 38 0 L 0 0 0 38" fill="none" stroke="#eaf2ff" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#sc-grid)" />
      </svg>
      <svg className="animate-drift-slow absolute left-6 top-[16%] h-9 w-9 opacity-[0.13]" viewBox="0 0 24 24" fill="none" style={{ color: "#7dd3fc" }}>
        <path d="M3 17l5-6 4 3 5-7 4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <svg className="animate-drift-slower absolute right-8 top-[38%] h-8 w-8 opacity-[0.12]" viewBox="0 0 24 24" fill="none" style={{ color: "#a78bfa" }}>
        <rect x="3" y="7" width="18" height="12" rx="2.5" stroke="currentColor" strokeWidth="1.3" />
        <path d="M9 7V5.5A1.5 1.5 0 0110.5 4h3A1.5 1.5 0 0115 5.5V7" stroke="currentColor" strokeWidth="1.3" />
      </svg>
      <svg className="animate-orbit-slow absolute -right-16 top-20 h-64 w-64 opacity-[0.16]" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="70" stroke="#38bdf8" strokeWidth="0.7" strokeDasharray="4 8" />
        <circle cx="100" cy="30" r="3.5" fill="#a78bfa" />
      </svg>
      <svg className="animate-orbit-rev absolute -left-20 bottom-12 h-56 w-56 opacity-[0.14]" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="80" stroke="#a78bfa" strokeWidth="0.7" strokeDasharray="3 10" />
        <circle cx="180" cy="100" r="3" fill="#38bdf8" />
      </svg>
    </div>
  );
}
