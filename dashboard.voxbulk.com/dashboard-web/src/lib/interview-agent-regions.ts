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

export const ENGLISH_REGION_ORDER = ["GB", "SC", "IE", "US", "CA", "AU"] as const;

export function genderLabel(gender?: string | null): string {
  const g = String(gender || "").toLowerCase();
  if (g === "male") return "Male";
  if (g === "female") return "Female";
  return "";
}
