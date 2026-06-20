import { Building2, Calendar, CalendarCheck, CalendarClock, CalendarRange, PlugZap } from "lucide-react";

import {
  IntegrationBrandMark,
  hasIntegrationBrandMark,
} from "@/components/integrations/integration-brand-mark";
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
  const slug = String(iconSlug || "").trim().toLowerCase();
  const key = String(providerKey || iconSlug || "").trim().toLowerCase();

  if (variant === "tile" && hasIntegrationBrandMark(providerKey, iconSlug)) {
    return (
      <span className={cn("block h-full w-full overflow-hidden", className)}>
        <IntegrationBrandMark providerKey={providerKey} iconSlug={iconSlug} className={imgClassName} />
      </span>
    );
  }

  if (variant === "inline" && hasIntegrationBrandMark(providerKey, iconSlug)) {
    return (
      <span
        className={cn(
          "grid shrink-0 place-items-center overflow-hidden rounded-lg border bg-background",
          className,
        )}
      >
        <IntegrationBrandMark
          providerKey={providerKey}
          iconSlug={iconSlug}
          className={cn("size-8", imgClassName)}
        />
      </span>
    );
  }

  const src = integrationLogoSrc(slug) || (providerKey ? integrationLogoSrc(key) : null);

  if (src) {
    if (variant === "tile") {
      return (
        <span className={cn("block h-full w-full overflow-hidden", className)}>
          <img
            src={src}
            alt=""
            aria-hidden
            className={cn("block h-full w-full object-cover", imgClassName)}
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

  const Fallback = FALLBACK_ICONS[slug] || FALLBACK_ICONS[key] || PlugZap;
  if (variant === "tile") {
    const tileBg = integrationLogoTileBg(key || slug);
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
