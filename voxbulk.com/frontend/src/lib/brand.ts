/** Canonical VOXBULK logos — synced from voxbulk-api/logos/ via scripts/sync-brand-assets.mjs */
export const brandAssets = {
  logoBlack: "/brand/logo-black.svg",
  logoWhite: "/brand/logo-white.svg",
  iconBlack: "/brand/icon-black.svg",
  iconWhite: "/brand/icon-white.svg",
  favicon: "/brand/favicon.ico",
  faviconPng: "/brand/favicon.png",
} as const;

/** Background the logo sits on — picks black or white wordmark for contrast. */
export type BrandSurface = "light" | "dark";

export function brandLogoForSurface(surface: BrandSurface, icon = false) {
  if (icon) return surface === "dark" ? brandAssets.iconWhite : brandAssets.iconBlack;
  return surface === "dark" ? brandAssets.logoWhite : brandAssets.logoBlack;
}

export const SITE_ORIGIN = "https://voxbulk.com";
