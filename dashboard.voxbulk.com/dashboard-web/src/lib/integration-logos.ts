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

export function integrationLogoSrc(keyOrSlug: string): string | null {
  const needle = String(keyOrSlug || "").trim().toLowerCase();
  return INTEGRATION_LOGOS[needle] ?? null;
}
