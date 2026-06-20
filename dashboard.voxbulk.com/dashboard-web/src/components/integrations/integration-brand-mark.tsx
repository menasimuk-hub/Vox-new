import type * as React from "react";

import { cn } from "@/lib/utils";

type MarkProps = {
  className?: string;
};

/** HubSpot sprocket — 24×24 path, centered and scaled to fill the tile. */
function HubSpotMark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      className={cn("block h-full w-full", className)}
    >
      <rect width="64" height="64" fill="#FF7A59" />
      <g transform="translate(32 32) scale(2.45) translate(-12 -12)">
        <path
          fill="#fff"
          d="M18.164 7.93V5.084a2.445 2.445 0 0 0 1.68-2.324 2.445 2.445 0 0 0-4.889 0 2.445 2.445 0 0 0 1.68 2.324v2.846a6.533 6.533 0 0 0-3.043 1.278l-7.678-7.677a2.89 2.89 0 0 0 .416-1.459 2.916 2.916 0 0 0-5.832 0A2.916 2.916 0 0 0 4.69 2.076l7.677 7.677a6.544 6.544 0 0 0-1.278 3.043H8.243a2.445 2.445 0 0 0-1.68-2.324 2.445 2.445 0 0 0 0 4.889 2.445 2.445 0 0 0 1.68-2.324h2.397v2.397a2.445 2.445 0 0 0-1.68 2.324 2.445 2.445 0 0 0 4.889 0 2.445 2.445 0 0 0-1.68-2.324v-2.397a6.513 6.513 0 0 0 3.881-2.256l2.786 2.786a2.916 2.916 0 0 0 .832 4.623 2.916 2.916 0 0 0 3.944-4.231l-2.786-2.786a6.544 6.544 0 0 0 1.278-3.043zm-8.023 4.386a3.943 3.943 0 1 1 0-7.886 3.943 3.943 0 0 1 0 7.886z"
        />
      </g>
    </svg>
  );
}

function CalendlyMark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      className={cn("block h-full w-full", className)}
    >
      <rect width="64" height="64" fill="#006BFF" />
      <g transform="translate(32 32) scale(2.55) translate(-12 -12)">
        <path
          fill="#fff"
          d="M10.651 5.646h4.697v6.616a4.793 4.793 0 1 1-4.697-6.616Zm4.697-2.677A7.454 7.454 0 1 0 21.95 10.67V0h-6.602Z"
        />
      </g>
    </svg>
  );
}

function CalComMark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      className={cn("block h-full w-full", className)}
    >
      <rect width="64" height="64" fill="#111827" />
      <g transform="translate(32 32) scale(2.45) translate(-12 -12)">
        <path
          fill="#fff"
          d="M15.096 2.932 9.096 2.936a.894.894 0 0 0-.894.894v10.318c0 .494.4.894.894.894h.001a.894.894 0 0 0 .894-.894V8.94l6.002-.004a.894.894 0 0 0 .894-.894V3.826a.894.894 0 0 0-.894-.894h-.003ZM4.116 11.028v-.001a.894.894 0 0 0-.894.894v6.072c0 .494.4.894.894.894h6.006a.894.894 0 0 0 .894-.894v-6.072a.894.894 0 0 0-.894-.894H4.116Z"
        />
      </g>
    </svg>
  );
}

function GoogleCalendarMark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      className={cn("block h-full w-full", className)}
    >
      <rect width="64" height="64" fill="#fff" />
      <g transform="translate(32 32) scale(2.35) translate(-12 -12)">
        <rect x="3" y="5" width="18" height="16" rx="2" fill="#fff" />
        <path fill="#4285F4" d="M3 7c0-1.1.9-2 2-2h14c1.1 0 2 .9 2 2v3H3V7z" />
        <path fill="#EA4335" d="M3 5h4v4H3z" />
        <path fill="#FBBC04" d="M17 5h4v4h-4z" />
        <path fill="#34A853" d="M3 21v-4h4v4H3z" />
        <path fill="#4285F4" d="M17 21h4v-4h-4v4z" />
        <rect x="7" y="11" width="10" height="2" rx="1" fill="#4285F4" />
        <rect x="7" y="15" width="7" height="2" rx="1" fill="#34A853" />
      </g>
    </svg>
  );
}

function MicrosoftMark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      className={cn("block h-full w-full", className)}
    >
      <path fill="#F25022" d="M0 0h30v30H0z" />
      <path fill="#7FBA00" d="M34 0h30v30H34z" />
      <path fill="#00A4EF" d="M0 34h30v30H0z" />
      <path fill="#FFB900" d="M34 34h30v30H34z" />
    </svg>
  );
}

function PipedriveMark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      className={cn("block h-full w-full", className)}
    >
      <rect width="64" height="64" fill="#017737" />
      <g transform="translate(32 32) scale(1.35) translate(-32 -32)">
        <path
          fill="#fff"
          d="M18 14h15c9.941 0 18 8.059 18 18s-8.059 18-18 18H18V14zm12 28h3c6.627 0 12-5.373 12-12s-5.373-12-12-12h-3v24z"
        />
      </g>
    </svg>
  );
}

function ZohoMark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      className={cn("block h-full w-full", className)}
    >
      <rect width="64" height="64" fill="#E42527" />
      <g transform="translate(32 36)">
        <text
          x="0"
          y="0"
          textAnchor="middle"
          fill="#fff"
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize="22"
          fontWeight="700"
        >
          Zoho
        </text>
      </g>
    </svg>
  );
}

const BRAND_MARKS: Record<string, React.ComponentType<MarkProps>> = {
  calendly: CalendlyMark,
  cal_com: CalComMark,
  google_calendar: GoogleCalendarMark,
  microsoft_calendar: MicrosoftMark,
  hubspot: HubSpotMark,
  hubspot_meetings: HubSpotMark,
  pipedrive: PipedriveMark,
  zoho: ZohoMark,
  zoho_crm: ZohoMark,
  zoho_bookings: ZohoMark,
};

export function IntegrationBrandMark({
  providerKey,
  iconSlug,
  className,
}: {
  providerKey?: string;
  iconSlug: string;
  className?: string;
}) {
  const key = String(providerKey || iconSlug || "")
    .trim()
    .toLowerCase();
  const Mark = BRAND_MARKS[key] || BRAND_MARKS[String(iconSlug || "").trim().toLowerCase()];
  if (!Mark) return null;
  return <Mark className={className} />;
}

export function hasIntegrationBrandMark(providerKey?: string, iconSlug?: string) {
  const key = String(providerKey || iconSlug || "")
    .trim()
    .toLowerCase();
  return Boolean(BRAND_MARKS[key] || BRAND_MARKS[String(iconSlug || "").trim().toLowerCase()]);
}
