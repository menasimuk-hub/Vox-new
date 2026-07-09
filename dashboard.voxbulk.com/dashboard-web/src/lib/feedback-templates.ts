/**
 * Catalog of web survey templates (mirrors feedback-flow / theme-registry).
 */

export type TemplateKind = "base" | "category" | "season" | "event";

export type SurveyTemplate = {
  id: string;
  label: string;
  emoji: string;
  kind: TemplateKind;
  gradient: string;
  accent: string;
  desc: string;
  industryId?: string;
  window?: { from: string; to: string };
};

export const BASE_TEMPLATE: SurveyTemplate = {
  id: "survey-temp",
  label: "Default (main)",
  emoji: "✨",
  kind: "base",
  gradient: "from-slate-400/30 to-slate-200/10",
  accent: "text-slate-700 dark:text-slate-200",
  desc: "Clean neutral look — works for every business.",
};

export const CATEGORY_TEMPLATES: SurveyTemplate[] = [
  {
    id: "restaurants-cafes",
    label: "Restaurants & cafés",
    emoji: "🍽️",
    kind: "category",
    gradient: "from-amber-500/30 via-red-400/20 to-rose-400/10",
    accent: "text-amber-700 dark:text-amber-300",
    desc: "Warm, appetising palette for F&B.",
    industryId: "restaurant",
  },
  {
    id: "retail-shops",
    label: "Retail shops",
    emoji: "🛍️",
    kind: "category",
    gradient: "from-fuchsia-500/25 via-pink-400/15 to-violet-400/10",
    accent: "text-fuchsia-700 dark:text-fuchsia-300",
    desc: "Playful retail-store vibe.",
    industryId: "retail",
  },
  {
    id: "salons-spas",
    label: "Salons & spas",
    emoji: "💆",
    kind: "category",
    gradient: "from-rose-400/25 via-pink-300/15 to-purple-300/10",
    accent: "text-rose-700 dark:text-rose-300",
    desc: "Calm, pampering pastel look.",
    industryId: "salon",
  },
  {
    id: "hotels-hospitality",
    label: "Hotels & hospitality",
    emoji: "🏨",
    kind: "category",
    gradient: "from-teal-500/25 via-cyan-400/15 to-blue-400/10",
    accent: "text-teal-700 dark:text-teal-300",
    desc: "Premium, hospitable feel.",
    industryId: "hotel",
  },
  {
    id: "fitness-gyms",
    label: "Fitness & gyms",
    emoji: "🏋️",
    kind: "category",
    gradient: "from-lime-500/25 via-emerald-400/15 to-green-400/10",
    accent: "text-emerald-700 dark:text-emerald-300",
    desc: "Bold, energetic sports palette.",
    industryId: "fitness",
  },
  {
    id: "events-entertainment",
    label: "Events & entertainment",
    emoji: "🎉",
    kind: "category",
    gradient: "from-violet-500/25 via-purple-400/15 to-indigo-400/10",
    accent: "text-violet-700 dark:text-violet-300",
    desc: "Festive, high-energy event look.",
    industryId: "events",
  },
  {
    id: "others",
    label: "Others",
    emoji: "🌟",
    kind: "category",
    gradient: "from-primary/25 to-primary/5",
    accent: "text-primary",
    desc: "Flexible neutral for any business.",
    industryId: "others",
  },
];

export const SEASON_TEMPLATES: SurveyTemplate[] = [
  {
    id: "survey-summer",
    label: "Summer",
    emoji: "☀️",
    kind: "season",
    gradient: "from-amber-400/30 via-orange-400/20 to-yellow-300/10",
    accent: "text-amber-600 dark:text-amber-400",
    desc: "Bright & sunny.",
    window: { from: "06-01", to: "08-31" },
  },
  {
    id: "survey-winter",
    label: "Winter",
    emoji: "❄️",
    kind: "season",
    gradient: "from-sky-400/30 via-blue-400/20 to-indigo-300/10",
    accent: "text-sky-600 dark:text-sky-400",
    desc: "Cool & crisp.",
    window: { from: "12-01", to: "02-28" },
  },
  {
    id: "island",
    label: "Island / tropical",
    emoji: "🌴",
    kind: "season",
    gradient: "from-emerald-400/30 via-teal-400/20 to-cyan-300/10",
    accent: "text-emerald-600 dark:text-emerald-400",
    desc: "Beach & vacation vibe.",
  },
];

