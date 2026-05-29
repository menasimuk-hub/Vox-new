export const PROFILE_COUNTRIES = [
  { value: "United Kingdom", label: "United Kingdom" },
  { value: "Canada", label: "Canada" },
  { value: "Australia", label: "Australia" },
  { value: "United States", label: "United States" },
] as const;

const COUNTRY_TO_MARKET: Record<string, string> = {
  "united kingdom": "gbp",
  uk: "gbp",
  gb: "gbp",
  canada: "cad",
  ca: "cad",
  australia: "aud",
  au: "aud",
  "united states": "usd",
  usa: "usd",
  us: "usd",
};

export function countryToMarket(country?: string | null): string {
  const key = String(country || "United Kingdom").trim().toLowerCase();
  return COUNTRY_TO_MARKET[key] || "gbp";
}

export function marketLabel(market: string): string {
  const labels: Record<string, string> = {
    gbp: "United Kingdom (GBP)",
    cad: "Canada (CAD)",
    aud: "Australia (AUD)",
    usd: "United States (USD)",
  };
  return labels[String(market || "gbp").toLowerCase()] || labels.gbp;
}

export function marketCurrencySymbol(market: string): string {
  const symbols: Record<string, string> = { gbp: "£", cad: "CA$", aud: "A$", usd: "$" };
  return symbols[String(market || "gbp").toLowerCase()] || "£";
}

export function formatQuoteDisplay(
  pence: number | null | undefined,
  market: string,
  settings?: { fx_cad_multiplier?: number; fx_aud_multiplier?: number; fx_usd_multiplier?: number },
): string {
  const base = Math.max(0, Number(pence || 0));
  const m = String(market || "gbp").toLowerCase();
  const fx: Record<string, number> = {
    gbp: 1,
    cad: Number(settings?.fx_cad_multiplier || 1.71),
    aud: Number(settings?.fx_aud_multiplier || 1.95),
    usd: Number(settings?.fx_usd_multiplier || 1.26),
  };
  const converted = m === "gbp" ? base : Math.round(base * (fx[m] || 1));
  const sym = marketCurrencySymbol(m);
  return `${sym}${(converted / 100).toFixed(2)}`;
}
