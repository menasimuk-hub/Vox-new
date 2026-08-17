import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Currency = "gbp" | "eur" | "aud" | "cad" | "usd";

export const FX: Record<Currency, number> = { gbp: 1, eur: 1.17, aud: 1.95, cad: 1.71, usd: 1.26 };
export const SYM: Record<Currency, string> = { gbp: "£", eur: "€", aud: "A$", cad: "CA$", usd: "$" };

/** Join symbol + amount so `$` never sits against a digit (`A$96` / `$13`).
 * Those sequences are `$n` backrefs in JS String.replace and Playwright/YAML snapshots,
 * which leak snapshot file paths into the UI instead of prices. */
export function formatMoney(symbol: string, amount: string | number): string {
  const n = String(amount);
  if (symbol.includes("$") && /^\d/.test(n)) return `${symbol}\u00A0${n}`;
  return `${symbol}${n}`;
}

/** Repair API/catalog strings that already glued `$` to a digit. Uses a replace callback so `$` is literal. */
export function sanitizeMoneyLabel(raw: string): string {
  return String(raw || "").replace(/(\$)(\d)/g, (_m, a: string, b: string) => `${a}\u00A0${b}`);
}
export const MARKETS: { code: Currency; label: string; flag: string; country: string }[] = [
  { code: "gbp", label: "GBP", flag: "🇬🇧", country: "United Kingdom" },
  { code: "eur", label: "EUR", flag: "🇪🇺", country: "European Union" },
  { code: "aud", label: "AUD", flag: "🇦🇺", country: "Australia" },
  { code: "cad", label: "CAD", flag: "🇨🇦", country: "Canada" },
  { code: "usd", label: "USD", flag: "🇺🇸", country: "United States" },
];

const COUNTRY_TO_CUR: Record<string, Currency> = {
  GB: "gbp",
  IE: "eur",
  DE: "eur",
  FR: "eur",
  ES: "eur",
  IT: "eur",
  NL: "eur",
  BE: "eur",
  AT: "eur",
  PT: "eur",
  FI: "eur",
  AU: "aud",
  CA: "cad",
  US: "usd",
};

type Ctx = { currency: Currency; setCurrency: (c: Currency) => void; auto: boolean };
const CurrencyCtx = createContext<Ctx>({ currency: "gbp", setCurrency: () => {}, auto: true });

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrencyState] = useState<Currency>("gbp");
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("vb_currency") : null;
    if (stored && (stored in FX)) {
      setCurrencyState(stored as Currency);
      setAuto(false);
      return;
    }
    // Auto-detect by IP
    fetch("https://ipapi.co/json/")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        const code = d?.country_code;
        if (code && COUNTRY_TO_CUR[code]) setCurrencyState(COUNTRY_TO_CUR[code]);
      })
      .catch(() => {});
  }, []);

  const setCurrency = (c: Currency) => {
    setCurrencyState(c);
    setAuto(false);
    try { localStorage.setItem("vb_currency", c); } catch {}
  };

  return <CurrencyCtx.Provider value={{ currency, setCurrency, auto }}>{children}</CurrencyCtx.Provider>;
}

export function useCurrency() { return useContext(CurrencyCtx); }
