/**
 * Smart Card theme catalog for dashboard picker (local swatches — do not rely on public CSS).
 */

export type SmartCardThemeId =
  | "smartcard"
  | "smartcard1"
  | "smartcard2"
  | "smartcard3"
  | "smartcard4";

export type SmartCardThemeCatalogItem = {
  id: SmartCardThemeId;
  label: string;
  emoji: string;
  desc: string;
  /** Tailwind-ish gradient classes for mini preview swatches */
  swatch: string;
  ink: string;
  accent: string;
};

export const SMART_CARD_THEME_CATALOG: SmartCardThemeCatalogItem[] = [
  {
    id: "smartcard",
    label: "Sky Indigo",
    emoji: "🌌",
    desc: "Dark cool glass — default",
    swatch: "from-sky-400 via-indigo-500 to-slate-900",
    ink: "#eaf2ff",
    accent: "#38bdf8",
  },
  {
    id: "smartcard1",
    label: "Emerald",
    emoji: "💚",
    desc: "Emerald & gold professional",
    swatch: "from-emerald-400 via-amber-400 to-emerald-950",
    ink: "#ecfdf5",
    accent: "#34d399",
  },
  {
    id: "smartcard2",
    label: "Blush",
    emoji: "🌸",
    desc: "Light rose & lilac",
    swatch: "from-rose-200 via-fuchsia-200 to-violet-200",
    ink: "#3b2135",
    accent: "#e0648f",
  },
  {
    id: "smartcard3",
    label: "Amber",
    emoji: "🧡",
    desc: "Warm hospitality charcoal",
    swatch: "from-amber-400 via-orange-500 to-stone-900",
    ink: "#fdf3e3",
    accent: "#fbbf24",
  },
  {
    id: "smartcard4",
    label: "Neon",
    emoji: "⚡",
    desc: "Lime & violet tech",
    swatch: "from-lime-400 via-fuchsia-400 to-violet-950",
    ink: "#eef0ff",
    accent: "#a3e635",
  },
];

export function normalizeSmartCardThemeId(raw: unknown): SmartCardThemeId {
  const v = String(raw || "").trim().toLowerCase();
  if (SMART_CARD_THEME_CATALOG.some((t) => t.id === v)) return v as SmartCardThemeId;
  return "smartcard";
}

/** Public site origin for theme preview URLs. */
export function smartCardPublicOrigin(): string {
  const fromEnv = (import.meta as any).env?.VITE_PUBLIC_SITE_URL as string | undefined;
  return (fromEnv || "https://voxbulk.com").replace(/\/$/, "");
}

export function smartCardThemePreviewUrl(
  themeId: SmartCardThemeId | string,
  opts?: { company?: string; name?: string; job?: string },
): string {
  const id = normalizeSmartCardThemeId(themeId);
  const base = `${smartCardPublicOrigin()}/smartcard/preview/${id}`;
  const params = new URLSearchParams();
  if (opts?.company?.trim()) params.set("company", opts.company.trim());
  if (opts?.name?.trim()) params.set("name", opts.name.trim());
  if (opts?.job?.trim()) params.set("job", opts.job.trim());
  const q = params.toString();
  return q ? `${base}?${q}` : base;
}

export function smartCardThemePreviewQrUrl(
  themeId: SmartCardThemeId | string,
  opts?: { company?: string; name?: string; job?: string; size?: number },
): string {
  const url = smartCardThemePreviewUrl(themeId, opts);
  const size = opts?.size ?? 120;
  return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(url)}`;
}
