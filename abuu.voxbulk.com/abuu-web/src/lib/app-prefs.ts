import { useEffect, useState } from "react";

export type Lang = "en" | "ar";
export type Theme = "light" | "dark";

/**
 * Safe unique id generator.
 *
 * `crypto.randomUUID()` only exists in secure contexts (https or localhost).
 * When the app is opened over a LAN IP (e.g. http://192.168.0.21:8081) it is
 * `undefined` and throws, which would crash event handlers (e.g. "Create Offer").
 * This helper falls back to a manual generator so ids always work.
 */
export function uid(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    /* fall through to manual generator */
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useTheme(scope: string) {
  const key = `theme:${scope}`;
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    const saved = (localStorage.getItem(key) as Theme) || "light";
    setTheme(saved);
  }, [key]);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem(key, theme);
  }, [theme, key]);
  return { theme, toggle: () => setTheme((t) => (t === "light" ? "dark" : "light")) };
}

export function useLang(scope: string) {
  const key = `lang:${scope}`;
  const [lang, setLang] = useState<Lang>("en");
  useEffect(() => {
    const saved = (localStorage.getItem(key) as Lang) || "en";
    setLang(saved);
  }, [key]);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    localStorage.setItem(key, lang);
  }, [lang, key]);
  return { lang, toggle: () => setLang((l) => (l === "en" ? "ar" : "en")), setLang };
}

export function useLocalState<T>(key: string, initial: T) {
  const [state, setState] = useState<T>(initial);
  const [isLoaded, setIsLoaded] = useState(false);

  // 1. Load from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw !== null) {
        setState(JSON.parse(raw));
      }
    } catch (e) {
      console.error("Error reading localStorage key:", key, e);
    }
    setIsLoaded(true);
  }, [key]);

  // 2. Save to localStorage only AFTER loading is complete
  useEffect(() => {
    if (!isLoaded) return;
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch (e) {
      console.error("Error writing localStorage key:", key, e);
    }
  }, [key, state, isLoaded]);

  return [state, setState] as const;
}
