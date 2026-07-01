export type InterviewRegionMeta = {
  code: string;
  label: string;
  flagEmoji: string;
  englishLabel: string;
};

export const INTERVIEW_REGIONS: Record<string, InterviewRegionMeta> = {
  GB: { code: "GB", label: "United Kingdom", flagEmoji: "🇬🇧", englishLabel: "British English" },
  SC: { code: "SC", label: "Scotland", flagEmoji: "🏴", englishLabel: "Scottish English" },
  IE: { code: "IE", label: "Ireland", flagEmoji: "🇮🇪", englishLabel: "Irish English" },
  US: { code: "US", label: "United States", flagEmoji: "🇺🇸", englishLabel: "US English" },
  CA: { code: "CA", label: "Canada", flagEmoji: "🇨🇦", englishLabel: "Canadian English" },
  AU: { code: "AU", label: "Australia", flagEmoji: "🇦🇺", englishLabel: "Australian English" },
};

export const ARABIC_REGION_META: Record<string, InterviewRegionMeta> = {
  SA: { code: "SA", label: "Saudi Gulf", flagEmoji: "🇸🇦", englishLabel: "Arabic (SA)" },
  EG: { code: "EG", label: "Egyptian Arabic", flagEmoji: "🇪🇬", englishLabel: "Arabic (EG)" },
};

export const ENGLISH_REGION_ORDER = ["GB", "SC", "IE", "US", "CA", "AU"] as const;
export const ARABIC_REGION_ORDER = ["SA", "EG"] as const;

export function genderLabel(gender?: string | null): string {
  const g = String(gender || "").toLowerCase();
  if (g === "male") return "Male";
  if (g === "female") return "Female";
  return "";
}

export function isArabicRegionCode(code: string): boolean {
  return code === "SA" || code === "EG" || code === "AR";
}

export function regionMenuLabel(code: string): string {
  if (code === "SA" || code === "EG") {
    return ARABIC_REGION_META[code]?.englishLabel || `Arabic (${code})`;
  }
  const meta = INTERVIEW_REGIONS[code];
  return meta ? `English (${code})` : code;
}

export function regionFlagEmoji(code: string): string {
  return ARABIC_REGION_META[code]?.flagEmoji || INTERVIEW_REGIONS[code]?.flagEmoji || "🏳️";
}

/** ISO flag images (flagcdn) — reliable on Windows; emoji flags often show as "IE", "GB" letters. */
const FLAGCDN_BY_REGION: Record<string, string> = {
  GB: "https://flagcdn.com/w40/gb.png",
  SC: "https://flagcdn.com/w40/gb-sct.png",
  IE: "https://flagcdn.com/w40/ie.png",
  US: "https://flagcdn.com/w40/us.png",
  CA: "https://flagcdn.com/w40/ca.png",
  AU: "https://flagcdn.com/w40/au.png",
  SA: "https://flagcdn.com/w40/sa.png",
  EG: "https://flagcdn.com/w40/eg.png",
};

export function regionFlagImageUrl(code: string): string {
  const key = String(code || "GB").trim().toUpperCase();
  return FLAGCDN_BY_REGION[key] || FLAGCDN_BY_REGION.GB;
}