export const EVENT_TEMPLATES: SurveyTemplate[] = [
  {
    id: "christmas",
    label: "Christmas",
    emoji: "🎄",
    kind: "event",
    gradient: "from-emerald-600/25 via-red-500/20 to-amber-400/10",
    accent: "text-emerald-700 dark:text-emerald-400",
    desc: "Festive red & green.",
    window: { from: "12-10", to: "12-27" },
  },
  {
    id: "new-year",
    label: "New Year",
    emoji: "🎆",
    kind: "event",
    gradient: "from-yellow-400/30 via-amber-500/20 to-slate-800/10",
    accent: "text-amber-600 dark:text-amber-400",
    desc: "Fireworks & gold.",
    window: { from: "12-28", to: "01-05" },
  },
  {
    id: "chinese-new-year",
    label: "Chinese New Year",
    emoji: "🧧",
    kind: "event",
    gradient: "from-red-600/30 via-yellow-500/20 to-red-400/10",
    accent: "text-red-700 dark:text-red-400",
    desc: "Red & gold prosperity.",
  },
  {
    id: "valentines-day",
    label: "Valentine's Day",
    emoji: "💝",
    kind: "event",
    gradient: "from-rose-500/30 via-pink-400/20 to-red-300/10",
    accent: "text-rose-700 dark:text-rose-400",
    desc: "Hearts & romance.",
    window: { from: "02-10", to: "02-16" },
  },
  {
    id: "easter",
    label: "Easter",
    emoji: "🐣",
    kind: "event",
    gradient: "from-pink-300/30 via-yellow-300/20 to-emerald-300/10",
    accent: "text-pink-700 dark:text-pink-400",
    desc: "Pastel spring look.",
  },
  {
    id: "halloween",
    label: "Halloween",
    emoji: "🎃",
    kind: "event",
    gradient: "from-orange-500/30 via-purple-700/25 to-slate-900/10",
    accent: "text-orange-600 dark:text-orange-400",
    desc: "Spooky orange & purple.",
    window: { from: "10-25", to: "11-01" },
  },
  {
    id: "thanksgiving",
    label: "Thanksgiving",
    emoji: "🦃",
    kind: "event",
    gradient: "from-amber-600/30 via-orange-500/20 to-yellow-400/10",
    accent: "text-amber-700 dark:text-amber-400",
    desc: "Harvest warm tones.",
  },
  {
    id: "diwali",
    label: "Diwali",
    emoji: "🪔",
    kind: "event",
    gradient: "from-yellow-500/30 via-orange-500/25 to-fuchsia-500/10",
    accent: "text-yellow-700 dark:text-yellow-400",
    desc: "Festival of lights.",
  },
  {
    id: "ramadan-eid",
    label: "Ramadan / Eid",
    emoji: "🌙",
    kind: "event",
    gradient: "from-indigo-500/30 via-violet-500/20 to-amber-400/10",
    accent: "text-indigo-700 dark:text-indigo-400",
    desc: "Crescent moon & lanterns.",
  },
  {
    id: "eid-al-adha",
    label: "Eid al-Adha",
    emoji: "🕌",
    kind: "event",
    gradient: "from-emerald-600/30 via-teal-500/20 to-amber-400/10",
    accent: "text-emerald-700 dark:text-emerald-400",
    desc: "Green & gold blessings.",
  },
];
