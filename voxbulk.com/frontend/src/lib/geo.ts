import type { Currency } from "@/components/CurrencyContext";

const COUNTRY_TO_CUR: Record<string, Currency> = {
  GB: "gbp",
  UK: "gbp",
  IE: "gbp",
  AU: "aud",
  NZ: "aud",
  CA: "cad",
  US: "usd",
  SG: "usd",
};

export function marketFromCountryCode(code?: string | null): Currency {
  const cc = String(code || "").trim().toUpperCase();
  return COUNTRY_TO_CUR[cc] || "gbp";
}

export type GeoHint = {
  country_code?: string;
  country?: string;
  timezone?: string;
  locale?: string;
};

export async function detectGeoHint(): Promise<GeoHint> {
  const locale = typeof navigator !== "undefined" ? navigator.language : "";
  const timezone = typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "";
  try {
    const res = await fetch("https://ipapi.co/json/");
    if (res.ok) {
      const d = await res.json();
      return {
        country_code: d?.country_code || undefined,
        country: d?.country_name || undefined,
        timezone: d?.timezone || timezone || undefined,
        locale: locale || undefined,
      };
    }
  } catch {
    /* ignore */
  }
  return { timezone: timezone || undefined, locale: locale || undefined };
}

export function clientGeoPayload(hint?: GeoHint) {
  return {
    client_timezone: hint?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || null,
    client_locale: hint?.locale || navigator.language || null,
    client_country: hint?.country_code || hint?.country || null,
  };
}
