import { EU_COUNTRIES, PRIMARY_MARKET_COUNTRIES, REST_OF_WORLD_COUNTRIES } from "./countries";

export { PROFILE_COUNTRIES } from "./countries";

const EU_COUNTRY_KEYS = new Set(
  EU_COUNTRIES.map((c) => c.value.toLowerCase()),
);

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

for (const c of EU_COUNTRIES) {
  COUNTRY_TO_MARKET[c.value.toLowerCase()] = "eur";
}

for (const c of REST_OF_WORLD_COUNTRIES) {
  COUNTRY_TO_MARKET[c.value.toLowerCase()] = "usd";
}

for (const c of PRIMARY_MARKET_COUNTRIES) {
  const key = c.value.toLowerCase();
  if (!COUNTRY_TO_MARKET[key]) {
    COUNTRY_TO_MARKET[key] = "usd";
  }
}

export function countryToMarket(country?: string | null): string {
  const key = String(country || "United States").trim().toLowerCase();
  if (EU_COUNTRY_KEYS.has(key)) return "eur";
  return COUNTRY_TO_MARKET[key] || "usd";
}

export function marketLabel(market: string): string {
  const labels: Record<string, string> = {
    gbp: "United Kingdom (GBP)",
    eur: "European Union (EUR)",
    cad: "Canada (CAD)",
    aud: "Australia (AUD)",
    usd: "United States (USD)",
  };
  const m = String(market || "usd").toLowerCase();
  return labels[m] || labels.usd;
}

export function marketCurrencySymbol(market: string): string {
  const symbols: Record<string, string> = {
    gbp: "£",
    eur: "€",
    cad: "CA$",
    aud: "A$",
    usd: "$",
  };
  return symbols[String(market || "usd").toLowerCase()] || "$";
}

export function formatQuoteDisplay(pence: number | null | undefined, market: string): string {
  const base = Math.max(0, Number(pence || 0));
  const sym = marketCurrencySymbol(market);
  return `${sym}${(base / 100).toFixed(2)}`;
}
