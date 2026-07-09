import type { ComponentType } from "react";
import type { Copy, Theme, ThemePack, WebThemeConfig } from "./types";

import * as surveyTemp from "./themes/survey-temp";
import * as surveySummer from "./themes/survey-summer";
import * as surveyWinter from "./themes/survey-winter";
import * as restaurantsCafes from "./themes/restaurants-cafes";
import * as retailShops from "./themes/retail-shops";
import * as salonsSpas from "./themes/salons-spas";
import * as hotelsHospitality from "./themes/hotels-hospitality";
import * as eventsEntertainment from "./themes/events-entertainment";
import * as fitnessGyms from "./themes/fitness-gyms";
import * as others from "./themes/others";
import * as christmas from "./themes/christmas";
import * as newYear from "./themes/new-year";
import * as valentinesDay from "./themes/valentines-day";
import * as easter from "./themes/easter";
import * as halloween from "./themes/halloween";
import * as thanksgiving from "./themes/thanksgiving";
import * as diwali from "./themes/diwali";
import * as chineseNewYear from "./themes/chinese-new-year";
import * as ramadanEid from "./themes/ramadan-eid";
import * as eidAlAdha from "./themes/eid-al-adha";
import * as island from "./themes/island";

type ThemeModule = { theme: Theme; Art: ComponentType };

const THEME_MODULES: Record<string, ThemeModule> = {
  "survey-temp": surveyTemp,
  "survey-summer": surveySummer,
  "survey-winter": surveyWinter,
  "restaurants-cafes": restaurantsCafes,
  "retail-shops": retailShops,
  "salons-spas": salonsSpas,
  "hotels-hospitality": hotelsHospitality,
  "events-entertainment": eventsEntertainment,
  "fitness-gyms": fitnessGyms,
  others,
  christmas,
  "new-year": newYear,
  "valentines-day": valentinesDay,
  easter,
  halloween,
  thanksgiving,
  diwali,
  "chinese-new-year": chineseNewYear,
  "ramadan-eid": ramadanEid,
  "eid-al-adha": eidAlAdha,
  island,
};

const INDUSTRY_DEFAULT_THEME: Record<string, string> = {
  restaurant: "restaurants-cafes",
  retail: "retail-shops",
  salon: "salons-spas",
  hotel: "hotels-hospitality",
  fitness: "fitness-gyms",
  events: "events-entertainment",
  others: "others",
};

