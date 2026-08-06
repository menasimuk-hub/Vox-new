import { Check } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";
import {
  SMART_CARD_THEME_CATALOG,
  smartCardThemePreviewQrUrl,
  type SmartCardThemeCatalogItem,
  type SmartCardThemeId,
} from "@/lib/smart-card-themes";

function ThemeSwatch({ tpl, size = "md" }: { tpl: SmartCardThemeCatalogItem; size?: "sm" | "md" }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-border/60",
        size === "sm" ? "h-14" : "h-20",
      )}
    >
      <div className={cn("absolute inset-0 bg-gradient-to-br", tpl.swatch)} />
      <div className="absolute inset-x-2 bottom-2 rounded-md bg-black/25 px-2 py-1 backdrop-blur-[2px]">
        <div className="h-1.5 w-2/3 rounded-full bg-white/80" />
        <div className="mt-1 h-1 w-1/2 rounded-full bg-white/50" />
      </div>
    </div>
  );
}

export function SmartCardThemeCard({
  tpl,
  active,
  onClick,
  companyName,
  personName,
  compact,
}: {
  tpl: SmartCardThemeCatalogItem;
  active: boolean;
  onClick: () => void;
  companyName?: string;
  personName?: string;
  compact?: boolean;
}) {
  const previewQr = smartCardThemePreviewQrUrl(tpl.id, {
    company: companyName,
    name: personName,
    size: compact ? 96 : 120,
  });

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex flex-col gap-1.5 rounded-xl border p-2 text-left transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
        active ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/30" : "border-border bg-background/60",
      )}
    >
      <ThemeSwatch tpl={tpl} size={compact ? "sm" : "md"} />
      <div className="flex items-center gap-1.5 px-0.5">
        <span className="text-sm leading-none">{tpl.emoji}</span>
        <span className="truncate text-[11px] font-semibold leading-tight">{tpl.label}</span>
        {active ? <Check className="ml-auto size-3.5 shrink-0 text-primary" /> : null}
      </div>
      {!compact && tpl.desc ? (
        <p className="px-0.5 text-[10px] leading-snug text-muted-foreground">{tpl.desc}</p>
      ) : null}
      <div className="mt-1 flex items-center gap-2 rounded-lg border border-border bg-white p-1.5">
        <img src={previewQr} alt={`Preview ${tpl.label}`} className="size-14 shrink-0" />
        <p className="text-[10px] leading-snug text-muted-foreground">Scan to preview on your phone</p>
      </div>
    </button>
  );
}

export function SmartCardThemePicker({
  value,
  onChange,
  companyName,
  personName,
  className,
}: {
  value: SmartCardThemeId | string;
  onChange: (id: SmartCardThemeId) => void;
  companyName?: string;
  personName?: string;
  className?: string;
}) {
  const active = String(value || "smartcard");
  return (
    <div className={cn("grid w-full gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5", className)}>
      {SMART_CARD_THEME_CATALOG.map((tpl) => (
        <SmartCardThemeCard
          key={tpl.id}
          tpl={tpl}
          active={active === tpl.id}
          onClick={() => onChange(tpl.id)}
          companyName={companyName}
          personName={personName}
        />
      ))}
    </div>
  );
}
