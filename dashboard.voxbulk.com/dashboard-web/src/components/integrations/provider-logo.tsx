import { Building2, Calendar, CalendarCheck, CalendarClock, CalendarRange, PlugZap } from "lucide-react";

import { integrationLogoSrc, integrationLogoTileBg } from "@/lib/integration-logos";
import { cn } from "@/lib/utils";

const FALLBACK_ICONS: Record<string, typeof CalendarCheck> = {
  calendly: CalendarCheck,
  cal_com: CalendarRange,
  google_calendar: Calendar,
  microsoft_calendar: CalendarClock,
  hubspot: Building2,
  hubspot_meetings: Building2,
  pipedrive: Building2,
  zoho: Building2,
  zoho_crm: Building2,
  zoho_bookings: Building2,
};

type Props = {
  iconSlug: string;
  providerKey?: string;
  label: string;
  className?: string;
  imgClassName?: string;
  variant?: "inline" | "tile";
};

export function ProviderLogo({
  iconSlug,
  providerKey,
  label,
  className,
  imgClassName,
  variant = "inline",
}: Props) {
  const src =
    integrationLogoSrc(iconSlug) ||
    (providerKey ? integrationLogoSrc(providerKey) : null);

  if (src) {
    if (variant === "tile") {
      const tileBg = integrationLogoTileBg(providerKey || iconSlug);
      return (
        <span
          className={cn(
            "flex h-full w-full items-center justify-center overflow-hidden",
            tileBg,
            className,
          )}
        >
          <img
            src={src}
            alt=""
            aria-hidden
            className={cn("block h-full w-full object-contain", imgClassName)}
          />
        </span>
      );
    }

    return (
      <span
        className={cn(
          "grid shrink-0 place-items-center overflow-hidden rounded-lg border bg-background p-1.5",
          className,
        )}
      >
        <img
          src={src}
          alt=""
          aria-hidden
          className={cn("size-full max-h-8 max-w-8 object-contain", imgClassName)}
        />
      </span>
    );
  }

  const Fallback = FALLBACK_ICONS[iconSlug] || FALLBACK_ICONS[providerKey || ""] || PlugZap;
  if (variant === "tile") {
    const tileBg = integrationLogoTileBg(providerKey || iconSlug);
    return (
      <span
        className={cn(
          "flex h-full w-full items-center justify-center text-white",
          tileBg,
          className,
        )}
        aria-hidden
      >
        <Fallback className="size-10" strokeWidth={1.75} />
        <span className="sr-only">{label}</span>
      </span>
    );
  }

  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-lg border bg-muted/40 text-foreground/80",
        className,
      )}
      aria-hidden
    >
      <Fallback className="size-5" strokeWidth={1.75} />
      <span className="sr-only">{label}</span>
    </span>
  );
}