const COPY_DEFAULTS: Record<string, Omit<Copy, "companyName">> = {
  "survey-temp": {
    serviceLabel: "Customer feedback",
    metaTitle: "Quick survey",
    metaDescription: "A 60-second survey. Tap or talk.",
    thankYouTitle: "Thank you",
    thankYouSubtitle: "Your feedback helps us improve. We read every reply.",
  },
  "survey-summer": {
    serviceLabel: "Summer",
    metaTitle: "Summer feedback",
    metaDescription: "Bright, breezy micro-survey.",
    thankYouTitle: "Sunshine thanks",
    thankYouSubtitle: "Thanks for sharing — enjoy the rest of your day. ☀️",
  },
  "survey-winter": {
    serviceLabel: "Winter",
    metaTitle: "Winter feedback",
    metaDescription: "A calm, frosty micro-survey.",
    thankYouTitle: "Warm wishes",
    thankYouSubtitle: "Thanks for sharing — stay cosy. ❄️",
  },
  "restaurants-cafes": {
    serviceLabel: "Restaurants & Cafés",
    metaTitle: "Restaurant feedback",
    metaDescription: "Quick feedback for food & service.",
    thankYouTitle: "Bon appétit",
    thankYouSubtitle: "Thanks for dining with us — your words help us improve.",
  },
  "retail-shops": {
    serviceLabel: "Retail Shops",
    metaTitle: "Retail feedback",
    metaDescription: "Quick in-store feedback.",
    thankYouTitle: "You're a gem",
    thankYouSubtitle: "Thanks for shopping with us — we appreciate your honesty.",
  },
  "salons-spas": {
    serviceLabel: "Salons & Spas",
    metaTitle: "Salon feedback",
    metaDescription: "Quick spa & salon feedback.",
    thankYouTitle: "Radiant, thank you",
    thankYouSubtitle: "Thanks for visiting — your feedback helps us pamper better.",
  },
  "hotels-hospitality": {
    serviceLabel: "Hotels & Hospitality",
    metaTitle: "Hotel feedback",
    metaDescription: "Quick stay feedback.",
    thankYouTitle: "Until next time",
    thankYouSubtitle: "Thank you for staying with us — safe travels.",
  },
  "events-entertainment": {
    serviceLabel: "Events & Entertainment",
    metaTitle: "Event feedback",
    metaDescription: "Quick event feedback.",
    thankYouTitle: "Encore",
    thankYouSubtitle: "Thanks for the feedback — see you at the next one.",
  },
  "fitness-gyms": {
    serviceLabel: "Fitness & Gyms",
    metaTitle: "Gym feedback",
    metaDescription: "Quick workout feedback.",
    thankYouTitle: "Reps logged",
    thankYouSubtitle: "Thanks for training with us — keep pushing.",
  },
  others: {
    serviceLabel: "Others",
    metaTitle: "Feedback",
    metaDescription: "Quick feedback survey.",
    thankYouTitle: "Thank you",
    thankYouSubtitle: "Your feedback helps us improve.",
  },
  christmas: {
    serviceLabel: "Christmas",
    metaTitle: "Christmas",
    metaDescription: "Holiday feedback in 60 seconds.",
    thankYouTitle: "Merry & bright",
    thankYouSubtitle: "Thanks for sharing — happy holidays. 🎄",
  },
  "new-year": {
    serviceLabel: "New Year",
    metaTitle: "New Year",
    metaDescription: "New Year feedback.",
    thankYouTitle: "Cheers to you",
    thankYouSubtitle: "Thanks for sharing — here's to a great year ahead. 🎆",
  },
  "valentines-day": {
    serviceLabel: "Valentine's Day",
    metaTitle: "Valentine's Day",
    metaDescription: "Valentine feedback.",
    thankYouTitle: "With love",
    thankYouSubtitle: "Thanks for sharing your thoughts. 💝",
  },
  easter: {
    serviceLabel: "Easter",
    metaTitle: "Easter",
    metaDescription: "Easter feedback.",
    thankYouTitle: "Happy Easter",
    thankYouSubtitle: "Thanks for sharing — enjoy the season. 🐣",
  },
  halloween: {
    serviceLabel: "Halloween",
    metaTitle: "Halloween",
    metaDescription: "Spooky season feedback.",
    thankYouTitle: "Spooktacular",
    thankYouSubtitle: "Thanks for sharing — have a frightfully good day. 🎃",
  },
  thanksgiving: {
    serviceLabel: "Thanksgiving",
    metaTitle: "Thanksgiving",
    metaDescription: "Thanksgiving feedback.",
    thankYouTitle: "With gratitude",
    thankYouSubtitle: "Thanks for sharing — we're grateful for you. 🦃",
  },
  diwali: {
    serviceLabel: "Diwali",
    metaTitle: "Diwali",
    metaDescription: "Festival of lights feedback.",
    thankYouTitle: "Shubh Diwali",
    thankYouSubtitle: "Thanks for sharing — wishing you light and joy. 🪔",
  },
  "chinese-new-year": {
    serviceLabel: "Chinese New Year",
    metaTitle: "Chinese New Year",
    metaDescription: "CNY feedback.",
    thankYouTitle: "Gong Xi Fa Cai",
    thankYouSubtitle: "Thanks for sharing — prosperity and happiness. 🧧",
  },
  "ramadan-eid": {
    serviceLabel: "Ramadan / Eid al-Fitr",
    metaTitle: "Ramadan / Eid",
    metaDescription: "Ramadan & Eid feedback.",
    thankYouTitle: "Eid Mubarak",
    thankYouSubtitle: "Thanks for sharing — peace and blessings. 🌙",
  },
  "eid-al-adha": {
    serviceLabel: "Eid al-Adha",
    metaTitle: "Eid al-Adha",
    metaDescription: "Eid al-Adha feedback.",
    thankYouTitle: "Eid Mubarak",
    thankYouSubtitle: "Thanks for sharing — warm wishes to you and yours. 🕌",
  },
  island: {
    serviceLabel: "Island",
    metaTitle: "Island",
    metaDescription: "Tropical feedback.",
    thankYouTitle: "Mahalo",
    thankYouSubtitle: "Thanks for sharing — aloha and safe travels. 🌴",
  },
};

