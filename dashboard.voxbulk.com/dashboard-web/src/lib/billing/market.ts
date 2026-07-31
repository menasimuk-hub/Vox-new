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

export function marketCurrencyCode(market: string): string {
  const codes: Record<string, string> = {
    gbp: "GBP",
    eur: "EUR",
    cad: "CAD",
    aud: "AUD",
    usd: "USD",
  };
  return codes[String(market || "usd").toLowerCase()] || "USD";
}

/** Org country / billing → ISO currency for package price pickers. */
export function orgCountryToCurrencyCode(country?: string | null): string {
  return marketCurrencyCode(countryToMarket(country));
}

export function pickPriceMinor(
  prices: Array<{ currency: string; monthly_price_minor?: number | null; yearly_price_minor?: number | null }>,
  currency: string,
  opts?: { yearly?: boolean },
): { currency: string; amountMinor: number | null } {
  const yearly = opts?.yearly !== false;
  const want = String(currency || "USD").toUpperCase();
  const row =
    prices.find((p) => String(p.currency || "").toUpperCase() === want) ||
    prices.find((p) => String(p.currency || "").toUpperCase() === "USD") ||
    prices[0];
  if (!row) return { currency: want, amountMinor: null };
  const amount = yearly ? row.yearly_price_minor : row.monthly_price_minor;
  return {
    currency: String(row.currency || want).toUpperCase(),
    amountMinor: amount != null ? Number(amount) : null,
  };
}

export function formatQuoteDisplay(pence: number | null | undefined, market: string): string {
  const base = Math.max(0, Number(pence || 0));
  const sym = marketCurrencySymbol(market);
  return `${sym}${(base / 100).toFixed(2)}`;
}
