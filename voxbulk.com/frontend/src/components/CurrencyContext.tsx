import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { detectGeoHint, marketFromCountryCode, type Currency } from "@/lib/geo";

export type { Currency };

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

const STORAGE_KEY = "vb_currency";

function isCurrency(v: string | null | undefined): v is Currency {
  return Boolean(v && v in FX);
}

type Ctx = { currency: Currency; setCurrency: (c: Currency) => void; auto: boolean };
const CurrencyCtx = createContext<Ctx>({ currency: "usd", setCurrency: () => {}, auto: true });

export function CurrencyProvider({ children }: { children: ReactNode }) {
  // USD until geo resolves — avoids flashing UK prices worldwide.
  const [currency, setCurrencyState] = useState<Currency>("usd");
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const stored = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    if (isCurrency(stored)) {
      setCurrencyState(stored);
      setAuto(false);
      return;
    }

    void (async () => {
      const hint = await detectGeoHint();
      if (cancelled) return;
      setCurrencyState(marketFromCountryCode(hint.country_code));
      setAuto(true);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const setCurrency = (c: Currency) => {
    setCurrencyState(c);
    setAuto(false);
    try {
      localStorage.setItem(STORAGE_KEY, c);
    } catch {
      /* ignore */
    }
  };

  return <CurrencyCtx.Provider value={{ currency, setCurrency, auto }}>{children}</CurrencyCtx.Provider>;
}

export function useCurrency() {
  return useContext(CurrencyCtx);
}