const OVERLAY_WINDOWS: Record<string, { from: string; to: string }> = {
  "survey-summer": { from: "06-01", to: "08-31" },
  "survey-winter": { from: "12-01", to: "02-28" },
  christmas: { from: "12-10", to: "12-27" },
  "new-year": { from: "12-28", to: "01-05" },
  "valentines-day": { from: "02-10", to: "02-16" },
  halloween: { from: "10-25", to: "11-01" },
};

const OVERLAY_IDS = new Set([
  "survey-summer",
  "survey-winter",
  "island",
  "christmas",
  "new-year",
  "chinese-new-year",
  "valentines-day",
  "easter",
  "halloween",
  "thanksgiving",
  "diwali",
  "ramadan-eid",
  "eid-al-adha",
]);

function mmdd(date = new Date()): string {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${m}-${d}`;
}

function inWindow(today: string, from: string, to: string): boolean {
  if (from <= to) return today >= from && today <= to;
  return today >= from || today <= to;
}

function activeOverlayId(config?: WebThemeConfig | null, today = new Date()): string | null {
  const ids = config?.overlay_ids || [];
  if (!ids.length) return null;
  const mode = config?.overlay_mode || "auto";
  if (mode === "fixed") return ids.find((id) => OVERLAY_IDS.has(id)) || ids[0] || null;
  const todayStr = mmdd(today);
  for (const id of ids) {
    const win = OVERLAY_WINDOWS[id];
    if (win && inWindow(todayStr, win.from, win.to)) return id;
    if (!win && OVERLAY_IDS.has(id)) return id;
  }
  return null;
}

export function defaultThemeForIndustry(industrySlug?: string | null): string {
  if (!industrySlug) return "survey-temp";
  return INDUSTRY_DEFAULT_THEME[industrySlug] || "survey-temp";
}

export function resolveThemeId(
  themeId?: string | null,
  industrySlug?: string | null,
  config?: WebThemeConfig | null,
): string {
  const base =
    !themeId || themeId === "auto"
      ? defaultThemeForIndustry(industrySlug)
      : themeId in THEME_MODULES
        ? themeId
        : defaultThemeForIndustry(industrySlug);
  const overlay = activeOverlayId(config);
  if (overlay && overlay in THEME_MODULES) return overlay;
  return base;
}

export function getThemePack(
  themeId: string,
  companyName: string,
  industryName?: string | null,
): ThemePack {
  const mod = THEME_MODULES[themeId] || THEME_MODULES["survey-temp"];
  const defaults = COPY_DEFAULTS[themeId] || COPY_DEFAULTS["survey-temp"];
  return {
    id: themeId,
    theme: mod.theme,
    Art: mod.Art,
    copyDefaults: {
      ...defaults,
      serviceLabel: industryName || defaults.serviceLabel,
    },
  };
}

export function buildCopy(pack: ThemePack, companyName: string, industryName?: string | null): Copy {
  return {
    companyName,
    serviceLabel: industryName || pack.copyDefaults.serviceLabel,
    metaTitle: pack.copyDefaults.metaTitle,
    metaDescription: pack.copyDefaults.metaDescription,
    thankYouTitle: pack.copyDefaults.thankYouTitle,
    thankYouSubtitle: pack.copyDefaults.thankYouSubtitle.replace("us", companyName),
  };
}

export const ALL_THEME_IDS = Object.keys(THEME_MODULES);

export function previewThemeUrl(publicBase: string, themeId: string, company?: string): string {
  const base = publicBase.replace(/\/+$/, "");
  const q = company ? `?company=${encodeURIComponent(company)}` : "";
  return `${base}/survey/preview/${themeId}${q}`;
}
