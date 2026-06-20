import { Building2, Calendar, CalendarCheck, CalendarClock, CalendarRange, PlugZap } from "lucide-react";

import { IntegrationBrandIcon, resolveBrandSlug } from "@/components/integrations/integration-brand-icons";
import { integrationLogoTileBg } from "@/lib/integration-logos";
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

/** Logos that fill the square — no inner padding. */
const FULL_BLEED_TILES = new Set(["microsoft_calendar", "pipedrive"]);

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
  const brandSlug = resolveBrandSlug(slug, key);

  if (brandSlug) {
    if (variant === "tile") {
      const fullBleed = FULL_BLEED_TILES.has(key) || FULL_BLEED_TILES.has(slug) || FULL_BLEED_TILES.has(brandSlug);
      const tileBg = integrationLogoTileBg(key || slug);
      return (
        <span
          className={cn(
            "flex h-full w-full items-center justify-center overflow-hidden",
            fullBleed ? tileBg : "bg-white",
            className,
          )}
        >
          <IntegrationBrandIcon
            slug={brandSlug}
            className={cn(
              "max-h-full max-w-full",
              fullBleed ? "h-full w-full" : "h-[88%] w-[88%]",
              imgClassName,
            )}
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
        <IntegrationBrandIcon slug={brandSlug} className={cn("size-full max-h-8 max-w-8", imgClassName)} />
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
