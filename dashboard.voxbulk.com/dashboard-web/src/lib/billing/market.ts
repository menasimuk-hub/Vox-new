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

export function formatQuoteDisplay(pence: number | null | undefined, market: string): string {
  // Amounts from the API are already in the org currency (explicit per-currency pricing, no FX).
  const base = Math.max(0, Number(pence || 0));
  const sym = marketCurrencySymbol(market);
  return `${sym}${(base / 100).toFixed(2)}`;
}
