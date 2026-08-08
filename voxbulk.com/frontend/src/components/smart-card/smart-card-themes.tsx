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
    surveyNote: "Takes about a minute",
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

/** Lightweight static backdrop — no animated blobs/SVGs (keeps card load fast). */
export function SmartCardThemeArt({ themeId }: { themeId: SmartCardThemeId }) {
  const tones: Record<string, [string, string]> = {
    smartcard1: ["rgba(16,185,129,0.12)", "rgba(212,175,55,0.10)"],
    smartcard2: ["rgba(244,114,182,0.14)", "rgba(167,139,250,0.12)"],
    smartcard3: ["rgba(251,146,60,0.12)", "rgba(239,68,68,0.08)"],
    smartcard4: ["rgba(163,230,53,0.10)", "rgba(168,85,247,0.12)"],
    smartcard: ["rgba(99,102,241,0.12)", "rgba(56,189,248,0.10)"],
  };
  const [a, b] = tones[themeId] || tones.smartcard;
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute -left-20 -top-20 h-64 w-64 rounded-full blur-3xl" style={{ background: a }} />
      <div className="absolute -bottom-16 -right-16 h-64 w-64 rounded-full blur-3xl" style={{ background: b }} />
    </div>
  );
}
