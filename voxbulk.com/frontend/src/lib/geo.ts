export type Currency = "gbp" | "eur" | "aud" | "cad" | "usd";

/** EU member states — marketing prices show EUR (matches backend billing_currency.EU_MEMBER_STATES). */
export const EU_MEMBER_STATES = new Set([
  "AT",
  "BE",
  "BG",
  "HR",
  "CY",
  "CZ",
  "DK",
  "EE",
  "FI",
  "FR",
  "DE",
  "GR",
  "HU",
  "IE",
  "IT",
  "LV",
  "LT",
  "LU",
  "MT",
  "NL",
  "PL",
  "PT",
  "RO",
  "SK",
  "SI",
  "ES",
  "SE",
]);

const EXPLICIT: Record<string, Currency> = {
  GB: "gbp",
  UK: "gbp",
  CA: "cad",
  AU: "aud",
  US: "usd",
};

/**
 * Public marketing currency from ISO country code.
 * UK → GBP, Canada → CAD, Australia → AUD, Europe (EU) → EUR, elsewhere → USD.
 */
export function marketFromCountryCode(code?: string | null): Currency {
  const cc = String(code || "").trim().toUpperCase().slice(0, 2);
  if (!cc) return "usd";
  if (EXPLICIT[cc]) return EXPLICIT[cc];
  if (EU_MEMBER_STATES.has(cc)) return "eur";
  return "usd";
}

/** Infer country from browser locale (e.g. en-GB → GB) when IP geo fails. */
export function countryFromLocale(locale?: string | null): string | null {
  const raw = String(locale || "").trim();
  const m = raw.match(/[-_]([A-Za-z]{2})\b/);
  return m ? m[1].toUpperCase() : null;
}

export type GeoHint = {
  country_code?: string;
  country?: string;
  timezone?: string;
  locale?: string;
};

export async function detectGeoHint(): Promise<GeoHint> {
  const locale = typeof navigator !== "undefined" ? navigator.language : "";
  const timezone =
    typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "";
  try {
    const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer =
      ctrl && typeof window !== "undefined"
        ? window.setTimeout(() => ctrl.abort(), 4000)
        : undefined;
    const res = await fetch("https://ipapi.co/json/", ctrl ? { signal: ctrl.signal } : undefined);
    if (typeof timer === "number") window.clearTimeout(timer);
    if (res.ok) {
      const d = await res.json();
      const code = String(d?.country_code || "").trim().toUpperCase().slice(0, 2);
      if (code) {
        return {
          country_code: code,
          country: d?.country_name || undefined,
          timezone: d?.timezone || timezone || undefined,
          locale: locale || undefined,
        };
      }
    }
  } catch {
    /* ignore — fall through to locale */
  }
  const fromLocale = countryFromLocale(locale);
  return {
    country_code: fromLocale || undefined,
    timezone: timezone || undefined,
    locale: locale || undefined,
  };
}

export function clientGeoPayload(hint?: GeoHint) {
  return {
    client_timezone: hint?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || null,
    client_locale: hint?.locale || navigator.language || null,
    client_country: hint?.country_code || hint?.country || null,
  };
}
