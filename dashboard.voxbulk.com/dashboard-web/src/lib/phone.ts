/** ISO region → international dial prefix (E.164). */
const REGION_DIAL: Record<string, string> = {
  GB: "+44",
  UK: "+44",
  US: "+1",
  CA: "+1",
  IE: "+353",
  AU: "+61",
  DE: "+49",
  FR: "+33",
  ES: "+34",
  IT: "+39",
  NL: "+31",
  AE: "+971",
  SA: "+966",
  IN: "+91",
};

const COUNTRY_NAME_REGION: Record<string, string> = {
  "united kingdom": "GB",
  uk: "GB",
  britain: "GB",
  "great britain": "GB",
  england: "GB",
  "united states": "US",
  usa: "US",
  america: "US",
  canada: "CA",
  ireland: "IE",
  australia: "AU",
  germany: "DE",
  france: "FR",
  spain: "ES",
  italy: "IT",
  netherlands: "NL",
  "united arab emirates": "AE",
  uae: "AE",
  dubai: "AE",
  "saudi arabia": "SA",
  india: "IN",
};

/** Resolve ISO region from org country / country_code. Defaults to GB. */
export function orgDialRegion(country?: string | null, countryCode?: string | null): string {
  const code = String(countryCode || "")
    .trim()
    .toUpperCase();
  if (code.length === 2 && REGION_DIAL[code]) return code === "UK" ? "GB" : code;
  if (code === "UK") return "GB";
  const name = String(country || "")
    .trim()
    .toLowerCase();
  if (!name) return "GB";
  if (COUNTRY_NAME_REGION[name]) return COUNTRY_NAME_REGION[name]!;
  for (const [key, region] of Object.entries(COUNTRY_NAME_REGION)) {
    if (name.includes(key)) return region;
  }
  return "GB";
}

export function dialPrefixForOrg(country?: string | null, countryCode?: string | null): string {
  const region = orgDialRegion(country, countryCode);
  return REGION_DIAL[region] || "+44";
}

/**
 * If the user typed a local number without a country code, prepend the org dial prefix.
 * Leaves numbers that already start with + / 00 alone. Empty input stays empty.
 */
export function ensurePhoneCountryCode(
  raw: string | null | undefined,
  dialPrefix = "+44",
): string {
  const value = String(raw || "").trim();
  if (!value) return "";
  if (value.startsWith("+")) return value;
  if (/^00\d/.test(value.replace(/\s/g, ""))) {
    return `+${value.replace(/\s/g, "").slice(2)}`;
  }
  const dial = String(dialPrefix || "+44").trim() || "+44";
  const dialDigits = dial.replace(/\D/g, "");
  const digits = value.replace(/\D/g, "");
  if (!digits) return value;
  if (digits.startsWith(dialDigits)) return `+${digits}`;
  // National trunk zero (e.g. UK 07… → +447…)
  if (digits.startsWith("0")) return `+${dialDigits}${digits.slice(1)}`;
  return `+${dialDigits}${digits}`;
}
