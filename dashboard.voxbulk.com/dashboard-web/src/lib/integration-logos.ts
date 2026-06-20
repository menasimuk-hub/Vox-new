/** Official provider marks served from /public/integrations (SVG). */
export const INTEGRATION_LOGOS: Record<string, string> = {
  calendly: "/integrations/calendly.svg",
  cal_com: "/integrations/cal-com.svg",
  google_calendar: "/integrations/google-calendar.svg",
  microsoft_calendar: "/integrations/microsoft.svg",
  hubspot: "/integrations/hubspot.svg",
  hubspot_meetings: "/integrations/hubspot.svg",
  pipedrive: "/integrations/pipedrive.svg",
  zoho: "/integrations/zoho.svg",
  zoho_crm: "/integrations/zoho.svg",
  zoho_bookings: "/integrations/zoho.svg",
};

/** Left tile panel background — keeps the logo zone visually full. */
export const INTEGRATION_LOGO_TILE_BG: Record<string, string> = {
  calendly: "bg-[#006BFF]",
  cal_com: "bg-[#111827]",
  google_calendar: "bg-white",
  microsoft_calendar: "bg-white",
  hubspot: "bg-[#FF7A59]",
  hubspot_meetings: "bg-[#FF7A59]",
  pipedrive: "bg-[#017737]",
  zoho: "bg-[#E42527]",
  zoho_crm: "bg-[#E42527]",
  zoho_bookings: "bg-[#E42527]",
};

export function integrationLogoSrc(keyOrSlug: string): string | null {
  const needle = String(keyOrSlug || "").trim().toLowerCase();
  return INTEGRATION_LOGOS[needle] ?? null;
}

export function integrationLogoTileBg(keyOrSlug: string): string {
  const needle = String(keyOrSlug || "").trim().toLowerCase();
  return INTEGRATION_LOGO_TILE_BG[needle] ?? "bg-muted";
}
